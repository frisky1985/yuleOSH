#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Spec-delta 自动生成器 (LE-003)。

从需求变更/测试失败自动生成 spec-delta.md 格式的变更记录。

Usage:
    from yuleosh.loop_engine.spec_delta_gen import SpecDeltaGenerator

    gen = SpecDeltaGenerator()
    delta = gen.generate(
        req_id="RS-001-01",
        change_type="modified",
        reason="CI test failure: test_brake_light_interrupt",
        attributed_test="test_brake_light_interrupt",
    )
    print(delta.to_markdown())
"""

import enum
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("yuleosh.loop_engine.spec_delta_gen")


# ═══════════════════════════════════════════════════════════════════════
# 变更类型
# ═══════════════════════════════════════════════════════════════════════

class ChangeType(str, enum.Enum):
    """Spec-delta 变更类型。"""
    MODIFIED = "modified"
    """现有需求被修改。"""
    ADDED = "added"
    """新增需求。"""
    REMOVED = "removed"
    """需求被移除。"""
    NEEDS_REVIEW = "needs_review"
    """需求需要审查 (通常由测试失败触发)。"""


# ═══════════════════════════════════════════════════════════════════════
# SpecDelta
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SpecDelta:
    """单个 spec-delta 记录。

    Attributes:
        req_id: 需求 ID。
        change_type: 变更类型。
        reason: 变更原因描述。
        attributed_test: 触发变更的测试函数名 (如适用)。
        attributed_source: 触发变更的来源 (e.g. CI pipeline, KPI breach)。
        previous_text: 变更前文本 (如有)。
        new_text: 变更后文本 (如有)。
        timestamp: 生成时间戳。
        generator_version: 生成器版本。
        tags: 标签列表。
        evidence_ref: 证据引用路径。
        metadata: 额外元数据。
    """
    req_id: str
    change_type: ChangeType
    reason: str = ""
    attributed_test: Optional[str] = None
    attributed_source: str = "loop_engine"
    previous_text: Optional[str] = None
    new_text: Optional[str] = None
    timestamp: str = ""
    generator_version: str = "2.5.0"
    tags: list[str] = field(default_factory=list)
    evidence_ref: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if isinstance(self.change_type, str):
            self.change_type = ChangeType(self.change_type)

    def to_dict(self) -> dict:
        return {
            "req_id": self.req_id,
            "change_type": self.change_type.value,
            "reason": self.reason,
            "attributed_test": self.attributed_test,
            "attributed_source": self.attributed_source,
            "previous_text": self.previous_text,
            "new_text": self.new_text,
            "timestamp": self.timestamp,
            "generator_version": self.generator_version,
            "tags": self.tags,
            "evidence_ref": self.evidence_ref,
            "metadata": self.metadata,
        }

    def to_markdown(self) -> str:
        """生成 spec-delta 条目的 Markdown 格式。

        输出格式遵循 spec-delta.md 约定：
        ```markdown
        ### RS-001-01 [modified]
        - **原因**: ...
        - **归因测试**: ...
        - **时间戳**: ...
        ```
        """
        lines = [
            f"### {self.req_id} [{self.change_type.value}]",
            "",
        ]
        if self.reason:
            lines.append(f"- **原因**: {self.reason}")
        if self.attributed_test:
            lines.append(f"- **归因测试**: `{self.attributed_test}`")
        if self.attributed_source:
            lines.append(f"- **来源**: {self.attributed_source}")
        lines.append(f"- **时间戳**: {self.timestamp}")
        if self.tags:
            lines.append(f"- **标签**: {', '.join(self.tags)}")
        if self.evidence_ref:
            lines.append(f"- **证据**: {self.evidence_ref}")
        if self.previous_text:
            lines.append(f"- **变更前**: {self.previous_text[:200]}")
        if self.new_text:
            lines.append(f"- **变更后**: {self.new_text[:200]}")

        lines.append("")  # trailing newline
        return "\n".join(lines)

    def __repr__(self):
        return f"<SpecDelta {self.req_id} [{self.change_type.value}]>"


# ═══════════════════════════════════════════════════════════════════════
# SpecDeltaGenerator
# ═══════════════════════════════════════════════════════════════════════

class SpecDeltaGenerator:
    """Spec-delta 自动生成器。

    功能:
        - 从需求变更/测试失败生成 SpecDelta 记录
        - 生成 spec-delta.md 格式的完整文档
        - 支持追加到已有 spec-delta 文件
        - 支持标记需求为 needs_review
    """

    def __init__(self, output_dir: Optional[str] = None,
                 default_tags: Optional[list[str]] = None):
        self.output_dir = output_dir or "."
        self.default_tags = default_tags or []

    def generate(self, req_id: str, change_type: ChangeType | str,
                 reason: str = "",
                 attributed_test: Optional[str] = None,
                 attributed_source: str = "loop_engine",
                 previous_text: Optional[str] = None,
                 new_text: Optional[str] = None,
                 evidence_ref: Optional[str] = None,
                 tags: Optional[list[str]] = None,
                 **metadata) -> SpecDelta:
        """生成一个 SpecDelta 记录。

        Args:
            req_id: 需求 ID。
            change_type: 变更类型。
            reason: 变更原因。
            attributed_test: 归因测试函数名。
            attributed_source: 变更来源。
            previous_text: 变更前文本。
            new_text: 变更后文本。
            evidence_ref: 证据引用。
            tags: 自定义标签 (会合并 default_tags)。
            **metadata: 额外元数据。

        Returns:
            生成的 SpecDelta 对象。
        """
        all_tags = list(self.default_tags)
        if tags:
            all_tags.extend(tags)

        delta = SpecDelta(
            req_id=req_id,
            change_type=change_type,
            reason=reason,
            attributed_test=attributed_test,
            attributed_source=attributed_source,
            previous_text=previous_text,
            new_text=new_text,
            evidence_ref=evidence_ref,
            tags=all_tags,
            metadata=metadata,
        )

        log.info("SpecDelta generated: %s [%s] by %s",
                 delta.req_id, delta.change_type.value, delta.attributed_source)
        return delta

    def generate_from_test_failure(self, test_name: str, req_id: str,
                                    error_message: str,
                                    evidence_ref: Optional[str] = None) -> SpecDelta:
        """从测试失败生成 spec-delta (Loop 1 的主要入口)。

        Args:
            test_name: 失败的测试函数名。
            req_id: 被覆盖的需求 ID。
            error_message: 测试失败的错误信息。
            evidence_ref: 证据引用。

        Returns:
            标记为 needs_review 的 SpecDelta。
        """
        return self.generate(
            req_id=req_id,
            change_type=ChangeType.NEEDS_REVIEW,
            reason=f"CI测试失败 '{test_name}': {error_message[:200]}",
            attributed_test=test_name,
            attributed_source="ci.failure",
            evidence_ref=evidence_ref,
            tags=["ci_failure", "needs_review", "defect_backprop"],
        )

    def append_to_file(self, delta: SpecDelta, filepath: Optional[str] = None) -> str:
        """将 SpecDelta 追加到 spec-delta 文件。

        Args:
            delta: SpecDelta 对象。
            filepath: 目标文件路径 (默认: output_dir/spec-delta.md)。

        Returns:
            写入的文件路径。
        """
        path = filepath or os.path.join(self.output_dir, "spec-delta.md")
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        markdown_entry = delta.to_markdown()

        # 如果文件不存在，添加文件头
        if not os.path.exists(path):
            header = [
                "# Spec Delta — Automated Change Log",
                "",
                f"> 自动生成时间: {datetime.now(timezone.utc).isoformat()}",
                f"> 生成器: yuleOSH Loop Engine v{delta.generator_version}",
                "",
                "---",
                "",
            ]
            markdown_entry = "\n".join(header) + "\n" + markdown_entry

        with open(path, "a", encoding="utf-8") as f:
            f.write(markdown_entry + "\n")

        log.info("SpecDelta appended to %s", path)
        return path

    def to_json(self, deltas: list[SpecDelta]) -> str:
        """将多个 SpecDelta 序列化为 JSON。"""
        return json.dumps([d.to_dict() for d in deltas], indent=2, ensure_ascii=False)

    @classmethod
    def from_test_failure_simple(cls, test_name: str, req_id: str,
                                  error_message: str) -> SpecDelta:
        """快速生成 spec-delta 的类方法。"""
        gen = cls()
        return gen.generate_from_test_failure(test_name, req_id, error_message)

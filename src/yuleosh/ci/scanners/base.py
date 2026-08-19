# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""ScannerAdapter — 外部扫描器适配层抽象（2026-08-19 老板拍板）。

yuleOSH 不换工具、不重造扫描器——统一消费任何 MISRA 扫描器输出：

- cppcheck（默认，C:2012）
- 商业工具（Parasoft C/C++test / Helix QAC / LDRA，支持 C:2023）
- 客户通过 MCP 暴露的工具（可选）

三层模式（详见 ~/.hermes/scanner-adapter-20260819.md）：

1. API/CLI 适配器（主路径，P1+P2）：``misra.scanner`` 配置选择工具，
   ``ScannerRegistry`` 统一注册/获取，``detect → run → parse → normalize``
   流程把任意工具输出收敛为统一 ``Violation`` 模型。
2. MCP 集成（P3 可选）：``misra.scanner: mcp`` + MCP 端点。
3. Skill 编排（辅助，不做门禁）。

统一 Violation 模型对齐现有 misra_report 的 dict 契约
（rule_id / severity / file / line / message / tool），下游
（enrich_with_definitions / translate_violations / 报告 / 门禁）零改动消费。
"""

from __future__ import annotations

import abc
import logging
import re
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("ci.scanners")

# Violation 已知字段（from_dict 时其余键进 extra 保留，保证 roundtrip 无损）
_KNOWN_VIOLATION_FIELDS = {
    "rule_id",
    "severity",
    "file",
    "line",
    "message",
    "tool",
    "column",
    "rule_year",
    "code_category",
    "file_rel",
    "severity_category",
}


@dataclass
class Violation:
    """统一扫描器违规模型（对齐 misra_report 的 dict 契约）。

    核心字段（设计文档钦定）：``rule_id / severity / file / line / message / tool``。
    其余字段与 misra_report 模型对齐；未知键经 ``extra`` 无损保留，
    保证 cppcheck 默认路径 roundtrip（dict → Violation → dict）零回归。
    """

    rule_id: str = ""
    severity: str = "style"
    file: str = ""
    line: int = 0
    message: str = ""
    tool: str = ""
    column: int = 0
    rule_year: str = ""
    code_category: str = ""
    file_rel: str = ""
    severity_category: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """序列化为 dict（与 parse_cppcheck_output 的 dict 契约兼容）。

        空值字段省略（下游 ``v.get(...)`` 兜底语义不变）；核心字段始终包含。
        """
        d: dict = {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "message": self.message,
            "rule_id": self.rule_id,
            "rule_year": self.rule_year,
            "tool": self.tool,
        }
        for k in ("code_category", "file_rel", "severity_category"):
            v = getattr(self, k)
            if v:
                d[k] = v
        for k, v in self.extra.items():
            d.setdefault(k, v)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Violation:
        """从 dict 构造（parse_cppcheck_output 等现有解析器输出直接可用）。"""
        return cls(
            rule_id=d.get("rule_id", ""),
            severity=d.get("severity", "style"),
            file=d.get("file", ""),
            line=int(d.get("line", 0) or 0),
            message=d.get("message", ""),
            tool=d.get("tool", ""),
            column=int(d.get("column", 0) or 0),
            rule_year=d.get("rule_year", ""),
            code_category=d.get("code_category", ""),
            file_rel=d.get("file_rel", ""),
            severity_category=d.get("severity_category", ""),
            extra={k: v for k, v in d.items() if k not in _KNOWN_VIOLATION_FIELDS},
        )


@dataclass
class ScannerResult:
    """扫描器执行结果（原始输出 + 状态）。"""

    tool: str = ""
    raw_output: str = ""
    command: list[str] = field(default_factory=list)
    ok: bool = True
    error: str = ""
    hint: str = ""
    elapsed: float = 0.0


# 规则数字提取：X.Y（支持 . _ - 分隔），排除 4 位年份（如 2012/2023）
_RULE_NUM_RE = re.compile(r"(?<!\d)(\d{1,2})[._-](\d{1,2})(?!\d)")
_FALLBACK_NUM_RE = re.compile(r"(\d+\.\d+)")


def extract_rule_number(rule_id: str) -> str:
    """从工具特定规则 ID 中提取 'X.Y' 数字部分。

    商业工具格式多样（``MISRA.C.2012.10.1`` / ``MISRA_C_2023_Rule_10_1`` /
    ``MISRA-C-2012-Rule-15-7`` / ``Rule 10.1`` / ``10.1``），统一提取数字部分
    再走 misra-rules.yaml 映射。4 位年份（2012/2023）不参与匹配。
    """
    if not rule_id:
        return ""
    m = _RULE_NUM_RE.search(rule_id)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    m2 = _FALLBACK_NUM_RE.search(rule_id)
    return m2.group(1) if m2 else ""


def canonicalize_rule_id(rule_id: str) -> str:
    """把任意工具输出的规则 ID 映射为 misra-rules.yaml 规范键。

    分层策略：
    1. 已是规范键（misra-cXXXX-...）→ 直接走 ``_normalize_rule_id``（诚实归一化：
       C:2012 modified/removed 规则保留 misra-c2012-* 身份）。
    2. 工具特定格式（``MISRA.C.2012.10.1`` / ``MISRA_C_2023_Rule_10_1``）→
       提取 'X.Y' 数字；ID 含 '2012' 按 C:2012 诚实映射，否则按 C:2023 映射。
    3. Dir/Directive 前缀保留（``Dir 4.1`` → ``misra-c2023-dir-4.1``）。
    """
    if not rule_id:
        return ""
    from yuleosh.ci.misra_report.core.parser import _normalize_rule_id

    rid = rule_id.strip()
    try:
        if re.match(r"^misra-c\d{4}-", rid, re.IGNORECASE):
            return _normalize_rule_id(rid)
        is_dir = bool(re.match(r"^(dir|directive)\b", rid, re.IGNORECASE))
        num = extract_rule_number(rid)
        if num:
            if "2012" in rid.lower():
                # C:2012 工具输出 → 诚实映射（modified/removed 保留 c2012 身份）
                pref = f"misra-c2012-{'dir-' if is_dir else ''}{num}"
            elif is_dir:
                pref = f"Dir {num}"
            else:
                pref = num
            return _normalize_rule_id(pref)
        # 无数字（纯文本）→ 直接归一化
        return _normalize_rule_id(rid)
    except Exception as exc:  # noqa: BLE001 — 解析器边界防御（第三方格式不可控）
        log.debug("rule normalize failed for %r: %s", rule_id, exc)
        return rid


class ScannerAdapter(abc.ABC):
    """扫描器适配器抽象（三层模式 1：API/CLI 适配器）。

    子类实现四段流程：

    - ``detect``：工具是否可用（安装 / 配置齐全）。返回 False 时调用方 skip。
    - ``run``：执行扫描，返回原始输出（ScannerResult）。
    - ``parse``：原始输出 → 统一 Violation 列表。
    - ``normalize``：工具特定规则 ID → misra-rules.yaml 规范 ID（默认实现可用）。
    """

    #: 注册名（misra.scanner 配置值），小写
    name: str = ""
    #: 展示名（日志/报告）
    display_name: str = ""

    def detect(self, project_dir: str, config: Any = None) -> bool:
        """检测扫描器是否可用。默认 False（未配置/未安装）。"""
        return False

    def detect_hint(self, project_dir: str, config: Any = None) -> str:
        """detect 失败时的修复提示。"""
        return f"install {self.display_name} or configure misra.scanner_config"

    @abc.abstractmethod
    def run(
        self,
        project_dir: str,
        config: Any = None,
        target_files: list[str] | None = None,
        **kwargs: Any,
    ) -> ScannerResult:
        """执行扫描。config 为 MisraConfig（或 None），target_files 为待扫文件。

        返回 ScannerResult：ok=False 时 error/hint 供门禁 fail-closed 展示。
        """

    @abc.abstractmethod
    def parse(self, raw: str) -> list[Violation]:
        """解析原始输出为统一违规列表。解析失败应返回 [] 并留 warning。"""

    def normalize(
        self, violations: list[Violation], ruleset: Any = None
    ) -> list[Violation]:
        """映射工具特定规则 ID → misra-rules.yaml 规范 ID。

        默认实现：canonicalize_rule_id（规则数字映射）+ 工具标记。
        商业工具如需特殊映射（如 Parasoft 的 rule 属性直读）可在子类覆盖。
        """
        for v in violations:
            if v.rule_id:
                v.rule_id = canonicalize_rule_id(v.rule_id)
            if not v.tool:
                v.tool = self.name
        return violations


def violations_to_dicts(violations: list[Violation] | list[dict]) -> list[dict]:
    """把 Violation 列表转换为 dict 列表（下游 misra_report 消费 dict 契约）。"""
    return [
        v.to_dict() if isinstance(v, Violation) else v
        for v in violations
    ]

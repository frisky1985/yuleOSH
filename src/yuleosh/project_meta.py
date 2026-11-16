#!/usr/bin/env python3

# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""ProjectMeta — 平台/安全等级元数据（AUD-ASPICE-001 NC-11）。

spec 里没有要求 AUTOSAR 全栈时，codegen 不得凭"嵌入式 = AUTOSAR"的默认
联想产出 ``Rte_*`` / ``SchM`` / ``.arxml`` —— 这是 RUN-A 中「1 Hz 闪灯被
扩写成 AUTOSAR CP 全栈」的直接原因。平台模式必须由项目元数据决定：

- ``BARE_METAL_MCU``：裸机 MCU（HAL + 应用逻辑），禁止 RTE/SchM/arxml。
- ``AUTOSAR_CP``：AUTOSAR Classic Platform，要求分层目录 + arxml 输入。
- ``HOST_SIM``：宿主机仿真/可验证实现，不生成目标相关中间件。
- ``AUTO``（默认）：沿用历史行为（不做平台强制）。

配置来源（优先级从高到低）：``OSH_PLATFORM`` 环境变量、
``.yuleosh.yaml`` 的 ``platform`` / ``project.platform`` / ``target.platform``。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

PLATFORM_BARE_METAL = "BARE_METAL_MCU"
PLATFORM_AUTOSAR_CP = "AUTOSAR_CP"
PLATFORM_HOST_SIM = "HOST_SIM"
PLATFORM_AUTO = "AUTO"

PLATFORMS = (PLATFORM_AUTO, PLATFORM_BARE_METAL, PLATFORM_AUTOSAR_CP,
             PLATFORM_HOST_SIM)

_ALIASES = {
    "BARE-METAL": PLATFORM_BARE_METAL,
    "BAREMETAL": PLATFORM_BARE_METAL,
    "BARE_METAL": PLATFORM_BARE_METAL,
    "MCU": PLATFORM_BARE_METAL,
    "AUTOSAR": PLATFORM_AUTOSAR_CP,
    "AUTOSAR-CP": PLATFORM_AUTOSAR_CP,
    "AUTOSAR_CLASSIC": PLATFORM_AUTOSAR_CP,
    "HOST": PLATFORM_HOST_SIM,
    "SIMULATION": PLATFORM_HOST_SIM,
}

#: 平台禁用文件模式（相对生成目录的 POSIX 路径）
_FORBIDDEN_PATTERNS: dict[str, tuple[tuple[str, str], ...]] = {
    PLATFORM_BARE_METAL: (
        (r"(^|/)src/rte/Rte.*\.(c|h)$", "AUTOSAR RTE glue is not allowed"),
        (r"(^|/)SchM\.(c|h)$", "AUTOSAR SchM scheduler stub is not allowed"),
        (r"(^|/)src/(application|bsw)/", "AUTOSAR layer directories are not allowed"),
        (r"\.arxml$", "ARXML descriptions are not allowed"),
    ),
    PLATFORM_HOST_SIM: (
        (r"(^|/)src/rte/Rte.*\.(c|h)$", "AUTOSAR RTE glue is not allowed"),
        (r"(^|/)SchM\.(c|h)$", "AUTOSAR SchM scheduler stub is not allowed"),
        (r"\.arxml$", "ARXML descriptions are not allowed"),
    ),
}

_BARE_METAL_RULES = (
    "9. PLATFORM HARD RULE (BARE_METAL_MCU):\n"
    "   - Target is a bare-metal MCU. Implement application logic on top of the\n"
    "     project HAL only (`hal_*` functions declared in existing headers).\n"
    "   - Do NOT generate AUTOSAR artifacts: no `Rte_*` files, no `SchM`/`SchM_*`\n"
    "     scheduler stubs, no `src/rte/`, `src/application/`, `src/bsw/`\n"
    "     layering, no `*.arxml`, no BSW service stubs.\n"
    "   - Do NOT call POSIX/OS APIs (`clock_gettime`, `nanosleep`, `usleep`,\n"
    "     `pthread_*`) unless the spec explicitly requires a host build.\n"
    "   - Timing must come from the HAL/spec contract (e.g. a 1 ms tick counter),\n"
    "     never from wall-clock APIs.\n"
)

_AUTOSAR_CP_RULES = (
    "9. PLATFORM HARD RULE (AUTOSAR_CP):\n"
    "   - Target is AUTOSAR Classic Platform. Follow the layering contract in\n"
    "     rule 8 (application SWC -> RTE -> BSW -> MCAL).\n"
    "   - The .arxml description is the authoritative input for ports and\n"
    "     runnables; generated SWC/RTE code MUST stay consistent with it.\n"
    "   - Do NOT introduce bare-metal bypasses (direct register access in an\n"
    "     application SWC) — hardware access belongs to MCAL.\n"
)

_HOST_SIM_RULES = (
    "9. PLATFORM HARD RULE (HOST_SIM):\n"
    "   - Target is host simulation. POSIX/OS APIs are allowed for timing and\n"
    "     I/O, but hardware access MUST go through the project HAL.\n"
    "   - Do NOT generate AUTOSAR RTE/SchM/arxml artifacts.\n"
)


def normalize_platform(raw: object) -> str:
    """把自由文本平台名归一化为受控取值（未知 → AUTO）。"""
    text = str(raw or "").strip().upper().replace(" ", "_")
    if not text:
        return PLATFORM_AUTO
    if text in PLATFORMS:
        return text
    return _ALIASES.get(text, PLATFORM_AUTO)


@dataclass
class ProjectMeta:
    """项目元数据：决定 codegen 的平台模式与安全等级。"""

    platform: str = PLATFORM_AUTO
    asil_level: str = "QM"
    aspice_level: str = ""
    source: str = ""

    @classmethod
    def load(cls, project_dir: str | Path) -> "ProjectMeta":
        raw_platform = os.environ.get("OSH_PLATFORM", "").strip()
        raw_asil = os.environ.get("OSH_ASIL_LEVEL", "").strip()
        raw_aspice = os.environ.get("OSH_ASPICE_LEVEL", "").strip()
        source = "env" if raw_platform else ""
        cfg = Path(project_dir) / ".yuleosh.yaml"
        if (not raw_platform or not raw_asil or not raw_aspice) and cfg.is_file():
            try:
                import yaml

                data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
                if isinstance(data, dict):
                    if not raw_platform:
                        raw_platform = str(
                            data.get("platform")
                            or (data.get("project") or {}).get("platform")
                            or (data.get("target") or {}).get("platform")
                            or ""
                        )
                        if raw_platform:
                            source = source or str(cfg)
                    if not raw_asil:
                        raw_asil = str(
                            data.get("asil_level")
                            or (data.get("project") or {}).get("asil_level")
                            or (data.get("safety") or {}).get("asil_level")
                            or ""
                        )
                    if not raw_aspice:
                        raw_aspice = str(
                            data.get("aspice_level")
                            or (data.get("aspice") or {}).get("level")
                            or (data.get("project") or {}).get("aspice_level")
                            or ""
                        )
            except Exception:  # noqa: BLE001 — 元数据读取失败按默认处理
                pass
        return cls(
            platform=normalize_platform(raw_platform),
            asil_level=_normalise_asil(raw_asil),
            aspice_level=_normalise_aspice(raw_aspice),
            source=source,
        )

    @property
    def is_autosar(self) -> bool:
        return self.platform == PLATFORM_AUTOSAR_CP

    @property
    def requires_signoff(self) -> bool:
        """CL2/CL3 要求关键基线人工签批（NC-09）。"""
        return self.aspice_level in ("CL2", "CL3")

    @property
    def forbids_autosar_artifacts(self) -> bool:
        return self.platform in (PLATFORM_BARE_METAL, PLATFORM_HOST_SIM)

    def prompt_rules(self) -> str:
        """返回注入 codegen prompt 的平台硬规则（AUTO 返回空串）。"""
        if self.platform == PLATFORM_BARE_METAL:
            return _BARE_METAL_RULES
        if self.platform == PLATFORM_AUTOSAR_CP:
            return _AUTOSAR_CP_RULES
        if self.platform == PLATFORM_HOST_SIM:
            return _HOST_SIM_RULES
        return ""


def _normalise_asil(raw: object) -> str:
    text = str(raw or "").strip().upper().replace("_", "-")
    if text in ("A", "B", "C", "D"):
        text = f"ASIL-{text}"
    return text if text in ("QM", "ASIL-A", "ASIL-B", "ASIL-C", "ASIL-D") else "QM"


def _normalise_aspice(raw: object) -> str:
    """归一化 ASPICE 能力等级：``2`` / ``cl-2`` / ``CL2`` → ``CL2``。"""
    text = str(raw or "").strip().upper().replace("_", "").replace("-", "")
    if not text:
        return ""
    if text.isdigit():
        text = f"CL{text}"
    if not text.startswith("CL"):
        text = f"CL{text}"
    return text if text in ("CL0", "CL1", "CL2", "CL3") else ""


def validate_platform_layout(files: list[str], platform: str) -> list[str]:
    """按平台规则检查生成文件路径，返回违规说明列表。

    ``files`` 为相对生成目录的 POSIX 路径。仅 BARE_METAL_MCU / HOST_SIM
    有硬性禁止项；其余平台返回空列表（由 AUTOSAR 布局检查负责）。
    """
    patterns = _FORBIDDEN_PATTERNS.get(platform, ())
    if not patterns:
        return []
    errors: list[str] = []
    for rel in files:
        posix = rel.replace("\\", "/").lstrip("./")
        for pattern, message in patterns:
            if re.search(pattern, posix):
                errors.append(f"PLATFORM VIOLATION [{platform}] {posix}: {message}")
                break
    return errors

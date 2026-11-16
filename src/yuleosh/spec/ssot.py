"""ssot.py — 轻量 SSOT 模型与拓扑闭环校验（AUD-ASPICE-001 NC-02）

设计意图与 SDD §3.2/§3.3 对齐：

* 需求 (Requirement)、接口 (InterfaceDef)、设计单元 (DesignUnit) 三类实体；
* 实例化后立即做拓扑校验：悬空引用、孤儿需求、重复 ID；
* 校验不通过即阻断（由调用方把 issue 转成 critical/major finding）。

与 SDD 的差异
-------------
SDD 指定 Pydantic v2。本仓库保持「零第三方运行时依赖」，
故用 ``dataclass`` + 显式校验实现同等语义（强类型、可序列化、可测试）。
如需与 SDD 完全一致，可在不改调用方的前提下把 dataclass 换成
Pydantic BaseModel（字段名一致）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

#: 需求 ID：SR-001 / SWR-001.1 / RS-001 / REQ-SYS-001 / REQ-SWE-001
REQUIREMENT_ID_RE = re.compile(
    r"\b(?:SR|SWR|RS|SYS|REQ-SYS|REQ-SWE)-\d{3}(?:\.\d+)?\b"
)
#: 设计单元 ID：DES-001 / DES-SWE-001 / DES-SYS-001
DESIGN_UNIT_ID_RE = re.compile(r"\bDES-(?:SYS|SWE)?-?\d{3}\b")
#: 接口 ID：IF-001 / IF-HAL-001
INTERFACE_ID_RE = re.compile(r"\bIF-[A-Z0-9-]*\d{3}\b")
#: Design Units 表行：| DES-SWE-001 | module | SR-001, SR-002 | IF-HAL-001 |
_DESIGN_ROW_RE = re.compile(r"^\s*\|\s*(DES-[^|]+?)\s*\|(.*)\|\s*$", re.M)
#: 需求小节标题：### SR-001 / ## REQ-SWE-002
_SECTION_REQ_RE = re.compile(
    rf"^#{{2,4}}\s+({REQUIREMENT_ID_RE.pattern[2:-2]})\b", re.M)


@dataclass(frozen=True)
class Requirement:
    id: str
    statement: str = ""
    parent_id: str | None = None


@dataclass(frozen=True)
class InterfaceDef:
    id: str
    header: str = ""
    direction: str = ""


@dataclass(frozen=True)
class DesignUnit:
    id: str
    module: str = ""
    satisfies_reqs: tuple[str, ...] = ()
    uses_interfaces: tuple[str, ...] = ()


@dataclass
class SpecModel:
    """OpenSpec 的结构化视图（唯一事实来源的只读投影）。"""
    requirements: list[Requirement] = field(default_factory=list)
    interfaces: list[InterfaceDef] = field(default_factory=list)
    design_units: list[DesignUnit] = field(default_factory=list)

    def requirement_ids(self) -> set[str]:
        return {r.id for r in self.requirements}

    def interface_ids(self) -> set[str]:
        return {i.id for i in self.interfaces}

    def covered_requirement_ids(self) -> set[str]:
        covered: set[str] = set()
        for du in self.design_units:
            covered.update(du.satisfies_reqs)
        return covered


@dataclass(frozen=True)
class TopologyIssue:
    rule: str
    severity: str  # critical | major | minor
    message: str

    def as_finding(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "source": "deterministic",
            "category": "Spec/Topology",
        }


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _split_ids(cell: str, pattern: re.Pattern[str]) -> tuple[str, ...]:
    return tuple(_unique(pattern.findall(cell)))


def extract_requirements(spec_content: str) -> list[Requirement]:
    """提取需求 ID（保留重复项，供 ``SSOT-DUP-REQ`` 校验）。

    优先按「小节标题」提取 —— 正文/追溯表中的重复引用不算重复实体；
    没有小节标题时退化为全文匹配。
    """
    ids = _SECTION_REQ_RE.findall(spec_content)
    if not ids:
        ids = REQUIREMENT_ID_RE.findall(spec_content)
    return [Requirement(id=i) for i in ids]


def extract_design_units(arch_content: str) -> list[DesignUnit]:
    """从架构文档的 Design Units 表格中提取设计单元。

    只解析 Markdown 表格行，避免把正文里偶然出现的 DES- 编号当成实体。
    """
    units: list[DesignUnit] = []
    for match in _DESIGN_ROW_RE.finditer(arch_content):
        des_id = match.group(1).strip()
        if des_id.upper() in ("DES-ID", "DESIGN-ID", "DES-ID "):
            continue  # 表头
        rest = match.group(2)
        cells = [c.strip() for c in rest.split("|")]
        reqs: tuple[str, ...] = ()
        ifaces: tuple[str, ...] = ()
        module = cells[0] if cells else ""
        for cell in cells:
            if not reqs:
                reqs = _split_ids(cell, REQUIREMENT_ID_RE)
            if not ifaces:
                ifaces = _split_ids(cell, INTERFACE_ID_RE)
        units.append(DesignUnit(id=des_id, module=module,
                                satisfies_reqs=reqs, uses_interfaces=ifaces))
    return units


def extract_interfaces(arch_content: str, spec_content: str = "") -> list[InterfaceDef]:
    ids = _unique(INTERFACE_ID_RE.findall(arch_content)
                  + INTERFACE_ID_RE.findall(spec_content))
    return [InterfaceDef(id=i) for i in ids]


def build_model(spec_content: str, arch_content: str = "") -> SpecModel:
    return SpecModel(
        requirements=extract_requirements(spec_content),
        interfaces=extract_interfaces(arch_content, spec_content),
        design_units=extract_design_units(arch_content),
    )


def validate_topology(model: SpecModel,
                      require_design_units: bool = True) -> list[TopologyIssue]:
    """拓扑闭环校验（对应 SDD §3.3 门禁 0）。"""
    issues: list[TopologyIssue] = []

    # 1. 重复 ID
    all_ids = [r.id for r in model.requirements]
    dupes = sorted({i for i in all_ids if all_ids.count(i) > 1})
    if dupes:
        issues.append(TopologyIssue(
            "SSOT-DUP-REQ", "major",
            f"需求 ID 重复: {', '.join(dupes)}（同一 ID 只能有一个实体）"))

    if require_design_units and model.requirements and not model.design_units:
        issues.append(TopologyIssue(
            "SSOT-NO-DESIGN-UNITS", "major",
            "架构文档缺少 Design Units 表（DES-xxx + Satisfies），"
            "需求→设计追溯无法建立"))
        return issues

    req_ids = model.requirement_ids()

    # 2. 悬空引用（DesignUnit 引用了不存在的 REQ）
    #    注：接口不做悬空校验 —— 没有独立的接口声明表时，无法区分
    #    「声明」与「使用」，强行校验会全部误报。
    for du in model.design_units:
        dangling_reqs = [r for r in du.satisfies_reqs if r not in req_ids]
        if dangling_reqs:
            issues.append(TopologyIssue(
                "SSOT-DANGLING-REQ", "critical",
                f"{du.id} 引用了不存在的需求: {', '.join(dangling_reqs)}"))
        if not du.satisfies_reqs:
            issues.append(TopologyIssue(
                "SSOT-DU-NO-REQ", "major",
                f"{du.id} 未声明 satisfies_reqs —— 该设计单元无法追溯"))

    # 3. 孤儿需求（没有任何设计单元承接）
    covered = model.covered_requirement_ids()
    orphans = sorted(req_ids - covered)
    if orphans:
        issues.append(TopologyIssue(
            "SSOT-ORPHAN-REQ", "major",
            f"{len(orphans)} 条需求未被任何设计单元承接: {', '.join(orphans)}"))

    return issues

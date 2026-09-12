"""StandardProfile — 多标准合规检查点的统一数据模型 (A-M1 / A1-02).

本模块定义 ``StandardProfile`` 及其子结构（dataclass 骨架），用于把
``aspice_v3.1.yaml`` 等标准定义文件**无损**映射到强类型 Python 对象，
为后续 A1-03 (loader + 校验) 与 A1-05 (ComplianceChecker profile 驱动改造) 提供
数据结构基础。

无损映射表见每个字段的 docstring（格式：``yaml 路径 → 字段``）。A-M2 的
ISO 26262 等其它标准只需提供同样结构的 yaml，即可零代码改动接入 checker。

设计原则：
- 所有集合用 ``list`` 保序，``dict`` 仅用于需按 key 检索的二级结构。
- 字符串统一为 ``str``，yaml 的 ``|`` 块文本原样保留（不折叠）。
- 不强求字段存在：yaml 缺字段时 loader 给默认值，校验在 A1-03 单独负责。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EvidenceSpec:
    """单条产出证据描述 (yaml: ``base_practices[].output_evidence[]``)。"""

    type: str  # yaml: output_evidence[].type  ("document"|"source"|"test"|"ci"|"evidence"|"sil")
    path: str  # yaml: output_evidence[].path  (文件或目录，相对项目根)
    description: str = ""  # yaml: output_evidence[].description


@dataclass
class BasePractice:
    """基础实践 (yaml: ``base_practices[]``)。"""

    id: str  # yaml: base_practices[].id  ("SWE.1.BP1")
    title: str = ""  # yaml: base_practices[].title
    output_evidence: List[EvidenceSpec] = field(default_factory=list)  # yaml: base_practices[].output_evidence[]
    check: List[str] = field(default_factory=list)  # yaml: base_practices[].check[]  (检查要点文本)


@dataclass
class ProcessArea:
    """过程域 (yaml 顶层键 ``swe.1``~``swe.6`` 等)。"""

    id: str  # yaml: <area>.id  ("SWE.1")
    title: str = ""  # yaml: <area>.title
    description: str = ""  # yaml: <area>.description (块文本)
    base_practices: List[BasePractice] = field(default_factory=list)  # yaml: <area>.base_practices[]


@dataclass
class ProfileMeta:
    """标准元信息 (yaml: ``meta``)。"""

    standard: str = "ASPICE"  # yaml: meta.standard
    version: str = "3.1"  # yaml: meta.version
    description: str = ""  # yaml: meta.description


@dataclass
class StandardProfile:
    """一个完整合规标准的强类型表示 (yaml 顶层)。

    无损映射总表 (yaml 路径 → 字段)：
      ``meta.standard``    → ``meta.standard``
      ``meta.version``     → ``meta.version``
      ``meta.description`` → ``meta.description``
      顶层 ``swe.N`` 键     → ``areas`` (list[ProcessArea], 保序)
      ``<area>.id``        → ``ProcessArea.id``
      ``<area>.title``     → ``ProcessArea.title``
      ``<area>.description`` → ``ProcessArea.description``
      ``<area>.base_practices`` → ``ProcessArea.base_practices``
      ``bp.id``            → ``BasePractice.id``
      ``bp.title``         → ``BasePractice.title``
      ``bp.output_evidence`` → ``BasePractice.output_evidence``
      ``bp.check``         → ``BasePractice.check``
      ``ev.type``          → ``EvidenceSpec.type``
      ``ev.path``          → ``EvidenceSpec.path``
      ``ev.description``   → ``EvidenceSpec.description``

    后续扩展（A-M2）：新增标准只需提供同样结构的 yaml，无需改动 dataclass。
    """

    meta: ProfileMeta = field(default_factory=ProfileMeta)
    areas: List[ProcessArea] = field(default_factory=list)

    # ------------------------------------------------------------------
    # 便捷访问
    # ------------------------------------------------------------------
    @property
    def standard(self) -> str:
        """标准名 (mirror of ``meta.standard``)。"""
        return self.meta.standard

    @property
    def version(self) -> str:
        """标准版本 (mirror of ``meta.version``)。"""
        return self.meta.version

    def area_by_id(self, area_id: str) -> Optional[ProcessArea]:
        """按过程域 id 检索（如 ``swe.1``）。"""
        for area in self.areas:
            if area.id == area_id:
                return area
        return None

    def all_base_practice_ids(self) -> List[str]:
        """返回所有 base_practice id（扁平、保序）。"""
        return [bp.id for area in self.areas for bp in area.base_practices]

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
    order: Optional[int] = None  # yaml: <area>.order (可选；控制报告章节排序，缺失则保文档序)
    key: Optional[str] = None  # yaml: 顶层平铺键 (如 "swe.1")；to_template_dict 据此还原原始键


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

    # ------------------------------------------------------------------
    # 反向序列化 (A1-05)：StandardProfile → checker 消费的 template dict
    # ------------------------------------------------------------------
    def to_template_dict(self) -> dict:
        """把 ``StandardProfile`` 还原为 ``ComplianceChecker`` 消费的 template dict。

        与 ``_yaml_to_profile`` 互逆：经 ``load_profile()`` → ``to_template_dict()``
        得到的 dict 与原始 yaml 在 checker 实际消费的字段上完全一致，从而：
          - 默认构造 ``ComplianceChecker(project_dir)`` 走 profile 路径后输出
            与直接读 yaml 字节级等同（A1-01 golden 安全网据此验证零漂移）。
          - A-M2 接入新标准时，checker 无需任何改动。

        原始 yaml 为顶层平铺结构（``meta`` + ``swe.1``~``swe.6``），
        故 area 键由 ``ProcessArea.key``（原 yaml 顶层键）还原，
        缺失时回退 ``area.id.lower()``。
        """
        meta = {
            "standard": self.meta.standard,
            "version": self.meta.version,
            "description": self.meta.description,
        }
        areas: dict = {}
        for area in self.areas:
            area_key = area.key or area.id.lower()
            area_body = {
                "id": area.id,
                "title": area.title,
                "description": area.description,
                "base_practices": [
                    {
                        "id": bp.id,
                        "title": bp.title,
                        "output_evidence": [
                            {
                                "type": ev.type,
                                "path": ev.path,
                                "description": ev.description,
                            }
                            for ev in bp.output_evidence
                        ],
                        "check": list(bp.check),
                    }
                    for bp in area.base_practices
                ],
            }
            if area.order is not None:
                area_body["order"] = area.order
            areas[area_key] = area_body
        return {"meta": meta, **areas}


# ==================================================================
# 加载与校验 (A1-03)
# ==================================================================
import os
from pathlib import Path

import yaml

# 默认搜索目录：本模块所在 compliance 目录；A1-06 迁移到 profiles/ 后仍向后兼容。
_DEFAULT_PROFILE_DIR = Path(__file__).resolve().parent
_PROFILE_SEARCH_DIRS = [_DEFAULT_PROFILE_DIR, _DEFAULT_PROFILE_DIR / "profiles"]

# 各结构允许的字段白名单（用于「未知字段」校验）
_ALLOWED_META_KEYS = {"standard", "version", "description"}
_ALLOWED_AREA_KEYS = {"id", "title", "description", "base_practices", "order"}
_ALLOWED_BP_KEYS = {"id", "title", "output_evidence", "check"}
_ALLOWED_EVIDENCE_KEYS = {"type", "path", "description"}

# evidence.type 强制取值白名单（A1-04 决策1：Option B 强制校验）。
# 拼写漂移原会静默落到「缺证据」假阴性；集中此处便于新标准扩展。
_EVIDENCE_TYPE_ENUM = frozenset({"document", "source", "test", "ci", "evidence", "sil"})


class ProfileError(Exception):
    """profile 校验错误，携带字段路径与修复提示。"""

    def __init__(self, field_path: str, message: str):
        self.field_path = field_path
        super().__init__(f"{message} (字段路径: {field_path})")


class ProfileNotFoundError(FileNotFoundError):
    """profile 文件不存在；携带可用清单作为修复提示。"""

    def __init__(self, name: str, searched: List[Path], available: List[str]):
        self.name = name
        self.searched = searched
        self.available = available
        avail = ", ".join(available) if available else "(无)"
        msg = (
            f"找不到合规标准 profile '{name}'。"
            f"已搜索: {[str(p) for p in searched]}。"
            f"可用 profile: {avail}。"
            f"修复: 在以上目录放置 <name>.yaml，或选用可用清单中的名称。"
        )
        super().__init__(msg)


def _profile_search_paths(name: str, profile_dir: Optional[Path] = None) -> List[Path]:
    if profile_dir:
        base = Path(profile_dir)
        dirs = [base, base / "profiles"]  # 自定义目录同样兼容 profiles/ 子目录
    else:
        dirs = _PROFILE_SEARCH_DIRS
    return [d / f"{name}.yaml" for d in dirs]


def _find_profile_file(name: str, profile_dir: Optional[Path] = None) -> Path:
    candidates = _profile_search_paths(name, profile_dir)
    for c in candidates:
        if c.exists():
            return c
    available = sorted(
        {p.stem for d in (_PROFILE_SEARCH_DIRS if not profile_dir else [Path(profile_dir)])
         for p in d.glob("*.yaml") if p.exists()}
    )
    raise ProfileNotFoundError(name, candidates, available)


def _require(cond: bool, field_path: str, message: str) -> None:
    if not cond:
        raise ProfileError(field_path, message)


def _validate(data: dict, name: str) -> None:
    """校验 yaml 结构：缺字段与未知字段两类错误均带路径与修复提示。"""
    _require(isinstance(data, dict), name, "profile 顶层必须是映射 (mapping)")
    _require("meta" in data, f"{name}.meta", "缺少必填字段 meta（标准元信息）")
    meta = data["meta"]
    _require(isinstance(meta, dict), f"{name}.meta", "meta 必须是映射")
    for k in meta:
        _require(k in _ALLOWED_META_KEYS, f"{name}.meta.{k}",
                 f"未知字段 '{k}'（meta 仅允许 {sorted(_ALLOWED_META_KEYS)}）")
    _require("standard" in meta and str(meta.get("standard", "")).strip(),
             f"{name}.meta.standard", "缺少必填字段 meta.standard（标准名，如 ASPICE）")

    for area_key, area in data.items():
        if area_key == "meta":
            continue
        _require(isinstance(area, dict), f"{name}.{area_key}",
                 f"过程域 '{area_key}' 必须是映射")
        for k in area:
            _require(k in _ALLOWED_AREA_KEYS, f"{name}.{area_key}.{k}",
                     f"未知字段 '{k}'（过程域仅允许 {sorted(_ALLOWED_AREA_KEYS)}）")
        _require("id" in area and str(area.get("id", "")).strip(),
                 f"{name}.{area_key}.id", f"过程域 '{area_key}' 缺少必填字段 id")
        bps = area.get("base_practices", [])
        _require(isinstance(bps, list), f"{name}.{area_key}.base_practices",
                 "base_practices 必须是列表")
        for i, bp in enumerate(bps):
            bp_path = f"{name}.{area_key}.base_practices[{i}]"
            _require(isinstance(bp, dict), bp_path, "base_practice 必须是映射")
            for k in bp:
                _require(k in _ALLOWED_BP_KEYS, f"{bp_path}.{k}",
                         f"未知字段 '{k}'（base_practice 仅允许 {sorted(_ALLOWED_BP_KEYS)}）")
            _require("id" in bp and str(bp.get("id", "")).strip(),
                     f"{bp_path}.id", "base_practice 缺少必填字段 id")
            evs = bp.get("output_evidence", [])
            _require(isinstance(evs, list), f"{bp_path}.output_evidence",
                     "output_evidence 必须是列表")
            for j, ev in enumerate(evs):
                ev_path = f"{bp_path}.output_evidence[{j}]"
                _require(isinstance(ev, dict), ev_path, "evidence 必须是映射")
                for k in ev:
                    _require(k in _ALLOWED_EVIDENCE_KEYS, f"{ev_path}.{k}",
                             f"未知字段 '{k}'（evidence 仅允许 {sorted(_ALLOWED_EVIDENCE_KEYS)}）")
                ev_type_val = str(ev.get("type", "")).strip()
                _require(ev_type_val, f"{ev_path}.type", "evidence 缺少必填字段 type")
                _require(ev_type_val in _EVIDENCE_TYPE_ENUM,
                         f"{ev_path}.type",
                         f"evidence.type 取值 '{ev_type_val}' 不在允许集合 {sorted(_EVIDENCE_TYPE_ENUM)}"
                         "（A1-04 决策1：强制白名单，拼写漂移会静默错报为缺证据）")
                _require("path" in ev and str(ev.get("path", "")).strip(),
                         f"{ev_path}.path", "evidence 缺少必填字段 path")


def _yaml_to_profile(data: dict) -> StandardProfile:
    """把已校验的 yaml dict 无损映射到 StandardProfile。"""
    meta_raw = data.get("meta", {}) or {}
    meta = ProfileMeta(
        standard=str(meta_raw.get("standard", "ASPICE")),
        version=str(meta_raw.get("version", "3.1")),
        description=str(meta_raw.get("description", "")).strip(),
    )
    areas: List[ProcessArea] = []
    for area_key, area in data.items():
        if area_key == "meta":
            continue
        raw_order = area.get("order")
        order = int(raw_order) if isinstance(raw_order, (int, float)) else None
        bps: List[BasePractice] = []
        for bp in area.get("base_practices", []) or []:
            evs = [
                EvidenceSpec(
                    type=str(ev.get("type", "")),
                    path=str(ev.get("path", "")),
                    description=str(ev.get("description", "")).strip(),
                )
                for ev in bp.get("output_evidence", []) or []
            ]
            bps.append(
                BasePractice(
                    id=str(bp.get("id", "")),
                    title=str(bp.get("title", "")).strip(),
                    output_evidence=evs,
                    check=[str(c) for c in bp.get("check", []) or []],
                )
            )
        areas.append(
            ProcessArea(
                id=str(area.get("id", "")),
                title=str(area.get("title", "")).strip(),
                description=str(area.get("description", "")).strip(),
                base_practices=bps,
                order=order,
                key=str(area_key),
            )
        )
    return StandardProfile(meta=meta, areas=areas)


def load_profile(name: str, profile_dir: Optional[Path] = None) -> StandardProfile:
    """加载并校验一个合规标准 profile (A1-03)。

    Args:
        name: profile 名（不含 .yaml），如 ``aspice_v3.1``。
        profile_dir: 可选自定义搜索目录；默认搜索 compliance/ 与 compliance/profiles/。

    Returns:
        校验通过的 ``StandardProfile``。

    Raises:
        ProfileNotFoundError: 文件不存在（含可用清单）。
        ProfileError: 结构缺字段或含未知字段（含字段路径与修复提示）。
        yaml.YAMLError: yaml 解析失败时透传（属文件级错误，路径即文件名）。
    """
    path = _find_profile_file(name, profile_dir)
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    _validate(data or {}, name)
    return _yaml_to_profile(data or {})

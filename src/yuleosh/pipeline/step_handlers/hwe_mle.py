"""HWE.1~HWE.4 硬件工程 / MLE.1~MLE.4 机器学习工程（ASPICE 3.1）。

与 MAN.5 / MAN.6 / 管理支撑组一致：**确定性生成 + 确定性评审**。

- **范围识别**：HWE 范围来自链接脚本 / CubeMX 配置 / 板级目录 / CAN 矩阵 /
  启动代码等客观文件信号；MLE 范围来自模型文件 / 训练脚本 / 数据集目录。
  扫描不到即如实记录「无范围」，绝不臆造条目。
- **登记表**（``docs/hw-item-register.yaml`` / ``docs/ml-item-register.yaml``）
  必须留有 ``scan_sources``；人工字段（owner/status/notes/证据引用）跨轮次保留。
- **结论不自封**：HWE.4 的「已验证」、MLE.4 的「已评估」必须引用磁盘上
  真实存在且包含对应条目 ID 的证据文件；复核步骤逐条重校验，假证据即 RED。
"""

from __future__ import annotations

import logging
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.step_handlers.mgmt_support import (
    _cell,
    _load_yaml,
    _now,
    _require_sections,
    _save_yaml,
    _sha256,
    _write_doc,
)
from yuleosh.pipeline.step_handlers.validation import _write_step_marker

log = logging.getLogger("pipeline.step_handlers.hwe_mle")

HW_REGISTER = "docs/hw-item-register.yaml"
HW_REQUIREMENTS = "docs/hw-requirements.md"
HW_DESIGN = "docs/hw-design.md"
HW_IMPL = "docs/hw-implementation-report.md"
HW_VERIF = "docs/hw-verification-report.md"

ML_REGISTER = "docs/ml-item-register.yaml"
ML_REQUIREMENTS = "docs/ml-requirements.md"
ML_APPROACH = "docs/ml-approach.md"
ML_TRAINING = "docs/ml-training-report.md"
ML_EVAL = "docs/ml-evaluation-report.md"

HW_KINDS = ("linker-script", "cube-config", "board-config",
            "can-matrix", "startup-code", "manual")
ML_KINDS = ("model", "training-script", "dataset", "manual")
ITEM_STATUSES = ("draft", "in-progress", "done", "待分析")

_HW_REQ_SECTIONS = ("## 硬件条目", "## 范围与扫描来源", "## 可追溯性")
_HW_DESIGN_SECTIONS = ("## 设计约束", "## 资源分配", "## 软硬件划分", "## 可追溯性")
_HW_IMPL_SECTIONS = ("## 构建产物", "## 实现覆盖", "## 可追溯性")
_HW_VERIF_SECTIONS = ("## 验证结果", "## 证据核对", "## 可追溯性")
_ML_REQ_SECTIONS = ("## 机器学习条目", "## 范围与扫描来源", "## 可追溯性")
_ML_APPROACH_SECTIONS = ("## 模型选型", "## 数据策略", "## 度量与预算", "## 可追溯性")
_ML_TRAINING_SECTIONS = ("## 训练来源", "## 训练记录", "## 可追溯性")
_ML_EVAL_SECTIONS = ("## 评估结果", "## 证据核对", "## 可追溯性")

_NO_HW_SCOPE = "（无条目：未检测到硬件范围）"
_NO_ML_SCOPE = "（无条目：未检测到机器学习范围）"

_EXCLUDE_DIRS = (".osh", ".git", ".venv", "node_modules",
                 "__pycache__", ".pytest_cache", "dist", "build-venv")
_MAX_ITEMS = 50

_HW_GLOBS = (
    ("**/*.ld", "linker-script"),
    ("**/*.sct", "linker-script"),
    ("**/*.ioc", "cube-config"),
    ("**/*.dbc", "can-matrix"),
    ("**/startup_*.s", "startup-code"),
    ("**/startup_*.S", "startup-code"),
)
_HW_DIR_KINDS = (("boards", "board-config"), ("board", "board-config"))

_ML_GLOBS = (
    ("**/*.onnx", "model"),
    ("**/*.pt", "model"),
    ("**/*.pth", "model"),
    ("**/*.h5", "model"),
    ("**/*.tflite", "model"),
    ("**/train*.py", "training-script"),
)
_ML_DIR_KINDS = (("models", "model"), ("ml", "model"), ("datasets", "dataset"))

_BUILD_GLOBS = ("**/*.hex", "**/*.bin", "**/*.elf")


# ── 通用扫描与登记 ──────────────────────────────────────────────────────


def _excluded(rel: str) -> bool:
    return any(part in _EXCLUDE_DIRS for part in Path(rel).parts)


def _scan_files(project_dir: str, globs: tuple, dir_kinds: tuple,
                label: str) -> tuple[list[dict], list[str]]:
    """按 glob 与目录信号扫描范围条目；返回 (条目, 扫描来源)。

    扫描来源总是记录（包括零命中），证明盘点确实发生——"没有范围"
    不能凭空成立。
    """
    root = Path(project_dir)
    found: dict[str, dict] = {}
    sources: list[str] = []
    for pattern, kind in globs:
        sources.append(f"glob:{pattern}")
        try:
            matches = sorted(root.glob(pattern))
        except OSError:
            continue
        for path in matches:
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            if _excluded(rel):
                continue
            found.setdefault(rel, {"title": path.name, "kind": kind,
                                   "source": rel})
            if len(found) >= _MAX_ITEMS:
                break
    for dirname, kind in dir_kinds:
        sources.append(f"dir:{dirname}/")
        base = root / dirname
        if not base.is_dir():
            continue
        try:
            members = sorted(p for p in base.rglob("*") if p.is_file())
        except OSError:
            continue
        for path in members[:_MAX_ITEMS]:
            rel = str(path.relative_to(root))
            if _excluded(rel):
                continue
            found.setdefault(rel, {"title": path.name, "kind": kind,
                                   "source": rel})
    log.info("[%s] 扫描完成: %d 个条目（来源 %d 类）", label, len(found), len(sources))
    return list(found.values())[:_MAX_ITEMS], sources


def _merge_items(existing: dict, generated: list[dict], id_prefix: str,
                 id_seq_width: int = 3) -> list[dict]:
    """合并自动条目与人工条目；按 source 匹配保留人工字段与既有 ID。"""
    prev_items = [i for i in existing.get("items") or [] if isinstance(i, dict)]
    prev_by_source = {str(i.get("source")): i for i in prev_items if i.get("source")}
    prev_ids = {str(i.get("id")) for i in prev_items if i.get("id")}

    merged: list[dict] = []
    seen_sources: set[str] = set()
    for gen in generated:
        prev = prev_by_source.get(gen["source"], {})
        entry = {**prev, **gen}
        # 人工字段以登记文件为准（跨轮次保留）
        for field in ("owner", "status", "notes", "verification_evidence"):
            if prev.get(field) not in (None, ""):
                entry[field] = prev[field]
        entry.setdefault("owner", "待指定")
        entry.setdefault("status", "待分析")
        entry.setdefault("notes", "")
        entry["origin"] = prev.get("origin") or "auto"
        entry["last_seen"] = _now()
        merged.append(entry)
        seen_sources.add(gen["source"])

    for item in prev_items:
        if item.get("source") in seen_sources:
            continue
        merged.append({"owner": "待指定", "status": "待分析", "notes": "",
                       **item})

    # 为没有既有 ID 的条目分配新 ID（跳过已被占用的编号，保持稳定）
    assigned = {str(i.get("id")) for i in merged if str(i.get("id") or "") in prev_ids}
    next_n = 1
    for item in merged:
        iid = str(item.get("id") or "")
        if iid and iid in prev_ids:
            continue
        while True:
            candidate = f"{id_prefix}-{next_n:0{id_seq_width}d}"
            next_n += 1
            if candidate not in assigned:
                break
        item["id"] = candidate
        assigned.add(candidate)
    merged.sort(key=lambda i: str(i["id"]))
    return merged


def _save_register(project_dir: str, rel_path: str, items: list[dict],
                   sources: list[str]) -> None:
    _save_yaml(project_dir, rel_path, {
        "version": 1,
        "generated_at": _now(),
        "scan_sources": sources,
        "items": items,
    })


def _validate_items(items: list[dict], kinds: tuple, label: str,
                    project_dir: str) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(items):
        iid = str(item.get("id") or "").strip()
        if not iid:
            problems.append(f"第 {idx + 1} 条{label}缺少 id")
            continue
        if iid in seen:
            problems.append(f"{label} id 重复: {iid}")
        seen.add(iid)
        if not str(item.get("title") or "").strip():
            problems.append(f"{iid} 缺少 title")
        if item.get("kind") not in kinds:
            problems.append(f"{iid} kind 非法: {item.get('kind')}")
        if item.get("status") not in ITEM_STATUSES:
            problems.append(f"{iid} status 非法: {item.get('status')}")
        source = str(item.get("source") or "").strip()
        if not source:
            problems.append(f"{iid} 缺少 source")
        elif (str(item.get("origin") or "auto") == "auto"
              and not (Path(project_dir) / source).exists()):
            problems.append(f"{iid} 的自动来源文件不存在: {source}")
    return problems


def _load_register(project_dir: str, rel_path: str) -> tuple[dict, list[dict]]:
    data = _load_yaml(project_dir, rel_path)
    items = [i for i in data.get("items") or [] if isinstance(i, dict)]
    return data, items


def _item_rows(items: list[dict]) -> list[str]:
    return [
        f"| {_cell(i.get('id'))} | {_cell(i.get('title'))} | {_cell(i.get('kind'))} "
        f"| {_cell(i.get('source'))} | {i.get('status')} | {_cell(i.get('owner'))} |"
        for i in items
    ]


# ══════════════════════════════════════════════════════════════════════
# HWE.1 硬件需求分析
# ══════════════════════════════════════════════════════════════════════


def _build_hw_requirements(items: list[dict], sources: list[str]) -> str:
    rows = _item_rows(items)
    listing = ("\n".join(rows) if rows else f"| — | {_NO_HW_SCOPE} | — | — | — | — |")
    return (
        "# 硬件需求分析（HWE.1）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 硬件条目数：{len(items)}\n\n"
        "## 硬件条目\n\n"
        "| ID | 条目 | 类型 | 来源 | 状态 | 责任人 |\n"
        "|:---|:---|:---|:---|:---|:---|\n"
        + listing + "\n\n"
        "## 范围与扫描来源\n\n"
        "硬件范围由以下客观信号识别（零命中亦如实记录）：\n\n"
        + "\n".join(f"- `{s}`" for s in sources) + "\n\n"
        + ("" if items else
           "> 本次扫描未命中任何硬件信号，判定为无硬件范围；"
           "不做任何硬件条目推断。若项目实际包含硬件，请补充上述信号文件"
           "或在登记文件中人工登记（origin: manual）。\n\n")
        + "## 可追溯性\n\n"
        "- 登记文件：`docs/hw-item-register.yaml`（scan_sources 为扫描证据）。\n"
        "- 硬件设计覆盖见 `docs/hw-design.md`（HWE.2）；"
        "验证结论见 `docs/hw-verification-report.md`（HWE.4）。\n"
    )


def step_hwe1_requirements(session: PipelineSession) -> str:
    """HWE.1 — 识别硬件范围条目并生成硬件需求分析。"""
    generated, sources = _scan_files(
        session.project_dir, _HW_GLOBS, _HW_DIR_KINDS, "HWE.1")
    existing = _load_yaml(session.project_dir, HW_REGISTER)
    items = _merge_items(existing, generated, "HWE")
    _save_register(session.project_dir, HW_REGISTER, items, sources)
    doc_path = _write_doc(session, HW_REQUIREMENTS,
                          _build_hw_requirements(items, sources))
    _write_step_marker(session, "hwe1-requirements", status="completed",
                       register=HW_REGISTER, requirements=HW_REQUIREMENTS,
                       item_count=len(items))
    return str(doc_path)


def step_review_hwe1(session: PipelineSession) -> str:
    """HWE.1 门禁：登记结构 + 扫描来源 + 需求文档章节与条目一致性。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, HW_REQUIREMENTS,
                             _HW_REQ_SECTIONS, problems)
    data = _load_yaml(session.project_dir, HW_REGISTER)
    if not data:
        problems.append(f"缺少或无法解析 {HW_REGISTER}")
    else:
        if not data.get("scan_sources"):
            problems.append(f"{HW_REGISTER} 缺少 scan_sources（无扫描证据）")
        _, items = _load_register(session.project_dir, HW_REGISTER)
        problems.extend(_validate_items(items, HW_KINDS, "硬件条目",
                                        session.project_dir))
        for item in items:
            if str(item.get("id")) not in text:
                problems.append(f"{HW_REQUIREMENTS} 未列出条目 {item.get('id')}")
    if problems:
        raise PipelineStepError("HWE.1 硬件需求门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "hwe1-review", status="completed",
                       verified=[HW_REGISTER, HW_REQUIREMENTS])
    return str(Path(session.project_dir) / HW_REQUIREMENTS)


# ══════════════════════════════════════════════════════════════════════
# HWE.2 硬件设计
# ══════════════════════════════════════════════════════════════════════


def _build_hw_design(items: list[dict]) -> str:
    ids = [str(i.get("id")) for i in items]
    coverage = ("\n".join(f"- {iid}" for iid in ids)
                if ids else f"- {_NO_HW_SCOPE}")
    return (
        "# 硬件设计（HWE.2）\n\n"
        f"- 生成时间：{_now()}\n\n"
        "## 设计约束\n\n"
        "- 约束来源：`docs/system-architecture.md` 与 `docs/hw-requirements.md`。\n"
        "- 人工约束记录在本节追加；自动内容只负责条目覆盖，不臆造约束。\n\n"
        "## 资源分配\n\n"
        "| 资源 | 分配 | 备注 |\n|:---|:---|:---|\n"
        "| 引脚/内存/外设 | 待人工记录 | — |\n\n"
        "## 软硬件划分\n\n"
        "本节覆盖的硬件条目：\n\n"
        + coverage + "\n\n"
        "## 可追溯性\n\n"
        "- 硬件条目登记：`docs/hw-item-register.yaml`（HWE.1）。\n"
        "- 实现核对见 `docs/hw-implementation-report.md`（HWE.3）。\n"
    )


def step_hwe2_design(session: PipelineSession) -> str:
    """HWE.2 — 生成硬件设计文档（覆盖登记表中的每个条目）。"""
    _, items = _load_register(session.project_dir, HW_REGISTER)
    doc_path = _write_doc(session, HW_DESIGN, _build_hw_design(items))
    _write_step_marker(session, "hwe2-design", status="completed",
                       design=HW_DESIGN, item_count=len(items))
    return str(doc_path)


def step_review_hwe2(session: PipelineSession) -> str:
    """HWE.2 门禁：设计文档章节齐全且覆盖每个登记条目（无范围须有明示）。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, HW_DESIGN,
                             _HW_DESIGN_SECTIONS, problems)
    if text:
        _, items = _load_register(session.project_dir, HW_REGISTER)
        if items:
            for item in items:
                if str(item.get("id")) not in text:
                    problems.append(f"{HW_DESIGN} 未覆盖硬件条目 {item.get('id')}")
        elif _NO_HW_SCOPE not in text:
            problems.append(f"{HW_DESIGN} 未明示无硬件范围（{_NO_HW_SCOPE}）")
    if problems:
        raise PipelineStepError("HWE.2 硬件设计门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "hwe2-review", status="completed",
                       verified=[HW_DESIGN])
    return str(Path(session.project_dir) / HW_DESIGN)


# ══════════════════════════════════════════════════════════════════════
# HWE.3 硬件实现（对照设计的实现核对）
# ══════════════════════════════════════════════════════════════════════


def _scan_build_outputs(project_dir: str) -> list[dict]:
    root = Path(project_dir)
    found: dict[str, dict] = {}
    for pattern in _BUILD_GLOBS:
        try:
            matches = sorted(root.glob(pattern))
        except OSError:
            continue
        for path in matches:
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            if _excluded(rel):
                continue
            found[rel] = {"path": rel, "size": path.stat().st_size,
                          "sha256": _sha256(path)}
            if len(found) >= _MAX_ITEMS:
                break
    return list(found.values())


def _build_hw_impl(items: list[dict], outputs: list[dict]) -> str:
    out_rows = [
        f"| {_cell(o['path'])} | {o['size']} | `{o['sha256'][:16]}…` |"
        for o in outputs
    ]
    out_table = ("\n".join(out_rows)
                 if out_rows else "| — | — | 未发现构建产物 |")
    coverage = (
        "\n".join(
            f"| {_cell(i.get('id'))} | {_cell(i.get('title'))} | {i.get('status')} |"
            for i in items)
        if items else f"| — | {_NO_HW_SCOPE} | — |")
    return (
        "# 硬件实现报告（HWE.3）\n\n"
        f"- 生成时间：{_now()}\n\n"
        "## 构建产物\n\n"
        "以下构建产物由文件系统扫描得到（路径 + 大小 + SHA256 前 16 位）：\n\n"
        "| 路径 | 字节数 | 摘要 |\n|:---|---:|:---|\n"
        + out_table + "\n\n"
        "## 实现覆盖\n\n"
        "硬件条目的实现状态取自登记文件（人工维护）：\n\n"
        "| ID | 条目 | 状态 |\n|:---|:---|:---|\n"
        + coverage + "\n\n"
        "## 可追溯性\n\n"
        "- 硬件设计：`docs/hw-design.md`（HWE.2）。\n"
        "- 验证结论：`docs/hw-verification-report.md`（HWE.4）。\n"
    )


def step_hwe3_implementation(session: PipelineSession) -> str:
    """HWE.3 — 扫描构建产物并对照登记条目生成实现报告。"""
    _, items = _load_register(session.project_dir, HW_REGISTER)
    outputs = _scan_build_outputs(session.project_dir)
    doc_path = _write_doc(session, HW_IMPL, _build_hw_impl(items, outputs))
    _write_step_marker(session, "hwe3-implementation", status="completed",
                       report=HW_IMPL, build_output_count=len(outputs))
    return str(doc_path)


def step_review_hwe3(session: PipelineSession) -> str:
    """HWE.3 门禁：报告中列出的构建产物必须真实存在且摘要一致。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, HW_IMPL,
                             _HW_IMPL_SECTIONS, problems)
    if text:
        # 报告中列出的每个构建产物路径必须在磁盘上存在（防臆造清单）。
        for line in text.splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3 or not cells[0] or cells[0] in ("路径", "—", ":---"):
                continue
            rel = cells[0]
            if not rel.endswith((".hex", ".bin", ".elf")):
                continue
            target = Path(session.project_dir) / rel
            if not target.is_file():
                problems.append(f"构建产物不存在: {rel}")
                continue
            digest_cell = cells[2].strip("`").rstrip("…").strip()
            if digest_cell and not _sha256(target).startswith(digest_cell):
                problems.append(f"构建产物摘要不一致: {rel}")
        _, items = _load_register(session.project_dir, HW_REGISTER)
        for item in items:
            if str(item.get("id")) not in text:
                problems.append(f"{HW_IMPL} 未列出硬件条目 {item.get('id')}")
    if problems:
        raise PipelineStepError("HWE.3 硬件实现门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "hwe3-review", status="completed",
                       verified=[HW_IMPL])
    return str(Path(session.project_dir) / HW_IMPL)


# ══════════════════════════════════════════════════════════════════════
# HWE.4 硬件验证（对照硬件需求）
# ══════════════════════════════════════════════════════════════════════


def _hw_item_verified(project_dir: str, item: dict) -> tuple[bool, str]:
    """条目标「已验证」的条件：登记中引用真实存在且包含该条目 ID 的证据文件。"""
    evidence = str(item.get("verification_evidence") or "").strip()
    if not evidence:
        return False, ""
    target = Path(project_dir) / evidence
    if not target.is_file():
        return False, evidence
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, evidence
    return (str(item.get("id")) in content), evidence


def _build_hw_verif(project_dir: str, items: list[dict]) -> str:
    rows = []
    for item in items:
        verified, evidence = _hw_item_verified(project_dir, item)
        verdict = "已验证" if verified else "未验证"
        rows.append(
            f"| {_cell(item.get('id'))} | {_cell(item.get('title'))} "
            f"| {verdict} | {_cell(evidence or '—')} |")
    table = ("\n".join(rows) if rows else f"| — | {_NO_HW_SCOPE} | — | — |")
    return (
        "# 硬件验证报告（HWE.4）\n\n"
        f"- 生成时间：{_now()}\n\n"
        "## 验证结果\n\n"
        "「已验证」要求登记条目引用真实存在且包含该条目 ID 的证据文件；"
        "本步骤不自行判定验证通过。\n\n"
        "| ID | 条目 | 结论 | 证据 |\n|:---|:---|:---|:---|\n"
        + table + "\n\n"
        "## 证据核对\n\n"
        "- 证据文件由复核步骤逐条重新打开校验；引用不存在或内容不含条目 ID 即 RED。\n"
        "- 未验证不是失败，而是如实状态；不得为求绿而补写假证据。\n\n"
        "## 可追溯性\n\n"
        "- 硬件条目：`docs/hw-item-register.yaml`（HWE.1）。\n"
        "- 实现状态：`docs/hw-implementation-report.md`（HWE.3）。\n"
    )


def step_hwe4_verification(session: PipelineSession) -> str:
    """HWE.4 — 按登记条目的证据引用生成硬件验证报告。"""
    _, items = _load_register(session.project_dir, HW_REGISTER)
    doc_path = _write_doc(session, HW_VERIF,
                          _build_hw_verif(session.project_dir, items))
    _write_step_marker(session, "hwe4-verification", status="completed",
                       report=HW_VERIF, item_count=len(items))
    return str(doc_path)


def step_review_hwe4(session: PipelineSession) -> str:
    """HWE.4 门禁：报告中的「已验证」逐条重校验证据文件。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, HW_VERIF,
                             _HW_VERIF_SECTIONS, problems)
    if text:
        _, items = _load_register(session.project_dir, HW_REGISTER)
        for item in items:
            iid = str(item.get("id"))
            if iid not in text:
                problems.append(f"{HW_VERIF} 未列出硬件条目 {iid}")
                continue
            verified, evidence = _hw_item_verified(session.project_dir, item)
            row_claimed = any(
                line.startswith(f"| {iid} ") and "| 已验证 |" in line
                for line in text.splitlines())
            if row_claimed and not verified:
                problems.append(
                    f"{iid} 报告标「已验证」但证据无效"
                    f"（{evidence or '未引用证据'}）")
    if problems:
        raise PipelineStepError("HWE.4 硬件验证门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "hwe4-review", status="completed",
                       verified=[HW_VERIF])
    return str(Path(session.project_dir) / HW_VERIF)


# ══════════════════════════════════════════════════════════════════════
# MLE.1 机器学习需求分析
# ══════════════════════════════════════════════════════════════════════


def _build_ml_requirements(items: list[dict], sources: list[str]) -> str:
    rows = _item_rows(items)
    listing = ("\n".join(rows) if rows else f"| — | {_NO_ML_SCOPE} | — | — | — | — |")
    return (
        "# 机器学习需求分析（MLE.1）\n\n"
        f"- 生成时间：{_now()}\n"
        f"- 机器学习条目数：{len(items)}\n\n"
        "## 机器学习条目\n\n"
        "| ID | 条目 | 类型 | 来源 | 状态 | 责任人 |\n"
        "|:---|:---|:---|:---|:---|:---|\n"
        + listing + "\n\n"
        "## 范围与扫描来源\n\n"
        "机器学习范围由以下客观信号识别（零命中亦如实记录）：\n\n"
        + "\n".join(f"- `{s}`" for s in sources) + "\n\n"
        + ("" if items else
           "> 本次扫描未命中任何机器学习信号，判定为无机器学习范围；"
           "不做任何条目推断。若项目实际包含模型/训练/数据集，请补充上述信号"
           "文件或在登记文件中人工登记（origin: manual）。\n\n")
        + "## 可追溯性\n\n"
        "- 登记文件：`docs/ml-item-register.yaml`（scan_sources 为扫描证据）。\n"
        "- 方案见 `docs/ml-approach.md`（MLE.2）；"
        "评估结论见 `docs/ml-evaluation-report.md`（MLE.4）。\n"
    )


def step_mle1_requirements(session: PipelineSession) -> str:
    """MLE.1 — 识别机器学习范围条目并生成需求分析。"""
    generated, sources = _scan_files(
        session.project_dir, _ML_GLOBS, _ML_DIR_KINDS, "MLE.1")
    existing = _load_yaml(session.project_dir, ML_REGISTER)
    items = _merge_items(existing, generated, "MLE")
    _save_register(session.project_dir, ML_REGISTER, items, sources)
    doc_path = _write_doc(session, ML_REQUIREMENTS,
                          _build_ml_requirements(items, sources))
    _write_step_marker(session, "mle1-requirements", status="completed",
                       register=ML_REGISTER, requirements=ML_REQUIREMENTS,
                       item_count=len(items))
    return str(doc_path)


def step_review_mle1(session: PipelineSession) -> str:
    """MLE.1 门禁：登记结构 + 扫描来源 + 文档章节与条目一致性。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, ML_REQUIREMENTS,
                             _ML_REQ_SECTIONS, problems)
    data = _load_yaml(session.project_dir, ML_REGISTER)
    if not data:
        problems.append(f"缺少或无法解析 {ML_REGISTER}")
    else:
        if not data.get("scan_sources"):
            problems.append(f"{ML_REGISTER} 缺少 scan_sources（无扫描证据）")
        _, items = _load_register(session.project_dir, ML_REGISTER)
        problems.extend(_validate_items(items, ML_KINDS, "机器学习条目",
                                        session.project_dir))
        for item in items:
            if str(item.get("id")) not in text:
                problems.append(f"{ML_REQUIREMENTS} 未列出条目 {item.get('id')}")
    if problems:
        raise PipelineStepError("MLE.1 机器学习需求门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "mle1-review", status="completed",
                       verified=[ML_REGISTER, ML_REQUIREMENTS])
    return str(Path(session.project_dir) / ML_REQUIREMENTS)


# ══════════════════════════════════════════════════════════════════════
# MLE.2 机器学习方案（模型选型 / 数据策略 / 度量与预算）
# ══════════════════════════════════════════════════════════════════════


def _build_ml_approach(items: list[dict]) -> str:
    ids = [str(i.get("id")) for i in items]
    coverage = ("\n".join(f"- {iid}" for iid in ids)
                if ids else f"- {_NO_ML_SCOPE}")
    return (
        "# 机器学习方案（MLE.2）\n\n"
        f"- 生成时间：{_now()}\n\n"
        "## 模型选型\n\n"
        "| 条目 | 模型类型 | 选型理由 |\n|:---|:---|:---|\n"
        "| 待人工记录 | — | — |\n\n"
        "## 数据策略\n\n"
        "- 训练/验证/测试数据划分与来源由人工在本节记录；自动内容不臆造数据结论。\n\n"
        "## 度量与预算\n\n"
        "| 指标 | 目标值 | 资源预算 |\n|:---|:---|:---|\n"
        "| 待人工记录 | — | — |\n\n"
        "本节覆盖的机器学习条目：\n\n"
        + coverage + "\n\n"
        "## 可追溯性\n\n"
        "- 条目登记：`docs/ml-item-register.yaml`（MLE.1）。\n"
        "- 训练记录：`docs/ml-training-report.md`（MLE.3）。\n"
    )


def step_mle2_approach(session: PipelineSession) -> str:
    """MLE.2 — 生成机器学习方案文档（覆盖登记表中的每个条目）。"""
    _, items = _load_register(session.project_dir, ML_REGISTER)
    doc_path = _write_doc(session, ML_APPROACH, _build_ml_approach(items))
    _write_step_marker(session, "mle2-approach", status="completed",
                       approach=ML_APPROACH, item_count=len(items))
    return str(doc_path)


def step_review_mle2(session: PipelineSession) -> str:
    """MLE.2 门禁：方案章节齐全且覆盖每个登记条目（无范围须有明示）。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, ML_APPROACH,
                             _ML_APPROACH_SECTIONS, problems)
    if text:
        _, items = _load_register(session.project_dir, ML_REGISTER)
        if items:
            for item in items:
                if str(item.get("id")) not in text:
                    problems.append(f"{ML_APPROACH} 未覆盖机器学习条目 {item.get('id')}")
        elif _NO_ML_SCOPE not in text:
            problems.append(f"{ML_APPROACH} 未明示无机器学习范围（{_NO_ML_SCOPE}）")
    if problems:
        raise PipelineStepError("MLE.2 机器学习方案门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "mle2-review", status="completed",
                       verified=[ML_APPROACH])
    return str(Path(session.project_dir) / ML_APPROACH)


# ══════════════════════════════════════════════════════════════════════
# MLE.3 机器学习训练
# ══════════════════════════════════════════════════════════════════════


def _extract_section(text: str, heading: str) -> str:
    """提取 ``## heading`` 到下一个 ``## `` 之间的正文（用于跨轮次保留人工记录）。"""
    lines = text.splitlines()
    start = None
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            start = idx + 1
            break
    if start is None:
        return ""
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body).strip("\n")


def _build_ml_training(items: list[dict], prior_records: str) -> str:
    sources = [i for i in items if i.get("kind") == "training-script"]
    src_rows = [
        f"| {_cell(i.get('id'))} | {_cell(i.get('source'))} |" for i in sources]
    src_table = ("\n".join(src_rows)
                 if src_rows else "| — | 未检测到训练脚本 |")
    records = prior_records or (
        "| 条目 | 数据集 | 配置 | 指标 | 数值 |\n"
        "|:---|:---|:---|:---|---:|\n"
        "| 待人工记录 | — | — | — | — |\n\n"
        "> 训练指标只能由人依据真实训练输出填写；本报告不生成任何数值。"
    )
    return (
        "# 机器学习训练报告（MLE.3）\n\n"
        f"- 生成时间：{_now()}\n\n"
        "## 训练来源\n\n"
        "以下训练脚本由文件系统扫描得到：\n\n"
        "| ID | 路径 |\n|:---|:---|\n"
        + src_table + "\n\n"
        "## 训练记录\n\n"
        + records + "\n\n"
        "## 可追溯性\n\n"
        "- 方案：`docs/ml-approach.md`（MLE.2）。\n"
        "- 评估：`docs/ml-evaluation-report.md`（MLE.4）。\n"
    )


def step_mle3_training(session: PipelineSession) -> str:
    """MLE.3 — 列出训练来源；训练记录段跨轮次保留（人工填写指标）。"""
    _, items = _load_register(session.project_dir, ML_REGISTER)
    prior = ""
    old = Path(session.project_dir) / ML_TRAINING
    if old.is_file():
        prior = _extract_section(
            old.read_text(encoding="utf-8", errors="replace"), "## 训练记录")
    doc_path = _write_doc(session, ML_TRAINING,
                          _build_ml_training(items, prior))
    _write_step_marker(session, "mle3-training", status="completed",
                       report=ML_TRAINING,
                       training_source_count=sum(
                           1 for i in items if i.get("kind") == "training-script"))
    return str(doc_path)


def step_review_mle3(session: PipelineSession) -> str:
    """MLE.3 门禁：训练来源表中的脚本路径必须真实存在。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, ML_TRAINING,
                             _ML_TRAINING_SECTIONS, problems)
    if text:
        in_sources = False
        for line in text.splitlines():
            if line.strip() == "## 训练来源":
                in_sources = True
                continue
            if line.startswith("## "):
                in_sources = False
            if not in_sources or not line.strip().startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2 or cells[0] in ("ID", "—", ":---"):
                continue
            rel = cells[1]
            if rel and not (Path(session.project_dir) / rel).is_file():
                problems.append(f"训练来源脚本不存在: {rel}")
    if problems:
        raise PipelineStepError("MLE.3 机器学习训练门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "mle3-review", status="completed",
                       verified=[ML_TRAINING])
    return str(Path(session.project_dir) / ML_TRAINING)


# ══════════════════════════════════════════════════════════════════════
# MLE.4 机器学习测试（模型评估）
# ══════════════════════════════════════════════════════════════════════


def _ml_item_evaluated(project_dir: str, item: dict) -> tuple[bool, str]:
    """模型标「已评估」的条件：``docs/ml-eval-<id>.yaml`` 存在且含非空 metrics。"""
    iid = str(item.get("id") or "")
    rel = f"docs/ml-eval-{iid}.yaml"
    data = _load_yaml(project_dir, rel)
    if not data:
        return False, rel
    metrics = data.get("metrics")
    return (isinstance(metrics, dict) and len(metrics) > 0), rel


def _build_ml_eval(project_dir: str, items: list[dict]) -> str:
    models = [i for i in items if i.get("kind") == "model"]
    rows = []
    for item in models:
        evaluated, evidence = _ml_item_evaluated(project_dir, item)
        verdict = "已评估" if evaluated else "未评估"
        rows.append(
            f"| {_cell(item.get('id'))} | {_cell(item.get('title'))} "
            f"| {verdict} | {_cell(evidence)} |")
    table = ("\n".join(rows) if rows else "| — | 未检测到模型条目 | — | — |")
    return (
        "# 机器学习评估报告（MLE.4）\n\n"
        f"- 生成时间：{_now()}\n\n"
        "## 评估结果\n\n"
        "「已评估」要求 ``docs/ml-eval-<id>.yaml`` 存在且含非空 ``metrics``；"
        "本步骤不自行判定评估通过。\n\n"
        "| ID | 模型 | 结论 | 证据 |\n|:---|:---|:---|:---|\n"
        + table + "\n\n"
        "## 证据核对\n\n"
        "- 评估证据由复核步骤逐条重新解析校验；缺文件或空 metrics 即 RED。\n"
        "- 未评估不是失败，而是如实状态；不得为求绿而编造指标。\n\n"
        "## 可追溯性\n\n"
        "- 条目登记：`docs/ml-item-register.yaml`（MLE.1）。\n"
        "- 训练记录：`docs/ml-training-report.md`（MLE.3）。\n"
    )


def step_mle4_evaluation(session: PipelineSession) -> str:
    """MLE.4 — 按模型条目的评估证据文件生成评估报告。"""
    _, items = _load_register(session.project_dir, ML_REGISTER)
    doc_path = _write_doc(session, ML_EVAL,
                          _build_ml_eval(session.project_dir, items))
    _write_step_marker(session, "mle4-evaluation", status="completed",
                       report=ML_EVAL,
                       model_count=sum(
                           1 for i in items if i.get("kind") == "model"))
    return str(doc_path)


def step_review_mle4(session: PipelineSession) -> str:
    """MLE.4 门禁：报告中的「已评估」逐条重校验评估证据文件。"""
    problems: list[str] = []
    text = _require_sections(session.project_dir, ML_EVAL,
                             _ML_EVAL_SECTIONS, problems)
    if text:
        _, items = _load_register(session.project_dir, ML_REGISTER)
        for item in items:
            if item.get("kind") != "model":
                continue
            iid = str(item.get("id"))
            if iid not in text:
                problems.append(f"{ML_EVAL} 未列出模型条目 {iid}")
                continue
            evaluated, evidence = _ml_item_evaluated(session.project_dir, item)
            row_claimed = any(
                line.startswith(f"| {iid} ") and "| 已评估 |" in line
                for line in text.splitlines())
            if row_claimed and not evaluated:
                problems.append(
                    f"{iid} 报告标「已评估」但证据无效（{evidence}）")
    if problems:
        raise PipelineStepError("MLE.4 机器学习评估门禁 RED：" + "；".join(problems))
    _write_step_marker(session, "mle4-review", status="completed",
                       verified=[ML_EVAL])
    return str(Path(session.project_dir) / ML_EVAL)

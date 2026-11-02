
# @req RS-006  @req RS-002
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""OpenSpec validate and diff endpoints."""

import json
import os
import sys
from pathlib import Path

from . import json_ok, json_error
from .middleware import require_auth


@require_auth
def handle_spec(method: str, path_tail: str, body: dict, query: dict, **kwargs):
    """Route to spec sub-resources."""
    if path_tail == "validate":
        return _validate(method, body)
    elif path_tail == "diff":
        return _diff(method, body)
    elif path_tail == "gen":
        return _gen(method, body)
    elif path_tail == "list":
        return _list_specs(method, query)
    elif path_tail == "projects":
        return _list_projects(method)
    elif path_tail == "read":
        return _read_spec(method, query)
    elif path_tail == "save":
        return _save_spec(method, body)
    return json_error(f"Unknown spec resource: {path_tail}", 404)


# ── Studio workbench helpers (P2) ───────────────────────────────────────

# 工作区模型：一个工程 = OSH_HOME/projects/<pid>/，规格放在它的 docs/ 下。
# 与 api/requirements.py 的工程解析、pipeline 的工程发现共用同一套真相，
# 避免规格写到工具仓库根目录后 Pipeline 找不到。
_PROJECTS_SUBDIR = "projects"
_SPEC_SUBDIR = "docs"
_SPEC_LIST_CAP = 200
# Read/save size cap — specs are hand-authored markdown, 2 MB is generous.
_SPEC_MAX_BYTES = 2 * 1024 * 1024
# Health probe: Studio 工程卡片只需要「这个工作区健康吗」的粗略信号，
# 不是完整校验报告，所以每个工程最多扫 20 个文件。
_HEALTH_FILE_CAP = 20


def _resolve_project_dir(project: str) -> tuple[Path | None, tuple | None]:
    """Resolve ``OSH_HOME/projects/<pid>`` with a path-traversal guard.

    Same rule as api/requirements.py: the project must be a single path
    segment.  Returns (dir, None) on success, (None, error_tuple) on failure.
    """
    if not project:
        return None, json_error("缺少 project 参数（Studio 需要先选择工程）", 400)
    if ("/" in project or "\\" in project or project in (".", "..")
            or project.startswith(".")):
        return None, json_error("非法 project 名称", 403)
    from . import OSH_HOME
    base = Path(OSH_HOME).resolve() / _PROJECTS_SUBDIR
    try:
        proj_dir = (base / project).resolve()
        proj_dir.relative_to(base)
    except (ValueError, OSError):
        return None, json_error("project 路径越界", 403)
    if not proj_dir.is_dir():
        return None, json_error(f"工程不存在: {project}", 404)
    return proj_dir, None


def _resolve_in_project(proj_dir: Path, raw: str) -> Path | None:
    """Resolve a user-supplied path inside one project dir (traversal guard)."""
    if Path(raw).is_absolute():
        resolved = Path(raw).resolve()
    else:
        resolved = (proj_dir / raw.lstrip("/")).resolve()
    try:
        resolved.relative_to(proj_dir)
    except ValueError:
        return None
    return resolved


def _project_name_map() -> dict[str, str]:
    """Best-effort dir-name → display-name map from the project store."""
    try:
        from yuleosh.store import Store
        rows = Store().list_projects()
    except Exception:  # noqa: BLE001 — 纯磁盘工程（无 DB）也必须可用
        return {}
    names: dict[str, str] = {}
    for row in rows:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        for key in (str(row.get("id") or ""), name):
            if key:
                names.setdefault(key, name)
    return names


def _spec_health(files: list[Path]) -> dict[str, int]:
    """Aggregate {errors, warnings, stubs, checked} over a workspace's specs.

    与 ``_save_spec`` 同一套标准：除 ``validate_spec`` 的 ERROR/WARN 外，
    「没有任何需求」或「没有任何场景」也记一个 ERROR —— 否则占位模板会被
    误判成健康。``stubs`` 记录连需求都没有的文件数，前端据此把「还没开始写
    的占位规格」和「写错了的规格」区分开。
    """
    errors = warnings = stubs = checked = 0
    try:
        from yuleosh.spec.validate import parse_spec, validate_spec
    except Exception:  # noqa: BLE001 — 健康探针不得拖垮工程列表
        return {"errors": 0, "warnings": 0, "stubs": 0, "checked": 0}

    for f in files[:_HEALTH_FILE_CAP]:
        try:
            doc = parse_spec(str(f))
            issues = validate_spec(doc)
        except Exception:  # noqa: BLE001 — 坏文件跳过
            continue
        checked += 1
        for issue in issues:
            severity = issue.get("severity")
            if severity == "ERROR":
                errors += 1
            elif severity in ("WARN", "WARNING"):
                warnings += 1
        if not doc.requirements:
            stubs += 1
            errors += 1
        if not doc.scenarios:
            errors += 1
    return {"errors": errors, "warnings": warnings, "stubs": stubs, "checked": checked}


def _list_projects(method: str) -> tuple[dict, int]:
    """GET /api/v1/spec/projects — Studio 工程列表（以磁盘工作区为准）。

    ``OSH_HOME/projects`` 下的目录即工作区（Trae「打开文件夹」语义），再用
    项目表补可读名称：目录名是 org_project 的 id，CJK 工程名无法直接反推。
    """
    if method != "GET":
        return json_error("Use GET to list projects", 405)

    from . import OSH_HOME
    base = Path(OSH_HOME).resolve() / _PROJECTS_SUBDIR
    if not base.is_dir():
        return json_ok({"projects": [], "count": 0})

    names = _project_name_map()
    projects: list[dict] = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        docs = d / _SPEC_SUBDIR
        files = sorted(docs.rglob("*.md")) if docs.is_dir() else []
        mtimes: list[float] = []
        for f in files:
            try:
                mtimes.append(f.stat().st_mtime)
            except OSError:
                continue
        projects.append({
            "id": d.name,
            "name": names.get(d.name, d.name),
            "dir": f"{_PROJECTS_SUBDIR}/{d.name}",
            "spec_count": len(files),
            "has_docs": docs.is_dir(),
            "mtime": max(mtimes) if mtimes else d.stat().st_mtime,
            "health": _spec_health(files),
        })
    projects.sort(key=lambda p: p["mtime"], reverse=True)
    return json_ok({"projects": projects, "count": len(projects)})


def _list_specs(method: str, query: dict) -> tuple[dict, int]:
    """GET /api/v1/spec/list?project=<pid> — 工程 docs/ 下的规格文件。"""
    if method != "GET":
        return json_error("Use GET to list specs", 405)

    project = (query.get("project") or [""])[0].strip()
    proj_dir, err = _resolve_project_dir(project)
    if err:
        return err

    docs = proj_dir / _SPEC_SUBDIR
    items: list[dict] = []
    if docs.is_dir():
        for f in sorted(docs.rglob("*.md")):
            try:
                st = f.stat()
            except OSError:
                continue
            items.append({
                "path": f.relative_to(proj_dir).as_posix(),
                "name": f.name,
                "size": st.st_size,
                "mtime": st.st_mtime,
            })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    items = items[:_SPEC_LIST_CAP]
    return json_ok({"project": project, "files": items, "count": len(items)})


def _read_spec(method: str, query: dict) -> tuple[dict, int]:
    """GET /api/v1/spec/read?project=<pid>&path=<rel> — 读取工程内的一个规格文件。"""
    if method != "GET":
        return json_error("Use GET to read a spec", 405)

    project = (query.get("project") or [""])[0].strip()
    raw = (query.get("path") or [""])[0].strip()
    if not raw:
        return json_error("'path' is required")

    proj_dir, err = _resolve_project_dir(project)
    if err:
        return err

    resolved = _resolve_in_project(proj_dir, raw)
    if resolved is None:
        return json_error("Spec path must be within the project directory", 403)
    if not resolved.is_file():
        return json_error(f"Spec file not found: {raw}", 404)
    if resolved.stat().st_size > _SPEC_MAX_BYTES:
        return json_error("Spec file too large (max 2MB)", 413)

    content = resolved.read_text(encoding="utf-8")
    return json_ok({"project": project, "path": raw, "content": content,
                    "size": len(content)})


def _save_spec(method: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/spec/save — validate-before-write for Studio editor content.

    Body: ``project`` (required workspace id), ``path`` (project-relative,
    default ``docs/spec.md``), ``markdown`` (required), ``force`` (overwrite).
    The document is written to a temp file and validated FIRST; validation
    ERRORs abort without touching the target (same contract as ``spec gen``).
    """
    if method != "POST":
        return json_error("Use POST to save a spec", 405)

    project = (body.get("project") or "").strip()
    raw = (body.get("path") or "").strip() or "docs/spec.md"
    markdown = body.get("markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        return json_error("'markdown' is required")
    if len(markdown.encode("utf-8")) > _SPEC_MAX_BYTES:
        return json_error("markdown too large (max 2MB)", 413)

    proj_dir, err = _resolve_project_dir(project)
    if err:
        return err

    resolved = _resolve_in_project(proj_dir, raw)
    if resolved is None:
        return json_error("Output path must be within the project directory", 403)
    if resolved.exists() and not body.get("force", False):
        return json_error(
            f"{raw} already exists — set force=true to overwrite", 409)

    from yuleosh.spec.validate import parse_spec, validate_spec

    resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp = resolved.with_name(f".{resolved.name}.studio-tmp")
    try:
        tmp.write_text(markdown, encoding="utf-8")
        doc = parse_spec(str(tmp))
        issues = validate_spec(doc)
        # The validator is lenient about empty docs (0 requirements → no
        # issues) — a "spec" with nothing to verify is useless to the
        # pipeline, so reject it explicitly (same bar as spec gen).
        if not doc.requirements:
            issues = issues + [{
                "severity": "ERROR",
                "message": "No requirements found — add at least one "
                           "'### REQ-xxx: <name>' section with SHALL statements",
            }]
        if not doc.scenarios:
            issues = issues + [{
                "severity": "ERROR",
                "message": "No scenarios found — add at least one "
                           "'#### Scenario: <name>' with GIVEN/WHEN/THEN",
            }]
        error_count = sum(1 for i in issues if i.get("severity") == "ERROR")
        if error_count > 0:
            return json_error(
                {"error": f"Spec validation failed ({error_count} error(s))",
                 "issues": issues}, 400)
        os.replace(tmp, resolved)
    finally:
        tmp.unlink(missing_ok=True)

    stats = {
        "requirements": len(doc.requirements),
        "scenarios": len(doc.scenarios),
        "total_shall": sum(len(r.shall) for r in doc.requirements),
    }
    return json_ok({
        "spec_path": str(resolved),
        "stats": stats,
        "issues": issues,
        "error_count": error_count,
    })


def _validate(method: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/spec/validate — validate an OpenSpec file."""
    if method != "POST":
        return json_error("Use POST to validate", 405)

    spec_path = body.get("path", "")
    if not spec_path:
        return json_error("'path' is required")

    from . import OSH_HOME
    project_root = Path(OSH_HOME).resolve()
    if Path(spec_path).is_absolute():
        resolved = Path(spec_path).resolve()
    else:
        resolved = (project_root / spec_path.lstrip("/")).resolve()

    # SECURITY: path traversal guard
    try:
        resolved.relative_to(project_root)
    except ValueError:
        return json_error("Spec path must be within project directory", 403)

    if not resolved.exists():
        return json_error(f"Spec file not found: {resolved}")

    # Import and run validation
    from yuleosh.spec.validate import parse_spec, validate_spec, _compute_coverage

    doc = parse_spec(str(resolved))
    issues = validate_spec(doc)
    coverage = _compute_coverage(doc)

    result = {
        "file": str(resolved),
        "requirements": len(doc.requirements),
        "scenarios": len(doc.scenarios),
        "total_shall": sum(len(r.shall) for r in doc.requirements),
        "issues": issues,
        "issue_count": len(issues),
        "error_count": sum(1 for i in issues if i["severity"] == "ERROR"),
        "coverage": coverage,
    }
    return json_ok(result)


def _diff(method: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/spec/diff — diff two OpenSpec files."""
    if method != "POST":
        return json_error("Use POST to diff", 405)

    old_path = body.get("old", "")
    new_path = body.get("new", "")

    if not old_path or not new_path:
        return json_error("'old' and 'new' paths are required")

    from yuleosh.spec.validate import diff_specs

    resolved_old = Path(old_path)
    resolved_new = Path(new_path)
    if not resolved_old.is_absolute():
        from . import OSH_HOME
        resolved_old = Path(OSH_HOME) / resolved_old
    if not resolved_new.is_absolute():
        from . import OSH_HOME
        resolved_new = Path(OSH_HOME) / resolved_new

    if not resolved_old.exists():
        return json_error(f"Old spec not found: {resolved_old}")
    if not resolved_new.exists():
        return json_error(f"New spec not found: {resolved_new}")

    delta = diff_specs(str(resolved_old), str(resolved_new))
    return json_ok(delta)


def _gen(method: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/spec/gen — natural language → OpenSpec document.

    Body: ``prompt`` (required), ``output`` (optional project-relative path;
    omit to return the markdown without writing), ``mock`` (bool),
    ``prefix`` (default REQ), ``title``, ``force`` (overwrite).
    """
    if method != "POST":
        return json_error("Use POST to generate a spec", 405)

    prompt = (body or {}).get("prompt", "").strip()
    if not prompt:
        return json_error("'prompt' is required")

    from yuleosh.spec.gen import generate_spec

    try:
        result = generate_spec(
            prompt,
            prefix=(body.get("prefix") or "REQ"),
            title=body.get("title") or None,
            mock=bool(body.get("mock", False)),
        )
    except ValueError as e:
        return json_error(str(e))
    except Exception as e:
        return json_error(f"Spec generation failed: {e}", 500)

    spec_path = None
    output = (body.get("output") or "").strip()
    if output:
        project = (body.get("project") or "").strip()
        if project:
            # 工作区模式：输出落在所选工程的目录内（docs/...）
            proj_dir, err = _resolve_project_dir(project)
            if err:
                return err
            resolved = _resolve_in_project(proj_dir, output)
            if resolved is None:
                return json_error("Output path must be within the project directory", 403)
        else:
            from . import OSH_HOME
            project_root = Path(OSH_HOME).resolve()
            if Path(output).is_absolute():
                resolved = Path(output).resolve()
            else:
                resolved = (project_root / output.lstrip("/")).resolve()
            # SECURITY: path traversal guard (same rule as spec/validate)
            try:
                resolved.relative_to(project_root)
            except ValueError:
                return json_error("Output path must be within project directory", 403)
        if resolved.exists() and not body.get("force", False):
            return json_error(
                f"{output} already exists — set force=true to overwrite", 409)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(result["markdown"], encoding="utf-8")
        spec_path = str(resolved)

    return json_ok({
        "markdown": result["markdown"],
        "spec_path": spec_path,
        "stats": result["stats"],
        "issues": result["issues"],
        "error_count": result["error_count"],
        "repairs": result["repairs"],
        "mock": result["mock"],
        "model": result["model"],
    })

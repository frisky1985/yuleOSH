
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
    elif path_tail == "generate":
        return _generate(method, body)
    elif path_tail == "save":
        return _save(method, body)
    return json_error(f"Unknown spec resource: {path_tail}", 404)


def _resolve_project_dir(raw: str) -> tuple[Path | None, str | None]:
    """把 project_dir 解析到 OSH_HOME 之内；越界返回 (None, error)。"""
    from . import OSH_HOME
    root = Path(OSH_HOME).resolve()
    if not raw:
        return None, "'project_dir' is required"
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (ValueError, OSError):
        return None, "project_dir must be within OSH_HOME"
    return resolved, None


def _generate(method: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/spec/generate — 自然语言/提示词 → OpenSpec 草稿。

    Body: {input_text, project_dir, mode?, auto?, mock?}
      - ``auto=False``（默认）永远写草稿并返回内容，供前端编辑；
      - ``auto=True`` 仅当自校验零错误且解析出需求时才落正式 spec；
      - ``mock=True`` 或缺 LLM_API_KEY 时使用 demo mock 客户端。
    """
    if method != "POST":
        return json_error("Use POST to generate", 405)

    input_text = (body.get("input_text") or body.get("prompt") or "").strip()
    if not input_text:
        return json_error("'input_text' is required")

    mode = body.get("mode") or "extract"
    if mode not in ("extract", "decompose"):
        return json_error("mode must be 'extract' or 'decompose'")

    project_dir, err = _resolve_project_dir(body.get("project_dir") or "")
    if err:
        return json_error(err, 400)
    if not project_dir.is_dir():
        # 仅当调用方显式声明时才创建（demo / 新建项目场景），避免 typo 静默落盘。
        if not body.get("create_if_missing"):
            return json_error(f"project_dir is not a directory: {project_dir}", 400)
        try:
            (project_dir / "docs").mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return json_error(f"Cannot create project_dir: {e}", 500)

    output_path = project_dir / "docs" / "spec.md"
    raw_output = (body.get("output_path") or "").strip()
    if raw_output:
        candidate = Path(raw_output)
        if not candidate.is_absolute():
            candidate = project_dir / candidate
        try:
            candidate.resolve().relative_to(project_dir.resolve())
        except (ValueError, OSError):
            return json_error("output_path must be within project_dir", 403)
        output_path = candidate

    # LLM 选择：显式 mock 或无 key 时降级到 demo mock，保证链路可跑通。
    llm_client = None
    used_mock = False
    if body.get("mock") or not os.environ.get("LLM_API_KEY"):
        from yuleosh.spec.mock_llm import make_mock_llm
        llm_client = make_mock_llm(mode=mode, input_text=input_text)
        used_mock = True

    from yuleosh.spec.generator import SpecGenerationError, generate_spec

    try:
        result = generate_spec(
            input_text,
            project_dir,
            output_path,
            mode=mode,
            auto=bool(body.get("auto")),
            llm_client=llm_client,
        )
    except SpecGenerationError as e:
        return json_error(f"Spec generation failed: {e}", 502)
    except ValueError as e:
        return json_error(str(e), 400)

    written_path = Path(result["output_path"])
    try:
        content = written_path.read_text(encoding="utf-8")
    except OSError as e:
        return json_error(f"Cannot read generated spec: {e}", 500)

    # 补全计数：generate_spec 的 validation 只含 requirement_count，
    # 前端需要同时展示场景数，这里直接解析一次落盘文件。
    req_count = result["validation"].get("requirement_count", 0)
    scn_count = 0
    try:
        from yuleosh.spec.validate import parse_spec
        doc = parse_spec(str(written_path))
        req_count = len(doc.requirements)
        scn_count = len(doc.scenarios)
    except Exception:  # noqa: BLE001 — 解析失败不影响生成结果返回
        pass

    return json_ok({
        "content": content,
        "output_path": str(written_path),
        "formal_path": str(output_path),
        "written": result["written"],
        "mode": result["mode"],
        "requirements": req_count,
        "scenarios": scn_count,
        "validation": result["validation"],
        "used_mock": used_mock,
    })


def _save(method: str, body: dict) -> tuple[dict, int]:
    """POST /api/v1/spec/save — 保存前端编辑后的 spec 内容。

    Body: {project_dir, content, target?: "spec"|"draft"}
    保存前重新解析并返回校验结果，避免把不可解析的内容写成正式 spec。
    """
    if method != "POST":
        return json_error("Use POST to save", 405)

    content = body.get("content")
    if not content or not str(content).strip():
        return json_error("'content' is required")

    target = body.get("target") or "spec"
    if target not in ("spec", "draft"):
        return json_error("target must be 'spec' or 'draft'")

    project_dir, err = _resolve_project_dir(body.get("project_dir") or "")
    if err:
        return json_error(err, 400)

    docs = project_dir / "docs"
    path = docs / ("spec.md" if target == "spec" else "spec.draft.md")

    try:
        docs.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as e:
        return json_error(f"Cannot write {path}: {e}", 500)

    from yuleosh.spec.validate import parse_spec, validate_spec, _compute_coverage

    try:
        doc = parse_spec(str(path))
        issues = validate_spec(doc)
        coverage = _compute_coverage(doc)
    except Exception as e:  # noqa: BLE001 — 解析异常按校验失败上报
        return json_ok({
            "path": str(path),
            "target": target,
            "requirements": 0,
            "scenarios": 0,
            "issues": [{"severity": "ERROR", "message": f"parse failed: {e}"}],
            "error_count": 1,
            "coverage": {},
        })

    return json_ok({
        "path": str(path),
        "target": target,
        "requirements": len(doc.requirements),
        "scenarios": len(doc.scenarios),
        "issues": issues,
        "error_count": sum(1 for i in issues if str(i.get("severity", "")).upper() == "ERROR"),
        "coverage": coverage,
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

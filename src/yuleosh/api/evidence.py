
# @req RS-006  @req RS-005
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Evidence endpoints — generate, list files, download compliance pack."""

import os
import shutil
import sys
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from . import json_ok, json_error
from ._errors import internal_error
from .middleware import require_auth
from yuleosh.api.cors import get_cors_origin


def _qp(query: dict, key: str, default: str = "") -> str:
    """Get a query parameter value (list-safe, like logs._qp)."""
    val = query.get(key)
    if isinstance(val, list):
        return val[0] if val else default
    return str(val) if val is not None else default


def _ev_home() -> str:
    """Effective ``OSH_HOME`` for evidence paths — resolved **at call time**.

    此前这里写 ``from . import OSH_HOME``，取的是 import 期快照：测试用
    ``monkeypatch.setenv("OSH_HOME", tmp)`` 隔离时，包仍然落进仓库的
    ``.osh/evidence/``（删除后还会再生）。改走 ``resolve_osh_home``，两类
    隔离手法（env / 模块常量）都能真正生效。详见
    ``yuleosh.api.resolve_osh_home`` 的说明。
    """
    from . import OSH_HOME, resolve_osh_home

    return resolve_osh_home(OSH_HOME)


@require_auth
def handle_evidence(method: str, path_tail: str, body: dict, query: dict, handler=None, **kwargs):
    """Route to evidence sub-resources."""
    if path_tail == "generate" and method == "POST":
        return _generate_evidence(body)
    elif path_tail == "stage" and method == "POST":
        return _run_stage(body)
    elif path_tail == "resume" and method == "POST":
        return _resume_stage(body)
    elif path_tail == "reset" and method == "POST":
        return _reset_state(body)
    elif path_tail == "status" and method == "GET":
        return _get_status()
    elif path_tail == "files" and method == "GET":
        return _list_evidence_files()
    elif path_tail == "history" and method == "GET":
        return _list_evidence_history()
    elif path_tail == "pack" and method == "GET":
        return _download_pack(handler, query)
    elif path_tail == "file" and method == "GET":
        return _download_file(handler, query)
    return json_error(f"Unknown evidence resource: {path_tail}", 404)


# ---------- P1 渐进执行 API ----------

def _validate_project_dir(raw_dir: str, home: str) -> tuple[str | None, tuple[dict, int] | None]:
    """复用 SEC-C1 安全校验。返回 (project_dir_or_None, error_response_or_None)。"""
    try:
        project_dir = str(Path(raw_dir).expanduser().resolve())
        Path(project_dir).relative_to(Path(home).resolve())
        return project_dir, None
    except (ValueError, TypeError, OSError):
        return None, json_error("project_dir must be inside OSH_HOME", 403)


def _run_stage(body: dict) -> tuple[dict, int]:
    """POST /api/v1/evidence/stage — 渐进执行：跑指定 stage。

    body:
        stage: wait_pipeline | collect | reports | pack  (必选)
        project_dir: str (可选，默认 OSH_HOME)
        spec_path: str (可选)
        formats: list[str] (可选)
    """
    home = _ev_home()
    raw_dir = body.get("project_dir") or home
    project_dir, err = _validate_project_dir(raw_dir, home)
    if err:
        return err

    stage = body.get("stage")
    if stage not in ("wait_pipeline", "collect", "reports", "pack"):
        return json_error(f"invalid stage: {stage}; choose from wait_pipeline/collect/reports/pack", 400)

    spec_path = body.get("spec_path")
    formats = body.get("formats")

    try:
        from yuleosh.evidence.pack import run_incremental_stage
        state = run_incremental_stage(
            project_dir,
            target_stage=stage,
            spec_path=spec_path,
            formats=formats,
        )
    except ValueError as exc:
        return json_error(str(exc), 400)
    except Exception as exc:  # noqa: BLE001
        return internal_error("evidence-stage", exc)

    return json_ok(state)


def _resume_stage(body: dict) -> tuple[dict, int]:
    """POST /api/v1/evidence/resume — 等待确认后推进到下一 stage。

    body:
        confirm: bool  (True=确认推进；False=仅查看当前状态，不推进)
        project_dir: str (可选)
    """
    home = _ev_home()
    raw_dir = body.get("project_dir") or home
    project_dir, err = _validate_project_dir(raw_dir, home)
    if err:
        return err

    confirm = bool(body.get("confirm", False))

    try:
        from yuleosh.evidence.pack import run_incremental_stage
        state = run_incremental_stage(project_dir, confirm=confirm)
    except Exception as exc:  # noqa: BLE001
        return internal_error("evidence-resume", exc)

    return json_ok(state)


def _reset_state(body: dict) -> tuple[dict, int]:
    """POST /api/v1/evidence/reset — 放弃当前渐进 session，从头开始。"""
    home = _ev_home()
    raw_dir = body.get("project_dir") or home
    project_dir, err = _validate_project_dir(raw_dir, home)
    if err:
        return err

    try:
        from yuleosh.evidence.pack import reset_incremental_state
        state = reset_incremental_state(project_dir)
    except Exception as exc:  # noqa: BLE001
        return internal_error("evidence-reset", exc)

    return json_ok(state)


def _get_status() -> tuple[dict, int]:
    """GET /api/v1/evidence/status — 读取当前渐进执行状态（前端 poll）。"""
    home = _ev_home()
    try:
        from yuleosh.evidence.pack import get_incremental_status
        state = get_incremental_status(home)
    except Exception as exc:  # noqa: BLE001
        return internal_error("evidence-status", exc)
    return json_ok(state)


def _snapshot_pack() -> str | None:
    """Copy the freshly generated compliance-pack.zip to a timestamped version
    snapshot so each generation is retrievable later (evidence history).

    Returns the versioned file name, or None if no pack exists yet.
    """
    ev_dir = Path(_ev_home()) / ".osh" / "evidence"
    src = ev_dir / "compliance-pack.zip"
    if not src.exists():
        return None
    ev_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    version = f"compliance-pack-{ts}.zip"
    dst = ev_dir / version
    n = 1
    while dst.exists():
        version = f"compliance-pack-{ts}-{n}.zip"
        dst = ev_dir / version
        n += 1
    shutil.copy2(src, dst)
    return version


def snapshot_bundle(bundle_dir: str, osh_home: str | None = None) -> str | None:
    """Zip an evidence *bundle directory* (e.g. `.yuleosh/evidence-bundle`)
    into a versioned `.osh/evidence/compliance-pack-<ts>.zip` and overwrite the
    latest `compliance-pack.zip`.  Returns the versioned name, or None when the
    bundle dir is missing.

    Used by the dashboard generate flow so its real generations also land in
    the evidence history list (the dashboard produces a bundle dir + manifest,
    whereas the evidence-page path produces compliance-pack.zip directly).

    ``osh_home`` lets the caller pin the destination root.  The dashboard
    **must** pass its own (``dashboard.OSH_HOME``) because the bundle dir is
    derived from the same value: previously the write target came from
    ``api.OSH_HOME`` while the bundle came from ``dashboard.OSH_HOME``, and the
    two snapshots diverging is exactly how generated packs escaped into the
    repository's ``.osh/evidence/`` during tests (2026-09-23).
    """
    src = Path(bundle_dir)
    if not src.exists() or not src.is_dir():
        return None
    ev_dir = Path(osh_home or _ev_home()) / ".osh" / "evidence"
    ev_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    version = f"compliance-pack-{ts}.zip"
    dst = ev_dir / version
    n = 1
    while dst.exists():
        version = f"compliance-pack-{ts}-{n}.zip"
        dst = ev_dir / version
        n += 1
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(src))
    shutil.copy2(dst, ev_dir / "compliance-pack.zip")
    return version


def _generate_evidence(body: dict) -> tuple[dict, int]:
    """POST /api/v1/evidence/generate — run evidence generation.

    P1 渐进执行改造 (2026-10-18): 默认 incremental=True（一次性跑完所有 stage，
    但状态落盘到 .state.json），支持 pause/resume。设 incremental=False 则走
    原有 subprocess.run 一键模式（向后兼容，用于需要独立进程隔离的场景）。

    SECURITY (SEC-C1): project_dir must resolve inside OSH_HOME — same
    guard as the pipeline trigger.  Otherwise an authenticated user could
    run the pack script with an arbitrary cwd (e.g. /etc) and probe/write
    anywhere on the server.
    """
    home = _ev_home()
    raw_dir = body.get("project_dir") or home
    try:
        project_dir = str(Path(raw_dir).expanduser().resolve())
        Path(project_dir).relative_to(Path(home).resolve())
    except (ValueError, TypeError, OSError):
        return json_error("project_dir must be inside OSH_HOME", 403)

    # 人类可读格式选择（md/html/xlsx/pdf）。非法值直接 400，不静默降级，
    # 避免用户以为拿到了 PDF 实际只有 Markdown。
    from yuleosh.evidence.exporters import parse_formats
    try:
        formats = parse_formats(body.get("formats"))
    except ValueError as exc:
        return json_error(str(exc), 400)

    incremental = body.get("incremental", False)

    if incremental:
        # P1 渐进模式：进程内调用 run_incremental_stage，一次性跑到 done
        try:
            from yuleosh.evidence.pack import run_incremental_stage
            state = run_incremental_stage(
                project_dir,
                target_stage="done",
                spec_path=body.get("spec_path"),
                formats=formats,
            )
            version = None
            if state.get("status") == "done":
                version = _snapshot_pack()
            return json_ok({
                "status": "completed" if state.get("status") == "done" else "failed",
                "project_dir": project_dir,
                "version": version,
                "formats": formats,
                "incremental": True,
                "state": state,
                "artifacts_count": len(state.get("artifacts_so_far", [])),
            })
        except Exception as exc:  # noqa: BLE001
            return internal_error("evidence-incremental", exc)

    # ---------- 原有 subprocess.run 模式（向后兼容）----------
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yuleosh.evidence.pack", "pack",
             "--formats", ",".join(formats)],
            # 全格式（含 PDF）时大矩阵渲染耗时实测 ~2min（acceptance 60s +
            # traceability 33s），120s 会中途杀掉子进程；放宽到 300s。
            capture_output=True, text=True, timeout=300,
            cwd=project_dir, check=False,
            env={**os.environ, "OSH_HOME": project_dir},
        )
        version = None
        if result.returncode == 0:
            version = _snapshot_pack()
        return json_ok({
            "status": "completed" if result.returncode == 0 else "failed",
            "project_dir": project_dir,
            "returncode": result.returncode,
            "version": version,
            "formats": formats,
            "incremental": False,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:500],
        })
    except subprocess.TimeoutExpired:
        return json_error("Evidence generation timed out", 504)
    except (OSError, subprocess.CalledProcessError) as e:
        # SEC-C2: never echo internal exception details to the client.
        return internal_error("evidence", e)


# 给用户在 UI 上展示的证据文件格式 —— 人可读产物。
# 机器真源（.json/.yaml/.xml）不暴露在列表里，但仍可通过
# /api/v1/evidence/file?name=<bare> 直接下载（供链校验/自动化脚本）。
_EVIDENCE_HUMAN_SUFFIXES = frozenset({
    ".md", ".html", ".htm", ".pdf", ".xlsx", ".xls", ".csv", ".txt",
})
# compliance-pack.zip 单独放行（审计时需要下载整包，不是机器真源）。
_EVIDENCE_HUMAN_ALLOWLIST = frozenset({"compliance-pack.zip"})


def _is_human_evidence_file(f: Path) -> bool:
    """True when *f* is a human-readable evidence artifact that should
    appear in the UI file list."""
    if f.name in _EVIDENCE_HUMAN_ALLOWLIST:
        return True
    return f.suffix.lower() in _EVIDENCE_HUMAN_SUFFIXES


def _list_evidence_files() -> tuple[dict, int]:
    """GET /api/v1/evidence/files — list generated evidence files.

    Only human-readable artifacts (md/html/pdf/xlsx/csv/txt and the
    compliance-pack.zip bundle) are returned.  Machine-authoritative
    formats (.json/.yaml/.xml — traceability-matrix.json, chain.json,
    manifest.json, etc.) are intentionally hidden from the UI list but
    still downloadable via ``/api/v1/evidence/file?name=<bare>`` so that
    the evidence chain verifier and audit automation can fetch them.
    """
    ev_dir = Path(_ev_home()) / ".osh" / "evidence"
    files = []
    if ev_dir.exists():
        for f in sorted(ev_dir.iterdir()):
            if f.is_file() and _is_human_evidence_file(f):
                files.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "mtime": f.stat().st_mtime,
                    "type": f.suffix.lstrip("."),
                })

    return json_ok({"files": files, "count": len(files)})


def _list_evidence_history() -> tuple[dict, int]:
    """GET /api/v1/evidence/history — list versioned evidence pack snapshots.

    Each generation snapshots compliance-pack.zip to compliance-pack-<ts>.zip,
    so this returns a chronological (newest-first) list of downloadable versions.
    """
    ev_dir = Path(_ev_home()) / ".osh" / "evidence"
    versions = []
    if ev_dir.exists():
        # Sort by mtime (newest first) — not by name, because same-second
        # collisions get a "-1" suffix that sorts before the plain name
        # lexicographically and would invert the intended order.
        for f in sorted(
            ev_dir.glob("compliance-pack-*.zip"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            versions.append({
                "name": f.name,
                "size": f.stat().st_size,
                "mtime": f.stat().st_mtime,
                "type": "zip",
            })
    latest = ev_dir / "compliance-pack.zip"
    return json_ok({
        "versions": versions,
        "count": len(versions),
        "has_latest": latest.exists(),
    })


def _build_pack_variant(zip_path: Path, ev_dir: Path, extra: list[str]) -> Path:
    """Return a ZIP that additionally carries on-demand converted formats.

    基线证据包只含 md + 机器真源；这里把 md 从**该 ZIP 内部**取出转换
    （历史快照内容可能与当前文件不同，不能直接读 .osh/evidence/*.md），
    再把产物追加进去，并同步更新 manifest.json，保证证据链可校验。
    结果按源包 mtime/size + 格式组合缓存。
    """
    import hashlib
    import json
    import tempfile

    from yuleosh.evidence.exporters import convert_markdown

    stat = zip_path.stat()
    key = hashlib.sha256(
        f"{zip_path.name}:{stat.st_mtime_ns}:{stat.st_size}:{','.join(extra)}".encode()
    ).hexdigest()[:12]
    cache_dir = ev_dir / ".exports"
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"pack-{key}.zip"
    if out.is_file() and out.stat().st_size > 0:
        return out

    tmp_out = cache_dir / f"pack-{key}.zip.tmp"
    with tempfile.TemporaryDirectory(prefix="osh-pack-") as tmp:
        tmp_dir = Path(tmp)
        with zipfile.ZipFile(zip_path) as src:
            md_names = [
                n for n in src.namelist()
                if n.lower().endswith(".md") and "/" not in n
            ]
            src.extractall(tmp_dir, members=md_names)

            manifest = {}
            if "manifest.json" in src.namelist():
                try:
                    manifest = json.loads(src.read("manifest.json"))
                except (ValueError, KeyError):
                    manifest = {}

            derived: list[dict] = []
            with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as dst:
                for item in src.infolist():
                    if item.filename == "manifest.json":
                        continue
                    dst.writestr(item, src.read(item.filename))
                for md_name in md_names:
                    for fmt in extra:
                        product = convert_markdown(
                            tmp_dir / md_name, fmt, cache_root=cache_dir
                        )
                        arcname = f"{Path(md_name).stem}.{fmt}"
                        dst.write(product, arcname=arcname)
                        data = product.read_bytes()
                        derived.append({
                            "path": arcname,
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "size_bytes": len(data),
                            "mtime_iso": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                        })

                if manifest:
                    manifest["files"] = list(manifest.get("files", [])) + derived
                    manifest["total_files"] = len(manifest["files"])
                    manifest["derived_formats"] = sorted(extra)
                    manifest["derived_generated_at"] = datetime.now().strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    )
                    dst.writestr(
                        "manifest.json",
                        json.dumps(manifest, indent=2, ensure_ascii=False),
                    )
    tmp_out.replace(out)
    return out


def _download_pack(handler, query: dict | None = None) -> tuple[dict, int]:
    """GET /api/v1/evidence/pack — download compliance ZIP pack.

    With ?version=<name> downloads a specific history snapshot; otherwise the
    latest compliance-pack.zip.  version must be a bare filename (path-traversal
    guarded) and resolve inside the evidence dir.
    """
    ev_dir = Path(_ev_home()) / ".osh" / "evidence"
    version = _qp(query or {}, "version").strip() if query else ""

    # Only treat ?version= as a real snapshot when it looks like one
    # (compliance-pack-<ts>.zip, bare name).  Unknown/legacy params such as
    # the dashboard's ?task_id= fall back to the latest pack, not a 400.
    is_snapshot = bool(version) and version.startswith("compliance-pack-") and version.endswith(".zip") and "/" not in version and "\\" not in version and version not in (".", "..")

    if is_snapshot:
        zip_path = ev_dir / version
        if not zip_path.exists():
            return json_error("Evidence version not found", 404)
    elif version:
        # Explicit ?version= that is not a real snapshot name (e.g. a
        # traversal attempt) — reject rather than silently serving latest.
        return json_error("Invalid version name", 400)
    else:
        zip_path = ev_dir / "compliance-pack.zip"
        if not zip_path.exists():
            return json_error("Compliance pack not found. Run evidence generation first.", 404)

    # ?formats=html,xlsx,pdf —— 下载时按需把 md 转成所选格式再打进包，
    # 生成阶段不再预产全部格式。基线包本身（md + 机器真源）保持不变。
    formats_raw = (_qp(query or {}, "formats") or "").strip()
    if formats_raw:
        from yuleosh.evidence.exporters import ExportUnavailable, parse_formats

        try:
            extra = [f for f in parse_formats(formats_raw) if f != "md"]
        except ValueError as exc:
            return json_error(str(exc), 400)
        if extra:
            try:
                zip_path = _build_pack_variant(Path(zip_path), ev_dir, extra)
            except ExportUnavailable as exc:
                return json_error(str(exc), 503)
            except Exception as e:  # noqa: BLE001 - 不向客户端回显内部细节
                return internal_error("evidence-pack-export", e)

    if handler is not None:
        data = zip_path.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/zip")
        handler.send_header(
            "Content-Disposition",
            'attachment; filename="compliance-pack.zip"',
        )
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Access-Control-Allow-Origin", get_cors_origin(handler.headers.get("Origin")))
        handler.end_headers()
        handler.wfile.write(data)
        # Signal that the response was already sent
        return None

    return json_ok({
        "path": str(zip_path),
        "size": zip_path.stat().st_size,
        "status": "ready",
    })


# Single-file download: map extension → Content-Type so the browser opens
# text artifacts inline-friendly and still downloads binaries correctly.
_FILE_CONTENT_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _download_file(handler, query: dict | None = None) -> tuple[dict, int] | None:
    """GET /api/v1/evidence/file?name=<bare_name> — download one evidence file.

    Lets an auditor grab a single artifact (e.g. traceability-matrix.md,
    review-log.json) without downloading and unzipping the whole pack.

    SECURITY: `name` must be a bare file name (no path separators, no
    dot-segments, no quote/newline/NUL to keep Content-Disposition well-formed),
    and the resolved path must stay inside .osh/evidence (also blocks symlink
    escapes).  Missing file → 404, bad name → 400.
    """
    ev_dir = Path(_ev_home()).resolve() / ".osh" / "evidence"
    name = (_qp(query or {}, "name") or "").strip()

    if (
        not name
        or name in (".", "..")
        or "/" in name
        or "\\" in name
        or name.startswith(".")
        or any(c in name for c in ('"', "\n", "\r", "\x00"))
    ):
        return json_error("Invalid file name", 400)

    try:
        target = (ev_dir / name).resolve()
        target.relative_to(ev_dir)
    except (ValueError, OSError):
        return json_error("Invalid file name", 400)

    if not target.is_file():
        return json_error("Evidence file not found", 404)

    # ?format=html|xlsx|pdf —— 按需转换（真源仍是 md，不预生成全部格式）。
    # 结果缓存在 .osh/evidence/.exports/，不进 UI 列表与合规包。
    fmt = (_qp(query or {}, "format") or "").strip().lower()
    download_name = name
    if fmt and fmt != "md":
        from yuleosh.evidence.exporters import (
            ExportUnavailable,
            SUPPORTED_FORMATS,
            convert_markdown,
        )

        if fmt not in SUPPORTED_FORMATS:
            return json_error(
                f"unsupported format: {fmt}; choose from {', '.join(SUPPORTED_FORMATS)}",
                400,
            )
        if target.suffix.lower() != ".md":
            return json_error("Only Markdown evidence can be converted", 400)
        try:
            target = convert_markdown(target, fmt)
            download_name = f"{Path(name).stem}.{fmt}"
        except ExportUnavailable as exc:
            return json_error(str(exc), 503)
        except Exception as e:  # noqa: BLE001 - 不向客户端回显内部细节
            return internal_error("evidence-export", e)

    ctype = _FILE_CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
    # inline=1 供 UI 内嵌预览（浏览器 PDF 阅读器）；缺省仍 attachment 触发下载。
    disposition = "inline" if _qp(query or {}, "inline") in ("1", "true", "yes") else "attachment"

    if handler is not None:
        data = target.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", ctype)
        handler.send_header("Content-Disposition", f'{disposition}; filename="{download_name}"')
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Access-Control-Allow-Origin", get_cors_origin(handler.headers.get("Origin")))
        handler.end_headers()
        handler.wfile.write(data)
        # Signal that the response was already sent
        return None

    return json_ok({
        "path": str(target),
        "name": download_name,
        "size": target.stat().st_size,
        "content_type": ctype,
        "status": "ready",
    })

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Test Log Management API — 测试日志检索（设计文档模块⑦，轻量实现）。

数据真实优先：直接扫描 ``OSH_HOME/.osh/sessions/<run_id>/`` 下的 ``*.log``
（pipeline.log / 串口日志 / step 输出）与 ``session.json``（run 元数据）。
关键词用简单子串匹配（不引入 FTS5，保持轻量）；无数据返回空列表 + note，
绝不 mock。

Mounted at /api/v1/logs in the main server router.

Endpoints:
    GET /api/v1/logs?project=&query=&device=&pipeline=&limit=50&since=&until=&level=
        — 跨 run 日志检索，返回 [{run_id, file, line, content, level, updated_at}]
        时间窗口 since/until 基于日志文件更新时间（文件 mtime，UTC），按 run/文件级过滤
    GET /api/v1/logs/pipeline?run=xxx
        — 某流水线 run 的全部 *.log 文件 + 内容前 200 行
    GET /api/v1/logs/summary?project=xxx[&since=YYYY-MM-DD]
        — 日志统计：每 run 的日志文件数 / 总行数 / ERROR 出现次数；默认近 7 天且硬上限 7 天
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import json_ok, json_error
from .middleware import require_auth

log = logging.getLogger("api.logs")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))

PREVIEW_LINES = 200
DEFAULT_LIMIT = 50
MAX_LIMIT = 500

# 级别启发式 token（按优先级匹配，ERROR 需在 WARN 之前等）
_LEVEL_TOKENS = ("ERROR", "FATAL", "WARN", "WARNING", "DEBUG", "TRACE", "INFO")


def _sessions_root() -> Path:
    """Session 根目录：OSH_HOME/.osh/sessions（OSH_HOME 支持测试 monkeypatch）。"""
    return Path(OSH_HOME) / ".osh" / "sessions"


def _qp(query: dict, key: str, default: str = "") -> str:
    """Get a query parameter value (list-safe, like dashboard._get_query_param)."""
    val = query.get(key)
    if isinstance(val, list):
        return val[0] if val else default
    return str(val) if val is not None else default


def _detect_level(line: str) -> str:
    """轻量级别识别：行内匹配 ERROR/FATAL/WARN/DEBUG/TRACE/INFO token。"""
    upper = line.upper()
    for token in _LEVEL_TOKENS:
        if token in upper:
            return "WARN" if token == "WARNING" else token
    return "INFO"


def _load_session_meta(run_dir: Path) -> dict:
    """读取 run 的 session.json 元数据（缺失/损坏时降级为目录名）。"""
    meta = {
        "run_id": run_dir.name,
        "project": None,
        "name": None,
        "status": None,
        "updated_at": None,
    }
    sj = run_dir / "session.json"
    if not sj.exists():
        return meta
    try:
        data = json.loads(sj.read_text(encoding="utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError) as e:
        log.debug("failed to parse %s: %s", sj, e)
        return meta
    meta["run_id"] = data.get("run_id") or run_dir.name
    meta["name"] = data.get("name")
    meta["project"] = data.get("project") or data.get("name")
    meta["status"] = data.get("status")
    meta["updated_at"] = data.get("updated_at")
    return meta


def _file_updated_at(fp: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(fp.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _meta_haystack(meta: dict) -> str:
    """把 run 元数据拼成小写 haystack，供 project/pipeline 子串过滤。"""
    return " ".join(str(v or "") for v in meta.values()).lower()


def _to_dt(s: Optional[str]) -> Optional[datetime]:
    """把 ISO/带时区字符串解析为 datetime（无时区按 UTC）。解析失败返回 None。"""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def _parse_window(s: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    """解析时间窗口参数（since/until）。

    支持 ``YYYY-MM-DD``（按 UTC 0 点 / 当日 23:59:59.999999）或
    ``YYYY-MM-DDTHH:MM``。返回 None 表示不过滤。
    """
    s = (s or "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        d = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end_of_day:
            d = d.replace(hour=23, minute=59, second=59, microsecond=999999)
        return d
    return _to_dt(s)


@require_auth
def handle_logs(method: str, path_tail: str, body: dict, query: dict,
                handler: Any = None, **kwargs) -> Optional[tuple[dict, int]]:
    """Handle /api/v1/logs... requests (module ⑦)."""
    parts = [p for p in (path_tail or "").split("/") if p]

    if not parts:
        if method == "GET":
            return _logs_search(query)
        return json_error(f"Method not allowed: {method} /api/v1/logs", 405)

    if parts[0] == "pipeline" and method == "GET":
        return _logs_pipeline(query)
    if parts[0] == "summary" and method == "GET":
        return _logs_summary(query)

    return json_error(f"Unknown logs sub-path or method: {method} {path_tail}", 404)


def _logs_search(query: dict) -> tuple[dict, int]:
    """GET /api/v1/logs — 跨 run 日志检索（子串匹配，轻量实现）。

    过滤参数（均可选，子串匹配）：
      project  — 匹配 session.json 的 project/name/run_id
      query    — 关键词，匹配日志行内容
      device   — 匹配日志行内容或文件路径（串口日志常含设备 id）
      pipeline — 匹配 run 元数据（run_id/name/project）
      limit    — 结果上限（默认 50，上限 500）
      since/until — 时间窗口（YYYY-MM-DD 或 YYYY-MM-DDTHH:MM），基于日志文件更新时间
      level    — 按级别过滤（ERROR/FATAL/WARN/INFO/DEBUG/TRACE）
    注：时间窗口按 run/文件级过滤（updated_at 取文件 mtime，非日志内容时间戳）。
    """
    project = _qp(query, "project")
    keyword = _qp(query, "query") or _qp(query, "q")
    device = _qp(query, "device")
    pipeline = _qp(query, "pipeline")
    since = _parse_window(_qp(query, "since"))
    until = _parse_window(_qp(query, "until"), end_of_day=True)
    level = _qp(query, "level").upper()
    try:
        limit = min(int(_qp(query, "limit", str(DEFAULT_LIMIT)) or DEFAULT_LIMIT), MAX_LIMIT)
    except ValueError:
        limit = DEFAULT_LIMIT

    keyword_l = keyword.lower()
    device_l = device.lower()
    pipeline_l = pipeline.lower()
    project_l = project.lower()

    root = _sessions_root()
    if not root.is_dir():
        return json_ok({"logs": [], "count": 0,
                        "note": "no session logs found under .osh/sessions"})

    results: list[dict] = []
    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        meta = _load_session_meta(run_dir)
        hay_meta = _meta_haystack(meta)
        if project_l and project_l not in hay_meta:
            continue
        if pipeline_l and pipeline_l not in hay_meta:
            continue

        for fp in run_dir.rglob("*.log"):
            if not fp.is_file():
                continue
            try:
                lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as e:
                log.debug("skip unreadable log %s: %s", fp, e)
                continue
            updated_at = _file_updated_at(fp)
            ua = _to_dt(updated_at)
            if since and ua and ua < since:
                continue
            if until and ua and ua > until:
                continue
            rel = str(fp.relative_to(root))
            file_hay = f"{rel} {fp.name}".lower()
            for lineno, line in enumerate(lines, start=1):
                line_l = line.lower()
                if keyword_l and keyword_l not in line_l:
                    continue
                if device_l and device_l not in line_l and device_l not in file_hay:
                    continue
                if level and _detect_level(line) != level:
                    continue
                results.append({
                    "run_id": meta["run_id"],
                    "file": rel,
                    "line": lineno,
                    "content": line,
                    "level": _detect_level(line),
                    "updated_at": updated_at,
                })
                if len(results) >= limit:
                    return json_ok({"logs": results, "count": len(results), "note": None})

    note = None if results else (
        "no logs matched the filters (real data only, no mock)"
    )
    return json_ok({"logs": results, "count": len(results), "note": note})


def _logs_pipeline(query: dict) -> tuple[dict, int]:
    """GET /api/v1/logs/pipeline?run=xxx — 单个 run 的全部日志。

    列出该 run 下所有 ``*.log`` 文件，每文件返回内容前 200 行（preview）。
    """
    run = _qp(query, "run")
    if not run:
        return json_error("run parameter is required", 400)

    root = _sessions_root()
    run_dir = root / run
    if not run_dir.is_dir():
        return json_error(f"run not found: {run}", 404)

    meta = _load_session_meta(run_dir)
    files: list[dict] = []
    for fp in sorted(run_dir.rglob("*.log")):
        if not fp.is_file():
            continue
        try:
            lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            log.debug("skip unreadable log %s: %s", fp, e)
            continue
        preview = lines[:PREVIEW_LINES]
        files.append({
            "file": str(fp.relative_to(root)),
            "lines": len(lines),
            "preview_lines": len(preview),
            "truncated": len(lines) > PREVIEW_LINES,
            "content": "\n".join(preview),
            "updated_at": _file_updated_at(fp),
        })

    note = None if files else "no *.log files found for this run"
    return json_ok({
        "run_id": run,
        "project": meta.get("project"),
        "name": meta.get("name"),
        "status": meta.get("status"),
        "files": files,
        "count": len(files),
        "note": note,
    })


def _logs_summary(query: dict) -> tuple[dict, int]:
    """GET /api/v1/logs/summary?project=xxx[&since=YYYY-MM-DD] — 每 run 的日志统计。

    统计项：日志文件数、总行数、ERROR/FATAL 出现次数、最后更新时间。
    时间窗口：默认近 7 天，且硬上限 7 天（更旧的 run 不进入摘要，需用检索接口按时间查询）。
      since — 窗口起点（YYYY-MM-DD），若早于 7 天前则按 7 天前裁剪
      until — 窗口终点（默认不限制）
    """
    project = _qp(query, "project").lower()

    # 摘要硬上限 7 天：即便前端请求更早，也只保留近 7 天
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    req_since = _parse_window(_qp(query, "since"))
    if req_since and req_since > cutoff:
        cutoff = req_since
    until = _parse_window(_qp(query, "until"), end_of_day=True)

    root = _sessions_root()

    runs: list[dict] = []
    if root.is_dir():
        for run_dir in sorted(root.iterdir()):
            if not run_dir.is_dir():
                continue
            meta = _load_session_meta(run_dir)
            if project and project not in _meta_haystack(meta):
                continue

            log_files = 0
            total_lines = 0
            error_count = 0
            updated_at: Optional[str] = None
            for fp in run_dir.rglob("*.log"):
                if not fp.is_file():
                    continue
                log_files += 1
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except OSError as e:
                    log.debug("skip unreadable log %s: %s", fp, e)
                    continue
                total_lines += len(text.splitlines())
                upper = text.upper()
                error_count += upper.count("ERROR") + upper.count("FATAL")
                u = _file_updated_at(fp)
                if u and (updated_at is None or u > updated_at):
                    updated_at = u

            # 7 天窗口过滤（按 run 最新日志文件更新时间）
            latest_dt = _to_dt(updated_at)
            if latest_dt and latest_dt < cutoff:
                continue
            if until and latest_dt and latest_dt > until:
                continue

            runs.append({
                "run_id": meta["run_id"],
                "name": meta.get("name"),
                "project": meta.get("project"),
                "status": meta.get("status"),
                "log_files": log_files,
                "total_lines": total_lines,
                "error_count": error_count,
                "updated_at": updated_at,
            })

    note = None if runs else (
        "no session logs found" + (f" for project {project}" if project else "")
    )
    return json_ok({
        "runs": runs,
        "count": len(runs),
        "note": note,
        "window_days": 7,
        "applied_since": cutoff.isoformat(),
    })

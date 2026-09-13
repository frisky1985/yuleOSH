"""统一的 pipeline 会话发现与「按项目分组（最新优先）」索引。

背景
----
yuleOSH 有两条跑 LLM 的路径，会话都落在 ``<project_dir>/.osh/sessions/<id>/`` 下：

* **前端 UI 触发**：``POST /api/v1/pipeline/run`` → 编排器后台线程，
  ``OSH_HOME=project_dir``，session 写到 ``<project_dir>/.osh/sessions/<id>``
  （project_dir 是 OSH_HOME 的子目录）。
* **后台 / CLI 跑**：``yuleosh pipeline run``，session 写到
  ``$OSH_HOME/.osh/sessions/<id>`` 或 ``<project_dir>/.osh/sessions/<id>``。

但 ``GET /api/v1/pipeline/status`` 旧实现只扫 **顶层**
``OSH_HOME/.osh/sessions`` 一个目录，且没有任何「按项目聚合」逻辑，导致：

* UI 触发跑落在子目录，状态接口根本扫不到；
* CLI 后台跑与后端 OSH_HOME 不一致时，前端也看不到；
* 「某个项目的最新一次运行结果」无处聚合，看板只能靠 SSE 的
  ``stats_by_project`` 事件（CLI 跑不会发）。

本模块提供 **递归发现 + 按项目分组（最新优先）** 的单一真相源：只要两条
路径共享同一个 ``OSH_HOME``（标准部署），它们的会话都会被同一份索引聚合，
前端据此把「最新结果」关联到对应项目 —— 无论来自后台跑还是 UI 触发。

设计要点
--------
* 纯标准库（pathlib/json），无重依赖，可被 api 层与单测轻量 import。
* 递归只认 ``**/.osh/sessions/*/session.json`` 形态，depth 受 ``max_depth``
  限制，不会扫飞。
* 项目目录以 **session.json 磁盘路径** 反推（``<project_dir>/.osh/sessions/<id>``
  上溯 3 级）为准，最贴合「产物/源码归属哪个项目」的真相；若 session.json
  自带 ``project_dir`` 字段则以它为准。
* 同一 project_dir 下多份会话按 ``updated_at`` 取最新一份作为 ``latest``，
  ``active`` 标志 = 任一会话处于 running/queued 等活跃态。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# 视为「仍在跑」的状态（一旦出现，该项目在 UI 上亮起「后台运行中」）
_ACTIVE_STATUSES = {"running", "queued", "started", "in_progress", "pending"}

# 安全护栏：从 OSH_HOME 根到 session.json 的路径深度
#   root/.../.osh/sessions/<id>/session.json  →  .osh(1)+sessions(2)+<id>(3)+session.json(4)
#   + 允许 project 嵌套在 OSH_HOME 下最多 max_depth 层
_DEFAULT_MAX_DEPTH = 6


def _project_dir_from_session_json(session_json: Path) -> Path:
    """从 session.json 路径反推 project_dir。

    ``<project_dir>/.osh/sessions/<id>/session.json``
      parents: session.json → <id> → sessions → .osh → project_dir
    → 上溯 4 级。
    """
    return session_json.parent.parent.parent.parent


def _project_dir_of(data: dict, session_json: Path) -> str:
    """解析会话归属的 project_dir（优先 session 自带，否则按路径反推）。"""
    pd = data.get("project_dir")
    if pd:
        return str(Path(pd).resolve())
    sp = data.get("spec_path")
    if sp:
        try:
            # spec 通常位于 <project_dir>/docs/spec.md → 父父即 project_dir
            return str(Path(sp).resolve().parent.parent)
        except (OSError, ValueError):
            pass
    return str(_project_dir_from_session_json(session_json).resolve())


def discover_project_sessions(
    osh_home: str | Path,
    max_depth: int = _DEFAULT_MAX_DEPTH,
) -> dict[str, Any]:
    """递归发现 OSH_HOME 下的所有 pipeline 会话，并按项目分组。

    Returns::

        {
          "projects": [            # 按项目聚合，每个项目取最新会话
            {
              "project_dir":  <abs str>,
              "project_name": <basename str>,
              "spec_path":    <str|None>,
              "latest_run_id": <str>,
              "latest_status": <str|None>,
              "latest_name":   <str|None>,
              "latest_updated_at": <str|None>,
              "active":        <bool>,     # 任一会话处于活跃态
              "runs_count":    <int>,
              "statuses":      [<str>...],  # 该项目所有会话状态
              "latest":        {<full session dict>},
            }, ...
          ],
          "sessions": [ <full session dict>, ... ],   # 扁平、按 run_id 去重
        }
    """
    root = Path(osh_home).resolve()
    items: list[tuple[str, dict, str]] = []  # (project_dir, data, run_id)
    seen: set[str] = set()

    if root.exists():
        for sj in root.rglob(".osh/sessions/*/session.json"):
            rel = sj.relative_to(root)
            # depth 护栏：超过 OSH_HOME 下 max_depth 层的跳过
            if len(rel.parts) > max_depth + 4:
                continue
            # 避免重复 .osh（如 OSH_HOME/.osh/sessions/x/.osh/sessions/y）
            if rel.parts.count(".osh") > 1:
                continue
            try:
                data = json.loads(sj.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            run_id = data.get("run_id") or sj.parent.name
            if run_id in seen:
                continue
            seen.add(run_id)
            pd = _project_dir_of(data, sj)
            items.append((pd, data, run_id))

    # ── 按 project_dir 分组 ──
    grouped: dict[str, list[tuple[dict, str]]] = {}
    for pd, data, run_id in items:
        grouped.setdefault(pd, []).append((data, run_id))

    projects: list[dict] = []
    for pd_str, lst in grouped.items():
        # 最新优先（updated_at 降序；空值排最后）
        lst_sorted = sorted(
            lst,
            key=lambda t: str(t[0].get("updated_at", "") or ""),
            reverse=True,
        )
        latest_data, latest_rid = lst_sorted[0]
        statuses = [str(t[0].get("status", "")).lower() for t in lst_sorted]
        active = any(st in _ACTIVE_STATUSES for st in statuses)
        projects.append(
            {
                "project_dir": pd_str,
                "project_name": Path(pd_str).name,
                "spec_path": latest_data.get("spec_path"),
                "latest_run_id": latest_rid,
                "latest_status": latest_data.get("status"),
                "latest_name": latest_data.get("name"),
                "latest_updated_at": latest_data.get("updated_at"),
                "active": active,
                "runs_count": len(lst_sorted),
                "statuses": statuses,
                "latest": latest_data,
            }
        )

    projects.sort(key=lambda p: (p["project_name"].lower(), p["project_dir"]))

    # 扁平会话列表（去重后），供需要全量视图的消费者使用
    flat = [data for _, data, _ in items]
    flat.sort(
        key=lambda d: str(d.get("updated_at", "") or ""),
        reverse=True,
    )

    return {"projects": projects, "sessions": flat}

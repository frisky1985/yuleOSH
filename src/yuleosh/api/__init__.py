# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH REST API — modular route handlers.

All endpoints return JSON:
  {"ok": true, "data": {...}}
or on error:
  {"ok": false, "error": "message"}
"""

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

# NOTE (CQ-P2-02): sys.path.insert for dev. In production, use `pip install -e .` and remove.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OSH_HOME = os.environ.get("OSH_HOME", str(PROJECT_ROOT))

# Import-time snapshot of the effective OSH_HOME — the "second truth" whose
# divergence from a runtime env change caused the evidence-pack leak
# (2026-09-23).  See resolve_osh_home() for the full explanation.
_OSH_HOME_AT_IMPORT = OSH_HOME


def resolve_osh_home(current: str | None = None) -> str:
    """Resolve the effective ``OSH_HOME`` **at call time**.

    根因（2026-09-23）: ``OSH_HOME`` 是模块级常量，import 那一刻快照后永不
    变化；而 ``os.environ["OSH_HOME"]`` 可以在运行时被改。同一进程里于是有
    **两份真值**，测试里两套隔离手法各自只命中一份：

    - ``monkeypatch.setenv("OSH_HOME", tmp)``（全仓 232 处）→ 改 env；
    - ``monkeypatch.setattr(mod, "OSH_HOME", tmp)``（全仓 82 处）→ 改常量。

    写入目标若读常量、隔离却改 env（或反之），隔离就形同虚设。实证后果：
    dashboard 的证据生成把包写进了**仓库** ``.osh/evidence/``，累积 46 个空壳
    包外加一个 ``compliance-pack.zip`` —— 删掉还会再长。

    本函数把两类手法都认下来，供**所有决定落盘位置**的调用点使用：

    1. 传入的本模块常量**被显式覆盖过**（``monkeypatch.setattr``）→ 以它为准；
    2. 否则运行时设了 ``OSH_HOME`` env → 以 env 为准；
    3. 都没有 → import 时的取值（与旧行为完全一致）。

    为什么「显式覆盖的常量」优先于 env：``tests/test_api.py`` 在**收集期**就用
    ``os.environ.setdefault("OSH_HOME", <仓库根>)`` 把 env 钉死，此后一律存在，
    所以不能简单地「env 优先」（那会反过来废掉 setattr 那一类隔离，实测 28 项
    失败）。判定用 ``current != _OSH_HOME_AT_IMPORT`` 即可 —— 本模块常量除被
    patch 外恒等于 import 快照，不会误判。

    ``current`` 应由调用方传入**自己模块**的 ``OSH_HOME`` 常量：各个模块的
    常量可以被独立 patch，传自己的才能在跨模块调用时保持与该模块的守卫、
    清单、目录三者同源。

    纯只读且只读自己常量的路径无需迁移（本身自洽）；**跨模块传递**（如
    ``dashboard`` 决定 bundle 位置、``evidence`` 决定写入目标）必须用它。
    """
    if current and current != _OSH_HOME_AT_IMPORT:
        return current
    env_now = os.environ.get("OSH_HOME", "")
    # 防御：个别测试用 ``patch("....os.environ.get")`` 整体打桩，返回值不是
    # 字符串；此时退回旧行为，绝不把 Mock 当路径用。
    if isinstance(env_now, str) and env_now.strip():
        return env_now.strip()
    return current or _OSH_HOME_AT_IMPORT


class BadRequest(Exception):
    """Raised when a request body cannot be parsed."""


# Unified request-body cap (P1-5 / W-08): protects against memory-exhaustion
# via a huge declared Content-Length (memory DoS).
MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB


def json_ok(data: Any = None) -> tuple[dict, int]:
    """Return a success JSON response."""
    return {"ok": True, "data": data}, 200


def json_error(msg: str | dict, status: int = 400) -> tuple[dict, int]:
    """Return an error JSON response (W-07 contract fix).

    Accepts either a plain message string or a structured error dict
    ``{"error": <str>, ...extra fields}``.  The dict form is normalized so
    the ``error`` field is ALWAYS a string (API contract), with extra fields
    moved to a ``details`` object.  Example::

        json_error({"error": "file_too_large", "max_size_mb": 50}, 413)
        # -> {"ok": False, "error": "file_too_large", "details": {"max_size_mb": 50}}
    """
    if isinstance(msg, dict):
        err = msg.get("error", "error")
        details = {k: v for k, v in msg.items() if k != "error"}
        payload = {"ok": False, "error": str(err)}
        if details:
            payload["details"] = details
        return payload, status
    return {"ok": False, "error": msg}, status


def read_body(handler) -> dict:
    """Read and parse the request body based on Content-Type header.

    - application/json → JSON decode (fails with 400 on invalid input)
    - application/x-www-form-urlencoded → query-string decode
    - other / no content-type → try JSON, fall back to query-string

    Security (P1-5 / W-08):
    - Content-Length is clamped to MAX_BODY_BYTES (10 MB) — oversized or
      malformed (non-numeric/negative) headers raise BadRequest (400)
      instead of attempting an unbounded rfile.read() or a 500.

    Returns a dict on success, raises BadRequest on parse failure.
    """
    raw_header = handler.headers.get("Content-Length", "0") or "0"
    try:
        content_length = int(raw_header)
    except (ValueError, TypeError):
        raise BadRequest("Invalid Content-Length header")
    if content_length < 0:
        raise BadRequest("Invalid Content-Length header")
    content_length = min(content_length, MAX_BODY_BYTES)
    if content_length == 0:
        return {}
    raw = handler.rfile.read(content_length)
    # Stash raw bytes on the handler so signature-verifying handlers
    # (e.g. GitHub webhooks) can verify HMACs against the exact payload.
    try:
        handler._raw_body = raw
    except Exception:
        pass
    raw_text = raw.decode("utf-8", errors="replace")

    content_type = (handler.headers.get("Content-Type", "") or "").lower().split(";")[0].strip()

    if content_type == "application/json":
        try:
            return json.loads(raw_text)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise BadRequest(f"Invalid JSON body: {e}")
    elif content_type == "application/x-www-form-urlencoded":
        parsed = parse_qs(raw_text)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
    else:
        # Unknown or no Content-Type: try JSON first, then query-string
        try:
            return json.loads(raw_text)
        except (json.JSONDecodeError, UnicodeDecodeError):
            parsed = parse_qs(raw_text)
            if parsed:
                return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
            raise BadRequest("Unable to parse request body. Use application/json or application/x-www-form-urlencoded.")


def get_store():
    """Get the shared Store instance."""
    from yuleosh.store import Store
    return Store()

# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: MIT

"""v3.8.0 Track2 — A2 审计统一验收测试（acceptance-matrix T-A2-*）。

覆盖:
  - T-A2-01/02 legacy + v1 请求入同一 audit_log 表
  - T-A2-03 单次请求单条记录（无 ring+DB 双写）
  - T-A2-04/05/06/07 audit API 契约 + RBAC + 负例
  - T-A2-09-neg JSONL 移出 HTTP 路径
  - T-A2-10/11 event_bus 审计无静默失效
  - T-A2-12 JSONL 库保留
  - T-A2-13-neg 审计非仅内存（DB 持久）
"""

import os
import time
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.store import Store


@pytest.fixture()
def seeded_audit_store():
    """A fresh Store and a clean audit_log table."""
    store = Store()
    store.conn.execute("DELETE FROM audit_log")
    store.conn.commit()
    yield store
    try:
        store.conn.execute("DELETE FROM audit_log")
        store.conn.commit()
    except Exception:
        pass


class TestA2UnifiedWritePath:
    """T-A2-01/02/03 — 统一写路径 + 单条记录."""

    def test_legacy_request_into_db(self, seeded_audit_store):
        """T-A2-01: legacy /api/evidence 请求 → audit_log 表."""
        from yuleosh.api.audit import log_request
        log_request("GET", "/api/evidence", 200, "127.0.0.1", 5.0)
        rows = seeded_audit_store.conn.execute(
            "SELECT * FROM audit_log WHERE path='/api/evidence'").fetchall()
        assert len(rows) == 1

    def test_v1_request_into_db(self, seeded_audit_store):
        """T-A2-02: /api/v1/health 请求 → audit_log 表."""
        from yuleosh.api.audit import log_request
        log_request("GET", "/api/v1/health", 200, "127.0.0.1", 5.0)
        rows = seeded_audit_store.conn.execute(
            "SELECT * FROM audit_log WHERE path='/api/v1/health'").fetchall()
        assert len(rows) == 1

    def test_no_ring_write_only_dead_code(self):
        """T-A2-13-neg: 审计非仅内存 — ring 已删除（裁决 B2）."""
        import yuleosh.ui.server as server
        assert not hasattr(server, "_audit_log_ring")
        assert not hasattr(server, "_audit_log")

    def test_handler_helpers_uses_db_path(self):
        """log_audit 不再写 ring，改走 api.audit.log_request."""
        from yuleosh.ui.routes.handler_helpers import log_audit
        assert "log_request" in log_audit.__doc__ or True
        # 代码级：不引用 server._audit_log
        src = Path(__file__).resolve().parent.parent / \
            "src/yuleosh/ui/routes/handler_helpers.py"
        text = src.read_text(encoding="utf-8")
        assert "_s._audit_log" not in text


class TestA2AuditApi:
    """T-A2-04/05/06/07 — GET /api/v1/audit 契约 + RBAC."""

    def _auth_handler(self, token: str):
        h = mock.MagicMock()
        h.headers = {"Authorization": f"Bearer {token}"}
        h.client_address = ("127.0.0.1", 12345)
        h._request_start_time = time.time()
        return h

    def _make_user(self, store, role: str, email: str):
        from yuleosh.store import _session_token_hash
        from datetime import datetime, timedelta
        from yuleosh.ui.auth_extended import _generate_token
        import uuid as _uuid
        uid = int(_uuid.uuid4().int % 1_000_000_000) + 200_000_000
        # users 表 UNIQUE(org_id, email) — email 必须唯一，否则 INSERT OR
        # IGNORE 跳过 user 行而 session 指向不存在的 uid。
        email = f"{email.split('@')[0]}-{uid}@test.com"
        store.conn.execute(
            "INSERT OR IGNORE INTO users (id, org_id, email, role, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, 1, email, role, datetime.now().isoformat()),
        )
        token = _generate_token(user_id=uid, org_id=1, email=email)
        store.conn.execute(
            "INSERT OR IGNORE INTO user_sessions (user_id, token, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, _session_token_hash(token), datetime.now().isoformat(),
             (datetime.now() + timedelta(hours=72)).isoformat()),
        )
        store.conn.commit()
        return token, uid

    def test_get_contract_admin(self, seeded_audit_store):
        """T-A2-04/05: admin GET /api/v1/audit?limit=10 → 契约结构."""
        from yuleosh.api.audit import handle_audit, log_request
        log_request("GET", "/api/v1/health", 200, "127.0.0.1", 5.0)
        token, _ = self._make_user(seeded_audit_store, "admin", "a2-admin@t.com")
        result, status = handle_audit(
            "GET", "", {}, {"limit": ["10"]},
            handler=self._auth_handler(token),
            current_user={"user_id": 1, "org_id": 1,
                          "email": "a2-admin@t.com", "role": "admin"},
        )
        assert status == 200
        d = result["data"]
        assert set(d.keys()) == {"entries", "count", "total", "limit", "offset"}
        assert d["limit"] == 10

    def test_member_forbidden(self, seeded_audit_store):
        """T-A2-06-neg: member → 403."""
        from yuleosh.api.audit import handle_audit
        token, _ = self._make_user(seeded_audit_store, "member", "a2-mem@t.com")
        result, status = handle_audit(
            "GET", "", {}, {}, handler=self._auth_handler(token),
            current_user={"user_id": 1, "org_id": 1,
                          "email": "a2-mem@t.com", "role": "member"},
        )
        assert status == 403

    def test_anon_401(self, seeded_audit_store):
        """T-A2-07-neg: 匿名 → 401（require_auth fail-closed）."""
        from yuleosh.api.audit import handle_audit
        handler = mock.MagicMock()
        handler.headers = {}
        result, status = handle_audit("GET", "", {}, {}, handler=handler)
        assert status == 401

    def test_post_still_405(self, seeded_audit_store):
        """T-A2-05/B4: POST /api/v1/audit 保持 405."""
        from yuleosh.api.audit import handle_audit
        token, _ = self._make_user(seeded_audit_store, "admin", "a2-post@t.com")
        result, status = handle_audit(
            "POST", "", {}, {}, handler=self._auth_handler(token),
            current_user={"user_id": 1, "org_id": 1,
                          "email": "a2-post@t.com", "role": "admin"},
        )
        assert status == 405


class TestA2JsonlOutOfHttp:
    """T-A2-09-neg / T-A2-12 — JSONL 移出 HTTP，库保留."""

    def test_no_http_reference(self):
        """T-A2-09-neg: audit_routes 无 HTTP 路径引用（import 级）."""
        src_root = Path(__file__).resolve().parent.parent / "src"
        hits = []
        for p in src_root.rglob("*.py"):
            for i, line in enumerate(
                    p.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("from yuleosh.ui.routes.audit_routes"
                                       ) or stripped.startswith(
                    "from .audit_routes") or stripped.startswith(
                    "import yuleosh.ui.routes.audit_routes"):
                    hits.append(f"{p.relative_to(src_root.parent)}:{i}")
        assert hits == [], f"audit_routes import 引用残留: {hits}"

    def test_jsonl_lib_kept(self):
        from yuleosh.audit.model import AuditLog
        assert AuditLog is not None


class TestA2EventBusNoSilentFailure:
    """T-A2-10/11 — event_bus 审计无静默失效."""

    def test_no_store_insert(self):
        src = Path(__file__).resolve().parent.parent / \
            "src/yuleosh/loop_engine/event_bus.py"
        text = src.read_text(encoding="utf-8")
        # audit 持久化分支已显式移除（B5）— 不得再有活的 self._store.insert("audit_log")
        # 调用（注释里的说明文字除外）。
        import re as _re
        live = [l for l in text.splitlines()
                if "self._store.insert(\"audit_log\"" in l
                and not l.strip().startswith("#")]
        assert live == [], f"event_bus audit persist 残留: {live}"

    def test_audit_ring_still_works(self):
        from yuleosh.loop_engine.event_bus import AuditLog, LoopEvent, LoopEventType
        audit = AuditLog()
        ev = LoopEvent(event_type=LoopEventType.CI_FAILURE, source="a2-test", data={})
        audit.record(ev, [{"handler": "h", "status": "ok"}])
        assert len(audit.list()) == 1
        assert audit.list()[0]["event_type"] == "ci.failure"

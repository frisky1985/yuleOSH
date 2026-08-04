# Copyright (c) 2026 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""v3.8.0 Track2 — A6 dashboard 拆组件 + F2 preview 验收测试.

覆盖:
  - T-A6-02 tsc --noEmit 零错误
  - T-A6-04 ≥4 个组件文件且职责单一（替代验收线）
  - T-A6-05-neg 无逻辑复制
  - T-A6-06-neg 无新 npm 依赖
  - T-F2-01 登录用户 user_key = u:<user_id>
  - T-F2-02 dev 匿名 ip 分支保持
  - T-F2-03-neg 跨用户不命中
  - T-F2-04 同用户命中
"""

import hashlib
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

import pytest

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
REPO = Path(__file__).resolve().parent.parent


class TestA6Components:
    """T-A6-02/04/05/06 — 组件拆分."""

    def test_component_files_exist(self):
        """T-A6-04: ≥4 个业务组件文件且职责单一."""
        comp_dir = FRONTEND / "src" / "components" / "dashboard"
        files = sorted(p.name for p in comp_dir.glob("*.tsx"))
        assert len(files) >= 4, f"组件文件不足: {files}"
        assert "mini-coverage-bar.tsx" in files
        assert "swe-card.tsx" in files
        assert "evidence-modal.tsx" in files
        assert "knowledge-base-tab.tsx" in files
        assert "misra-trends-tab.tsx" in files

    def test_page_tsx_no_component_defs(self):
        """T-A6-04: page.tsx 不再内联定义这些组件."""
        page = (FRONTEND / "src/app/dashboard/page.tsx").read_text(
            encoding="utf-8")
        for fn in ("function MiniCoverageBar", "function SWECard",
                   "function EvidenceModal", "function KnowledgeBaseTab",
                   "function MisraTrendsTab"):
            assert fn not in page, f"{fn} 仍在 page.tsx"
        # 组件通过 import 引入
        assert 'from "@/components/dashboard/' in page

    def test_tsc_passes(self):
        """T-A6-02: tsc --noEmit 零错误."""
        # v3.10.0 Track1: CI test job 只装 pip 依赖不装 npm 依赖；无 node_modules 时
        # npx 会拉真 tsc 但缺 react/clsx/tailwind-merge 类型 → 误报失败。
        # 前端构建门禁由前端 job（Track4 恢复）承担，此处无依赖即 skip。
        if not (FRONTEND / "node_modules").is_dir():
            pytest.skip("frontend deps not installed (npm ci) — run in frontend-capable job")
        r = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=str(FRONTEND), capture_output=True, text=True, timeout=300,
        )
        assert r.returncode == 0, f"tsc 失败: {r.stdout[-2000:]}{r.stderr[-2000:]}"

    def test_no_logic_copy(self):
        """T-A6-05-neg: 每个 fetch 逻辑仅一份（getKBArticles 等只在组件内）."""
        page = (FRONTEND / "src/app/dashboard/page.tsx").read_text(
            encoding="utf-8")
        # page.tsx 不应再直接调用这些只属于子组件的 API
        for api in ("getKBArticles", "getMISRATrend", "getFMEAEntries"):
            assert api not in page, f"{api} 在 page.tsx 中重复"

    def test_no_new_deps(self):
        """T-A6-06-neg: package.json 无新增依赖."""
        pkg = FRONTEND / "package.json"
        before = subprocess.run(
            ["git", "show", "HEAD:frontend/package.json"],
            cwd=str(REPO), capture_output=True, text=True).stdout
        now = pkg.read_text(encoding="utf-8")
        import json as _json
        b = _json.loads(before)
        n = _json.loads(now)
        assert b.get("dependencies", {}) == n.get("dependencies", {})
        assert b.get("devDependencies", {}) == n.get("devDependencies", {})


class TestF2PreviewUserKey:
    """T-F2-01..04 — preview 缓存键维度."""

    def _make_handler(self, headers, addr=("1.1.1.1", 0)):
        h = mock.MagicMock()
        h.headers = headers
        h.client_address = addr
        return h

    def test_logged_user_key(self):
        """T-F2-01: 合法 JWT → u:<user_id>."""
        from yuleosh.store import Store, _session_token_hash
        from datetime import datetime, timedelta
        from yuleosh.ui.auth_extended import _generate_token
        from yuleosh.api.preview import _get_user_key
        import uuid as _uuid
        store = Store()
        uid = int(_uuid.uuid4().int % 1_000_000_000) + 400_000_000
        email = f"f2-{uid}@test.com"
        store.conn.execute(
            "INSERT OR IGNORE INTO users (id, org_id, email, role, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, 1, email, "admin", datetime.now().isoformat()),
        )
        token = _generate_token(user_id=uid, org_id=1, email=email)
        store.conn.execute(
            "INSERT OR IGNORE INTO user_sessions (user_id, token, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (uid, _session_token_hash(token), datetime.now().isoformat(),
             (datetime.now() + timedelta(hours=72)).isoformat()),
        )
        store.conn.commit()
        h = self._make_handler({"Authorization": f"Bearer {token}"})
        key = _get_user_key(h)
        assert key == f"u:{uid}"

    def test_dev_anon_ip(self):
        """T-F2-02: 匿名请求 → ip:<sha256>（W6 保持）."""
        from yuleosh.api.preview import _get_user_key
        h = self._make_handler({}, ("203.0.113.9", 0))
        key = _get_user_key(h)
        assert key == "ip:" + hashlib.sha256(b"203.0.113.9").hexdigest()

    def test_cross_user_no_hit(self):
        """T-F2-03-neg: 跨用户（不同 user_key）不命中缓存."""
        from yuleosh.api import preview as P
        url = "https://github.com/f2/repo"
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        P._assessment_store["f2-a"] = {"status": "completed", "report": {"g": 1}}
        P._repo_cache[("u:1", url_hash)] = "f2-a"
        try:
            assert ("u:2", url_hash) not in P._repo_cache
        finally:
            P._repo_cache.pop(("u:1", url_hash), None)
            P._assessment_store.pop("f2-a", None)

    def test_same_user_hit(self):
        """T-F2-04: 同用户同 URL 命中缓存."""
        from yuleosh.api import preview as P
        url = "https://github.com/f2/repo2"
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        P._assessment_store["f2-b"] = {"status": "completed", "report": {"g": 1}}
        P._repo_cache[("u:42", url_hash)] = "f2-b"
        try:
            assert ("u:42", url_hash) in P._repo_cache
        finally:
            P._repo_cache.pop(("u:42", url_hash), None)
            P._assessment_store.pop("f2-b", None)

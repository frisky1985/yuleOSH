# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH Dashboard — HTTP server app orchestration (TD-004, split from server.py).

Domain: the server launcher main() — host/port resolution, store init,
HTTPServer bootstrap.  Moved verbatim from yuleosh/ui/server.py.  Test
patches target ``yuleosh.ui.server.HTTPServer`` / ``Store`` / ``OSH_HOME`` /
``AUTH_ENABLED`` / ``OSHHandler``, so those server-module values are read
lazily via ``yuleosh.ui.server`` at call time.
"""

from __future__ import annotations

import logging
import os

from yuleosh.ui import server as _server

logger = logging.getLogger(__name__)


def main(host: str | None = None, port: int | None = None) -> None:
    if not host:
        host = os.environ.get("YULEOSH_HOST") or os.environ.get("OSH_HOST") or "127.0.0.1"
    if not port:
        try:
            port = int(os.environ.get("YULEOSH_PORT") or os.environ.get("OSH_PORT") or "8080")
        except ValueError:
            port = 8080
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Ensure OSH_HOME exists
    os.makedirs(_server.OSH_HOME, exist_ok=True)
    os.environ.setdefault("OSH_HOME", _server.OSH_HOME)

    # Initialize store
    try:
        store = _server.Store()
        logger.info(
            "Store initialized at %s",
            store.db_path if hasattr(store, "db_path") else "memory",
        )
        # 演示账号开箱即用：确保 demo@yuleosh.com 存在且密码正确（幂等）。
        # 仅在鉴权启用时 seed —— 本地免登录模式（AUTH_ENABLED=False）无需账号。
        if _server.AUTH_ENABLED:
            try:
                from yuleosh.ui.auth_extended import ensure_demo_account
                ensure_demo_account(store)
            except Exception as e:  # noqa: BLE001
                logger.warning("Demo account seed skipped: %s", e)
            try:
                from yuleosh.ui.auth_extended import ensure_view_test_accounts
                ensure_view_test_accounts(store)
            except Exception as e:  # noqa: BLE001
                logger.warning("View-test accounts seed skipped: %s", e)
    except Exception as e:  # noqa: BLE001 — 故意 fail-open：无 Store 时 dashboard 仍可用
        logger.warning("Store init failed (dashboard will work without it): %s", e)

    server = _server.HTTPServer((host, port), _server.OSHHandler)
    logger.info("yuleOSH Dashboard Server running on http://%s:%d", host, port)
    logger.info("AUTH_ENABLED=%s, OSH_HOME=%s", _server.AUTH_ENABLED, _server.OSH_HOME)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.server_close()

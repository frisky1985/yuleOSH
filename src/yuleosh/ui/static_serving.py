# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""yuleOSH Dashboard — static & page file serving (TD-004, split from server.py).

Domain: serving frontend/out/ static assets and dashboard template pages
for the OSHHandler server.  Moved verbatim from yuleosh/ui/server.py; the
method bodies are attached to OSHHandler by server.py.

Test patches target ``yuleosh.ui.server.OSH_HOME`` / ``UI_DIR`` /
``_REPO_ROOT``, so those server-module values are read lazily via
``yuleosh.ui.server`` at call time (same pattern as
yuleosh/ui/routes/handler_helpers.py).
"""

import os
import re
from pathlib import Path

from yuleosh.ui.http_security import _csp_for_html, _inject_csp_nonce


def _serve_static(self, path: str) -> None:
    """Serve a static file from frontend/out/."""
    # TD-004: OSH_HOME / _REPO_ROOT are read lazily via the server module
    # so ``mock.patch("yuleosh.ui.server.OSH_HOME", ...)`` keeps working.
    from yuleosh.ui import server as _server
    OSH_HOME = _server.OSH_HOME
    _REPO_ROOT = _server._REPO_ROOT
    OSH_HOME_DIR = Path(os.environ.get("HOME", "."))
    # Look for frontend/out at the repo root
    candidates = [
        # OSH_HOME 优先（含测试 mock）：显式指定的项目根。
        Path(OSH_HOME) / "frontend" / "out",
        # v3.12.x CI 真跑修复: repo-root checkout 兜底（CI
        # download-artifact 将 frontend/out 放在 checkout 根）。
        # OSH_HOME 默认值已与 _REPO_ROOT 一致，仅当 OSH_HOME 被
        # 显式覆盖（如测试 mock）时此处才成为独立候选。
        _REPO_ROOT / "frontend" / "out",
        OSH_HOME_DIR / ".openclaw" / "workspace" / "tasks" / "yuleOSH" / "frontend" / "out",
    ]
    static_dir = None
    for c in candidates:
        if c.exists():
            static_dir = c
            break

    if not static_dir:
        self._json_response({"error": "Static files not found"}, 500)
        return

    # Resolve file path
    if path == "/" or path == "":
        file_path = static_dir / "index.html"
    else:
        # Strip leading / and sanitize
        rel = path.lstrip("/")
        file_path = static_dir / rel
        # If path is a directory, try index.html
        if file_path.is_dir():
            file_path = file_path / "index.html"

    # Security: prevent directory traversal
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(static_dir.resolve())):
            file_path = static_dir / "404.html"
    except (ValueError, OSError):
        file_path = static_dir / "404.html"

    if not file_path.exists():
        file_path = static_dir / "404.html"
        if not file_path.exists():
            self._json_response({"error": "Not found"}, 404)
            return

    mime_map = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }
    ext = file_path.suffix.lower()
    content_type = mime_map.get(ext, "application/octet-stream")

    data = file_path.read_bytes()
    self.send_response(200)
    self.send_header("Content-Type", content_type)
    # T2 (v3.9.0, SHALL-T2.1): HTML responses get the nonce CSP header
    # (inline RSC scripts are rewritten with the matching nonce).  The
    # body length changes after injection — set it after the rewrite.
    if ext == ".html" or file_path.name == "index.html":
        data, nonce = _inject_csp_nonce(data)
        self.send_header("Content-Security-Policy",
                         _csp_for_html(nonce, data))
    self.send_header("Content-Length", str(len(data)))
    # M-2 (SEC-P2): cache-control for static assets.
    #   - content-hashed build artifacts (_next/static/*.js etc.) are
    #     immutable → long-lived public cache;
    #   - HTML documents are NEVER long-cached (updates must be visible);
    #   - non-hashed assets get a short max-age only (no immutable).
    if self._is_immutable_asset(file_path):
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
    elif ext == ".html" or file_path.name == "index.html":
        self.send_header("Cache-Control", "no-cache")
    else:
        self.send_header("Cache-Control", "public, max-age=3600")
    self._add_security_headers()
    self.end_headers()
    self.wfile.write(data)

def _is_immutable_asset(file_path: Path) -> bool:
    """True for content-hashed build artifacts (M-2).

    Conservative rule: the file must live under a build output dir
    (``_next/static`` or ``static``) AND its name must look like
    ``<8+ alnum/-/_>.<ext>`` — the Next.js ``[name].[hash].js`` pattern.
    User-uploaded resources never match (no hash in name, or not under
    a build dir), so they are never marked immutable.
    """
    rel = str(file_path)
    if "/_next/static/" not in rel and "/static/" not in rel:
        return False
    name = file_path.name
    stem = name.rsplit(".", 1)[0] if "." in name else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,}", stem or ""):
        return False
    return file_path.suffix.lower() in (".js", ".css", ".woff", ".woff2", ".png", ".svg")

def _serve_file(self, file_path: Path, content_type: str) -> None:
    """Serve a file by its absolute path.

    F4 (v3.8.0): HTML documents get ``Cache-Control: no-cache`` (aligned
    with M-2's ``_serve_static`` semantics) so page updates are always
    visible; non-HTML content keeps the default (no long-lived cache).
    """
    try:
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        # F4: pages must not be stale-cached (M-2 HTML rule).
        if "html" in content_type or file_path.suffix.lower() in (".html", ".htm"):
            self.send_header("Cache-Control", "no-cache")
            # T2 (v3.9.0, SHALL-T2.1): HTML responses carry the CSP
            # header with a per-request nonce covering the inline RSC
            # scripts (B5 ①).  Content-Length is set once, AFTER the
            # nonce rewrite (body length changes).
            data, nonce = _inject_csp_nonce(data)
            self.send_header("Content-Security-Policy",
                             _csp_for_html(nonce, data))
        self.send_header("Content-Length", str(len(data)))
        self._add_security_headers()
        self.end_headers()
        self.wfile.write(data)
    except FileNotFoundError:
        self._serve_static("/404.html")

def _serve_page(self, template_name: str, context: dict) -> None:
    """Render a dashboard template page."""
    # TD-004: UI_DIR is read lazily via the server module so that
    # ``mock.patch("yuleosh.ui.server.UI_DIR", ...)`` keeps working.
    from yuleosh.ui import server as _server
    ui_dir = _server.UI_DIR
    template_path = ui_dir / template_name
    if template_path.exists():
        self._serve_file(template_path, "text/html; charset=utf-8")
        return
    # Fallback to pages/
    pages_path = ui_dir / "pages" / template_name
    if pages_path.exists():
        self._serve_file(pages_path, "text/html; charset=utf-8")
        return
    # Fallback to marketing/
    marketing_path = ui_dir / "marketing" / template_name
    if marketing_path.exists():
        self._serve_file(marketing_path, "text/html; charset=utf-8")
        return
    # Not found
    self._serve_static("/404.html")

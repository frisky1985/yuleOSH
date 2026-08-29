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
from typing import Optional

from yuleosh.ui.http_security import _csp_for_html, _inject_csp_nonce

# next.config.js sets ``assetPrefix: "/yuleOSH"`` — a URL-only prefix that
# Next.js prepends to every exported asset reference.  The files themselves
# live at the frontend/out root (out/_next/static/...), so the prefix must be
# stripped before resolving on disk; otherwise every CSS/JS bundle misses and
# falls through to the 404 page, leaving the Next.js UI unstyled and inert.
_ASSET_PREFIXES = ("yuleOSH/",)


def _static_export_dir() -> Optional[Path]:
    """Locate the Next.js export dir (frontend/out/), or None when absent.

    TD-004: OSH_HOME / _REPO_ROOT are read lazily via the server module so
    ``mock.patch("yuleosh.ui.server.OSH_HOME", ...)`` keeps working.
    """
    from yuleosh.ui import server as _server
    OSH_HOME = _server.OSH_HOME
    _REPO_ROOT = _server._REPO_ROOT
    OSH_HOME_DIR = Path(os.environ.get("HOME", "."))
    candidates = [
        # OSH_HOME 优先（含测试 mock）：显式指定的项目根。
        Path(OSH_HOME) / "frontend" / "out",
        # v3.12.x CI 真跑修复: repo-root checkout 兜底（CI
        # download-artifact 将 frontend/out 放在 checkout 根）。
        _REPO_ROOT / "frontend" / "out",
        OSH_HOME_DIR / ".openclaw" / "workspace" / "tasks" / "yuleOSH" / "frontend" / "out",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _resolve_static_file(path: str) -> Optional[Path]:
    """Resolve a URL path to a real file under frontend/out/, or None.

    Shared by ``_serve_static`` (serves it) and the page router (probes
    whether an exported page exists, without writing a response).  Directory
    paths resolve to their ``index.html`` — the Next.js export layout — so
    ``/dashboard/pipeline`` finds ``out/dashboard/pipeline/index.html``.

    Returns None for missing files, traversal attempts, and a missing export
    dir; callers decide what that means (404.html vs the page-router 404).
    """
    static_dir = _static_export_dir()
    if static_dir is None:
        return None

    if path == "/" or path == "":
        file_path = static_dir / "index.html"
    else:
        rel = path.lstrip("/")
        # assetPrefix is URL-only (see _ASSET_PREFIXES) — drop it so
        # /yuleOSH/_next/static/x.css resolves to out/_next/static/x.css.
        for prefix in _ASSET_PREFIXES:
            if rel.startswith(prefix):
                rel = rel[len(prefix):]
                break
        file_path = static_dir / rel
        # If path is a directory, try index.html
        if file_path.is_dir():
            file_path = file_path / "index.html"

    # Security: prevent directory traversal
    try:
        resolved = file_path.resolve()
        if not str(resolved).startswith(str(static_dir.resolve())):
            return None
    except (ValueError, OSError):
        return None
    return resolved if resolved.is_file() else None


def _serve_static(self, path: str) -> None:
    """Serve a static file from frontend/out/."""
    file_path = _resolve_static_file(path)

    if file_path is None:
        # Historical fallbacks preserved (tests and _serve_page rely on
        # them): 404.html when the export dir has one, else a JSON error.
        static_dir = _static_export_dir()
        if static_dir is not None:
            fallback = static_dir / "404.html"
            if fallback.exists():
                file_path = fallback
        if file_path is None:
            if static_dir is None:
                self._json_response({"error": "Static files not found"}, 500)
            else:
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

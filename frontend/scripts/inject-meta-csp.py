#!/usr/bin/env python3
"""T2 (v3.9.0, 裁决 B8 ①) — inject a meta CSP into the static export.

GitHub Pages cannot set response headers (T-T2-12-neg), so the only CSP
that reaches gh-pages visitors is an HTML ``<meta>`` tag.  The inline RSC
``self.__next_f.push(...)`` scripts are static build output — we compute
their sha256 hashes and whitelist exactly those (strongest option for a
static host).  'unsafe-inline' stays ONLY in style-src-attr (the export's
inline style= attributes).

Idempotent: pages that already carry a meta CSP are skipped.

Usage: python3 frontend/scripts/inject-meta-csp.py   (run after npm run build)
"""

import base64
import hashlib
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "out"

_META_RE = re.compile(
    r'<meta http-equiv="Content-Security-Policy"[^>]*>', re.IGNORECASE
)
_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
                        re.IGNORECASE | re.DOTALL)


def _sha256_b64(content: str) -> str:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return "'sha256-{}'".format(
        base64.b64encode(bytes.fromhex(digest)).decode("ascii"))


def _meta_csp(html: str) -> str:
    hashes = [_sha256_b64(m.group(1)) for m in _SCRIPT_RE.finditer(html)]
    if not hashes:
        raise SystemExit(f"error: no inline scripts found in {html[:60]}...")
    policy = (
        "default-src 'self'; "
        "script-src 'self' " + " ".join(hashes) + "; "
        "style-src 'self' 'unsafe-inline'; style-src-attr 'unsafe-inline'; "
        "font-src 'self'; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return (f'<meta http-equiv="Content-Security-Policy" '
            f'content="{policy}">')


def main() -> int:
    html_files = sorted(OUT.rglob("*.html"))
    if not html_files:
        print("no html files under", OUT)
        return 1
    injected = 0
    for path in html_files:
        html = path.read_text(encoding="utf-8")
        # replace an existing meta CSP (re-runs after rebuild/updates)
        html = _META_RE.sub("", html)
        meta = _meta_csp(html)
        # insert after <head> (or at the very start if no head tag)
        head = re.search(r"<head[^>]*>", html, re.IGNORECASE)
        if head:
            html = html[:head.end()] + "\n    " + meta + html[head.end():]
        else:
            html = meta + "\n" + html
        path.write_text(html, encoding="utf-8")
        injected += 1
    print(f"meta CSP injected into {injected} pages under {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Import automotive-claude-code-agents skills into a bundled yuleOSH pack.

Source: https://github.com/im-hashim/automotive-claude-code-agents (MIT).

The upstream repository stores ~4.8k skills as YAML (plus a small set of
curated Markdown knowledge files).  yuleOSH loads them from a single bundled
JSON pack so every project can use them without a per-project install step.

Usage::

    git clone --depth 1 https://github.com/im-hashim/automotive-claude-code-agents /tmp/aca
    python3 scripts/import-automotive-skills.py --repo /tmp/aca

The generated pack lives at ``src/yuleosh/skills/packs/automotive/``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "src" / "yuleosh" / "skills" / "packs" / "automotive"
SKIP_MD = ("README", "INDEX", "NEW_DOMAINS", "DELIVERABLES", "SUMMARY")
STANDARD_TAGS = {
    "ISO 26262": "iso26262",
    "ISO 21434": "iso21434",
    "ISO 21448": "sotif",
    "ASPICE": "aspice",
    "MISRA": "misra",
    "AUTOSAR": "autosar",
    "ISO 14229": "uds",
    "ISO 15765": "can",
    "ISO 11898": "can",
}


def _as_lines(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [v.strip() for v in value.splitlines() if v.strip()]
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            if isinstance(item, dict):
                out.append("; ".join(f"{k}: {v}" for k, v in item.items()))
            else:
                out.append(str(item).strip())
        return [v for v in out if v]
    return [str(value)]


def _section(title: str, lines: list[str]) -> str:
    if not lines:
        return ""
    body = "\n".join(f"- {line}" for line in lines)
    return f"## {title}\n{body}\n"


def _content_from_yaml(data: dict) -> str:
    parts = [
        _section("适用场景", _as_lines(data.get("use_cases"))),
        _section("相关标准", _as_lines(data.get("automotive_standards"))),
        _section("约束", _as_lines(data.get("constraints"))),
        _section("推荐工具", _as_lines(data.get("tools_required"))),
        _section("交付物", _as_lines(data.get("deliverables"))),
    ]
    instructions = str(data.get("instructions") or "").strip()
    if instructions:
        parts.append("## 方法\n" + instructions)
    return "\n".join(p for p in parts if p).strip()


def _standard_tags(data: dict) -> list[str]:
    text = " ".join(_as_lines(data.get("automotive_standards")))
    return [tag for needle, tag in STANDARD_TAGS.items() if needle.lower() in text.lower()]


def _dedupe_name(name: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    for i in range(2, 1000):
        candidate = f"{name}-{i}"
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise RuntimeError(f"cannot dedupe skill name: {name}")


def _description_from_md(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", ">", "|", "-", "*", "`")):
            return line[:240]
    return ""


def build_entries(repo: Path) -> list[dict]:
    skills_dir = repo / "skills"
    if not skills_dir.is_dir():
        raise SystemExit(f"not an automotive-claude-code-agents checkout: {repo}")
    install_date = date.today().isoformat()
    used: set[str] = set()
    entries: list[dict] = []

    for path in sorted(skills_dir.rglob("*.yaml")):
        rel = path.relative_to(skills_dir)
        if any(part.startswith("_") for part in rel.parts):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            continue
        category = str(data.get("category") or rel.parts[0])
        subcategory = str(data.get("subcategory") or "")
        content = _content_from_yaml(data)
        if not content:
            continue
        name = _dedupe_name(f"automotive-{category}-{path.stem}", used)
        tags = [category, "automotive"]
        if subcategory:
            tags.append(subcategory)
        tags.extend(_standard_tags(data))
        tags = list(dict.fromkeys(tags))
        entries.append({
            "name": name,
            "title": (subcategory or path.stem).replace("-", " ").title(),
            "description": str(data.get("description") or "").strip(),
            "content": content,
            "tags": tags,
            "version": str(data.get("version") or "1.0.0"),
            "created_at": install_date,
            "source": f"skills/{rel.as_posix()}",
        })

    for path in sorted(skills_dir.rglob("*.md")):
        rel = path.relative_to(skills_dir)
        if any(part.startswith("_") for part in rel.parts):
            continue
        if any(marker in path.name for marker in SKIP_MD):
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) < 200:
            continue
        category = rel.parts[0] if len(rel.parts) > 1 else path.parent.name
        name = _dedupe_name(f"automotive-{category}-{path.stem}", used)
        tags = [category, "automotive", "curated"]
        tags.extend(t for needle, t in STANDARD_TAGS.items() if needle.lower() in text.lower())
        tags = list(dict.fromkeys(tags))
        title = path.stem.replace("-", " ").replace("_", " ").title()
        entries.append({
            "name": name,
            "title": title,
            "description": _description_from_md(text),
            "content": text,
            "tags": tags,
            "version": "1.0.0",
            "created_at": install_date,
            "source": f"skills/{rel.as_posix()}",
        })

    return entries


def _commit(repo: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    entries = build_entries(args.repo.resolve())
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema": "yuleosh-skill-pack/v1",
        "source": "https://github.com/im-hashim/automotive-claude-code-agents",
        "license": "MIT",
        "commit": _commit(args.repo.resolve()),
        "generated": date.today().isoformat(),
        "count": len(entries),
        "skills": entries,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    (out / "skills.json").write_bytes(raw)

    licenses = list(args.repo.glob("LICENSE*")) + list(args.repo.glob("COPYING*"))
    if licenses:
        (out / "LICENSE").write_text(licenses[0].read_text(encoding="utf-8"), encoding="utf-8")

    (out / "SOURCE.md").write_text(
        "# automotive-claude-code-agents skill pack\n\n"
        f"- Source: {payload['source']}\n"
        f"- Commit: `{payload['commit']}`\n"
        f"- License: {payload['license']} (see LICENSE)\n"
        f"- Generated: {payload['generated']}\n"
        f"- Skills: {len(entries)} (YAML + curated Markdown)\n"
        f"- SHA-256: `{hashlib.sha256(raw).hexdigest()}`\n\n"
        "Regenerate with `python3 scripts/import-automotive-skills.py --repo <checkout>`.\n",
        encoding="utf-8",
    )

    curated = sum(1 for e in entries if "curated" in e["tags"])
    print(f"imported {len(entries)} skills ({curated} curated md) -> {out} "
          f"({len(raw) / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

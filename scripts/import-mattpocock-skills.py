#!/usr/bin/env python3
"""Import Matt Pocock skills into the yuleOSH skill library.

Scans ~/mattpocock-skills/skills/**/SKILL.md (MIT licensed), parses
frontmatter (name/description), and writes .osh/skills/skills.json in the
yuleOSH Skill JSON format. Run: python3 scripts/import-mattpocock-skills.py
"""

import json
import re
import sys
from pathlib import Path

MP_ROOT = Path.home() / "mattpocock-skills" / "skills"
OUT = Path(__file__).resolve().parent.parent / ".osh" / "skills" / "skills.json"

_FM = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def parse_skill(path: Path, category: str) -> dict:
    text = path.read_text(encoding="utf-8")
    m = _FM.match(text)
    meta = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip()
        body = text[m.end():].strip()
    else:
        body = text.strip()
    name = meta.get("name", path.parent.name)
    return {
        "name": name,
        "title": meta.get("title", name.replace("-", " ").title()),
        "description": meta.get("description", f"Matt Pocock skill: {name}"),
        "content": body,
        "tags": ["mattpocock", category],
        "version": "1.0.0",
    }


def main() -> int:
    skills = []
    for category_dir in sorted(MP_ROOT.iterdir()):
        if not category_dir.is_dir():
            continue
        for skill_dir in sorted(category_dir.iterdir()):
            sk = skill_dir / "SKILL.md"
            if sk.exists():
                skills.append(parse_skill(sk, category_dir.name))
    skills.sort(key=lambda s: s["name"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"version": "1", "skills": skills}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"✅ 导入 {len(skills)} 个 mattpocock 技能 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

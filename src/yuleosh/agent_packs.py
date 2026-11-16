#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Bundled agent role packs.

The ``automotive`` pack maps every expert profile / tooling command from
https://github.com/im-hashim/automotive-claude-code-agents onto yuleOSH's
eight pipeline roles (pm / requirements / architect / developer / qa /
verifier / cm / tool).

Installing the pack writes one ``<role>.md`` per role into
``<project>/.yuleosh/agents/``.  ``load_agent_constraints_by_role`` then
attributes each file to its role and injects only that role's text into
the current step's system prompt.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parent / "agent_packs"

# Keep in sync with yuleosh.agent_registry.AGENT_ROLES values.
ROLE_ORDER = ("pm", "requirements", "architect", "developer",
              "qa", "verifier", "cm", "tool")

PACK_SOURCE_SUBDIR = "pack-source"


def available_packs() -> list[str]:
    """Return bundled pack names (e.g. ``["automotive"]``)."""
    if not PACK_ROOT.is_dir():
        return []
    return sorted(p.name for p in PACK_ROOT.iterdir()
                  if p.is_dir() and (p / "manifest.json").is_file())


def pack_manifest(pack: str = "automotive") -> dict:
    path = PACK_ROOT / pack / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"unknown agent pack: {pack}")
    return json.loads(path.read_text(encoding="utf-8"))


def pack_roles(pack: str = "automotive") -> dict[str, Path]:
    """Return ``{role: markdown_path}`` for a pack."""
    roles_dir = PACK_ROOT / pack / "roles"
    if not roles_dir.is_dir():
        raise FileNotFoundError(f"agent pack has no roles/: {pack}")
    return {role: roles_dir / f"{role}.md"
            for role in ROLE_ORDER if (roles_dir / f"{role}.md").is_file()}


def install_pack(project_dir: str | Path, pack: str = "automotive",
                 force: bool = False) -> dict:
    """Install a bundled pack into ``<project>/.yuleosh/agents/``.

    Existing files are kept unless ``force`` is set, so project-specific
    role constraints are never silently overwritten.

    Returns ``{"installed": [...], "skipped": [...], "dest": str}``.
    """
    dest_dir = Path(project_dir).resolve() / ".yuleosh" / "agents"
    dest_dir.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    skipped: list[str] = []
    for role, src in pack_roles(pack).items():
        dest = dest_dir / f"{role}.md"
        if dest.exists() and not force:
            skipped.append(role)
            continue
        shutil.copyfile(src, dest)
        installed.append(role)

    # Provenance lives in a subdirectory: the role loader only scans
    # top-level ``*.md`` files, so it cannot mis-attribute these.
    src_dir = dest_dir / PACK_SOURCE_SUBDIR
    src_dir.mkdir(exist_ok=True)
    for name in ("manifest.json", "SOURCE.md", "LICENSE"):
        src = PACK_ROOT / pack / name
        if src.is_file():
            shutil.copyfile(src, src_dir / name)

    return {"installed": installed, "skipped": skipped, "dest": str(dest_dir)}


def handle_agents_command(args) -> int:
    """Dispatch ``yuleosh agents list|install-pack``."""
    sub = getattr(args, "agents_sub", None)
    if sub == "list":
        for pack in available_packs():
            try:
                manifest = pack_manifest(pack)
            except (OSError, ValueError):
                continue
            roles = pack_roles(pack)
            print(f"  {pack}: {len(roles)} roles · "
                  f"{len(manifest.get('agents', []))} agents · "
                  f"{len(manifest.get('commands', []))} commands")
            for stat in manifest.get("roles", []):
                print(f"    - {stat['role']:<13} agents={stat['agents']:<3} "
                      f"commands={stat['commands']:<3} chars={stat['chars']}")
        return 0

    if sub == "install-pack":
        project = getattr(args, "project", ".") or "."
        pack = getattr(args, "pack", "automotive") or "automotive"
        try:
            result = install_pack(project, pack=pack,
                                  force=bool(getattr(args, "force", False)))
        except FileNotFoundError as exc:
            print(f"  ❌ {exc}")
            return 1
        print(f"  ✅ {pack}: installed {len(result['installed'])} role file(s) "
              f"into {result['dest']}")
        if result["skipped"]:
            print(f"  ⏭️  kept existing: {', '.join(result['skipped'])} "
                  f"(use --force to overwrite)")
        return 0

    print("Usage: yuleosh agents list | "
          "yuleosh agents install-pack [--pack automotive] "
          "[--project DIR] [--force]")
    return 1

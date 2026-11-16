#!/usr/bin/env python3
"""Import automotive-claude-code-agents agents/commands as yuleOSH roles.

Upstream layout (https://github.com/im-hashim/automotive-claude-code-agents):

  agents/<domain>/*.yaml   — 218 expert agent profiles
  commands/<domain>/*.sh   — 192 tooling command references

yuleOSH has a fixed set of eight roles (pm / requirements / architect /
developer / qa / verifier / cm / tool) and injects one role's constraint
file per pipeline step.  This script maps every upstream domain to exactly
one role, compresses the profiles into a prompt-sized markdown constraint
file per role, and writes a full manifest for traceability.

Usage::

    python3 scripts/import-automotive-agents.py \
        --repo /tmp/automotive-claude-code-agents
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required: pip install pyyaml")

DEFAULT_OUT = Path("src/yuleosh/agent_packs/automotive")

# Upstream domain -> yuleOSH role (single mapping, deterministic).
AGENT_DOMAINS: dict[str, str] = {
    "adas": "developer",
    "ai-ecu": "architect",
    "automotive-workflow": "pm",
    "autosar": "architect",
    "battery": "developer",
    "calibration": "developer",
    "cloud": "architect",
    "cockpit": "developer",
    "core": "architect",
    "cybersecurity": "verifier",
    "diagnostics": "developer",
    "ev-systems": "developer",
    "functional-safety": "verifier",
    "hardware-safety": "qa",
    "hpc-platform": "architect",
    "kubernetes": "tool",
    "logging": "developer",
    "mbd": "developer",
    "ml-analytics": "developer",
    "oem": "requirements",
    "orchestration": "pm",
    "powertrain-chassis": "developer",
    "product-owner": "requirements",
    "project-management": "pm",
    "qnx": "architect",
    "safety": "qa",
    "sdv-platform": "architect",
    "security": "verifier",
    "services": "architect",
    "specialists": "requirements",
    "testing": "qa",
    "tier1": "developer",
    "tier2": "developer",
    "tier3": "developer",
    "toolchain": "tool",
    "tools": "tool",
    "v2x": "architect",
    "vehicle-systems": "architect",
    "zonal-architecture": "architect",
}

COMMAND_DOMAINS: dict[str, str] = {
    "adas": "developer",
    "autosar": "architect",
    "battery": "developer",
    "body": "developer",
    "calibration": "developer",
    "charging": "developer",
    "chassis": "developer",
    "cloud": "tool",
    "cockpit": "developer",
    "compliance": "verifier",
    "diagnostics": "developer",
    "embedded": "developer",
    "ev": "developer",
    "general": "cm",
    "hil-sil": "qa",
    "infotainment": "developer",
    "integration": "qa",
    "kubernetes": "tool",
    "lifecycle": "cm",
    "llm-council": "pm",
    "logging": "developer",
    "manufacturing": "developer",
    "mbd": "developer",
    "network": "developer",
    "powertrain": "developer",
    "qnx": "architect",
    "regulatory": "verifier",
    "safety": "qa",
    "security": "verifier",
    "simulation": "qa",
    "testing": "qa",
    "tools": "tool",
    "v2x": "architect",
}

ROLE_TITLES = {
    "pm": ("PM", "小明"),
    "requirements": ("Requirements", "Hermes"),
    "architect": ("Architect", "Claude"),
    "developer": ("Developer", "小克"),
    "qa": ("QA", "小马"),
    "verifier": ("Verifier", "Codex"),
    "cm": ("CM", "小仓"),
    "tool": ("Tool", "QEMU"),
}

# Domains that must survive truncation first (per-role relevance).
DOMAIN_PRIORITY = {
    "orchestration": 0,
    "functional-safety": 0,
    "testing": 0,
    "safety": 0,
    "autosar": 1,
    "security": 1,
    "cybersecurity": 1,
    "compliance": 1,
    "regulatory": 1,
    "embedded": 1,
}

MAX_ROLE_CHARS = 16000
COMMAND_RESERVE = 7500
DESC_FULL = 100
CAP_CHARS = 40


def _load_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _md_agent(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem.replace("-", " ")
    desc = ""
    caps: list[str] = []
    in_caps = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and title == path.stem.replace("-", " "):
            title = stripped[2:].strip()
        elif stripped.startswith("#"):
            in_caps = any(k in stripped.lower() for k in (
                "capabilit", "responsibilit", "expertise", "competenc", "skill"))
        elif stripped.startswith(("- ", "* ")):
            if in_caps:
                caps.append(re.sub(r"\*\*|__|`", "", stripped[2:]).strip())
        elif not desc and stripped and not stripped.startswith(("|", ">")):
            desc = stripped
    return {
        "name": path.stem,
        "description": desc or title,
        "capabilities": caps,
    }


def _agents(skills_root: Path) -> list[dict]:
    out: list[dict] = []
    agents_dir = skills_root / "agents"
    if not agents_dir.is_dir():
        return out
    for path in sorted(agents_dir.rglob("*")):
        if not path.is_file():
            continue
        domain = path.relative_to(agents_dir).parts[0]
        if path.suffix in (".yaml", ".yml"):
            data = _load_yaml(path)
        elif path.suffix == ".md":
            data = _md_agent(path)
        else:
            continue
        name = str(data.get("name") or path.stem).strip()
        description = str(data.get("description") or data.get("role") or "").strip()
        caps = [str(c).strip() for c in (data.get("capabilities") or []) if str(c).strip()]
        out.append({
            "kind": "agent",
            "name": name,
            "domain": domain,
            "role": AGENT_DOMAINS.get(domain, "developer"),
            "description": description,
            "capabilities": caps,
            "source": f"agents/{path.relative_to(agents_dir).as_posix()}",
        })
    return out


_COMMAND_HEADER = re.compile(
    r"^#\s*(?P<title>[^=\n].*?)\s*$", re.MULTILINE)
_OPTION = re.compile(r"^#\s+(-[\w/]*(?:,\s*--[\w-]+)?)\s+(?P<desc>.+)$")


def _parse_command(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    head = "\n".join(text.splitlines()[:40])
    title = ""
    usage = ""
    options: list[str] = []
    for line in head.splitlines():
        stripped = line.strip()
        if stripped.startswith("#!"):
            continue
        if not stripped.startswith("#"):
            continue
        body = stripped.lstrip("#").strip()
        if body.startswith("=") or not body:
            continue
        if body.lower().startswith("usage:"):
            usage = body[6:].strip()
        elif body.lower().startswith("options:"):
            continue
        elif body.startswith("-"):
            m = _OPTION.match(stripped)
            if m and m.group("desc") and "Show help" not in m.group("desc"):
                options.append(f"{m.group(1)} {m.group('desc').strip()}")
            elif body.startswith("-") and len(body) > 3 and body[1] != "-":
                options.append(body)
        elif not title and not body.startswith("-"):
            title = body
    desc = title
    for sep in ("—", " - ", " -- "):
        if sep in title:
            desc = title.split(sep, 1)[1].strip()
            break
    return {
        "kind": "command",
        "name": path.stem,
        "description": desc or title,
        "usage": usage,
        "options": options[:3],
    }


def _commands(skills_root: Path) -> list[dict]:
    out: list[dict] = []
    commands_dir = skills_root / "commands"
    if not commands_dir.is_dir():
        return out
    for path in sorted(commands_dir.rglob("*.sh")):
        domain = path.relative_to(commands_dir).parts[0]
        data = _parse_command(path)
        out.append({
            **data,
            "domain": domain,
            "role": COMMAND_DOMAINS.get(domain, "developer"),
            "source": f"commands/{path.relative_to(commands_dir).as_posix()}",
        })
    return out


def _sort_key(entry: dict):
    return (DOMAIN_PRIORITY.get(entry["domain"], 50), entry["domain"], entry["name"])


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clip(text: str, limit: int) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return (cut or text[:limit].rstrip()) + "…"


def _agent_lines(entries: list[dict], budget: int) -> tuple[list[str], int]:
    """Render every agent at least as a one-line index, then spend any
    remaining budget upgrading entries (in priority order) to full profiles.
    """
    def bare(entry: dict) -> str:
        return (f"- **{entry['name']}**（{entry['domain']}）: "
                f"{_clip(entry['description'], 60)}")

    def full(entry: dict) -> str:
        caps = "; ".join(_clip(c, CAP_CHARS) for c in entry["capabilities"][:2])
        line = (f"- **{entry['name']}**（{entry['domain']}）: "
                f"{_clip(entry['description'], DESC_FULL)}")
        if caps:
            line += f"｜能力: {caps}"
        return line

    bare_lines = [bare(e) for e in entries]
    used = sum(len(x) + 1 for x in bare_lines)
    skipped = 0
    if used > budget:
        # Extreme fallback: drop tail entries until the bare index fits.
        kept: list[str] = []
        spent = 0
        for line in bare_lines:
            if spent + len(line) + 1 > budget:
                skipped += 1
                continue
            kept.append(line)
            spent += len(line) + 1
        bare_lines = kept
        used = spent

    extra_budget = max(0, budget - used)
    out: list[str] = []
    for entry, bare_line in zip(entries, bare_lines):
        full_line = full(entry)
        extra = len(full_line) - len(bare_line)
        if extra > 0 and extra <= extra_budget:
            out.append(full_line)
            extra_budget -= extra
        else:
            out.append(bare_line)
    return out, skipped


def _command_lines(entries: list[dict], budget: int) -> tuple[list[str], int]:
    lines: list[str] = []
    used = 0
    skipped = 0
    for entry in entries:
        line = (f"- `{entry['source'][len('commands/'):]}` — "
                f"{_clip(entry['description'], 45)}")
        if used + len(line) + 1 <= budget:
            lines.append(line)
            used += len(line) + 1
        else:
            skipped += 1
    return lines, skipped


def _render_role(role: str, agents: list[dict], commands: list[dict],
                 source: str, commit: str) -> tuple[str, dict]:
    title, label = ROLE_TITLES[role]
    # Reserve only what the commands actually need, so agent-heavy roles
    # (pm/architect) do not lose profiles to an unused command budget.
    reserve = min(COMMAND_RESERVE, len(commands) * 80 + 500)
    agent_budget = MAX_ROLE_CHARS - reserve
    agent_lines, agent_skipped = _agent_lines(agents, agent_budget)
    cmd_lines, cmd_skipped = _command_lines(
        commands, MAX_ROLE_CHARS - sum(len(x) + 1 for x in agent_lines) - 600)
    header = [
        f"<!-- source: {source} @ {commit} — MIT -->",
        f"# 角色约束 — {title}（{label}）",
        "",
        "以下专家画像与命令参考来自 automotive-claude-code-agents，"
        "由 yuleOSH 按角色聚合。它们是**方法论约束**：",
        "- 采用对应专家视角与检查项，但不得改变流水线门禁的判定标准；",
        "- 命令仅作工具链用法参考，yuleOSH 不会执行它们；若工程内不存在"
        "对应工具，必须显式说明不可用，禁止伪造执行结果；",
        "- 与 spec/需求冲突时，以 spec 为唯一事实来源。",
        "",
    ]
    body = [f"## 专家画像（{len(agents)} 个，来自 agents/）", *agent_lines]
    if not agents:
        body.append("- 本角色无专属画像；命令参考中的发布/配置流程即为约束来源。")
    if agent_skipped:
        body.append(f"- …另有 {agent_skipped} 个画像因预算限制未展开，"
                    "完整清单见 manifest.json")
    body += ["", f"## 命令参考（{len(commands)} 个，来自 commands/）", *cmd_lines]
    if cmd_skipped:
        body.append(f"- …另有 {cmd_skipped} 个命令未展开，完整清单见 manifest.json")
    text = "\n".join(header + body) + "\n"
    stats = {
        "role": role,
        "agents": len(agents),
        "commands": len(commands),
        "agents_omitted": agent_skipped,
        "commands_omitted": cmd_skipped,
        "chars": len(text),
    }
    return text, stats


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

    repo = args.repo.resolve()
    if not (repo / "agents").is_dir():
        sys.exit(f"not an automotive-claude-code-agents checkout: {repo}")

    agents = _agents(repo)
    commands = _commands(repo)
    commit = _commit(repo)
    install_date = date.today().isoformat()

    by_role_agents: dict[str, list[dict]] = {r: [] for r in ROLE_TITLES}
    by_role_commands: dict[str, list[dict]] = {r: [] for r in ROLE_TITLES}
    for entry in agents:
        by_role_agents[entry["role"]].append(entry)
    for entry in commands:
        by_role_commands[entry["role"]].append(entry)

    roles_dir = args.out / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    for stale in roles_dir.glob("*.md"):
        stale.unlink()

    stats = []
    for role in ROLE_TITLES:
        a = sorted(by_role_agents[role], key=_sort_key)
        c = sorted(by_role_commands[role], key=_sort_key)
        text, stat = _render_role(role, a, c, "automotive-claude-code-agents", commit)
        (roles_dir / f"{role}.md").write_text(text, encoding="utf-8")
        stats.append(stat)

    manifest = {
        "schema": "yuleosh-agent-pack/v1",
        "pack": "automotive",
        "source": "https://github.com/im-hashim/automotive-claude-code-agents",
        "commit": commit,
        "license": "MIT",
        "generated": install_date,
        "agents": agents,
        "commands": commands,
        "roles": stats,
    }
    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    (args.out / "SOURCE.md").write_text(
        "# automotive-claude-code-agents role pack\n\n"
        "- Source: https://github.com/im-hashim/automotive-claude-code-agents\n"
        f"- Commit: `{commit}`\n"
        "- License: MIT (see LICENSE)\n"
        f"- Generated: {install_date}\n"
        f"- Agents: {len(agents)} · Commands: {len(commands)} · Roles: {len(ROLE_TITLES)}\n"
        f"- Manifest SHA-256: `{digest}`\n\n"
        "Regenerate with `python3 scripts/import-automotive-agents.py "
        "--repo <checkout>`.\n",
        encoding="utf-8")

    license_src = repo / "LICENSE"
    if license_src.is_file():
        (args.out / "LICENSE").write_text(
            license_src.read_text(encoding="utf-8", errors="replace"),
            encoding="utf-8")

    for stat in stats:
        print(f"  {stat['role']:<13} agents={stat['agents']:<3} "
              f"commands={stat['commands']:<3} chars={stat['chars']:<6} "
              f"omitted={stat['agents_omitted']}/{stat['commands_omitted']}")
    print(f"imported {len(agents)} agents + {len(commands)} commands "
          f"-> {args.out} ({digest[:12]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

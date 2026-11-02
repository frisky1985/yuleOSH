#!/usr/bin/env python3
"""Build test impact closure from the src import graph.

For each changed src module, find every test file that (transitively)
imports it, by walking the real import graph — not by grepping test
keywords. Usage:

    python scripts/impact_closure.py <changed_file.py> [<changed_file.py> ...]

Prints the closure test files (relative paths), one per line.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"
TESTS = REPO / "tests"


def module_name(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    return ".".join(rel.parts)


def py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def build_import_graph() -> dict[str, set[str]]:
    """module -> set of modules it imports (intra-yuleosh only)."""
    graph: dict[str, set[str]] = {}
    for f in py_files(SRC):
        mod = module_name(f)
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            graph[mod] = set()
            continue
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imports.add(a.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import
                    base = mod.rsplit(".", 1)[0]
                    for _ in range(node.level - 1):
                        base = base.rsplit(".", 1)[0]
                    imports.add(
                        f"{base}.{node.module}" if node.module else base
                    )
                elif node.module:
                    imports.add(node.module)
        graph[mod] = {i for i in imports if i.startswith("yuleosh")}
    return graph


def reachable_modules(seeds: set[str], graph: dict[str, set[str]]) -> set[str]:
    """Modules reachable from seeds following imports forward."""
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        m = stack.pop()
        if m in seen:
            continue
        seen.add(m)
        for imp in graph.get(m, ()):  # m imports imp
            if imp not in seen:
                stack.append(imp)
    return seen


def main() -> int:
    changed = [Path(a).resolve() for a in sys.argv[1:]]
    seeds = {module_name(p) for p in changed if p.is_file() and str(p).startswith(str(SRC))}
    if not seeds:
        print("", end="")
        return 0

    graph = build_import_graph()
    # a test imports changed module M iff M is reachable from the test module
    closure: list[str] = []
    for tf in py_files(TESTS):
        tmod = module_name(tf).replace("tests.", "", 1) if False else None
        # tests are top-level modules; compute their name relative to repo root
        tname = ".".join(tf.relative_to(REPO).with_suffix("").parts)
        # test module names are not in graph (only src) — parse directly
        try:
            tree = ast.parse(tf.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    imports.add(a.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue  # tests don't use relative imports to src
                if node.module:
                    imports.add(node.module)
        imports = {i for i in imports if i.startswith("yuleosh")}
        if reachable_modules(imports, graph) & seeds:
            closure.append(str(tf.relative_to(REPO)))
    for c in closure:
        print(c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

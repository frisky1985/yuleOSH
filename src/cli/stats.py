#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH Stats — Project metrics summary.

Usage:
    yuleosh stats [--json]

Outputs:
    - Lines of code (total, by language)
    - Test count and pass rate
    - Spec coverage score
    - Pipeline run history
    - CI run history
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Add src for store / spec imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from store import Store


def count_source_lines(project_dir: str) -> dict:
    """Count lines of code by language."""
    langs = {
        ".py": {"label": "Python", "files": 0, "lines": 0},
        ".sh": {"label": "Shell", "files": 0, "lines": 0},
        ".html": {"label": "HTML", "files": 0, "lines": 0},
        ".css": {"label": "CSS", "files": 0, "lines": 0},
        ".js": {"label": "JavaScript", "files": 0, "lines": 0},
        ".c": {"label": "C", "files": 0, "lines": 0},
        ".h": {"label": "C Header", "files": 0, "lines": 0},
        ".cpp": {"label": "C++", "files": 0, "lines": 0},
        ".hpp": {"label": "C++ Header", "files": 0, "lines": 0},
        ".toml": {"label": "TOML", "files": 0, "lines": 0},
        ".md": {"label": "Markdown", "files": 0, "lines": 0},
        ".yml": {"label": "YAML", "files": 0, "lines": 0},
        ".yaml": {"label": "YAML", "files": 0, "lines": 0},
        ".json": {"label": "JSON", "files": 0, "lines": 0},
    }

    src_dir = Path(project_dir) / "src"
    test_dir = Path(project_dir) / "tests"

    EXCLUDED_DIRS = {"self", ".osh", "__pycache__", ".git", "node_modules", "venv", ".venv"}

    for base_dir in [src_dir, test_dir]:
        if not base_dir.exists():
            continue
        for root, dirs, files in os.walk(base_dir):
            # Skip hidden dirs, caches, and dogfooding/OSH artifacts
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
            for f in files:
                ext = Path(f).suffix
                stat_info = langs.get(ext)
                if stat_info is None:
                    continue
                filepath = Path(root) / f
                try:
                    line_count = len(filepath.read_text().splitlines())
                    stat_info["files"] += 1
                    stat_info["lines"] += line_count
                except Exception as e:
                    import logging; logging.getLogger("cli.stats").warning("File read: %s", e)
                    pass

    total_files = sum(v["files"] for v in langs.values())
    total_lines = sum(v["lines"] for v in langs.values())
    active_langs = {k: v for k, v in langs.items() if v["files"] > 0}

    # Also check docs directory
    docs_dir = Path(project_dir) / "docs"
    doc_files = 0
    doc_lines = 0
    if docs_dir.exists():
        for f in docs_dir.rglob("*.md"):
            try:
                doc_lines += len(f.read_text().splitlines())
                doc_files += 1
            except Exception as e:
                import logging; logging.getLogger("cli.stats").warning("Doc read: %s", e)
                pass

    return {
        "total_files": total_files + doc_files,
        "total_lines": total_lines + doc_lines,
        "source_files": total_files,
        "source_lines": total_lines,
        "doc_files": doc_files,
        "doc_lines": doc_lines,
        "languages": active_langs,
    }


def count_tests(project_dir: str) -> dict:
    """Count test files and test functions, excluding self/ and .osh/ directories."""
    test_dir = Path(project_dir) / "tests"
    if not test_dir.exists():
        return {"test_files": 0, "test_functions": 0, "test_functions_by_file": {}}

    test_functions = 0
    by_file = {}

    import re
    EXCLUDED_DIRS = {"self", ".osh", "__pycache__"}
    for root, dirs, files in os.walk(test_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
        for f in sorted(files):
            if f.endswith(".py") and not f.startswith("_"):
                filepath = Path(root) / f
                try:
                    content = filepath.read_text()
                    funcs = re.findall(r'^def (test_\w+)\(', content, re.MULTILINE)
                    class_funcs = re.findall(r'^\s+def (test_\w+)\(', content, re.MULTILINE)
                    all_funcs = funcs + class_funcs
                    test_functions += len(all_funcs)
                    rel = str(Path(root).relative_to(test_dir) / f)
                    if all_funcs:
                        by_file[rel] = len(all_funcs)
                except Exception as e:
                    import logging; logging.getLogger("cli.stats").warning("Func parse: %s", e)
                    pass

    return {
        "test_files": len(by_file),
        "test_functions": test_functions,
        "test_functions_by_file": by_file,
    }


def compute_spec_coverage(project_dir: str) -> dict:
    """Compute spec coverage from docs/spec.md."""
    spec_path = Path(project_dir) / "docs" / "spec.md"
    if not spec_path.exists():
        return {"score": 0, "requirements": 0, "scenarios": 0, "message": "No spec.md found"}

    try:
        sys.path.insert(0, str(Path(project_dir) / "src" / "spec"))
        from validate import parse_spec, validate_spec, _compute_coverage

        doc = parse_spec(str(spec_path))
        issues = validate_spec(doc)
        coverage = _compute_coverage(doc)

        return {
            "score": coverage["score"],
            "requirements": len(doc.requirements),
            "scenarios": len(doc.scenarios),
            "total_shall": sum(len(r.shall) for r in doc.requirements),
            "error_count": sum(1 for i in issues if i["severity"] == "ERROR"),
            "warn_count": sum(1 for i in issues if i["severity"] == "WARN"),
            "issues": len(issues),
            "pass_threshold": coverage["pass_threshold"],
        }
    except Exception as e:
        return {"score": 0, "requirements": 0, "message": f"Error: {e}"}


def count_pipeline_runs(project_dir: str) -> dict:
    """Count historical pipeline runs."""
    sessions_dir = Path(project_dir) / ".osh" / "sessions"
    if not sessions_dir.exists():
        return {"total_runs": 0, "completed": 0, "failed": 0, "recent_runs": []}

    runs = {"completed": 0, "failed": 0, "total_runs": 0}
    recent = []

    for d in sorted(sessions_dir.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        session_file = d / "session.json"
        if not session_file.exists():
            continue
        try:
            data = json.loads(session_file.read_text())
            status = data.get("status", "unknown")
            if status == "completed":
                runs["completed"] += 1
            elif status == "failed":
                runs["failed"] += 1
            runs["total_runs"] += 1

            if len(recent) < 5:
                recent.append({
                    "name": data.get("name", d.name),
                    "status": status,
                    "created_at": data.get("created_at", ""),
                    "steps": len(data.get("steps", [])),
                })
        except Exception as e:
            import logging; logging.getLogger("cli.stats").warning("Session read: %s", e)
            pass

    runs["recent_runs"] = recent
    return runs


def count_ci_runs(project_dir: str) -> dict:
    """Count CI pipeline runs."""
    ci_dir = Path(project_dir) / ".osh" / "ci"
    if not ci_dir.exists():
        return {"total_runs": 0, "by_layer": {}, "passed": 0, "failed": 0}

    by_layer = {"1": 0, "2": 0, "3": 0}
    passed = 0
    failed = 0
    total = 0

    for f in sorted(ci_dir.glob("layer*.json")):
        try:
            data = json.loads(f.read_text())
            layer = data.get("layer", 0)
            status = data.get("status", "unknown")
            layer_key = str(layer)
            if layer_key in by_layer:
                by_layer[layer_key] += 1
            if status == "passed":
                passed += 1
            elif status == "failed":
                failed += 1
            total += 1
        except Exception as e:
            import logging; logging.getLogger("cli.stats").warning("CI read: %s", e)
            pass

    return {"total_runs": total, "by_layer": by_layer, "passed": passed, "failed": failed}


def cmd_stats(project_dir: str = None, to_json: bool = False):
    """Show project statistics."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    # Gather metrics
    loc = count_source_lines(project_dir)
    tests = count_tests(project_dir)
    spec = compute_spec_coverage(project_dir)
    pipelines = count_pipeline_runs(project_dir)
    ci_runs = count_ci_runs(project_dir)

    result = {
        "project": os.path.basename(project_dir),
        "project_dir": project_dir,
        "source_code": loc,
        "tests": tests,
        "spec_coverage": spec,
        "pipeline_runs": pipelines,
        "ci_runs": ci_runs,
    }

    if to_json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        _print_stats_human(result)

    return result


def _print_stats_human(stats: dict):
    loc = stats["source_code"]
    tests = stats["tests"]
    spec = stats["spec_coverage"]
    pipelines = stats["pipeline_runs"]
    ci = stats["ci_runs"]

    print(f"\n📊 yuleOSH Project Statistics")
    print(f"{'='*50}")
    print(f"  Project: {stats['project']}")
    print(f"  Directory: {stats['project_dir']}")
    print()

    # Source code
    print(f"📝 Source Code")
    print(f"  Total files:   {loc['total_files']}")
    print(f"  Total lines:   {loc['total_lines']}")
    print(f"  Source files:  {loc['source_files']} ({loc['source_lines']} lines)")
    print(f"  Doc files:     {loc['doc_files']} ({loc['doc_lines']} lines)")
    if loc.get("languages"):
        langs = sorted(loc["languages"].items(), key=lambda x: x[1]["lines"], reverse=True)
        print(f"  Languages:")
        for ext, info in langs:
            bar = "█" * max(1, info["lines"] // max(1, max(v["lines"] for _, v in langs)) * 20)
            print(f"    {info['label']:<14} {info['files']:>3} files, {info['lines']:>5} lines  {bar}")
    print()

    # Tests
    print(f"🧪 Tests")
    print(f"  Test files:    {tests['test_files']}")
    print(f"  Test functions: {tests['test_functions']}")
    if tests.get("test_functions_by_file"):
        print(f"  Per file:")
        for fname, count in sorted(tests["test_functions_by_file"].items()):
            print(f"    {fname}: {count} test(s)")
    print()

    # Spec coverage
    print(f"📋 Spec Coverage")
    print(f"  Score:         {spec.get('score', 'N/A')}% {'✅ PASS' if spec.get('pass_threshold') else '❌ FAIL'}")
    print(f"  Requirements:  {spec.get('requirements', 0)}")
    print(f"  Scenarios:     {spec.get('scenarios', 0)}")
    print(f"  Total SHALLs:  {spec.get('total_shall', 0)}")
    print(f"  Issues:        {spec.get('issues', 0)} ({spec.get('error_count', 0)} errors, {spec.get('warn_count', 0)} warnings)")
    print()

    # Pipeline runs
    print(f"🔄 Pipeline Runs")
    print(f"  Total:         {pipelines['total_runs']}")
    print(f"  Completed:     {pipelines.get('completed', 0)}")
    print(f"  Failed:        {pipelines.get('failed', 0)}")
    if pipelines.get("recent_runs"):
        print(f"  Recent:")
        for r in pipelines["recent_runs"]:
            icon = "✅" if r["status"] == "completed" else "❌"
            print(f"    {icon} {r['name']} [{r['steps']} steps] — {r['created_at']}")
    print()

    # CI runs
    print(f"🔬 CI Runs")
    print(f"  Total:         {ci['total_runs']}")
    print(f"  Passed:        {ci['passed']}")
    print(f"  Failed:        {ci['failed']}")
    for layer, count in sorted(ci.get("by_layer", {}).items()):
        print(f"  Layer {layer}:    {count} run(s)")
    print()


def main():
    to_json = "--json" in sys.argv
    project_dir = None
    args = [a for a in sys.argv[1:] if a != "--json"]

    if len(args) > 0:
        project_dir = args[0]

    cmd_stats(project_dir, to_json)


if __name__ == "__main__":
    main()

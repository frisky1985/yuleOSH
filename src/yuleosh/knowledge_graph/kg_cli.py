#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Knowledge Graph CLI — yuleosh kg commands (P1).

Provides CLI for incremental build, snapshot management, and impact analysis.

Commands:
  yuleosh kg build                     — Incremental build (CI mode)
  yuleosh kg bootstrap                 — Full bootstrap from traceability data
  yuleosh kg snapshot list             — List graph snapshots
  yuleosh kg snapshot diff A B         — Diff two snapshots
  yuleosh kg query impact <file>       — Impact analysis for changed file(s)

Log output is written to knowledge-graph/ directory under the project root.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from yuleosh.knowledge_graph.store import KGStore
from yuleosh.knowledge_graph.queries import impact_analysis, list_snapshots, get_graph_stats, get_aspice_coverage

log = logging.getLogger("yuleosh.knowledge_graph.kg_cli")

# ── Helpers ─────────────────────────────────────────────────────────────

_LOG_DIR = "knowledge-graph"


def _get_store(project_dir: str, kwargs: Optional[dict] = None) -> KGStore:
    """Get a KG store, auto-selecting backend based on YULEOSH_DB_URL."""
    from yuleosh.knowledge_graph import get_store
    store_kwargs = dict(kwargs or {})
    if "db_path" not in store_kwargs:
        store_kwargs["db_path"] = str(Path(project_dir) / ".yuleosh" / "knowledge_graph.db")
    return get_store(**store_kwargs)


def _ensure_log_dir(project_dir: str) -> Path:
    """Create the knowledge-graph log directory if it doesn't exist."""
    log_dir = Path(project_dir) / _LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def _write_log(project_dir: str, filename: str, content: str):
    """Write content to a knowledge-graph log file."""
    log_dir = _ensure_log_dir(project_dir)
    path = log_dir / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


def _get_changed_files_from_git(base_ref: str = "HEAD~1") -> list[str]:
    """Get changed files from git diff against a base ref."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref],
            capture_output=True, text=True, check=False, timeout=30,
        )
        if result.returncode == 0:
            files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
            return files
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning("Git diff failed: %s", e)

    return []


# ═══════════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════════


def cmd_build(args):
    """yuleosh kg build — Incremental knowledge graph build.

    Detects changed files from git diff (or takes explicit --files),
    runs incremental bootstrap, and saves log to knowledge-graph/.
    """
    project_dir = getattr(args, "project_dir", os.environ.get("OSH_HOME", os.getcwd()))
    store = _get_store(project_dir)

    # Determine changed files
    changed_files = []
    if getattr(args, "files", None):
        changed_files = [f.strip() for f in args.files.split(",") if f.strip()]
    elif getattr(args, "auto", False) or args.auto:
        ref = getattr(args, "base_ref", "HEAD~1")
        changed_files = _get_changed_files_from_git(ref)
    elif getattr(args, "ci", False):
        # CI mode: try git HEAD~1 first, then fall back to empty
        changed_files = _get_changed_files_from_git("HEAD~1")

    # Also take positional files if provided
    if getattr(args, "positional_files", None):
        changed_files.extend(args.positional_files)

    changed_files = list(set(changed_files))
    changed_files.sort()

    if not changed_files:
        log.info("No changed files detected; running full bootstrap")
        changed_files = None

    # Generate build_id
    build_id = getattr(args, "build_id", None)
    if not build_id:
        build_id = f"kg-build-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    log.info("KG build starting: build_id=%s, changed_files=%s",
             build_id, f"{len(changed_files)} files" if changed_files else "full bootstrap")

    # Clean any existing spec_diff/code_results in the KG from prior builds
    if changed_files:
        from yuleosh.knowledge_graph.spec_diff import (
            detect_spec_files_in_changes, analyze_spec_file_changes,
            apply_spec_changes_to_store,
        )
        spec_files = detect_spec_files_in_changes(changed_files)
        if spec_files:
            log.info("Detected %d spec file changes: %s", len(spec_files), spec_files)
            for spec_file in spec_files:
                full_path = os.path.join(project_dir, spec_file)
                if os.path.isfile(full_path):
                    try:
                        # Compare with git HEAD~1 version
                        from yuleosh.knowledge_graph.spec_diff import get_spec_changes_from_git
                        changes = get_spec_changes_from_git("HEAD~1", spec_file)
                        spec_result = apply_spec_changes_to_store(store, changes)
                        log.info("Spec file %s: %s", spec_file, json.dumps(spec_result))
                    except Exception as e:
                        log.warning("Failed to process spec file %s: %s", spec_file, e)

    # Run incremental bootstrap
    from yuleosh.knowledge_graph.importer import incremental_bootstrap
    result = incremental_bootstrap(
        store,
        project_dir=project_dir,
        changed_files=changed_files,
        create_snapshot=True,
        build_id=build_id,
        snapshot_meta={
            "source": "kg_build_cli",
            "auto": getattr(args, "auto", False),
            "ci": getattr(args, "ci", False),
        },
    )

    # Apply test results if available
    if changed_files:
        from yuleosh.knowledge_graph.verify_delta import load_test_results, apply_test_results
        test_results = load_test_results(project_dir)
        if test_results:
            test_result = apply_test_results(store, test_results)
            result["test_results"] = test_result

    # Run impact analysis
    if changed_files:
        impact = impact_analysis(store, changed_files)
        result["impact"] = impact

    # Save log
    log_path = _write_log(project_dir, f"build-{build_id}.json",
                          json.dumps(result, indent=2, ensure_ascii=False, default=str))
    result["log_path"] = log_path

    # Print summary
    mode = result.get("mode", "full")
    stats = result.get("stats", {})
    summary = result.get("summary", {})
    print(f"\n  🔨 KG Build: {build_id}")
    print(f"  {'=' * 50}")
    print(f"  Mode:    {'⚡ incremental' if mode == 'incremental' else '🔄 full bootstrap'}")
    print(f"  Nodes:   {summary.get('total_nodes', stats.get('total_nodes', '?'))}")
    print(f"  Edges:   {summary.get('total_edges', stats.get('total_edges', '?'))}")
    print(f"  Log:     {log_path}")
    print()

    incremental_detail = result.get("incremental", {})
    if isinstance(incremental_detail, dict) and incremental_detail.get("changed_files", 0) > 0:
        print(f"  Changed files scanned: {incremental_detail.get('changed_files', 0)}")
        code_files = incremental_detail.get("code_files", 0)
        test_files = incremental_detail.get("test_files", 0)
        print(f"  Source files: {code_files} | Test files: {test_files}")

        # Show functions scanned
        funcs = incremental_detail.get("functions", 0)
        classes = incremental_detail.get("classes", 0)
        methods = incremental_detail.get("methods", 0)
        if funcs or classes or methods:
            print(f"  Functions: {funcs} | Classes: {classes} | Methods: {methods}")

    # Show spec changes
    spec_result = result.get("spec_changes", {})
    if spec_result:
        print(f"  Spec changes applied: "
              f"{spec_result.get('created', 0)} created, "
              f"{spec_result.get('updated', 0)} updated, "
              f"{spec_result.get('deleted', 0)} deleted")

    # Show test results
    test_res = result.get("test_results", {})
    if test_res:
        print(f"  Test results: {test_res.get('passed', 0)} passed, "
              f"{test_res.get('failed', 0)} failed, "
              f"{test_res.get('skipped', 0)} skipped")
        print(f"  Verifies edges updated: {test_res.get('verifies_updated', 0)}")
        print(f"  Covers edges updated: {test_res.get('covers_updated', 0)}")

    # Show impact
    impact = result.get("impact", {})
    if impact:
        reqs = impact.get("affected_reqs", [])
        tests = impact.get("affected_tests", [])
        if reqs:
            print(f"\n  📋 Impact Analysis:")
            print(f"  Affected requirements ({len(reqs)}):")
            for r in reqs[:10]:
                confidence = r.get("confidence", "?")
                print(f"    - {r.get('req_id', '?')} ({confidence})")
            if len(reqs) > 10:
                print(f"    ... and {len(reqs) - 10} more")
        if tests:
            print(f"  Affected tests:")
            for t in tests[:5]:
                funcs_list = ", ".join(t.get("functions", [])[:3])
                print(f"    - {t.get('file', '?')} [{funcs_list}]")
            if len(tests) > 5:
                print(f"    ... and {len(tests) - 5} more")

    return result


def cmd_bootstrap(args):
    """yuleosh kg bootstrap — Full bootstrap from traceability data."""
    project_dir = getattr(args, "project_dir", os.environ.get("OSH_HOME", os.getcwd()))
    store = _get_store(project_dir)

    from yuleosh.knowledge_graph.importer import bootstrap
    result = bootstrap(store, project_dir=project_dir, create_snapshot=True)

    # Save log
    log_path = _write_log(project_dir, "bootstrap.json",
                          json.dumps(result, indent=2, ensure_ascii=False, default=str))

    summary = result.get("summary", {})
    print(f"\n  🔨 KG Bootstrap Complete")
    print(f"  {'=' * 50}")
    print(f"  Total nodes: {summary.get('total_nodes', '?')}")
    print(f"  Total edges: {summary.get('total_edges', '?')}")
    print(f"  Log:         {log_path}")
    print()

    return result


def cmd_snapshot_list(args):
    """yuleosh kg snapshot list — List graph snapshots."""
    project_dir = getattr(args, "project_dir", os.environ.get("OSH_HOME", os.getcwd()))
    store = _get_store(project_dir)

    limit = getattr(args, "limit", 20)
    snapshots = list_snapshots(store, limit=limit)

    if not snapshots:
        print("  📭 No snapshots found")
        return {"snapshots": []}

    print(f"\n  📸 Graph Snapshots (last {len(snapshots)})")
    print(f"  {'=' * 70}")
    print(f"  {'Build ID':<35} {'Nodes':<8} {'Edges':<8} {'Built':<25}")
    print(f"  {'─' * 70}")
    for s in snapshots:
        bid = s.get("build_id", "?").ljust(35)[:35]
        nc = str(s.get("node_count", "?"))
        ec = str(s.get("edge_count", "?"))
        bt = (s.get("built_at") or "").ljust(25)[:25]
        print(f"  {bid} {nc:<8} {ec:<8} {bt}")
    print()

    return {"snapshots": snapshots, "count": len(snapshots)}


def cmd_snapshot_diff(args):
    """yuleosh kg snapshot diff A B — Compare two snapshots."""
    project_dir = getattr(args, "project_dir", os.environ.get("OSH_HOME", os.getcwd()))
    store = _get_store(project_dir)

    build_a = getattr(args, "build_a", "")
    build_b = getattr(args, "build_b", "")

    if not build_a or not build_b:
        print("  ❌ Usage: yuleosh kg snapshot diff <build_a> <build_b>", file=sys.stderr)
        return {}

    try:
        diff = store.snapshot_diff(build_a, build_b)
    except Exception as e:
        log.error("Snapshot diff failed: %s", e)
        print(f"  ❌ Failed to compute diff: {e}", file=sys.stderr)
        return {}

    print(f"\n  📊 Snapshot Diff: {build_a} → {build_b}")
    print(f"  {'=' * 60}")
    print(f"  Nodes: {len(diff.get('added_nodes', []))} added, "
          f"{len(diff.get('removed_nodes', []))} removed")
    print(f"  Count: {diff.get('node_count_a', '?')} → {diff.get('node_count_b', '?')}")
    print()

    added_nodes = diff.get("added_nodes", [])
    removed_nodes = diff.get("removed_nodes", [])
    if added_nodes:
        print(f"  ➕ Added nodes ({len(added_nodes)}):")
        for n in added_nodes[:15]:
            eid = n.get("entity_id", "?")
            etype = n.get("entity_type", "?")
            print(f"    {etype:<15} {eid}")
        if len(added_nodes) > 15:
            print(f"    ... and {len(added_nodes) - 15} more")

    if removed_nodes:
        print(f"\n  ➖ Removed nodes ({len(removed_nodes)}):")
        for n in removed_nodes[:15]:
            eid = n.get("entity_id", "?")
            etype = n.get("entity_type", "?")
            print(f"    {etype:<15} {eid}")
        if len(removed_nodes) > 15:
            print(f"    ... and {len(removed_nodes) - 15} more")

    print()
    print(f"  Summary: {diff.get('summary', 'N/A')}")

    return diff


def cmd_query_impact(args):
    """yuleosh kg query impact <file_path> — Analyze change impact.

    Runs impact analysis on the given file path(s).
    Supports single file or comma-separated multiple files.
    """
    project_dir = getattr(args, "project_dir", os.environ.get("OSH_HOME", os.getcwd()))
    store = _get_store(project_dir)

    file_path = getattr(args, "file_path", "")
    if not file_path:
        print("  ❌ Usage: yuleosh kg query impact <file_path>", file=sys.stderr)
        return {}

    # Support both single file and comma-separated multiple files
    if "," in file_path:
        changed_files = [f.strip() for f in file_path.split(",") if f.strip()]
    else:
        changed_files = [file_path]

    layer = getattr(args, "layer", None)
    result = impact_analysis(store, changed_files, layer=layer)

    reqs = result.get("affected_reqs", [])
    tests = result.get("affected_tests", [])
    functions = result.get("affected_functions", [])
    summary = result.get("impact_summary", "")
    has_low_conf = result.get("low_confidence_warning", False)

    print(f"\n  📋 Impact Analysis for: {', '.join(changed_files)}")
    print(f"  {'=' * 60}")
    print(f"  {summary}")
    if has_low_conf:
        print(f"  ⚠️  Low confidence warnings present")
    print()

    if reqs:
        print(f"  Affected Requirements ({len(reqs)}):")
        print(f"  {'─' * 55}")
        print(f"  {'ID':<20} {'Confidence':<12}")
        print(f"  {'─' * 55}")
        for r in reqs:
            rid = r.get("req_id", "?").ljust(18)[:18]
            conf = r.get("confidence", "?")
            print(f"  {rid} {conf:<12}")
        print()

    if tests:
        print(f"  Affected Tests:")
        print(f"  {'─' * 55}")
        print(f"  {'File':<35} {'Functions'}")
        print(f"  {'─' * 55}")
        for t in tests[:20]:
            fname = t.get("file", "?").ljust(33)[:33]
            funcs = ", ".join(t.get("functions", [])[:3])
            print(f"  {fname} {funcs}")
        if len(tests) > 20:
            print(f"  ... and {len(tests) - 20} more files")
        print()

    if functions:
        print(f"  Code Functions:")
        for f in functions[:10]:
            print(f"    - {f}")
        if len(functions) > 10:
            print(f"    ... and {len(functions) - 10} more")
        print()

    # Save impact report
    report_filename = f"impact-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    log_path = _write_log(project_dir, report_filename,
                          json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"  💾 Report saved: {log_path}")

    return result


def cmd_stats(args):
    """yuleosh kg stats — Show graph statistics."""
    project_dir = getattr(args, "project_dir", os.environ.get("OSH_HOME", os.getcwd()))
    store = _get_store(project_dir)

    stats = get_graph_stats(store)

    print(f"\n  📊 Knowledge Graph Statistics")
    print(f"  {'=' * 50}")
    print(f"  Total nodes:      {stats.get('total_nodes', 0)}")
    print(f"  Total edges:      {stats.get('total_edges', 0)}")

    nodes_by_type = stats.get("nodes_by_type", {})
    if nodes_by_type:
        print(f"\n  Nodes by type:")
        for ntype, count in sorted(nodes_by_type.items()):
            print(f"    {ntype:<20} {count}")

    edges_by_type = stats.get("edges_by_type", {})
    if edges_by_type:
        print(f"\n  Edges by type:")
        for etype, count in sorted(edges_by_type.items()):
            print(f"    {etype:<20} {count}")

    # Snapshot count
    snapshots = list_snapshots(store, limit=1)
    if snapshots:
        latest = snapshots[0]
        print(f"\n  Latest snapshot:")
        print(f"    Build ID: {latest.get('build_id', '?')}")
        print(f"    Built at: {latest.get('built_at', '?')}")
        print(f"    Nodes:    {latest.get('node_count', '?')}")
        print(f"    Edges:    {latest.get('edge_count', '?')}")

    print()

    return stats


# ═══════════════════════════════════════════════════════════════════════
# P2: Report Commands (KG-40-RTM, KG-METRICS)
# ═══════════════════════════════════════════════════════════════════════


def cmd_report(args):
    """yuleosh kg report — Generate RTM and metrics reports."""
    project_dir = getattr(args, "project_dir", os.environ.get("OSH_HOME", os.getcwd()))
    store = _get_store(project_dir)

    report_sub = getattr(args, "report_sub", None)

    if report_sub == "rtm":
        return _cmd_report_rtm(store, project_dir, args)
    elif report_sub == "metrics":
        return _cmd_report_metrics(store, project_dir, args)
    else:
        print("  ❌ Usage: yuleosh kg report {rtm|metrics}", file=sys.stderr)
        print("    rtm      — Generate traceability matrix")
        print("    metrics  — Generate metrics report")
        return {}


def _cmd_report_rtm(store, project_dir, args):
    """Generate RTM report."""
    from yuleosh.knowledge_graph.reporter import generate_rtm

    fmt = getattr(args, "format", "markdown")
    layer = getattr(args, "layer", None)
    output = getattr(args, "output", None)
    title = getattr(args, "title", None)

    content = generate_rtm(store, fmt=fmt, layer=layer, title=title)

    if output:
        path = Path(output)
        path.write_text(content, encoding="utf-8")
        print(f"\n  📄 RTM report saved: {path.resolve()}")
        print(f"  {'=' * 50}")
    else:
        # Print to stdout
        print(content)

    # Also save to log directory
    ext = {"markdown": "md", "html": "html", "csv": "csv"}.get(fmt, "md")
    log_filename = f"rtm-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{ext}"
    log_path = _write_log(project_dir, log_filename, content)
    print(f"  💾 Log saved: {log_path}")

    return {"format": fmt, "log_path": log_path}


def _cmd_report_metrics(store, project_dir, args):
    """Generate metrics report."""
    from yuleosh.knowledge_graph.reporter import generate_metrics, format_metrics_text

    fmt = getattr(args, "format", "text")
    trend = getattr(args, "trend", 5)
    output = getattr(args, "output", None)

    metrics = generate_metrics(store, trend_snapshots=trend)

    if fmt == "json":
        content = json.dumps(metrics, indent=2, ensure_ascii=False, default=str)
    else:
        content = format_metrics_text(metrics)

    if output:
        path = Path(output)
        path.write_text(content, encoding="utf-8")
        print(f"\n  📊 Metrics report saved: {path.resolve()}")
        print(f"  {'=' * 50}")
    else:
        print(content)

    # Also save to log directory
    ext = "json" if fmt == "json" else "md"
    log_filename = f"metrics-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{ext}"
    log_path = _write_log(project_dir, log_filename, content)
    print(f"  💾 Log saved: {log_path}")

    return metrics


# ═══════════════════════════════════════════════════════════════════════
# P2: Events Commands (KG-EVENT)
# ═══════════════════════════════════════════════════════════════════════


def cmd_events(args):
    """yuleosh kg events — Event bus operations."""
    from yuleosh.knowledge_graph.events import kg_events

    project_dir = getattr(args, "project_dir", os.environ.get("OSH_HOME", os.getcwd()))
    events_sub = getattr(args, "events_sub", None)

    if events_sub == "listen":
        return _cmd_events_listen(args, kg_events)
    elif events_sub == "history":
        return _cmd_events_history(args, kg_events)
    else:
        print("  ❌ Usage: yuleosh kg events {listen|history}", file=sys.stderr)
        print("    listen   — Listen for events (blocking, Ctrl+C to stop)")
        print("    history  — Show recent event history")
        return {}


def _cmd_events_listen(args, event_bus):
    """Listen for KG events in real-time."""
    import time

    event_filter = getattr(args, "filter", None)
    duration = getattr(args, "duration", None)

    print(f"\n  🔔 Listening for KG events...")
    if event_filter:
        print(f"  Filter: {event_filter}")
    if duration:
        print(f"  Duration: {duration}s")
    else:
        print(f"  Duration: unlimited (Ctrl+C to stop)")
    print(f"  {'=' * 50}")

    received = []

    def print_event(event):
        if event_filter and event.event_type != event_filter:
            return
        received.append(event)
        ts = event.timestamp[11:23]
        print(f"  [{ts}] {event.event_type}")
        if event.data:
            summary = json.dumps(event.data, ensure_ascii=False)[:120]
            print(f"         {summary}")

    event_bus.on("*", print_event)

    try:
        if duration:
            time.sleep(duration)
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print()
        pass
    finally:
        event_bus.off("*", print_event)

    print(f"  {'=' * 50}")
    print(f"  Received {len(received)} event(s)")
    print()

    return {"received": len(received)}


def _cmd_events_history(args, event_bus):
    """Show recent event history."""
    event_filter = getattr(args, "filter", None)
    limit = getattr(args, "limit", 50)

    history = event_bus.history(event_type=event_filter, limit=limit)

    if not history:
        print("  📭 No events found")
        return {"events": [], "count": 0}

    print(f"\n  📜 Recent Events (last {len(history)})")
    print(f"  {'=' * 60}")
    print(f"  {'Event Type':<25} {'Timestamp':<20} {'Source':<15}")
    print(f"  {'─' * 60}")
    for h in history:
        et = h.get("event_type", "?").ljust(23)[:23]
        ts = (h.get("timestamp", "") or "")[11:23].ljust(18)[:18]
        src = h.get("source", "?").ljust(13)[:13]
        print(f"  {et} {ts} {src}")
    print()

    return {"events": history, "count": len(history)}

#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH — Embedded AI Development Platform CLI

Usage:
    yuleosh init [dir]                       — Initialize project
    yuleosh template init <project-name>     — Create new project from starter template
    yuleosh spec validate <file>             — Validate OpenSpec spec
    yuleosh spec diff <old> <new>            — Diff two specs
    yuleosh pipeline run [--mock] <spec>     — Run full Agent pipeline
    yuleosh pipeline status [name]           — Show pipeline status
    yuleosh review auto                      — Auto-review changes
    yuleosh review task <name> [kind]        — Review specific task
    yuleosh ci run <layer>                   — Run CI layer (1/2/3)
    yuleosh evidence pack                    — Generate ASPICE compliance pack
    yuleosh stats [--json]                   — Show project statistics
    yuleosh ui                              — Start dashboard server (:8080)
"""

import argparse
import os
import sys
from pathlib import Path

OSH_HOME = os.environ.get(
    "OSH_HOME",
    os.path.dirname(os.path.abspath(__file__)),
)


def ensure_osh_home():
    os.environ.setdefault("OSH_HOME", OSH_HOME)


def cmd_init(dir_path: str = "."):
    """Initialize a new yuleOSH project directory."""
    target = Path(dir_path)
    dirs = [
        target / "specs",
        target / "tasks",
        target / "src",
        target / "docs",
        target / "evidence",
        target / ".osh",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print(f"✅ Initialized yuleOSH project at {target}")


def cmd_template_init(project_name: str):
    """Create a new project from the starter template."""
    from src.cli.template import cmd_template_init

    cmd_template_init(project_name, os.getcwd())


def cmd_spec_validate(filepath: str):
    from src.spec.validate import parse_spec, validate_spec

    # Use the API directly instead of mutating sys.argv
    try:
        doc = parse_spec(filepath)
        issues = validate_spec(doc)
        error_count = sum(1 for i in issues if i.get("severity") == "ERROR")
        if error_count > 0:
            print(f"❌ Spec validation failed: {error_count} error(s)")
            for i in issues:
                if i.get("severity") == "ERROR":
                    print(f"  - {i.get('message', i)}")
            sys.exit(1)
        print(f"✅ Spec validated successfully")
    except Exception as e:
        print(f"❌ Spec validation failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_spec_diff(old: str, new: str):
    from src.spec.validate import diff_specs

    try:
        result = diff_specs(old, new)
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Spec diff failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_pipeline_run(spec_path: str, mock: bool = False):
    from src.pipeline.run import run_pipeline

    session = run_pipeline(spec_path, mock=mock)
    sys.exit(0 if session.status == "completed" else 1)


def cmd_pipeline_status(name: str = None):
    from src.pipeline.run import status_pipeline

    status_pipeline(name)


def cmd_review_auto():
    from src.review.run import auto_review

    auto_review()


def cmd_review_task(task: str, kind: str = "feature"):
    import subprocess

    from src.review.run import run_review

    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True, cwd=OSH_HOME,
    )
    changed = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    run_review(task, kind, OSH_HOME, changed)


def cmd_demo_uart(target_dir: str = None, do_build: bool = False, skip_cmake: bool = False):
    """Create and run the STM32+ESP32 UART demo project."""
    from src.cli.commands.demo_uart import cmd_demo_uart

    sys.exit(cmd_demo_uart(target_dir, do_build, skip_cmake))


def cmd_ci_run(layer: str):
    from src.ci.run import run_layer1, run_layer2, run_layer3

    layers = {"1": run_layer1, "2": run_layer2, "3": run_layer3}
    handler = layers.get(layer)
    if not handler:
        print(f"❌ Unknown CI layer: {layer}", file=sys.stderr)
        sys.exit(1)

    success = handler()
    sys.exit(0 if success else 1)


def cmd_evidence_pack():
    from src.evidence.pack import generate_evidence

    generate_evidence()


def cmd_stats(json_output: bool = False):
    from src.cli.stats import cmd_stats

    cmd_stats(to_json=json_output)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the yuleOSH CLI."""
    parser = argparse.ArgumentParser(
        prog="yuleosh",
        description="yuleOSH — Embedded AI Development Platform CLI",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = sub.add_parser("init", help="Initialize a yuleOSH project directory")
    p_init.add_argument("dir", nargs="?", default=".", help="Project directory")

    # template
    p_template = sub.add_parser("template", help="Project template management")
    tsub = p_template.add_subparsers(dest="template_sub")
    p_template_init = tsub.add_parser("init", help="Create project from template")
    p_template_init.add_argument("project_name", help="Project name")

    # spec
    p_spec = sub.add_parser("spec", help="OpenSpec management")
    ssub = p_spec.add_subparsers(dest="spec_sub")
    p_spec_val = ssub.add_parser("validate", help="Validate an OpenSpec file")
    p_spec_val.add_argument("file", help="Spec file path")
    p_spec_diff = ssub.add_parser("diff", help="Diff two OpenSpec files")
    p_spec_diff.add_argument("old", help="Old spec file")
    p_spec_diff.add_argument("new", help="New spec file")

    # pipeline
    p_pipe = sub.add_parser("pipeline", help="Agent pipeline management")
    psub = p_pipe.add_subparsers(dest="pipeline_sub")
    p_pipe_run = psub.add_parser("run", help="Run the full Agent pipeline")
    p_pipe_run.add_argument("--mock", action="store_true", help="Run in mock mode (no real LLM)")
    p_pipe_run.add_argument("spec", help="Specification file path")
    p_pipe_status = psub.add_parser("status", help="Show pipeline status")
    p_pipe_status.add_argument("name", nargs="?", help="Pipeline session name")

    # review
    p_review = sub.add_parser("review", help="Code review management")
    rsub = p_review.add_subparsers(dest="review_sub")
    rsub.add_parser("auto", help="Auto-review recent changes")
    p_review_task = rsub.add_parser("task", help="Review a specific task")
    p_review_task.add_argument("name", help="Task name")
    p_review_task.add_argument("kind", nargs="?", default="feature", help="Task kind")

    # ci
    p_ci = sub.add_parser("ci", help="CI pipeline management")
    csub = p_ci.add_subparsers(dest="ci_sub")
    p_ci_run = csub.add_parser("run", help="Run a CI layer")
    p_ci_run.add_argument("layer", help="CI layer (1/2/3)")

    # evidence
    sub.add_parser("evidence", help="Generate ASPICE compliance evidence")

    # stats
    p_stats = sub.add_parser("stats", help="Show project statistics")
    p_stats.add_argument("--json", action="store_true", help="Output as JSON")

    # demo
    p_demo = sub.add_parser("demo", help="Create and run demo projects")
    dsub = p_demo.add_subparsers(dest="demo_sub")
    p_demo_uart = dsub.add_parser("uart", help="STM32F4 ↔ ESP32 UART communication demo")
    p_demo_uart.add_argument("--dir", default=None, help="Target directory for the demo project")
    p_demo_uart.add_argument("--build", action="store_true", help="Build and run the demo after creating it")
    p_demo_uart.add_argument("--skip-cmake", action="store_true", help="Skip CMake environment check")

    # ui
    sub.add_parser("ui", help="Start the web dashboard")

    return parser


def main():
    ensure_osh_home()

    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Dispatch
    if args.command == "init":
        cmd_init(args.dir)
    elif args.command == "template":
        if args.template_sub == "init":
            cmd_template_init(args.project_name)
        else:
            parser.print_help()
            sys.exit(1)
    elif args.command == "spec":
        if args.spec_sub == "validate":
            cmd_spec_validate(args.file)
        elif args.spec_sub == "diff":
            cmd_spec_diff(args.old, args.new)
        else:
            parser.print_help()
            sys.exit(1)
    elif args.command == "pipeline":
        if args.pipeline_sub == "run":
            cmd_pipeline_run(args.spec, mock=args.mock)
        elif args.pipeline_sub == "status":
            cmd_pipeline_status(args.name)
        else:
            parser.print_help()
            sys.exit(1)
    elif args.command == "review":
        if args.review_sub == "auto":
            cmd_review_auto()
        elif args.review_sub == "task":
            cmd_review_task(args.name, args.kind)
        else:
            parser.print_help()
            sys.exit(1)
    elif args.command == "demo":
        if args.demo_sub == "uart":
            cmd_demo_uart(args.dir, args.build, args.skip_cmake)
        else:
            parser.print_help()
            sys.exit(1)
    elif args.command == "ci":
        if args.ci_sub == "run":
            cmd_ci_run(args.layer)
        else:
            parser.print_help()
            sys.exit(1)
    elif args.command == "evidence":
        cmd_evidence_pack()
    elif args.command == "stats":
        cmd_stats(json_output=args.json)
    elif args.command == "ui":
        from src.ui.server import main as ui_main
        ui_main()


if __name__ == "__main__":
    main()

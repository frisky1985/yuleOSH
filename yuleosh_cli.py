#!/usr/bin/env python3
"""
yuleOSH — 嵌入式AI开发全流程平台 CLI

Usage:
    yuleosh init [dir]                       — Initialize project
    yuleosh template init <project-name>     — Create new project from starter template
    yuleosh spec validate <file>             — Validate OpenSpec spec
    yuleosh spec diff <old> <new>            — Diff two specs
    yuleosh pipeline run <spec>              — Run full Agent pipeline
    yuleosh pipeline status [name]           — Show pipeline status
    yuleosh review auto                      — Auto-review changes
    yuleosh review task <name> [kind]        — Review specific task
    yuleosh ci run <layer>                   — Run CI layer (1/2/3)
    yuleosh evidence pack                    — Generate ASPICE compliance pack
    yuleosh stats [--json]                   — Show project statistics
"""

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
    from src.spec.validate import main as spec_main

    # Rewrite argv for the submodule
    sys.argv = ["validate", filepath]
    spec_main()


def cmd_spec_diff(old: str, new: str):
    from src.spec.diff import main as diff_main

    sys.argv = ["diff", old, new]
    diff_main()


def cmd_pipeline_run(spec_path: str):
    from src.pipeline.run import run_pipeline

    session = run_pipeline(spec_path)
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


def main():
    ensure_osh_home()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd in ("help", "--help", "-h"):
        print(__doc__)
        return

    # yuleosh init
    if cmd == "init":
        cmd_init(sys.argv[2] if len(sys.argv) > 2 else ".")
        return

    # yuleosh template
    if cmd == "template":
        if len(sys.argv) < 3:
            print("Usage: yuleosh template init <project-name>", file=sys.stderr)
            sys.exit(1)
        subcmd = sys.argv[2]
        if subcmd == "init":
            if len(sys.argv) < 4:
                print("Usage: yuleosh template init <project-name>", file=sys.stderr)
                sys.exit(1)
            cmd_template_init(sys.argv[3])
        else:
            print(f"Unknown template command: {subcmd}", file=sys.stderr)
            sys.exit(1)
        return

    # yuleosh stats
    if cmd == "stats":
        to_json = "--json" in sys.argv
        cmd_stats(to_json)
        return

    # yuleosh spec
    if cmd == "spec":
        if len(sys.argv) < 3:
            print("Usage: yuleosh spec validate|diff <args>", file=sys.stderr)
            sys.exit(1)
        subcmd = sys.argv[2]
        if subcmd == "validate":
            if len(sys.argv) < 4:
                print("Usage: yuleosh spec validate <file>", file=sys.stderr)
                sys.exit(1)
            cmd_spec_validate(sys.argv[3])
        elif subcmd == "diff":
            if len(sys.argv) < 5:
                print("Usage: yuleosh spec diff <old> <new>", file=sys.stderr)
                sys.exit(1)
            cmd_spec_diff(sys.argv[3], sys.argv[4])
        else:
            print(f"Unknown spec command: {subcmd}", file=sys.stderr)
            sys.exit(1)
        return

    # yuleosh pipeline
    if cmd == "pipeline":
        if len(sys.argv) < 3:
            print("Usage: yuleosh pipeline run|status", file=sys.stderr)
            sys.exit(1)
        subcmd = sys.argv[2]
        if subcmd == "run":
            if len(sys.argv) < 4:
                print("Usage: yuleosh pipeline run <spec>", file=sys.stderr)
                sys.exit(1)
            cmd_pipeline_run(sys.argv[3])
        elif subcmd == "status":
            cmd_pipeline_status(sys.argv[3] if len(sys.argv) > 3 else None)
        else:
            print(f"Unknown pipeline command: {subcmd}", file=sys.stderr)
            sys.exit(1)
        return

    # yuleosh review
    if cmd == "review":
        if len(sys.argv) < 3:
            print("Usage: yuleosh review auto|task", file=sys.stderr)
            sys.exit(1)
        subcmd = sys.argv[2]
        if subcmd == "auto":
            cmd_review_auto()
        elif subcmd == "task":
            if len(sys.argv) < 4:
                print("Usage: yuleosh review task <name> [kind]", file=sys.stderr)
                sys.exit(1)
            cmd_review_task(sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "feature")
        else:
            print(f"Unknown review command: {subcmd}", file=sys.stderr)
            sys.exit(1)
        return

    # yuleosh ci
    if cmd == "ci":
        if len(sys.argv) < 3:
            print("Usage: yuleosh ci run <layer>", file=sys.stderr)
            sys.exit(1)
        subcmd = sys.argv[2]
        if subcmd == "run":
            if len(sys.argv) < 4:
                print("Usage: yuleosh ci run <layer>", file=sys.stderr)
                sys.exit(1)
            cmd_ci_run(sys.argv[3])
        else:
            print(f"Unknown ci command: {subcmd}", file=sys.stderr)
            sys.exit(1)
        return

    # yuleosh evidence
    if cmd == "evidence":
        cmd_evidence_pack()
        return

    # yuleosh ui
    if cmd == "ui":
        from src.ui.server import main as ui_main

        ui_main()
        return

    print(f"Unknown command: {cmd}", file=sys.stderr)
    print(__doc__)
    sys.exit(1)


if __name__ == "__main__":
    main()

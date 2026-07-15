# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Ultra-Plan CLI — integrated into yuleosh plan subcommand.

Usage:
    yuleosh plan "Write unit tests for BCM door module"   — Generate a plan
    yuleosh plan --apply                                   — Execute the last plan
    yuleosh plan --list                                    — List saved plans
    yuleosh plan --show <id>                               — Show a specific plan
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from yuleosh.plan import PlanAgent, Plan, PlanStep


PLANS_DIR = Path(".yuleosh") / "plans"


def _get_latest_plan_id(project_dir: str) -> Optional[str]:
    """Get the most recent plan ID from the plans directory."""
    plans_path = Path(project_dir) / PLANS_DIR
    if not plans_path.is_dir():
        return None
    plan_files = sorted(plans_path.glob("plan-*.json"), reverse=True)
    if not plan_files:
        return None
    return plan_files[0].stem.replace("plan-", "")


def _load_plan(project_dir: str, plan_id: str) -> Optional[Plan]:
    """Load a plan from disk by ID."""
    plan_path = Path(project_dir) / PLANS_DIR / f"plan-{plan_id}.json"
    if not plan_path.exists():
        return None
    with open(plan_path, encoding="utf-8") as f:
        data = json.load(f)
    return Plan.from_dict(data)


def _save_plan(project_dir: str, plan: Plan) -> str:
    """Save a plan to disk and return its ID."""
    plans_path = Path(project_dir) / PLANS_DIR
    plans_path.mkdir(parents=True, exist_ok=True)
    plan_id = plan.title.lower().replace(" ", "-")[:48]
    plan_path = plans_path / f"plan-{plan_id}.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan.to_dict(), f, ensure_ascii=False, indent=2)
    return plan_id


def build_plan_subparser(subparsers):
    """Add the 'plan' subcommand parser."""
    plan_parser = subparsers.add_parser("plan", help="Ultra-Plan: generate structured implementation plans")
    plan_parser.add_argument(
        "description",
        nargs="*",
        help="Natural-language task description (e.g. 'add HIL tests for BCM')",
    )
    plan_parser.add_argument(
        "--apply", "-a",
        action="store_true",
        help="Execute the generated plan via CheckpointEngine",
    )
    plan_parser.add_argument(
        "--list", "-l",
        action="store_true",
        dest="list_plans",
        help="List saved plans",
    )
    plan_parser.add_argument(
        "--show",
        type=str,
        nargs="?",
        const="latest",
        help="Show a specific plan (default: latest)",
    )
    plan_parser.add_argument(
        "--json",
        action="store_true",
        help="Output plan as JSON (instead of Markdown)",
    )
    plan_parser.add_argument(
        "--project-dir",
        default=os.environ.get("OSH_HOME", "."),
        help="Project root directory",
    )


def handle_plan_command(args: argparse.Namespace) -> int:
    """Route plan subcommand to the appropriate handler."""
    project_dir = os.path.abspath(args.project_dir)

    # --list: list saved plans
    if args.list_plans:
        return _handle_list(project_dir)

    # --show: show a specific plan
    if args.show:
        plan_id = args.show if args.show != "latest" else _get_latest_plan_id(project_dir)
        if not plan_id:
            print("📭  No saved plans found.")
            return 1
        plan = _load_plan(project_dir, plan_id)
        if not plan:
            print(f"❌  Plan '{plan_id}' not found.")
            return 1
        agent = PlanAgent(project_dir)
        print(agent.to_markdown(plan))
        return 0

    # --apply: execute the latest plan
    if args.apply:
        return _handle_apply(project_dir)

    # Default: generate a plan from description
    description = " ".join(args.description) if args.description else ""
    if not description:
        print("❌  Please provide a task description or use --apply/--list/--show")
        print("   Usage: yuleosh plan 'task description'")
        print("          yuleosh plan --apply")
        print("          yuleosh plan --list")
        return 1

    return _handle_generate(project_dir, description, args.json)


def _handle_generate(project_dir: str, description: str, as_json: bool) -> int:
    """Generate a plan from a task description."""
    try:
        agent = PlanAgent(project_dir)
        plan = agent.plan(description)

        # Save to disk
        plan_id = _save_plan(project_dir, plan)
        print(f"  📋 Plan saved: plan-{plan_id}.json\n", file=sys.stderr)

        if as_json:
            print(agent.to_json(plan))
        else:
            print(agent.to_markdown(plan))

        print(f"\n  {'─' * 50}", file=sys.stderr)
        print(f"  💡 Run `yuleosh plan --apply` to execute this plan", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"❌  Plan generation failed: {e}", file=sys.stderr)
        return 1


def _handle_apply(project_dir: str) -> int:
    """Execute the latest plan via CheckpointEngine."""
    plan_id = _get_latest_plan_id(project_dir)
    if not plan_id:
        print("📭  No saved plans found. Generate one first with `yuleosh plan '...'`")
        return 1

    plan = _load_plan(project_dir, plan_id)
    if not plan:
        print(f"❌  Plan '{plan_id}' not found.")
        return 1

    print(f"\n  🚀 Executing Plan: {plan.title}\n", file=sys.stderr)

    try:
        from yuleosh.plan.output import to_pipeline_steps
        steps = to_pipeline_steps(plan)
    except ImportError:
        steps = []

    if not steps:
        print("  ⚠️  No pipeline-compatible steps found. Printing plan instead:\n")
        agent = PlanAgent(project_dir)
        print(agent.to_markdown(plan))
        return 0

    print(f"  ✅ Plan approved! Injecting {len(steps)} steps into CheckpointEngine...\n", file=sys.stderr)

    try:
        from yuleosh.engine.checkpoint import CheckpointEngine
        engine = CheckpointEngine(f"plan-{plan_id}", project_dir)
        for step in steps:
            engine.add_step(
                step_id=step.get("step_id", f"step-{len(engine._step_defs)}"),
                name=step.get("name", "Unnamed"),
                handler=None,
                agent=step.get("agent"),
            )

        result = engine.run()
        if result:
            print(f"\n  ✅ Plan '{plan.title}' executed successfully!", file=sys.stderr)
        else:
            print(f"\n  ⚠️  Plan '{plan.title}' completed with issues. Check pipeline status.", file=sys.stderr)
        return 0 if result else 1

    except Exception as e:
        print(f"❌  Execution failed: {e}", file=sys.stderr)
        return 1


def _handle_list(project_dir: str) -> int:
    """List saved plans."""
    plans_path = Path(project_dir) / PLANS_DIR
    if not plans_path.is_dir():
        print("📭  No saved plans found.")
        return 0

    plan_files = sorted(plans_path.glob("plan-*.json"))
    if not plan_files:
        print("📭  No saved plans found.")
        return 0

    print(f"\n📋 Saved Plans ({len(plan_files)}):\n")
    for pf in plan_files:
        try:
            with open(pf, encoding="utf-8") as f:
                data = json.load(f)
            title = data.get("title", "Untitled")
            status = data.get("status", "unknown")
            steps = len(data.get("steps", []))
            effort = data.get("total_effort_hours", 0)
            print(f"  {pf.stem.replace('plan-', ''):32s}  {title:40s}  {status:10s}  {steps} steps  {effort:.1f}h")
        except Exception:
            print(f"  {pf.name:32s}  <unreadable>")

    return 0

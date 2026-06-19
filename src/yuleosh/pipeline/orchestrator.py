#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Pipeline Orchestrator — run_pipeline entry point, session status,
and CLI entry point (main).

Import chain:  orchestrator -> stages -> session
"""

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from yuleosh.pipeline.session import PipelineSession, PipelineStepError

log = logging.getLogger("pipeline.orchestrator")

# Notifications (optional import)
_notify = None
try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from notify import notify_pipeline
    _notify = notify_pipeline
except ImportError:
    _notify = None

def run_pipeline(spec_path: str, name: Optional[str] = None, llm_client: Optional[Callable] = None,
                mock: bool = False, profile: Optional[str] = None):
    """Run the full OSH pipeline for a given spec.
    
    Args:
        spec_path: Path to the specification file.
        name: Optional session name (auto-generated if None).
        llm_client: Optional injected LLM callable for testing.
            When provided, all LLM-dependent steps use this callable
            instead of the global ``chat_completion``.
        mock: If True, skip LLM key check (for demo/testing).
        profile: Optional profile name override (default: from ci-config.yaml or "safety").
    """

    # Deferred import from run shim so that test mocks on
    # yuleosh.pipeline.run.PIPELINE_STEPS and run._check_llm_key take effect.
    from yuleosh.pipeline.run import PIPELINE_STEPS as _steps, _check_llm_key as _check_key

    # Check for LLM API key before starting (skip when a mock/injected client is provided)
    if not mock and llm_client is None:
        key = _check_key()
        if not key:
            sys.exit(1)
    
    # G-33: Profile validation
    try:
        from yuleosh.ci.profile import validate_active_profile, filter_steps_for_profile, get_current_profile
        project_dir = os.environ.get("OSH_HOME", os.path.dirname(os.path.abspath(spec_path)))
        active_profile = profile or get_current_profile(project_dir)
        valid, msg = validate_active_profile(project_dir)
        if not valid:
            print(f"\n⚠️  Profile validation: {msg}")
            print("   Falling back to 'safety' profile.")
            active_profile = "safety"
        else:
            print(f"\n📋 Active profile: '{active_profile}' ({msg})")
        _steps = filter_steps_for_profile(_steps, active_profile, project_dir)
        if not _steps:
            print("\n❌ No steps remaining after profile filtering!")
            sys.exit(1)
    except ImportError:
        active_profile = "safety"
        log.info("Profile module not available, using all steps")
    except Exception as e:
        log.warning("Profile validation skipped: %s", e)
        active_profile = "safety"

    try:
        if name is None:
            name = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        session = PipelineSession(name, spec_path, llm_client=llm_client)
        session.profile = active_profile
        print(f"\n🚀 Pipeline started: {name}")
        print(f"   Spec: {spec_path}")
        print(f"   Profile: {active_profile}")
        print(f"   Session: {session.session_dir}")
        print()
        
        log.info(f"Pipeline starting: {name}, spec={spec_path}, profile={active_profile}")
        
        for step_key, agent, step_name, handler in _steps:
            step_idx = len(session.steps)
            session.add_step(step_key, agent, step_name)
            session.start_step(step_idx)
            
            print(f"  [{step_idx+1}/{len(_steps)}] {agent}: {step_name}")
            log.info(f"Step {step_idx+1}/{len(_steps)}: [{agent}] {step_name}")
            
            try:
                # Set status to completed before the final report step
                # so the report captures the correct status
                if step_key == "final-report":
                    session.status = "completed"
                output_path = handler(session)
                session.complete_step(step_idx, str(output_path))
                session.set_artifact(step_key, str(output_path))
                # Persist immediately after the final-report step completes
                # to eliminate the race condition between setting status and
                # the deferred save at the end of the loop.
                if step_key == "final-report":
                    session._save()
                log.info(f"Step {step_idx+1} completed: {step_key}")
                print()
            except Exception as e:
                log.error(f"Step {step_idx+1} [{agent}] {step_name} failed: {e}")
                log.debug(traceback.format_exc())
                session.fail_step(step_idx, str(e))
                print(f"  ❌ Step failed: {e}")
                print()
                break
        
        if session.status != "failed":
            session._save()
        
        print(f"\n{'='*50}")
        if session.status == "completed":
            print(f"Pipeline: {session.status} 🎉")
        else:
            print(f"Pipeline: {session.status} ❌")
        print(f"Session: {session.session_dir}")
        print(f"Errors: {len(session.errors)}")
        print()
        
        log.info(f"Pipeline finished: {session.status}, errors={len(session.errors)}")

        # Token usage summary
        if session.token_usage_total > 0:
            step_tokens = [
                f"  {s['step']}: {s['usage'].get('total_tokens', 0)} tokens"
                for s in session.token_usage_steps
            ]
            log.info(
                "Pipeline token usage: %d total tokens across %d LLM calls:\n%s",
                session.token_usage_total,
                len(session.token_usage_steps),
                "\n".join(step_tokens),
            )
            print(f"\n📊 Token Usage: {session.token_usage_total} total tokens "
                  f"({len(session.token_usage_steps)} LLM calls)")
            for s in session.token_usage_steps:
                u = s["usage"]
                print(f"   {s['step']}: {u.get('total_tokens', 0)} tokens "
                      f"(prompt {u.get('prompt_tokens', 0)}, "
                      f"completion {u.get('completion_tokens', 0)})")

        # Send notification on pipeline completion or failure
        if _notify:
            try:
                _notify(
                    name=session.name,
                    status=session.status,
                    total_steps=len(_steps),
                    completed_steps=sum(1 for s in session.steps if s.get("status") == "completed"),
                    errors=session.errors,
                )
            except Exception as ne:
                log.warning(f"Notification failed: {ne}")

        return session
    except Exception as e:
        log.critical(f"Pipeline orchestrator crashed: {e}")
        print(f"\n❌ Pipeline orchestrator crashed: {e}", file=sys.stderr)
        sys.exit(1)


def status_pipeline(name: Optional[str] = None) -> None:
    """Display pipeline session status(es).

    Args:
        name: Optional session name. If None, lists all sessions.
    """
    base = Path(os.environ.get("OSH_HOME", ".")) / ".osh" / "sessions"
    
    sessions = []
    if name:
        sdir = base / name
        if sdir.exists():
            sessions.append(name)
    else:
        sessions = sorted([d.name for d in base.iterdir() if d.is_dir()])
    
    if not sessions:
        print("No pipeline sessions found.")
        return
    
    for sname in sessions:
        sfile = base / sname / "session.json"
        if sfile.exists():
            with open(sfile) as f:
                data = json.load(f)
            status_icon = {"completed": "✅", "running": "🔄", "failed": "❌", "created": "📋"}
            icon = status_icon.get(data["status"], "❓")
            steps_done = sum(1 for s in data["steps"] if s["status"] == "completed")
            steps_total = len(data["steps"])
            print(f"  {icon} {sname}: [{steps_done}/{steps_total}] {data['status']}")


def main():
    if len(sys.argv) < 2:
        print("Usage:", file=sys.stderr)
        print("  python3 run.py <spec.md>          — Run full pipeline", file=sys.stderr)
        print("  python3 run.py status [name]      — Show pipeline status", file=sys.stderr)
        print("  python3 run.py --profile <name> <spec.md>  — Run with specific profile", file=sys.stderr)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    try:
        if cmd == "status":
            status_pipeline(sys.argv[2] if len(sys.argv) > 2 else None)
        elif cmd == "--profile" and len(sys.argv) >= 4:
            profile_name = sys.argv[2]
            spec_path = sys.argv[3]
            session = run_pipeline(spec_path, profile=profile_name)
            sys.exit(0 if session.status == "completed" else 1)
        else:
            session = run_pipeline(cmd)
            sys.exit(0 if session.status == "completed" else 1)
    except KeyboardInterrupt:
        log.warning("Pipeline interrupted by user")
        print("\n⚠️  Pipeline interrupted by user", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        log.critical(f"Unhandled exception in pipeline: {e}")
        print(f"\n❌ Unhandled exception: {e}", file=sys.stderr)
        sys.exit(1)



if __name__ == "__main__":
    main()


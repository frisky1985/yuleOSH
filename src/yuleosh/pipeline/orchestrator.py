#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

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
from yuleosh.llm.fallback import apply_fallback_chain
from yuleosh.llm.validation import validate_llm_output

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

# ── Auto-detect project type from .yuleosh.yaml ──────────────────────

def _detect_project_type(project_dir: str) -> Optional[dict]:
    """Read .yuleosh.yaml and detect the project type (e.g. autosar).

    Returns a dict with 'type', 'name', and 'template_name' if found.
    Returns None if no config or no type field.
    """
    import yaml as _yaml
    proj_path = Path(project_dir)
    candidates = [
        proj_path / ".yuleosh.yaml",
        proj_path / "yuleosh.yaml",
        proj_path / ".yuleosh" / "config.yml",
    ]
    for cfg_file in candidates:
        if cfg_file.exists():
            try:
                raw = _yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
                if raw and isinstance(raw, dict):
                    ptype = raw.get("type") or raw.get("project", {}).get("type")
                    if ptype:
                        return {
                            "type": ptype,
                            "name": raw.get("name") or raw.get("project", {}).get("name", ptype),
                            "template_name": raw.get("template") or raw.get("project", {}).get("template", ptype),
                            "config_source": str(cfg_file),
                        }
            except Exception as e:
                log.debug("Could not parse %s: %s", cfg_file, e)
    return None


def _ensure_autosar_pipeline_config(project_dir: str, template_dir: Optional[Path] = None) -> bool:
    """If project type is autosar and no `.yuleosh/ci-config.yaml` exists,
    copy the template pipeline config.

    Returns True if a config was generated.
    """
    ci_config = Path(project_dir) / ".yuleosh" / "ci-config.yaml"
    if ci_config.exists():
        return False  # Already configured

    if template_dir is None:
        # Try built-in template path
        template_dir = Path(os.path.dirname(__file__)).parent.parent.parent / "templates" / "autosar"
        if not template_dir.exists():
            template_dir = Path(os.path.dirname(__file__)).parent.parent / "templates" / "autosar"

    pipeline_cfg = template_dir / "pipeline" / "config.yaml" if template_dir else None
    if pipeline_cfg and pipeline_cfg.exists():
        # Ensure .yuleosh dir exists
        (Path(project_dir) / ".yuleosh").mkdir(parents=True, exist_ok=True)
        ci_config.write_text(pipeline_cfg.read_text(encoding="utf-8"))
        log.info("Generated autosar pipeline config: %s", ci_config)
        return True

    return False


def _detect_and_bootstrap(project_dir: str) -> Optional[dict]:
    """Auto-detect project type and bootstrap missing config.

    Returns the detected project info dict, or None if not detected.
    """
    info = _detect_project_type(project_dir)
    if not info:
        return None

    ptype = info["type"]
    log.info("Detected project type: %s (name=%s)", ptype, info["name"])

    templates_base = Path(os.path.dirname(__file__)).parent.parent / "templates"
    if not templates_base.exists():
        templates_base = Path(os.path.dirname(__file__)).parent.parent.parent / "templates"

    if ptype == "autosar":
        tdir = templates_base / "autosar-classic" if templates_base.exists() else None
        if tdir and tdir.exists():
            # Register: ensure template.yaml is used
            template_yaml = tdir / "template.yaml"
            if template_yaml.exists():
                log.info("AUTOSAR template found: %s", template_yaml)
            _ensure_autosar_pipeline_config(project_dir, tdir)
        else:
            log.info("AUTOSAR template dir not found, skipping bootstrap")

    return info


# ── Agent constraints loading ──────────────────────────────────────

_DEFAULT_AGENT_SPEC = """
# Default Agent Spec (from ci-config.yaml)

## Roles
- 小明: Project Manager / Orchestrator
- 小克: Architect / Developer / Tester
- 小马: Quality Architect / Reviewer

## Core Rules
- P0/P1 issues MUST be resolved before phase completion.
- Context safety: split when > 50% context used.
- Loop Chain: fix discovered issues immediately without asking.
- Expert review required at phase completion.
"""


def load_agent_constraints(project_dir: str) -> tuple[str, str]:
    """Load agent constraints from `.yuleosh/agents/` directory.

    Reads all ``*.md`` files from ``.yuleosh/agents/`` and concatenates
    their content into a single string suitable for injection into the
    LLM system prompt.

    If the directory does not exist or is empty, falls back to the
    default agent spec from ``ci-config.yaml`` or the built-in default.

    Returns:
        Tuple of (constraints_text, source_description).
        ``source_description`` is one of:
            "agents_dir"    — loaded from .yuleosh/agents/*.md
            "ci_config"     — loaded from ci-config.yaml default_agent_spec
            "builtin_fallback" — built-in default spec
    """
    import yaml as _yaml

    agents_dir = Path(project_dir) / ".yuleosh" / "agents"

    if agents_dir.is_dir():
        md_files = sorted(agents_dir.glob("*.md"))
        if md_files:
            parts = []
            for f in md_files:
                try:
                    content = f.read_text(encoding="utf-8")
                    parts.append(f"<!-- from: {f.name} -->\n{content}")
                except Exception as e:
                    log.warning("Failed to read agent constraint %s: %s", f, e)
            if parts:
                log.info(
                    "Loaded %d agent constraint file(s) from .yuleosh/agents/",
                    len(parts),
                )
                return "\n\n".join(parts), "agents_dir"

    # Fallback: try ci-config.yaml default_agent_spec
    ci_config = Path(project_dir) / ".yuleosh" / "ci-config.yaml"
    if ci_config.exists():
        try:
            raw = _yaml.safe_load(ci_config.read_text(encoding="utf-8"))
            if raw and isinstance(raw, dict):
                default_spec = raw.get("default_agent_spec")
                if default_spec:
                    log.info(
                        "Loaded default agent spec from %s", ci_config.name
                    )
                    return str(default_spec), "ci_config"
        except Exception as e:
            log.debug("Could not parse %s for default_agent_spec: %s", ci_config, e)

    # Built-in fallback
    log.info("Using built-in default agent spec (no .yuleosh/agents/ or ci-config default)")
    return _DEFAULT_AGENT_SPEC.strip(), "builtin_fallback"


def _mock_llm_client() -> Callable:
    """Create a mock LLM client for demo/testing (--mock flag).

    Returns a function with the same signature as ``chat_completion``
    that returns a plausible OpenAI-style response dict without
    making any network calls.
    """
    import json as _json
    from datetime import datetime as _dt

    def _mock_callback(system_prompt: str, user_prompt: str, **kwargs) -> dict:
        """Mock LLM call that returns a canned response.

        Returns a flat dict with ``content`` at the top level,
        matching what yuleOSH pipeline step handlers expect
        (``result["content"]``).
        """
        content = (
            f"# Mock Response — yuleOSH --mock mode\n\n"
            f"**Generated at**: {_dt.now().isoformat()}\n\n"
            f"This is a mock LLM response generated by the ``--mock`` flag.\n\n"
            f"### Notes\n"
            f"- The pipeline ran in mock mode — no real LLM was called.\n"
            f"- All steps will produce placeholder outputs.\n"
            f"- Use a real API key (``LLM_API_KEY``) for production runs.\n"
            f"- Token usage statistics are simulated (1000 tokens per call)."
        )
        return {
            "content": content,
            "model": "mock-mode",
            "usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            },
        }

    return _mock_callback


def run_pipeline(spec_path: str, name: Optional[str] = None, llm_client: Optional[Callable] = None,
                mock: bool = False, profile: Optional[str] = None):
    """Run the full OSH pipeline for a given spec.
    
    Args:
        spec_path: Path to the specification file.
        name: Optional session name (auto-generated if None).
        llm_client: Optional injected LLM callable for testing.
            When provided, all LLM-dependent steps use this callable
            instead of the global ``chat_completion``.
        mock: If True, run with a fake LLM that returns placeholder
            responses — no API key needed (for demo/testing).
        profile: Optional profile name override (default: from ci-config.yaml or "safety").
    """

    # Deferred import from run shim so that test mocks on
    # yuleosh.pipeline.run.PIPELINE_STEPS and run._check_llm_key take effect.
    from yuleosh.pipeline.run import PIPELINE_STEPS as _steps, _check_llm_key as _check_key

    # When --mock is used, create a fake LLM client and inject it
    if mock:
        if llm_client is None:
            llm_client = _mock_llm_client()
        print("\n🧪 Pipeline running in MOCK mode — no real LLM will be called.\n")
    elif llm_client is None:
        # Check for LLM API key before starting
        key = _check_key()
        if not key:
            sys.exit(1)
    
    # ── Auto-detect project type and bootstrap ──
    project_root = os.path.dirname(os.path.abspath(spec_path))
    project_info = _detect_and_bootstrap(project_root)
    if project_info:
        print(f"\n📋 Detected project: {project_info['name']} (type: {project_info['type']})")
        if project_info["type"] == "autosar":
            print(f"   AUTOSAR template auto-loaded from: {project_info.get('config_source', 'template')}")

    # ── Load agent constraints from .yuleosh/agents/ ──
    agent_constraints, constraints_source = load_agent_constraints(project_root)
    if agent_constraints:
        source_labels = {
            "agents_dir": "📋 Agent constraints loaded from .yuleosh/agents/",
            "ci_config": "📋 Agent constraints loaded from ci-config.yaml default",
            "builtin_fallback": "📋 Agent constraints: built-in default",
        }
        label = source_labels.get(constraints_source, "📋 Agent constraints loaded")
        print(f"   {label}")

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
        
        session = PipelineSession(
            name,
            spec_path,
            llm_client=llm_client,
            agent_constraints=agent_constraints,
        )
        # D3: allow enabling generate-code mode via env (no code changes).
        env_dev_mode = os.environ.get("OSH_DEVELOPMENT_MODE", "").strip()
        if env_dev_mode:
            session.development_mode = env_dev_mode
            print(f"   📝 development_mode from env: {env_dev_mode}")
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
                # Run step handler
                if step_key == "final-report":
                    session.status = "completed"

                # --- LLM Fallback Integration ---
                # Wrap handler call so that if it uses an LLM, the
                # fallback chain is applied to validate the output.
                output_path = _run_step_with_fallback(
                    handler, session, step_key, step_name, spec_path,
                )

                session.complete_step(step_idx, str(output_path))
                session.set_artifact(step_key, str(output_path))
                if step_key == "final-report":
                    session._save()
                log.info(f"Step {step_idx+1} completed: {step_key}")
                print()
            except (PipelineStepError, RuntimeError) as e:
                log.error(f"Step {step_idx+1} [{agent}] {step_name} failed: {e}")
                log.debug(traceback.format_exc())
                session.fail_step(step_idx, str(e))
                print(f"  ❌ Step failed: {e}")
                print()
                # Block dependent steps: no more steps run after failure
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


# ------------------------------------------------------------------
# LLM Fallback Integration
# ------------------------------------------------------------------


def _run_step_with_fallback(
    handler: Callable,
    session: PipelineSession,
    step_key: str,
    step_name: str,
    spec_path: str,
) -> str:
    """Run a pipeline step handler with LLM output validation and fallback.

    The handler is called normally.  Afterward, if the output looks like
    LLM-generated content (contains certain markers or is structured),
    the fallback chain validates it.

    If the handler raises an exception, it's caught and surfaced as a
    PipelineStepError, which blocks dependent steps.
    """
    try:
        output_path = handler(session)
        return str(output_path)
    except Exception as e:
        log.error("Step [%s] handler raised: %s", step_key, e)
        log.debug(traceback.format_exc())

        # Attempt template fallback
        fallback_result = apply_fallback_chain(
            step_name=step_key,
            llm_output="",
            template_ctx={"title": step_name},
            session_dir=session.session_dir,
            start_level=4,  # Skip straight to template
        )

        if fallback_result.status == "fallback":
            # Write the template fallback output
            fallback_path = session.session_dir / f"{step_key}-fallback.md"
            fallback_path.write_text(fallback_result.output)
            log.info("Step [%s] used template fallback: %s", step_key, fallback_path)
            return str(fallback_path)

        raise PipelineStepError(f"Step [{step_key}] failed: {e}") from e


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


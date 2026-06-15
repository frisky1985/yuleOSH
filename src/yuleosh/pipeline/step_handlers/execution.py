#!/usr/bin/env python3
# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Execution step handlers — architecture, development, test planning, self-test.

Exports:
  step_claude_arch      — AI-powered architecture design
  step_claude_dev       — AI-powered development planning
  step_test_planning    — AI-powered test planning
  step_claude_test      — self-test with real test runner output
"""

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

from yuleosh.pipeline.session import PipelineSession, PipelineStepError
from yuleosh.pipeline.stages import timed_step, _call_llm, _parse_spec
from yuleosh.pipeline.prompts import (
    build_architecture_prompt,
    build_development_prompt,
    build_test_planning_prompt,
)

log = logging.getLogger("pipeline.step_handlers.execution")

__all__ = ["step_claude_arch", "step_claude_dev", "step_test_planning", "step_claude_test"]


@timed_step
def step_claude_arch(session: PipelineSession) -> str:
    """Step 4: Claude — AI-powered architecture design.

    Scans the project directory to discover actual source structure,
    then sends the spec + structure to the LLM for real architecture analysis.
    """
    try:
        print("  💻 [Claude] Running AI-powered architecture analysis...")
        log.info("Running AI-powered architecture analysis")

        # Discover project structure
        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()
        src_dir = project_dir / "src"

        directories = []
        source_files = []
        tech_stack = set()
        src_tree_lines = []

        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                rel_dir = Path(root).relative_to(project_dir)
                directories.append(str(rel_dir))
                indent = "  " * (len(Path(rel_dir).parts) - 1) if len(Path(rel_dir).parts) > 1 else ""
                src_tree_lines.append(f"{indent}{Path(rel_dir).name}/")
                for f in sorted(files):
                    if f.endswith((".py", ".sh", ".html", ".js", ".css", ".ts", ".go", ".rs", ".json", ".toml", ".yaml", ".yml", ".md")):
                        source_files.append(str(Path(rel_dir) / f))
                        src_tree_lines.append(f"{indent}  {f}")
                        ext = Path(f).suffix
                        if ext == ".py":
                            tech_stack.add("Python")
                        elif ext == ".go":
                            tech_stack.add("Go")
                        elif ext == ".rs":
                            tech_stack.add("Rust")
                        elif ext in (".html", ".js", ".css", ".ts"):
                            tech_stack.add("Web (HTML/JS/CSS)")
                        elif ext == ".sh":
                            tech_stack.add("Shell")

        # Read spec
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # Read key source files for context
        key_file_snippets = []
        for sf in sorted(source_files)[:15]:
            fpath = project_dir / sf
            if fpath.exists() and fpath.stat().st_size < 10000:
                try:
                    content = fpath.read_text()[:2000]
                    key_file_snippets.append(f"### {sf}\n```\n{content}\n```")
                except Exception:
                    pass

        tech_stack_str = ", ".join(sorted(tech_stack)) if tech_stack else "Python"
        tree_str = "\n".join(src_tree_lines[:80])

        system_prompt, user_prompt = build_architecture_prompt(
            spec_content=spec_content,
            spec_name=spec_path.name,
            session_name=session.name,
            directories=directories,
            source_files=source_files,
            tech_stack=sorted(tech_stack),
            source_tree_str=tree_str,
            key_file_snippets=key_file_snippets,
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt)
        except Exception as e:
            log.error(f"LLM call failed during architecture analysis: {e}")
            raise PipelineStepError(
                f"Architecture analysis LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        analysis = result["content"]
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "architecture", "usage": usage})

        out_path = session.session_dir / "architecture.md"
        try:
            out_path.write_text(analysis)
        except OSError as e:
            log.error(f"Cannot write architecture: {e}")
            raise PipelineStepError(f"Cannot write architecture: {e}")
        print(f"  ✅ [Claude] AI architecture analysis at {out_path}")
        log.info(f"AI architecture analysis saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Architecture step failed: {e}")
        raise PipelineStepError(f"Architecture step failed: {e}")


@timed_step
def step_claude_dev(session: PipelineSession) -> str:
    """Step 5: Claude — AI-powered development planning.

    Reads spec content + architecture analysis from artifacts,
    sends to LLM, and generates a real development plan with
    task breakdown and tech debt identification.
    """
    try:
        print("  💻 [Claude] Running AI-powered development planning...")
        log.info("Running AI-powered development planning")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # --- Gather project metrics (git stats + line counts) ---
        git_log = ""
        git_commits = 0
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10", "--format=%h %s (%ar)"],
                capture_output=True, text=True, timeout=10, cwd=project_dir
            )
            if result.returncode == 0:
                git_log = result.stdout.strip()
                git_commits = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
        except Exception as e:
            log.warning(f"Git log failed (non-fatal): {e}")
            git_log = "(not a git repository or git not available)"

        src_lines = 0
        test_lines = 0
        src_files = list(project_dir.glob("src/**/*.py")) + list(project_dir.glob("src/**/*.sh")) + list(project_dir.glob("src/**/*.html"))
        test_files = list(project_dir.glob("tests/**/*.py"))

        for f in src_files:
            try:
                src_lines += len(f.read_text().splitlines())
            except Exception:
                pass
        for f in test_files:
            try:
                test_lines += len(f.read_text().splitlines())
            except Exception:
                pass

        # --- Read spec content ---
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # --- Read artifacts ---
        architecture_content = artifacts_read(session.artifacts, "architecture")
        prd_content = artifacts_read(session.artifacts, "prd")
        super_content = artifacts_read(session.artifacts, "super-analysis")

        # --- Build LLM prompt ---
        system_prompt, user_prompt = build_development_prompt(
            spec_content=spec_content,
            spec_name=Path(session.spec_path).name,
            architecture_content=architecture_content,
            prd_content=prd_content,
            super_analysis_content=super_content,
            src_lines=src_lines,
            src_file_count=len(src_files),
            test_lines=test_lines,
            test_file_count=len(test_files),
            git_commits=git_commits,
            git_log=git_log,
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
        except Exception as e:
            log.error(f"LLM call failed during development planning: {e}")
            raise PipelineStepError(
                f"Development planning LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        plan = result["content"]
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "development", "usage": usage})

        full_output = (
            f"# Development Plan: {session.name}\n\n"
            f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
            f"> Source spec: {session.spec_path}\n"
            f"> Tokens: {usage.get('total_tokens', '?')} "
            f"(prompt {usage.get('prompt_tokens', '?')} + "
            f"completion {usage.get('completion_tokens', '?')})\n\n"
            f"{plan}"
        )

        out_path = session.session_dir / "development-plan.md"
        try:
            out_path.write_text(full_output)
        except OSError as e:
            log.error(f"Cannot write development plan: {e}")
            raise PipelineStepError(f"Cannot write development plan: {e}")
        print(f"  ✅ [Claude] AI development plan at {out_path}")
        log.info(f"AI development plan saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Development step failed: {e}")
        raise PipelineStepError(f"Development step failed: {e}")


@timed_step
def step_test_planning(session: PipelineSession) -> str:
    """Step 6: Claude — AI-powered test planning.

    Reads spec + architecture + development plan from artifacts,
    sends to LLM, and generates a comprehensive test plan with
    strategy, requirement traceability matrix, and coverage targets.
    """
    try:
        print("  📋 [Claude] Running AI-powered test planning...")
        log.info("Running AI-powered test planning")

        # --- Gather inputs ---
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"
        parsed = _parse_spec(session.spec_path)
        requirements = parsed["requirements"]

        # Artifacts from prior steps
        architecture_content = artifacts_read(session.artifacts, "architecture")
        dev_plan_content = artifacts_read(session.artifacts, "development")

        # --- Build prompt ---
        system_prompt, user_prompt = build_test_planning_prompt(
            spec_content=spec_content,
            requirements=requirements,
            architecture_content=architecture_content,
            development_plan_content=dev_plan_content,
        )

        # --- Call LLM ---
        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
        except Exception as e:
            log.error(f"LLM call failed during test planning: {e}")
            raise PipelineStepError(
                f"Test planning LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        plan = result["content"]
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )
        session.token_usage_total += usage.get("total_tokens", 0)
        session.token_usage_steps.append({"step": "test-planning", "usage": usage})

        total_shall = sum(len(r.get("shall_statements", [])) for r in requirements)
        full_output = (
            f"# Test Plan: {session.name}\n\n"
            f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
            f"> Source spec: {session.spec_path}\n"
            f"> Requirements: {len(requirements)}  |  SHALLs: {total_shall}\n"
            f"> Tokens: {usage.get('total_tokens', '?')} "
            f"(prompt {usage.get('prompt_tokens', '?')} + "
            f"completion {usage.get('completion_tokens', '?')})\n\n"
            f"{plan}"
        )

        out_path = session.session_dir / "test-plan.md"
        try:
            out_path.write_text(full_output)
        except OSError as e:
            log.error(f"Cannot write test plan: {e}")
            raise PipelineStepError(f"Cannot write test plan: {e}")
        print(f"  ✅ [Claude] AI test plan generated at {out_path}")
        log.info(f"AI test plan saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Test planning step failed: {e}")
        raise PipelineStepError(f"Test planning step failed: {e}")


@timed_step
def step_claude_test(session: PipelineSession) -> str:
    """Step 7: Claude — Self-test with real test runner output.

    Runs pytest or go test to get actual test results, parse them,
    and write a meaningful test report.
    """
    try:
        print("  🧪 [Claude] Self-testing...")
        log.info("Running self-test step")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # Try pytest first
        test_output = ""
        test_summary = ""
        passed = 0
        failed = 0
        total = 0
        is_python = True

        # Check if go.mod exists for Go project
        has_go = (project_dir / "go.mod").exists()

        if has_go:
            is_python = False
            try:
                result = subprocess.run(
                    ["go", "test", "./...", "-count=1"],
                    capture_output=True, text=True, timeout=120, cwd=project_dir
                )
                test_output = result.stdout + "\n" + result.stderr
                for line in result.stdout.split("\n"):
                    if line.startswith("ok "):
                        passed += 1
                        total += 1
                    elif line.startswith("FAIL "):
                        failed += 1
                        total += 1
                test_summary = f"Go test: {total} packages, {passed} passed, {failed} failed"
            except FileNotFoundError:
                log.warning("Go not installed \u2014 tests cannot run")
                test_summary = "Go not installed \u2014 tests skipped"
            except subprocess.TimeoutExpired:
                log.warning("Go tests timed out")
                test_summary = "Go tests timed out"
            except Exception as e:
                log.warning(f"Go test error: {e}")
                test_summary = f"Go test error: {e}"
        else:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "tests/", "-q", "--ignore=tests/test_e2e.py"],
                    capture_output=True, text=True, timeout=120, cwd=project_dir
                )
                test_output = result.stdout + "\n" + result.stderr
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if "passed" in line or "failed" in line:
                        test_summary = line
                        m = re.search(r"(\d+) passed", line)
                        if m:
                            passed = int(m.group(1))
                        m = re.search(r"(\d+) failed", line)
                        if m:
                            failed = int(m.group(1))
                        total = passed + failed
                if not test_summary:
                    test_summary = f"pytest completed (exit code {result.returncode})"
            except FileNotFoundError:
                log.warning("pytest not installed \u2014 tests cannot run")
                test_summary = "pytest not installed \u2014 tests skipped"
            except subprocess.TimeoutExpired:
                log.warning("Tests timed out")
                test_summary = "Tests timed out"
            except Exception as e:
                log.warning(f"Test error: {e}")
                test_summary = f"Test error: {e}"

        # Read spec scenarios for mapping
        spec_scenarios = []
        spec_path = Path(session.spec_path)
        if spec_path.exists():
            try:
                content = spec_path.read_text()
                current_scenario = ""
                for line in content.split("\n"):
                    if line.strip().startswith("### ") and "GIVEN" in line.upper():
                        if current_scenario:
                            spec_scenarios.append(current_scenario)
                        current_scenario = line.strip().replace("### ", "")
                if current_scenario:
                    spec_scenarios.append(current_scenario)
            except Exception:
                pass

        status_icon = "\u2705" if failed == 0 else "\u274c"
        runner = "pytest" if is_python else "go test"

        out_path = session.session_dir / "self-test-report.md"
        content = f"""# Self-Test Report: {session.name}

## Test Runner
- **Runner**: {runner}
- **Total Tests**: {total}
- **Passed**: {passed}
- **Failed**: {failed}
- **Status**: {status_icon}

## Test Summary
```
{test_summary}
```

## Test Output
```
{test_output[:2000]}
```

## Spec Scenarios ({len(spec_scenarios)})
"""
        for s in spec_scenarios:
            content += f"- {s}\n"

        content += """
## Coverage Note
Run CI Layer 1 to generate detailed coverage metrics for compliance.
"""
        try:
            out_path.write_text(content)
        except OSError as e:
            log.error(f"Cannot write test report: {e}")
            raise PipelineStepError(f"Cannot write test report: {e}")
        print(f"  \u2705 [Claude] Self-test report at {out_path}")
        log.info(f"Self-test report saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Self-test step failed: {e}")
        raise PipelineStepError(f"Self-test step failed: {e}")


# ---------------------------------------------------------------------------
# Internal helper: read artifact content from session artifacts dict
# ---------------------------------------------------------------------------


def artifacts_read(artifacts: dict[str, str], key: str) -> str | None:
    """Read the content of a prior-step artifact if it exists.

    Returns the content string, or None if the artifact key is absent
    or the file does not exist or cannot be read.
    """
    if key in artifacts:
        p = Path(artifacts[key])
        if p.exists():
            try:
                return p.read_text()
            except Exception:
                pass
    return None

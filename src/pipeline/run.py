#!/usr/bin/env python3
"""
OSH Pipeline Engine — Agent orchestration pipeline.

Routes tasks through:
  小明 (PM) → Hermes (Product/Review) → Claude (Arch/Dev)
  
Follows Harness Engineering SOP flow.
"""

import functools
import json
import logging
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

# Notifications (optional import)
_notify = None
try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from notify import notify_pipeline
    _notify = notify_pipeline
except ImportError:
    _notify = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")

# Add src to path for store import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from llm.client import chat_completion  # noqa: E402

# Local imports
from pipeline.prompts import build_test_planning_prompt  # noqa: E402
try:
    from store import Store
    _store = Store()
except Exception:
    _store = None

# Step base classes (refactored — replaces duplicated step handler boilerplate)
try:
    from pipeline.steps import get_step_instance  # noqa: E402
    _have_step_classes = True
except ImportError:
    _have_step_classes = False


# ------------------------------------------------------------------
# Exception classes — no silent degradation
# ------------------------------------------------------------------

class PipelineStepError(RuntimeError):
    """Raised when a pipeline step encounters a hard failure.

    Replaces silent degradation (try/except/pass) with an explicit,
    interruptible error that stops the pipeline.
    """
    pass


# ------------------------------------------------------------------
# Timing / profiling decorator
# ------------------------------------------------------------------


def timed_step(handler):
    """Decorate a step handler to measure and log execution time."""
    @functools.wraps(handler)
    def wrapper(session):
        t0 = time.perf_counter()
        try:
            result = handler(session)
            elapsed = time.perf_counter() - t0
            log.info(f"Step {handler.__name__} took {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - t0
            log.info(f"Step {handler.__name__} FAILED after {elapsed:.3f}s")
            raise
    return wrapper


# ------------------------------------------------------------------
# Spec cache — stores parsed results in SQLite keyed by path+mtime
# ------------------------------------------------------------------


def _get_spec_mtime(spec_path: str) -> float:
    """Return file mtime for cache invalidation."""
    try:
        return Path(spec_path).stat().st_mtime
    except OSError:
        return 0.0


class PipelineSession:
    """Represents a running pipeline session."""
    
    def __init__(
        self,
        name: str,
        spec_path: str,
        llm_client: Optional[Callable] = None,
    ):
        self.name = name
        self.spec_path = str(Path(spec_path).resolve())
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.status = "created"  # created → running → completed | failed
        self.current_step = 0
        self.steps: list[dict] = []
        self.artifacts: dict = {}
        self.errors: list[str] = []
        self.session_dir = self._ensure_session_dir()
        self.llm_client = llm_client

    def _ensure_session_dir(self) -> Path:
        """Ensure the session directory exists and return its path."""
        base = Path(os.environ.get("OSH_HOME", "."))
        sdir = base / ".osh" / "sessions" / self.name
        sdir.mkdir(parents=True, exist_ok=True)
        return sdir

    def add_step(self, step_name: str, agent: str, action: str) -> dict:
        """Add a new step to the pipeline and return it."""
        step = {
            "step": len(self.steps) + 1,
            "name": step_name,
            "agent": agent,
            "action": action,
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "output_path": None,
            "errors": [],
        }
        self.steps.append(step)
        return step

    def start_step(self, step_idx: int) -> None:
        """Mark a step as running and record the start timestamp."""
        if step_idx < len(self.steps):
            self.steps[step_idx]["status"] = "running"
            self.steps[step_idx]["started_at"] = datetime.now().isoformat()
            self.current_step = step_idx
            self._save(persist=False)

    def complete_step(self, step_idx: int, output_path: str) -> None:
        """Mark a step as completed with its output path."""
        if step_idx < len(self.steps):
            self.steps[step_idx]["status"] = "completed"
            self.steps[step_idx]["completed_at"] = datetime.now().isoformat()
            self.steps[step_idx]["output_path"] = output_path
            self.updated_at = datetime.now().isoformat()
            self._save(persist=False)

    def fail_step(self, step_idx: int, error: str) -> None:
        """Fail a step, record the error, and set session status to failed."""
        if step_idx < len(self.steps):
            self.steps[step_idx]["status"] = "failed"
            self.steps[step_idx]["completed_at"] = datetime.now().isoformat()
            self.steps[step_idx]["errors"].append(error)
            self.errors.append(error)
            self.status = "failed"
            self.updated_at = datetime.now().isoformat()
            self._save()

    def set_artifact(self, key: str, path: str) -> None:
        """Register a generated artifact and persist session state."""
        self.artifacts[key] = str(path)
        self._save(persist=False)

    def _save(self, persist: bool = True) -> None:
        """Persist session state to disk (JSON) and SQLite store.
        
        Args:
            persist: If True, write to disk & store.  Set False for
                     intermediate calls to avoid file I/O churn.
        """
        if not persist:
            return
        data = self.to_dict()
        with open(self.session_dir / "session.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Also persist to SQLite
        if _store:
            try:
                _store.save_pipeline(self.name, data)
            except Exception as e:
                log.warning(f"Store save_pipeline failed (non-fatal): {e}")

    def to_dict(self) -> dict:
        """Serialize session to a dictionary for storage."""
        return {
            "name": self.name,
            "spec_path": self.spec_path,
            "status": self.status,
            "current_step": self.current_step,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": self.steps,
            "artifacts": self.artifacts,
            "errors": self.errors,
        }


# --- LLM call helper (DI support) ---


def _call_llm(
    session: PipelineSession,
    system_prompt: str,
    user_prompt: str,
    **kwargs,
) -> dict:
    """Call LLM using the session's injected client or fall back to global chat_completion.

    This is the single point of dependency injection for LLM calls in pipeline steps.
    Tests can inject a mock via ``PipelineSession(llm_client=mock_fn)``.
    """
    client = session.llm_client if session.llm_client is not None else chat_completion
    return client(system_prompt, user_prompt, **kwargs)


# --- Step Handlers ---

@timed_step
def step_spec_check(session: PipelineSession) -> str:
    """Step 0: 小明 — OpenSpec 合规检查"""
    try:
        print("  🔍 [小明] Validating OpenSpec...")
        log.info(f"Validating spec: {session.spec_path}")
        result = subprocess.run(
            [sys.executable, "src/spec/validate.py", session.spec_path, "--json"],
            capture_output=True, text=True, cwd=os.environ.get("OSH_HOME", "."),
        )
        out_path = session.session_dir / "spec-check.json"
        with open(out_path, "w") as f:
            f.write(result.stdout if result.stdout else result.stderr)
        
        if result.returncode != 0:
            err_msg = result.stderr or result.stdout or "Unknown error"
            log.error(f"Spec validation failed (exit {result.returncode}): {err_msg[:200]}")
            raise PipelineStepError(f"Spec validation failed:\n{err_msg}")
        
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            log.error(f"Spec check output is not valid JSON: {e}")
            raw_preview = result.stdout[:500] if result.stdout else "(empty output)"
            raise PipelineStepError(
                f"Spec check output is not valid JSON: {e}\n"
                f"Raw output (first 500 chars):\n{raw_preview}"
            )
        
        if data.get("error_count", 0) > 0:
            issues = [i["message"] for i in data.get("issues", []) if i["severity"] == "ERROR"]
            for iss in issues:
                log.error(f"Spec error: {iss}")
            raise PipelineStepError(f"Spec has {data['error_count']} error(s): {'; '.join(issues)}")
        
        print(f"  ✅ [小明] Spec validated: {data['coverage']['score']}% coverage")
        log.info(f"Spec validated: {data['coverage']['score']}% coverage")
        return str(out_path)
    except subprocess.TimeoutExpired:
        log.error("Spec validation timed out")
        raise PipelineStepError("Spec validation timed out")
    except subprocess.CalledProcessError as e:
        log.error(f"Spec validation subprocess failed: {e}")
        raise PipelineStepError(f"Spec validation subprocess failed: {e}")
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Spec validation unexpected error: {e}")
        raise PipelineStepError(f"Spec validation unexpected error: {e}")


def _parse_spec(spec_path: str) -> dict:
    """Parse spec file: returns requirements + scenarios, cached via SQLite.

    Cache is invalidated when the spec file's mtime changes.
    """
    mtime = _get_spec_mtime(spec_path)

    # Try cache hit
    if _store:
        try:
            cached = _store.get_cached_spec_parse(spec_path, mtime)
            if cached is not None:
                return cached
        except Exception as e:
            log.warning(f"Spec cache read failed (will re-parse): {e}")

    # Parse fresh
    requirements = _parse_requirements(spec_path)
    scenarios = _parse_scenarios(spec_path)
    result = {"requirements": requirements, "scenarios": scenarios}

    # Store in cache
    if _store:
        try:
            _store.cache_spec_parse(spec_path, mtime, result)
        except Exception as e:
            log.warning(f"Spec cache write failed (non-fatal): {e}")

    return result


def _parse_requirements(spec_path: str) -> list[dict]:
    """Read requirements from a spec file. Each requirement is a dict with name and shall_statements."""
    requirements = []
    try:
        path = Path(spec_path)
        if not path.exists():
            log.warning(f"Spec file not found: {spec_path}")
            return requirements
        content = path.read_text()
        lines = content.split("\n")
        current_name = None
        current_shalls = []
        in_requirement = False
        for line in lines:
            stripped = line.strip()
            # Detect requirement header: ### Req-XXX:
            if stripped.startswith("### ") and "Req-" in stripped:
                if current_name:
                    requirements.append({
                        "name": current_name,
                        "shall_statements": current_shalls
                    })
                current_name = stripped.replace("### ", "")
                current_shalls = []
                in_requirement = True
            elif in_requirement and stripped.startswith("-") and ("SHALL" in stripped or "SHOULD" in stripped):
                current_shalls.append(stripped)
            elif in_requirement and stripped.startswith("### ") and "Req-" not in stripped:
                # End of requirement, next section (Scenario or other)
                in_requirement = False
        if current_name:
            requirements.append({
                "name": current_name,
                "shall_statements": current_shalls
            })
    except Exception as e:
        log.warning(f"Failed to parse requirements from {spec_path}: {e}")
    return requirements


def _parse_scenarios(spec_path: str) -> list[str]:
    """Read GIVEN/WHEN/THEN scenarios from a spec file."""
    scenarios = []
    try:
        path = Path(spec_path)
        if not path.exists():
            log.warning(f"Spec file not found for scenarios: {spec_path}")
            return scenarios
        content = path.read_text()
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("### ") and ("GIVEN" in stripped or "WHEN" in stripped or "THEN" in stripped):
                scenarios.append(stripped.replace("### ", ""))
    except Exception as e:
        log.warning(f"Failed to parse scenarios from {spec_path}: {e}")
    return scenarios


@timed_step
def step_super_analysis(session: PipelineSession) -> str:
    """Step 1: 小明 — S.U.P.E.R analysis powered by real LLM."""
    try:
        print("  📊 [小明] Running AI-powered S.U.P.E.R analysis...")
        log.info("Running AI-powered S.U.P.E.R analysis")

        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"
        parsed = _parse_spec(session.spec_path)
        requirements = parsed["requirements"]
        scenarios = parsed["scenarios"]
        total_shall = sum(len(r.get("shall_statements", [])) for r in requirements)

        system_prompt = (
            "You are a senior product analyst. Perform a S.U.P.E.R. analysis of the given "
            "OpenSpec specification document. Analyze: S (Situation — project context), "
            "U (Understanding — key requirements and intent), "
            "P (Problem — core objectives), "
            "E (Execution — how to deliver), "
            "R (Resources — tools, frameworks, skills needed), and "
            "P (Priority — P0/P1/P2 grouping of requirements). "
            "Output a well-structured Markdown report."
        )
        user_prompt = (
            f"# Specification: {spec_path.name}\n\n"
            f"```markdown\n{spec_content[:12000]}\n```\n\n"
            f"## Parsed Metadata\n"
            f"- Requirements found: {len(requirements)}\n"
            f"- Total SHALL statements: {total_shall}\n"
            f"- Scenarios found: {len(scenarios)}\n\n"
            f"Write a complete S.U.P.E.R. analysis as Markdown. "
            f"Use the parsed metadata above as a starting point but enrich it "
            f"with genuine insights derived from the spec content."
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt)
        except Exception as e:
            log.error(f"LLM call failed during S.U.P.E.R analysis: {e}")
            raise PipelineStepError(
                f"S.U.P.E.R analysis LLM call failed: {e}\n"
                f"Spec: {session.spec_path}\n"
                f"This error is not silently degraded — the pipeline stops here."
            )

        analysis = result["content"]
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )

        # Prepend a metadata header
        full_output = (
            f"# S.U.P.E.R Analysis: {Path(session.spec_path).stem}\n\n"
            f"> Source spec: {session.spec_path}\n"
            f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
            f"> Requirements: {len(requirements)}  |  SHALLs: {total_shall}  |  Scenarios: {len(scenarios)}\n"
            f"> Tokens: {usage.get('total_tokens', '?')} (prompt {usage.get('prompt_tokens', '?')} + completion {usage.get('completion_tokens', '?')})\n\n"
            f"{analysis}"
        )

        out_path = session.session_dir / "startup-analysis.md"
        try:
            out_path.write_text(full_output)
        except OSError as e:
            log.error(f"Cannot write analysis file: {e}")
            raise PipelineStepError(f"Cannot write analysis file: {e}")
        print(f"  ✅ [小明] AI S.U.P.E.R analysis generated at {out_path}")
        log.info(f"AI S.U.P.E.R analysis saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"S.U.P.E.R analysis failed: {e}")
        raise PipelineStepError(f"S.U.P.E.R analysis failed: {e}")


@timed_step
def step_hermes_prd(session: PipelineSession) -> str:
    """Step 2: Hermes — AI-powered PRD generation from spec.

    Reads the spec file, parses requirements and scenarios,
    then uses the LLM to produce a real Product Requirements Document.
    """
    try:
        print("  🔮 [Hermes] Running AI-powered PRD generation...")
        log.info("Running AI-powered PRD generation")

        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"
        parsed = _parse_spec(session.spec_path)
        requirements = parsed["requirements"]
        scenarios = parsed["scenarios"]
        total_shall = sum(len(r.get("shall_statements", [])) for r in requirements)

        # Read S.U.P.E.R analysis from artifacts if available
        super_content = ""
        super_key = "super-analysis"
        if super_key in session.artifacts:
            super_path = Path(session.artifacts[super_key])
            if super_path.exists():
                super_content = super_path.read_text()

        system_prompt = (
            "You are a senior product manager (Hermes). Given an OpenSpec specification "
            "document and optionally a S.U.P.E.R analysis, generate a comprehensive "
            "Product Requirements Document (PRD) in Markdown.\n\n"
            "The PRD must cover:\n"
            "1. **Product Overview** — summary of the product scope and target users\n"
            "2. **Goals & Success Metrics** — measurable objectives for this release\n"
            "3. **User Stories** — structured as GIVEN/WHEN/THEN scenarios mapped to each requirement\n"
            "4. **Functional Requirements** — mapped from each spec SHALL/SHOULD statement, "
            "with implementation notes and priority (P0/P1/P2)\n"
            "5. **Non-Functional Requirements** — performance, security, compliance\n"
            "6. **Acceptance Criteria** — how we know each requirement is done\n"
            "7. **Out of Scope** — explicitly what this release does NOT cover\n\n"
            "Be thorough and reference specific requirement names and scenario details."
        )
        user_prompt = (
            f"# Specification: {Path(session.spec_path).name}\n\n"
            f"```markdown\n{spec_content[:12000]}\n```\n\n"
            f"## Parsed Metadata\n"
            f"- Requirements found: {len(requirements)}\n"
            f"- Total SHALL/SHOULD statements: {total_shall}\n"
            f"- Scenarios found: {len(scenarios)}\n\n"
        )
        if super_content:
            user_prompt += (
                f"## S.U.P.E.R. Analysis (from prior step)\n"
                f"```markdown\n{super_content[:4000]}\n```\n\n"
            )
        user_prompt += (
            f"Write a comprehensive PRD based on the above specification. "
            f"Map each requirement to concrete user stories and acceptance criteria. "
            f"Assign priority (P0/P1/P2) to each requirement group."
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt)
        except Exception as e:
            log.error(f"LLM call failed during PRD generation: {e}")
            raise PipelineStepError(
                f"PRD generation LLM call failed: {e}\n"
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

        full_output = (
            f"# PRD: {session.name}\n\n"
            f"> Generated from spec: {session.spec_path}\n"
            f"> Generated by: LLM ({result.get('model', 'unknown')})\n"
            f"> Requirements: {len(requirements)}  |  SHALLs: {total_shall}  |  Scenarios: {len(scenarios)}\n"
            f"> Tokens: {usage.get('total_tokens', '?')} (prompt {usage.get('prompt_tokens', '?')} + completion {usage.get('completion_tokens', '?')})\n\n"
            f"{analysis}"
        )

        out_path = session.session_dir / "prd.md"
        try:
            out_path.write_text(full_output)
        except OSError as e:
            log.error(f"Cannot write PRD: {e}")
            raise PipelineStepError(f"Cannot write PRD: {e}")
        print(f"  ✅ [Hermes] AI-powered PRD generated at {out_path}")
        log.info(f"AI-powered PRD saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"PRD step failed: {e}")
        raise PipelineStepError(f"PRD step failed: {e}")


@timed_step
def step_internal_review(session: PipelineSession) -> str:
    """Step 3: 小明 — 内部评审"""
    try:
        print("  🔍 [小明] Internal review...")
        log.info("Running internal review")
        
        artifacts = session.artifacts
        report = []
        
        for key, path in artifacts.items():
            p = Path(path)
            if p.exists():
                report.append(f"✅ {key}: {path}")
            else:
                report.append(f"❌ {key}: MISSING")
                log.warning(f"Artifact missing: {key} at {path}")
        
        # Check consistency
        required = ["spec-check", "super-analysis", "prd"]
        missing = [r for r in required if r not in artifacts]
        
        if missing:
            log.error(f"Internal review failed — missing artifacts: {', '.join(missing)}")
            raise PipelineStepError(f"Internal review failed — missing artifacts: {', '.join(missing)}")
        
        out_path = session.session_dir / "review-result.md"
        try:
            out_path.write_text("\n".join(report))
        except OSError as e:
            log.error(f"Cannot write review result: {e}")
            raise PipelineStepError(f"Cannot write review result: {e}")
        print(f"  ✅ [小明] Internal review passed")
        log.info("Internal review passed")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Internal review failed: {e}")
        raise PipelineStepError(f"Internal review failed: {e}")


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

        system_prompt = (
            "You are a senior software architect. Analyze the project specification "
            "and source code structure provided. Produce a comprehensive architecture "
            "design document in Markdown covering:\n"
            "1. **Project Overview** — tech stack, module count, file count\n"
            "2. **Directory Structure** — show the tree and explain each module's role\n"
            "3. **Bounded Contexts** — domain boundaries derived from the spec\n"
            "4. **Architecture Decision Records (ADRs)** — at least 3 meaningful ADRs\n"
            "5. **Key Design Considerations** — constraints, trade-offs, patterns used\n"
            "Be specific and reference actual file paths and code elements."
        )
        user_prompt = (
            f"# Project: {session.name}\n\n"
            f"## Tech Stack\n{tech_stack_str}\n\n"
            f"## Source Tree ({len(directories)} dirs, {len(source_files)} files)\n```\n{tree_str}\n```\n\n"
            f"## Specification ({spec_path.name})\n```markdown\n{spec_content[:8000]}\n```\n\n"
            f"## Key Source File Snippets\n"
            + "\n".join(key_file_snippets[:10])
            + "\n\nWrite a comprehensive architecture document."
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

        total_lines = 0
        src_lines = 0
        test_lines = 0
        src_files = list(project_dir.glob("src/**/*.py")) + list(project_dir.glob("src/**/*.sh")) + list(project_dir.glob("src/**/*.html"))
        test_files = list(project_dir.glob("tests/**/*.py"))

        for f in src_files:
            try:
                n = len(f.read_text().splitlines())
                src_lines += n
                total_lines += n
            except Exception:
                pass
        for f in test_files:
            try:
                n = len(f.read_text().splitlines())
                test_lines += n
                total_lines += n
            except Exception:
                pass

        # --- Read spec content ---
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # --- Read architecture analysis from artifacts ---
        architecture_content = ""
        arch_key = "architecture"
        if arch_key in session.artifacts:
            arch_path = Path(session.artifacts[arch_key])
            if arch_path.exists():
                architecture_content = arch_path.read_text()

        # --- Read PRD from artifacts (if available) ---
        prd_content = ""
        prd_key = "prd"
        if prd_key in session.artifacts:
            prd_path = Path(session.artifacts[prd_key])
            if prd_path.exists():
                prd_content = prd_path.read_text()

        # --- Read S.U.P.E.R analysis (if available) ---
        super_content = ""
        super_key = "super-analysis"
        if super_key in session.artifacts:
            super_path = Path(session.artifacts[super_key])
            if super_path.exists():
                super_content = super_path.read_text()

        # --- Build LLM prompt ---
        system_prompt = (
            "You are a senior software developer and tech lead. "
            "Given a project specification, S.U.P.E.R. analysis, PRD, and architecture document, "
            "produce a detailed development plan in Markdown covering:\n"
            "1. **Development Plan** — what to build, in what order, and why (priority-driven)\n"
            "2. **Task Breakdown** — atomic implementation tasks with estimated effort, "
            "file paths to modify, and acceptance criteria for each\n"
            "3. **Tech Debt Identification** — areas in the existing code that need refactoring, "
            "patterns that don't scale, missing tests, or quality concerns\n"
            "4. **Implementation Order** — recommended sequence of work with dependencies\n"
            "5. **Risk Assessment** — technical risks, unknowns, and mitigation strategies\n"
            "Be specific, reference actual file paths from the project, and provide actionable tasks."
        )

        context_parts = [
            f"# Specification: {Path(session.spec_path).name}\n```markdown\n{spec_content[:6000]}\n```"
        ]
        if architecture_content:
            context_parts.append(
                f"# Architecture Analysis\n```markdown\n{architecture_content[:4000]}\n```"
            )
        if prd_content:
            context_parts.append(
                f"# PRD\n```markdown\n{prd_content[:3000]}\n```"
            )
        if super_content:
            context_parts.append(
                f"# S.U.P.E.R. Analysis\n```markdown\n{super_content[:3000]}\n```"
            )

        context_parts.append(
            f"# Project Metrics\n"
            f"- Source lines: {src_lines} across {len(src_files)} files\n"
            f"- Test lines: {test_lines} across {len(test_files)} files\n"
            f"- Test-to-source ratio: {test_lines/src_lines:.1%} (if src_lines > 0 else 'N/A')\n"
            f"- Recent git commits: {git_commits}\n"
            f"```\n{git_log}\n```"
        )

        user_prompt = "\n\n---\n\n".join(context_parts)
        user_prompt += "\n\n---\n\nNow produce the development plan, task breakdown, and tech debt identification as Markdown."

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

        # Architecture analysis from artifacts
        architecture_content = None
        if "architecture" in session.artifacts:
            ap = Path(session.artifacts["architecture"])
            if ap.exists():
                architecture_content = ap.read_text()

        # Development plan from artifacts
        dev_plan_content = None
        if "development" in session.artifacts:
            dp = Path(session.artifacts["development"])
            if dp.exists():
                dev_plan_content = dp.read_text()

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
                # Parse: "ok  package 0.5s" or "FAIL  package 0.5s"
                for line in result.stdout.split("\n"):
                    if line.startswith("ok "):
                        passed += 1
                        total += 1
                    elif line.startswith("FAIL "):
                        failed += 1
                        total += 1
                test_summary = f"Go test: {total} packages, {passed} passed, {failed} failed"
            except FileNotFoundError:
                log.warning("Go not installed — tests cannot run")
                test_summary = "Go not installed — tests skipped"
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
                # Parse pytest output like "33 passed in 0.03s"
                for line in result.stdout.split("\n"):
                    line = line.strip()
                    if "passed" in line or "failed" in line:
                        test_summary = line
                        import re
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
                log.warning("pytest not installed — tests cannot run")
                test_summary = "pytest not installed — tests skipped"
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
                in_scenario = False
                current_scenario = ""
                for line in content.split("\n"):
                    if line.strip().startswith("### ") and "GIVEN" in line.upper():
                        if current_scenario:
                            spec_scenarios.append(current_scenario)
                        current_scenario = line.strip().replace("### ", "")
                        in_scenario = True
                    elif in_scenario and line.strip():
                        pass
                if current_scenario:
                    spec_scenarios.append(current_scenario)
            except Exception as e:
                log.warning(f"Failed to parse spec scenarios for test report: {e}")

        status_icon = "✅" if failed == 0 else "❌"
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

        content += f"""
## Coverage Note
Run CI Layer 1 to generate detailed coverage metrics for compliance.
"""
        try:
            out_path.write_text(content)
        except OSError as e:
            log.error(f"Cannot write test report: {e}")
            raise PipelineStepError(f"Cannot write test report: {e}")
        print(f"  ✅ [Claude] Self-test report at {out_path}")
        log.info(f"Self-test report saved to {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Self-test step failed: {e}")
        raise PipelineStepError(f"Self-test step failed: {e}")


def _try_parse_hermes_json(raw: str, session_name: str) -> dict:
    """Parse Hermes review JSON from LLM output with robust fallback.

    Supports common format deviations:
      - Markdown ```json code fences
      - Leading/trailing explanatory text
      - Missing required fields (fills in defaults)
      - Pre/post whitespace
      - Multiple code blocks (uses the first valid JSON block)

    Returns a valid review dict in all cases (with status='retry' if
    parsing ultimately fails, including raw output for debugging).
    """
    json_str = raw.strip()
    raw_preview_500 = raw[:500]

    # Try bare JSON first
    if json_str.startswith("{") and json_str.endswith("}"):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass  # Fall through to fence stripping

    # Strip markdown fences: ```json ... ``` or ``` ... ```
    if "```" in json_str:
        # Collect all fenced blocks
        blocks = []
        in_fence = False
        current = []
        for line in json_str.split("\n"):
            if line.strip().startswith("```"):
                if in_fence:
                    # End of a fenced block
                    blocks.append("\n".join(current))
                    current = []
                    in_fence = False
                else:
                    in_fence = True
                    # Skip the opening fence (optionally with "json" after)
                    lang = line.strip().lstrip("```").strip().lower()
                    if lang and lang != "json":
                        # It's a non-JSON code block, skip content
                        in_fence = False
                    current = []
            elif in_fence:
                current.append(line)

        for block in blocks:
            block = block.strip()
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue

    # If we have leading text before a JSON block, try to find { ... }
    brace_start = json_str.find("{")
    if brace_start >= 0:
        # Find matching closing brace
        depth = 0
        for i in range(brace_start, len(json_str)):
            if json_str[i] == "{":
                depth += 1
            elif json_str[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = json_str[brace_start:i+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue

    # Final fallback: return retry status with raw output embedded
    log.warning(f"Could not parse Hermes review JSON. Raw output (first 500 chars): {raw_preview_500}")
    return {
        "session": session_name,
        "reviewer": "Hermes",
        "timestamp": datetime.now().isoformat(),
        "status": "retry",
        "_raw_llm_output": raw,
        "findings": [{
            "severity": "major",
            "category": "reviewer-error",
            "file": "",
            "line": None,
            "message": (
                f"LLM review output was not valid JSON. "
                f"Raw output (first 500 chars): {raw_preview_500}"
            ),
        }],
        "finding_breakdown": {"critical": 0, "major": 1, "minor": 0, "info": 0},
        "summary": f"LLM review could not be parsed — check raw output.",
    }


@timed_step
def step_hermes_review(session: PipelineSession) -> str:
    """Step 7: Hermes — AI-powered code review.

    Reads spec + all artifacts (architecture, test report, development plan, etc.),
    sends to LLM, and produces a real code review with findings.
    """
    try:
        print("  🔮 [Hermes] Running AI-powered code review...")
        log.info("Running AI-powered code review")

        project_dir = Path(os.environ.get("OSH_HOME", ".")).resolve()

        # --- Read spec ---
        spec_path = Path(session.spec_path)
        spec_content = spec_path.read_text() if spec_path.exists() else "(spec file not found)"

        # --- Collect all available artifacts ---
        artifact_contents = {}
        for key in ["architecture", "development", "self-test", "prd", "super-analysis", "review-result"]:
            if key in session.artifacts:
                ap = Path(session.artifacts[key])
                if ap.exists():
                    artifact_contents[key] = ap.read_text()

        # --- Scan actual source files ---
        source_files = []
        src_dir = project_dir / "src"
        if src_dir.exists():
            for root, dirs, files in os.walk(src_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for f in sorted(files):
                    if f.endswith(".py"):
                        fpath = Path(root) / f
                        rel = fpath.relative_to(project_dir)
                        content = fpath.read_text() if fpath.exists() and fpath.stat().st_size < 20000 else ""
                        source_files.append({"path": str(rel), "lines": len(content.splitlines()), "content": content[:3000]})

        # --- Build LLM prompt ---
        system_prompt = (
            "You are an expert code reviewer (Hermes). Review the project's source code "
            "against the specification and all available pipeline artifacts. "
            "Produce a detailed review JSON with findings.\n\n"
            "Respond with ONLY valid JSON (no markdown, no explanation). "
            "The JSON must have this exact structure:\n"
            "{\n"
            '  "session": "<session-name>",\n'
            '  "reviewer": "Hermes",\n'
            '  "timestamp": "<ISO-timestamp>",\n'
            '  "status": "passed|failed|retry",\n'
            '  "findings": [\n'
            "    {\n"
            '      "severity": "critical|major|minor|info",\n'
            '      "category": "architecture|domain|style|security|coverage|spec-compliance",\n'
            '      "file": "<relative-file-path>",\n'
            '      "line": <integer-or-null>,\n'
            '      "message": "<detailed-description>"\n'
            "    }\n"
            "  ],\n"
            '  "finding_breakdown": {\n'
            '    "critical": <int>, "major": <int>, "minor": <int>, "info": <int>\n'
            "  },\n"
            '  "summary": "<overall-review-summary>"\n'
            "}"
        )

        artifact_sections = []
        for key, content in artifact_contents.items():
            artifact_sections.append(f"### {key}\n```\n{content[:3000]}\n```")

        source_sections = []
        for sf in source_files:
            source_sections.append(f"### {sf['path']} ({sf['lines']} lines)\n```python\n{sf['content']}\n```")

        # Limit source files to avoid huge prompts
        if len(source_sections) > 8:
            source_sections = source_sections[:8]
            source_sections.append("*(additional source files truncated)*")

        user_prompt = (
            f"# Specification: {Path(session.spec_path).name}\n"
            f"```markdown\n{spec_content[:5000]}\n```\n\n"
            f"# Pipeline Artifacts\n"
            + "\n".join(artifact_sections)
            + "\n\n# Source Code\n"
            + "\n".join(source_sections)
            + "\n\n---\n\n"
            f"Review session: {session.name}\n"
            f"Timestamp: {datetime.now().isoformat()}\n\n"
            "Produce the JSON review. Check:\n"
            "- Does the code satisfy all spec SHALL/SHOULD statements?\n"
            "- Are there any architecture violations or layering issues?\n"
            "- Code style, security, and test coverage concerns?\n"
            "- Quality of the development plan and architecture design?"
        )

        try:
            result = _call_llm(session, system_prompt, user_prompt, max_tokens=4096)
        except Exception as e:
            log.error(f"LLM call failed during code review: {e}")
            raise PipelineStepError(
                f"Code review LLM call failed: {e}\n"
                f"Spec: {session.spec_path}"
            )

        raw = result["content"].strip()
        usage = result.get("usage", {})
        log.info(
            "LLM returned %d tokens (prompt=%s, completion=%s)",
            usage.get("total_tokens", "?"),
            usage.get("prompt_tokens", "?"),
            usage.get("completion_tokens", "?"),
        )

        # Parse with robust fallback (handles markdown fences, leading text, etc.)
        review = _try_parse_hermes_json(raw, session.name)

        # Ensure required fields
        review.setdefault("session", session.name)
        review.setdefault("reviewer", "Hermes")
        review.setdefault("timestamp", datetime.now().isoformat())
        review.setdefault("status", "passed")
        review.setdefault("findings", [])
        review.setdefault("finding_breakdown", {"critical": 0, "major": 0, "minor": 0, "info": 0})
        review.setdefault("summary", "")

        out_path = session.session_dir / "code-review.json"
        try:
            with open(out_path, "w") as f:
                json.dump(review, f, indent=2, ensure_ascii=False)
        except (OSError, IOError) as e:
            log.error(f"Cannot write code review: {e}")
            raise PipelineStepError(f"Cannot write code review: {e}")
        print(f"  ✅ [Hermes] AI code review completed ({len(review['findings'])} findings, status={review['status']})")
        log.info(f"AI code review: {len(review['findings'])} findings, status={review['status']}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Code review step failed: {e}")
        raise PipelineStepError(f"Code review step failed: {e}")


@timed_step
def step_final_report(session: PipelineSession) -> str:
    """Step 8: 小明 — 最终报告生成"""
    try:
        print("  📋 [小明] Generating final report...")
        log.info("Generating final report")
        
        out_path = session.session_dir / "final-report.md"
        lines = [
            f"# Final Report: {session.name}",
            f"",
            f"**Status**: {session.status}",
            f"**Spec**: {session.spec_path}",
            f"**Created**: {session.created_at}",
            f"**Completed**: {session.updated_at}",
            f"",
            f"## Pipeline Steps",
            f"",
        ]
        
        for step in session.steps:
            status_icon = {"completed": "✅", "running": "🔄", "pending": "⏳", "failed": "❌"}
            icon = status_icon.get(step["status"], "❓")
            lines.append(f"{icon} **Step {step['step']}** [{step['agent']}] {step['name']}: {step['status']}")
        
        if session.errors:
            lines.extend(["", "## Errors", ""])
            for e in session.errors:
                lines.append(f"- ❌ {e}")
        
        lines.extend(["", "## Artifacts", ""])
        for key, path in session.artifacts.items():
            lines.append(f"- **{key}**: {path}")
        
        try:
            out_path.write_text("\n".join(lines))
        except OSError as e:
            log.error(f"Cannot write final report: {e}")
            raise PipelineStepError(f"Cannot write final report: {e}")
        print(f"  ✅ Final report at {out_path}")
        log.info(f"Final report generated at {out_path}")
        return str(out_path)
    except PipelineStepError:
        raise
    except Exception as e:
        log.error(f"Final report step failed: {e}")
        raise PipelineStepError(f"Final report step failed: {e}")


# --- Pipeline definition ---
#
# Steps that have been refactored into PipelineStep base classes use
# the step class instance; others remain as legacy function references.
# This hybrid approach enables gradual migration.

def _resolve_handler(step_key: str, legacy_fn) -> callable:
    """Use the refactored PipelineStep class if available, else fall back."""
    if _have_step_classes:
        instance = get_step_instance(step_key)
        if instance is not None:
            return instance
    return legacy_fn


PIPELINE_STEPS = [
    ("spec-check", "小明", "OpenSpec 合规检查", step_spec_check),
    ("super-analysis", "小明", "S.U.P.E.R 启动分析",
     _resolve_handler("super-analysis", step_super_analysis)),
    ("prd", "Hermes", "产品需求分析",
     _resolve_handler("prd", step_hermes_prd)),
    ("internal-review", "小明", "内部评审", step_internal_review),
    ("architecture", "Claude", "架构设计",
     _resolve_handler("architecture", step_claude_arch)),
    ("development", "Claude", "开发实现",
     _resolve_handler("development", step_claude_dev)),
    ("test-planning", "Claude", "测试规划",
     _resolve_handler("test-planning", step_test_planning)),
    ("self-test", "Claude", "自测验证", step_claude_test),
    ("code-review", "Hermes", "代码审查",
     _resolve_handler("code-review", step_hermes_review)),
    ("final-report", "小明", "最终报告", step_final_report),
]


def _check_llm_key() -> str | None:
    """Check for a valid LLM API key in environment variables.

    Returns the key if found, or None if neither LLM_API_KEY nor
    OPENAI_API_KEY is set.
    """
    key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        print("""
❌ LLM API key not found

yuleOSH's pipeline requires an LLM API key to run AI agent steps.
Set one of these environment variables:

    export LLM_API_KEY=sk-...    # OpenAI/OpenAI-compatible API
    export OPENAI_API_KEY=sk-... # OpenAI

Then re-run: yuleosh pipeline run <spec>

\U0001f4a1 For demo/testing without a real LLM, use the --mock flag:
    yuleosh pipeline run --mock docs/spec.md
""")
    return key


def run_pipeline(spec_path: str, name: Optional[str] = None, llm_client: Optional[Callable] = None, mock: bool = False):
    """Run the full OSH pipeline for a given spec.
    
    Args:
        spec_path: Path to the specification file.
        name: Optional session name (auto-generated if None).
        llm_client: Optional injected LLM callable for testing.
            When provided, all LLM-dependent steps use this callable
            instead of the global ``chat_completion``.
        mock: If True, skip LLM key check (for demo/testing).
    """

    # Check for LLM API key before starting (skip when a mock/injected client is provided)
    if not mock and llm_client is None:
        key = _check_llm_key()
        if not key:
            sys.exit(1)
    
    try:
        if name is None:
            name = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        session = PipelineSession(name, spec_path, llm_client=llm_client)
        print(f"\n🚀 Pipeline started: {name}")
        print(f"   Spec: {spec_path}")
        print(f"   Session: {session.session_dir}")
        print()
        
        log.info(f"Pipeline starting: {name}, spec={spec_path}")
        
        for step_key, agent, step_name, handler in PIPELINE_STEPS:
            step_idx = len(session.steps)
            session.add_step(step_key, agent, step_name)
            session.start_step(step_idx)
            
            print(f"  [{step_idx+1}/{len(PIPELINE_STEPS)}] {agent}: {step_name}")
            log.info(f"Step {step_idx+1}/{len(PIPELINE_STEPS)}: [{agent}] {step_name}")
            
            try:
                # Set status to completed before the final report step
                # so the report captures the correct status
                if step_key == "final-report":
                    session.status = "completed"
                output_path = handler(session)
                session.complete_step(step_idx, str(output_path))
                session.set_artifact(step_key, str(output_path))
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

        # Send notification on pipeline completion or failure
        if _notify:
            try:
                _notify(
                    name=session.name,
                    status=session.status,
                    total_steps=len(PIPELINE_STEPS),
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
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    try:
        if cmd == "status":
            status_pipeline(sys.argv[2] if len(sys.argv) > 2 else None)
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

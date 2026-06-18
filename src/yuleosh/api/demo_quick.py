"""
yuleOSH Demo — Quick pipeline from a one-line requirement.

Generates a minimal OpenSpec from a user's one-line requirement,
runs the full mock pipeline (no real LLM needed), and produces
evidence ZIP.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path


DEMO_SPEC_TEMPLATE = """# {spec_title}

> Version: 1.0.0-demo | Generated: {timestamp}

{description}

## 1. Requirements

### REQ-001: {req_name}
- The system SHALL {req_shall}

#### Reason
User-requested feature: {req_name}

## 2. Scenarios

### Scenario: Main scenario
- GIVEN System is initialized
- WHEN {req_name} is triggered
- THEN System responds correctly

"""


def generate_demo_spec(user_input: str) -> str:
    """Generate a minimal OpenSpec markdown from a one-line requirement."""
    req_name = user_input.strip()
    req_shall = f"implement {req_name}"
    spec_title = f"Demo: {req_name}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    description = (f"Auto-generated spec from user requirement: \"{user_input}\". "
                   f"Lightweight demonstration spec for yuleOSH pipeline.")
    return DEMO_SPEC_TEMPLATE.format(
        spec_title=spec_title, timestamp=timestamp,
        description=description, req_name=req_name, req_shall=req_shall,
    )


def _demo_mock_llm(system_prompt: str, user_prompt: str, **kwargs) -> dict:
    """Mock LLM client returning plausible demo content."""
    return {
        "content": (
            "# Demo Analysis\n\n## Summary\n"
            "The requirement has been analyzed. 1 functional component identified.\n\n"
            "## Architecture\n- **Component**: DemoController\n"
            "  - Handles user-requested functionality\n"
            "## Implementation\n- **Source files**: src/demo.c, include/demo.h\n"
            "## Test Plan\n- **Unit tests**: 2 test cases\n"
        ),
        "model": "demo-mock",
        "usage": {"prompt_tokens": 150, "completion_tokens": 120, "total_tokens": 270},
        "finish_reason": "stop",
    }


def run_demo_pipeline_steps(spec_path: str, project_dir: Path):
    """Run all 10 pipeline steps directly with mock LLM."""
    from yuleosh.pipeline.session import PipelineSession
    from yuleosh.pipeline.step_handlers.spec import step_spec_check
    from yuleosh.pipeline.step_handlers.analysis import (
        step_super_analysis, step_hermes_prd, step_internal_review)
    from yuleosh.pipeline.step_handlers.execution import (
        step_claude_arch, step_claude_dev, step_test_planning, step_claude_test)
    from yuleosh.pipeline.step_handlers.review import (
        step_hermes_review, step_final_report)

    steps = [
        ("spec-check", step_spec_check),
        ("super-analysis", step_super_analysis),
        ("prd", step_hermes_prd),
        ("internal-review", step_internal_review),
        ("architecture", step_claude_arch),
        ("development", step_claude_dev),
        ("test-planning", step_test_planning),
        ("self-test", step_claude_test),
        ("code-review", step_hermes_review),
        ("final-report", step_final_report),
    ]

    session = PipelineSession(
        f"demo-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        spec_path, llm_client=_demo_mock_llm,
    )

    for idx, (step_key, handler) in enumerate(steps):
        session.add_step(step_key, "Agent", step_key)
        session.start_step(idx)
        try:
            if step_key == "final-report":
                session.status = "completed"
            output = handler(session)
            session.complete_step(idx, output)
            session.set_artifact(step_key, output)
            if step_key == "final-report":
                session._save()
            print(f"    ✅ {step_key}")
        except Exception as e:
            print(f"    ❌ {step_key}: {e}")
            session.fail_step(idx, str(e))
            break

    return session


def run_demo_pipeline(user_input: str, work_dir: str) -> dict:
    """Run the full demo pipeline: spec gen -> pipeline -> evidence."""
    work_path = Path(work_dir).resolve()
    project_dir = work_path / "demo-project"
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Init minimal project structure
    for sub in [".osh", "docs", "src", "tests", "specs"]:
        (project_dir / sub).mkdir(exist_ok=True)

    # Generate spec
    spec_content = generate_demo_spec(user_input)
    spec_path = project_dir / "docs" / "spec.md"
    spec_path.write_text(spec_content)
    print(f"  📝 Generated demo spec: {spec_path}")

    # Create a minimal demo test so evidence generation has something
    demo_test = project_dir / "tests" / "test_demo.py"
    demo_test.write_text(
        '"""Demo tests."""\nimport pytest\n\n'
        'def test_demo_basic():\n    """Covers: REQ-001"""\n    assert True\n\n'
        'def test_demo_edge():\n    """Covers: REQ-001"""\n    assert True\n'
    )

    # Inject mock LLM + set OSH_HOME to demo project
    print(f"  🚀 Starting pipeline (mock LLM mode)...")
    old_key = os.environ.get("LLM_API_KEY", "")
    old_osh = os.environ.get("OSH_HOME", "")
    os.environ["LLM_API_KEY"] = "demo-mock-key"
    os.environ["OSH_HOME"] = str(project_dir)
    try:
        session = run_demo_pipeline_steps(str(spec_path), project_dir)
    finally:
        if old_key:
            os.environ["LLM_API_KEY"] = old_key
        else:
            os.environ.pop("LLM_API_KEY", None)
        if old_osh:
            os.environ["OSH_HOME"] = old_osh
        else:
            os.environ.pop("OSH_HOME", None)

    if session.status == "failed":
        return {
            "status": "failed",
            "spec_path": str(spec_path),
            "session_dir": str(session.session_dir),
            "errors": session.errors,
        }

    # Generate evidence pack
    print(f"  📦 Generating evidence pack...")
    from yuleosh.evidence.generator import EvidenceCollector
    from yuleosh.evidence.compliance import pack_compliance_zip as _pack_zip

    ev_collector = EvidenceCollector(str(project_dir))
    # Set requirements/scenarios directly (bypasses validate module import)
    spec_text = spec_path.read_text()
    ev_collector.requirements = [{
        "name": user_input.strip(),
        "req_id": "REQ-001",
        "shall_count": 1,
        "shall": [f"implement {user_input.strip()}"],
        "reason": "User-requested feature",
    }]
    ev_collector.scenarios = [{
        "name": "Main scenario",
        "given": ["System is initialized"],
        "when": [f"{user_input.strip()} is triggered"],
        "then": ["System responds correctly"],
    }]
    ev_collector._collect_test_coverage()
    ev_collector.collect_reviews()
    ev_collector.collect_ci_results()
    ev_collector.collect_sil_reports()

    artifacts = []
    artifacts.append(ev_collector.generate_traceability_matrix())
    artifacts.append(ev_collector.generate_requirement_coverage())
    artifacts.append(ev_collector.generate_code_coverage_report())
    artifacts.append(ev_collector.generate_acceptance_matrix())
    artifacts.append(ev_collector.aggregate_review_logs())
    zip_path_str = _pack_zip(ev_collector)
    artifacts.append(zip_path_str)

    evidence_dir = project_dir / ".osh" / "evidence"
    evidence_zip = zip_path_str if os.path.exists(zip_path_str) else ""

    print(f"  ✅ Evidence generation complete: {evidence_dir}")
    print(f"  📦 Compliance pack: {evidence_zip}")

    return {
        "status": "completed",
        "spec_path": str(spec_path),
        "session_dir": str(session.session_dir),
        "evidence_dir": str(evidence_dir),
        "evidence_zip": evidence_zip,
        "artifacts": artifacts,
        "token_usage": getattr(session, "token_usage_total", 0),
    }


def main(user_input: str, work_dir: str = ".") -> dict:
    """CLI entry point for ``yuleosh demo quick <requirement>``."""
    print(f"\n{'='*60}")
    print(f"  🔥 yuleOSH Demo Quick Pipeline")
    print(f"{'='*60}")
    print(f"  Input: {user_input}")
    print()

    result = run_demo_pipeline(user_input, work_dir)

    print(f"\n{'='*60}")
    if result["status"] == "completed":
        print(f"  ✅ Demo pipeline completed successfully!")
        print(f"  📄 Spec: {result['spec_path']}")
        print(f"  📂 Evidence: {result['evidence_dir']}")
        if result["evidence_zip"]:
            zip_size = Path(result["evidence_zip"]).stat().st_size
            print(f"  📦 ZIP: {result['evidence_zip']} ({zip_size:,} bytes)")
        if result.get("token_usage"):
            print(f"  📊 Tokens: {result['token_usage']}")
        print(f"  🎯 Artifacts: {len(result.get('artifacts', []))}")
    else:
        print(f"  ❌ Demo pipeline failed:")
        for e in result.get("errors", []):
            print(f"     - {e}")

    print(f"{'='*60}\n")
    return result

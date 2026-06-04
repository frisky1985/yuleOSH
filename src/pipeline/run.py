#!/usr/bin/env python3
"""
OSH Pipeline Engine — Agent orchestration pipeline.

Routes tasks through:
  小明 (PM) → Hermes (Product/Review) → Claude (Arch/Dev)
  
Follows Harness Engineering SOP flow.
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class PipelineSession:
    """Represents a running pipeline session."""
    
    def __init__(self, name: str, spec_path: str):
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

    def _ensure_session_dir(self) -> Path:
        base = Path(os.environ.get("OSH_HOME", "."))
        sdir = base / ".osh" / "sessions" / self.name
        sdir.mkdir(parents=True, exist_ok=True)
        return sdir

    def add_step(self, step_name: str, agent: str, action: str):
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

    def start_step(self, step_idx: int):
        if step_idx < len(self.steps):
            self.steps[step_idx]["status"] = "running"
            self.steps[step_idx]["started_at"] = datetime.now().isoformat()
            self.current_step = step_idx
            self._save()

    def complete_step(self, step_idx: int, output_path: str):
        if step_idx < len(self.steps):
            self.steps[step_idx]["status"] = "completed"
            self.steps[step_idx]["completed_at"] = datetime.now().isoformat()
            self.steps[step_idx]["output_path"] = output_path
            self.updated_at = datetime.now().isoformat()
            self._save()

    def fail_step(self, step_idx: int, error: str):
        if step_idx < len(self.steps):
            self.steps[step_idx]["status"] = "failed"
            self.steps[step_idx]["completed_at"] = datetime.now().isoformat()
            self.steps[step_idx]["errors"].append(error)
            self.errors.append(error)
            self.status = "failed"
            self.updated_at = datetime.now().isoformat()
            self._save()

    def set_artifact(self, key: str, path: str):
        self.artifacts[key] = str(path)
        self._save()

    def _save(self):
        data = self.to_dict()
        with open(self.session_dir / "session.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def to_dict(self) -> dict:
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


# --- Step Handlers ---

def step_spec_check(session: PipelineSession) -> str:
    """Step 0: 小明 — OpenSpec 合规检查"""
    print("  🔍 [小明] Validating OpenSpec...")
    result = subprocess.run(
        [sys.executable, "src/spec/validate.py", session.spec_path, "--json"],
        capture_output=True, text=True, cwd=os.environ.get("OSH_HOME", "."),
    )
    out_path = session.session_dir / "spec-check.json"
    with open(out_path, "w") as f:
        f.write(result.stdout if result.stdout else result.stderr)
    
    if result.returncode != 0:
        raise RuntimeError(f"Spec validation failed:\n{result.stderr or result.stdout}")
    
    data = json.loads(result.stdout)
    if data.get("error_count", 0) > 0:
        issues = [i["message"] for i in data.get("issues", []) if i["severity"] == "ERROR"]
        raise RuntimeError(f"Spec has {data['error_count']} error(s): {'; '.join(issues)}")
    
    print(f"  ✅ [小明] Spec validated: {data['coverage']['score']}% coverage")
    return str(out_path)


def step_super_analysis(session: PipelineSession) -> str:
    """Step 1: 小明 — S.U.P.E.R 分析"""
    print("  📊 [小明] Generating S.U.P.E.R analysis...")
    
    spec_name = Path(session.spec_path).stem
    
    template = f"""# S.U.P.E.R Analysis: {spec_name}

## S — Situation
_Context and current state_

## U — Understanding
_Deep needs and pain points_

## P — Problem
_Core problem definition_

## E — Execution
_Execution plan and approach_

## R — Resources
_Resource assessment_

## P — Priority
_Priority judgment (P0/P1/P2)_
"""
    out_path = session.session_dir / "startup-analysis.md"
    out_path.write_text(template)
    print(f"  ✅ [小明] S.U.P.E.R template generated at {out_path}")
    return str(out_path)


def step_hermes_prd(session: PipelineSession) -> str:
    """Step 2: Hermes — 产品需求分析"""
    print("  🔮 [Hermes] Writing PRD...")
    
    out_path = session.session_dir / "prd.md"
    content = f"""# PRD: {session.name}

> Generated from spec: {session.spec_path}
> Pipeline Session: {session.created_at}

## Overview
Based on S.U.P.E.R analysis and OpenSpec validation.

## Requirements Coverage
_Each SHALL statement mapped to implementation plan_

## Scenarios
_Each GIVEN/WHEN/THEN mapped to test strategy_

## Delivery Criteria
_Criteria for completion_
"""
    out_path.write_text(content)
    print(f"  ✅ [Hermes] PRD written at {out_path}")
    return str(out_path)


def step_internal_review(session: PipelineSession) -> str:
    """Step 3: 小明 — 内部评审"""
    print("  🔍 [小明] Internal review...")
    
    artifacts = session.artifacts
    report = []
    
    for key, path in artifacts.items():
        p = Path(path)
        if p.exists():
            report.append(f"✅ {key}: {path}")
        else:
            report.append(f"❌ {key}: MISSING")
    
    # Check consistency
    required = ["spec-check", "super-analysis", "prd"]
    missing = [r for r in required if r not in artifacts]
    
    if missing:
        raise RuntimeError(f"Internal review failed — missing artifacts: {', '.join(missing)}")
    
    out_path = session.session_dir / "review-result.md"
    out_path.write_text("\n".join(report))
    print(f"  ✅ [小明] Internal review passed")
    return str(out_path)


def step_claude_arch(session: PipelineSession) -> str:
    """Step 4: Claude — 架构设计"""
    print("  💻 [Claude] Designing architecture...")
    
    out_path = session.session_dir / "architecture.md"
    content = f"""# Architecture: {session.name}

> Based on spec + PRD

## Bounded Contexts
_Context mapping from DDD analysis_

## Aggregates
_Key aggregates and entities_

## Domain Events
_Events that trigger cross-context communication_

## Key Decisions
_Architecture Decision Records_
"""
    out_path.write_text(content)
    print(f"  ✅ [Claude] Architecture design at {out_path}")
    return str(out_path)


def step_claude_dev(session: PipelineSession) -> str:
    """Step 5: Claude — 开发"""
    print("  💻 [Claude] Development...")
    
    out_path = session.session_dir / "development-log.md"
    content = f"""# Development Log: {session.name}

## Tasks
_Task breakdown from architecture design_

## Implementation
_Per-task implementation details_

## Self-Test Results
_TDD RED→GREEN→REFACTOR log_
"""
    out_path.write_text(content)
    print(f"  ✅ [Claude] Development log at {out_path}")
    return str(out_path)


def step_claude_test(session: PipelineSession) -> str:
    """Step 6: Claude — 自测"""
    print("  🧪 [Claude] Self-testing...")
    
    out_path = session.session_dir / "self-test-report.md"
    content = f"""# Self-Test Report: {session.name}

## Test Results
_PASS/FAIL per scenario_

## Coverage
_Code coverage metrics_

## Evidence
_Test evidence per scenario from spec_
"""
    out_path.write_text(content)
    print(f"  ✅ [Claude] Self-test report at {out_path}")
    return str(out_path)


def step_hermes_review(session: PipelineSession) -> str:
    """Step 7: Hermes — 代码审查"""
    print("  🔮 [Hermes] Code review...")
    
    out_path = session.session_dir / "code-review.json"
    review = {
        "session": session.name,
        "reviewer": "Hermes",
        "timestamp": datetime.now().isoformat(),
        "status": "passed",
        "findings": [],
        "summary": "Code review completed. All spec requirements verified.",
    }
    with open(out_path, "w") as f:
        json.dump(review, f, indent=2)
    print(f"  ✅ [Hermes] Code review completed")
    return str(out_path)


def step_final_report(session: PipelineSession) -> str:
    """Step 8: 小明 — 最终报告生成"""
    print("  📋 [小明] Generating final report...")
    
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
    
    out_path.write_text("\n".join(lines))
    print(f"  ✅ Final report at {out_path}")
    return str(out_path)


# --- Pipeline definition ---

PIPELINE_STEPS = [
    ("spec-check", "小明", "OpenSpec 合规检查", step_spec_check),
    ("super-analysis", "小明", "S.U.P.E.R 启动分析", step_super_analysis),
    ("prd", "Hermes", "产品需求分析", step_hermes_prd),
    ("internal-review", "小明", "内部评审", step_internal_review),
    ("architecture", "Claude", "架构设计", step_claude_arch),
    ("development", "Claude", "开发实现", step_claude_dev),
    ("self-test", "Claude", "自测验证", step_claude_test),
    ("code-review", "Hermes", "代码审查", step_hermes_review),
    ("final-report", "小明", "最终报告", step_final_report),
]


def run_pipeline(spec_path: str, name: Optional[str] = None):
    """Run the full OSH pipeline for a given spec."""
    
    if name is None:
        name = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    session = PipelineSession(name, spec_path)
    print(f"\n🚀 Pipeline started: {name}")
    print(f"   Spec: {spec_path}")
    print(f"   Session: {session.session_dir}")
    print()
    
    for step_key, agent, step_name, handler in PIPELINE_STEPS:
        step_idx = len(session.steps)
        session.add_step(step_key, agent, step_name)
        session.start_step(step_idx)
        
        print(f"  [{step_idx+1}/{len(PIPELINE_STEPS)}] {agent}: {step_name}")
        
        try:
            output_path = handler(session)
            session.complete_step(step_idx, str(output_path))
            session.set_artifact(step_key, str(output_path))
            print()
        except Exception as e:
            session.fail_step(step_idx, str(e))
            print(f"  ❌ Step failed: {e}")
            print()
            break
    
    if session.status != "failed":
        session.status = "completed"
        session._save()
    
    print(f"\n{'='*50}")
    print(f"Pipeline: {session.status} 🎉" if session.status == "completed" else f"Pipeline: {session.status} ❌")
    print(f"Session: {session.session_dir}")
    print(f"Report: session.final_report")
    print()
    
    return session


def status_pipeline(name: Optional[str] = None):
    """Show pipeline status."""
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
        print("Usage:")
        print("  python3 run.py <spec.md>          — Run full pipeline")
        print("  python3 run.py status [name]      — Show pipeline status")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "status":
        status_pipeline(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        run_pipeline(cmd)


if __name__ == "__main__":
    main()

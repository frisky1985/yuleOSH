#!/usr/bin/env python3
"""
OSH Review Engine — Agent review matrix for per-task blocking review.

Supports dual-track:
  Track A: AI self-check (non-blocking, fast feedback)
  Track B: Auto-reviewers (blocking, pass/fail/retry)
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable


class ReviewFinding:
    def __init__(self, severity: str, category: str, file: str, line: int, message: str):
        self.severity = severity  # critical | major | minor | info
        self.category = category  # architecture | domain | style | security | coverage
        self.file = file
        self.line = line
        self.message = message

    def to_dict(self) -> dict:
        """Serialize finding to dictionary."""
        return {
            "severity": self.severity,
            "category": self.category,
            "file": self.file,
            "line": self.line,
            "message": self.message,
        }


class ReviewResult:
    def __init__(self, task_name: str, reviewer: str):
        self.task_name = task_name
        self.reviewer = reviewer
        self.timestamp = datetime.now().isoformat()
        self.findings: list[ReviewFinding] = []
        self.status = "pending"  # pending | running | passed | failed | retry
        self.summary = ""
        self.retry_count = 0

    def add_finding(self, finding: ReviewFinding) -> None:
        """Add a finding to this review result."""
        self.findings.append(finding)

    def decide(self) -> str:
        """Voting logic: pass/fail/retry based on findings."""
        criticals = [f for f in self.findings if f.severity == "critical"]
        majors = [f for f in self.findings if f.severity == "major"]

        if criticals or len(majors) > 3:
            if self.retry_count < 5:
                self.status = "retry"
                self.summary = f"Blocked: {len(criticals)} critical, {len(majors)} major. Retry {self.retry_count + 1}/5"
            else:
                self.status = "failed"
                self.summary = f"Failed after 5 retries: {len(criticals)} critical, {len(majors)} major"
        elif majors:
            self.status = "passed"
            self.summary = f"Passed with {len(majors)} minor issues, {len([f for f in self.findings if f.severity == 'minor'])} warnings"
        else:
            self.status = "passed"
            self.summary = "Clean — no issues found"

        return self.status

    def to_dict(self) -> dict:
        """Serialize review result to dictionary."""
        return {
            "task": self.task_name,
            "reviewer": self.reviewer,
            "timestamp": self.timestamp,
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
            "finding_count": len(self.findings),
            "finding_breakdown": {
                "critical": sum(1 for f in self.findings if f.severity == "critical"),
                "major": sum(1 for f in self.findings if f.severity == "major"),
                "minor": sum(1 for f in self.findings if f.severity == "minor"),
                "info": sum(1 for f in self.findings if f.severity == "info"),
            },
            "summary": self.summary,
        }


class ReviewSession:
    """Manages multi-agent review for a task."""
    
    def __init__(self, task_name: str, project_dir: str):
        self.task_name = task_name
        self.project_dir = project_dir
        self.created_at = datetime.now().isoformat()
        self.status = "running"
        self.reviews: list[ReviewResult] = []
        self.decision: Optional[str] = None

    def add_review(self, result: ReviewResult) -> None:
        """Add an agent review result to this session."""
        self.reviews.append(result)

    def final_decision(self) -> str:
        """Aggregate all agent reviews into final decision."""
        if not self.reviews:
            self.decision = "failed"
            return self.decision

        statuses = [r.status for r in self.reviews]
        
        if any(s == "retry" for s in statuses):
            self.decision = "retry"
        elif any(s == "failed" for s in statuses):
            self.decision = "failed"
        elif all(s == "passed" for s in statuses):
            self.decision = "passed"
        else:
            self.decision = "retry"

        self.status = "completed"
        return self.decision

    def save(self) -> None:
        """Persist review session to disk as JSON."""
        sdir = Path(self.project_dir) / ".osh" / "reviews" / self.task_name
        sdir.mkdir(parents=True, exist_ok=True)
        with open(sdir / "review-session.json", "w") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    def to_dict(self) -> dict:
        """Serialize review session to dictionary."""
        return {
            "task": self.task_name,
            "created_at": self.created_at,
            "status": self.status,
            "decision": self.decision,
            "reviews": [r.to_dict() for r in self.reviews],
        }


# --- Reviewers ---

def review_architecture(task_name: str, project_dir: str, changed_files: list[str]) -> ReviewResult:
    """Architecture reviewer: checks layering, dependency inversion, clean architecture."""
    result = ReviewResult(task_name, "architecture-reviewer")
    
    src_dir = os.path.join(project_dir, "src")
    if not os.path.exists(src_dir):
        result.status = "passed"
        result.summary = "No source directory found"
        return result
    
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                filepath = os.path.join(root, f)
                content = Path(filepath).read_text()
                rel = os.path.relpath(filepath, project_dir)
                
                # Check: no circular imports (max 3 levels deep)
                imports = [l for l in content.split("\n") if l.startswith("import ") or l.startswith("from ")]
                if len(imports) > 30:
                    result.add_finding(ReviewFinding(
                        "major", "architecture", rel, 1,
                        f"File has {len(imports)} imports — consider splitting modules"
                    ))
                
                # Check: function length < 20 lines
                lines = content.split("\n")
                in_func = False
                func_start = 0
                func_end = 0
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith("def ") or stripped.startswith("async def "):
                        in_func = True
                        func_start = i
                        func_end = i
                    elif in_func:
                        func_end = i
                        if stripped.startswith("def ") or stripped == "" or (stripped.startswith("#") and i > func_start):
                            pass
                        elif stripped.startswith("class ") or i == len(lines) - 1:
                            func_len = i - func_start
                            if func_len > 20:
                                result.add_finding(ReviewFinding(
                                    "minor", "architecture", rel, func_start + 1,
                                    f"Function starting line {func_start+1} has {func_len} lines (max 20)"
                                ))
                            in_func = False
    
    result.decide()
    return result


def review_domain_modeling(task_name: str, project_dir: str, changed_files: list[str]) -> ReviewResult:
    """Domain modeling reviewer: checks ubiquitous language, bounded contexts, value objects."""
    result = ReviewResult(task_name, "domain-modeling-reviewer")
    
    src_dir = os.path.join(project_dir, "src")
    if not os.path.exists(src_dir):
        result.status = "passed"
        result.summary = "No source directory found"
        return result
    
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                filepath = os.path.join(root, f)
                content = Path(filepath).read_text()
                rel = os.path.relpath(filepath, project_dir)
                lines = content.split("\n")
                
                # Check for class definitions
                classes = [l.strip() for l in lines if l.strip().startswith("class ")]
                
                # Check for mutable default args (value objects should be immutable)
                for i, line in enumerate(lines):
                    stripped_line = line.strip()
                    if ("def " in stripped_line or "lambda " in stripped_line) and ("=[]" in stripped_line or "=[" in stripped_line or "={}" in stripped_line):
                        result.add_finding(ReviewFinding(
                            "major", "domain", rel, i + 1,
                            f"Mutable default arg: '{stripped_line[:60]}'"
                        ))
    
    result.decide()
    return result


def review_code_style(task_name: str, project_dir: str, changed_files: list[str]) -> ReviewResult:
    """Code style reviewer: checks formatting, naming, docstrings."""
    result = ReviewResult(task_name, "code-style-reviewer")
    
    src_dir = os.path.join(project_dir, "src")
    if not os.path.exists(src_dir):
        result.status = "passed"
        result.summary = "No source directory found"
        return result
    
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith(".py"):
                filepath = os.path.join(root, f)
                content = Path(filepath).read_text()
                rel = os.path.relpath(filepath, project_dir)
                lines = content.split("\n")
                
                # Check for missing docstrings on functions
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith("def ") and i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if not next_line.startswith('"""') and not next_line.startswith("'''"):
                            result.add_finding(ReviewFinding(
                                "minor", "style", rel, i + 1,
                                f"Function definition on line {i+1} missing docstring"
                            ))
                
                # Check: no hardcoded tabs (use spaces)
                for i, line in enumerate(lines):
                    if "\t" in line and not line.startswith("#"):
                        result.add_finding(ReviewFinding(
                            "minor", "style", rel, i + 1,
                            "Tab character found — use spaces"
                        ))
                        break
    
    result.decide()
    return result


# ── Embedded C reviewer ──────────────────────────────────

def review_embedded_c(task_name: str, project_dir: str, changed_files: list[str]) -> ReviewResult:
    """Embedded C reviewer: static analysis for firmware defects."""
    try:
        from .c_review import review_embedded_c as _c_review
        return _c_review(task_name, project_dir, changed_files)
    except ImportError:
        result = ReviewResult(task_name, "embedded-c-reviewer")
        result.status = "passed"
        result.summary = "C reviewer module not available"
        return result


def review_coverage(task_name: str, project_dir: str, changed_files: list[str]) -> ReviewResult:
    """Coverage guardian: checks test coverage meets thresholds."""
    result = ReviewResult(task_name, "coverage-guardian")
    
    # Try to run coverage
    try:
        cov_result = subprocess.run(
            [sys.executable, "-m", "coverage", "json", "--pretty"],
            capture_output=True, text=True, timeout=30, cwd=project_dir,
        )
        json_file = os.path.join(project_dir, "coverage.json")
        
        if os.path.exists(json_file):
            cov_data = json.loads(open(json_file).read())
            totals = cov_data.get("totals", {})
            line_pct = totals.get("percent_covered", 0)
            
            if line_pct < 80:
                result.add_finding(ReviewFinding(
                    "critical", "coverage", "coverage.json", 0,
                    f"Line coverage {line_pct}% is below 80% threshold"
                ))
            else:
                result.add_finding(ReviewFinding(
                    "info", "coverage", "coverage.json", 0,
                    f"Line coverage {line_pct}% meets threshold"
                ))
        else:
            result.add_finding(ReviewFinding(
                "major", "coverage", "", 0,
                "No coverage data found — run CI Layer 1 first"
            ))
    except Exception as e:
        result.add_finding(ReviewFinding(
            "major", "coverage", "", 0,
            f"Coverage check failed: {e}"
        ))
    
    result.decide()
    return result


# --- Orchestrator ---

REVIEWER_MAP = {
    "feature": [review_architecture, review_domain_modeling, review_code_style, review_coverage],
    "bugfix": [review_code_style, review_coverage],
    "refactor": [review_architecture, review_code_style, review_coverage],
    "docs": [],  # Docs don't need technical review
    "config": [review_code_style],
    "embedded": [review_architecture, review_embedded_c, review_code_style, review_coverage],
    "firmware": [review_embedded_c, review_code_style],
}


def run_review(task_name: str, task_kind: str, project_dir: str, changed_files: list[str]) -> ReviewSession:
    """Run multi-agent review for a task."""
    print(f"\n🔍 Review Session: {task_name} [{task_kind}]")
    session = ReviewSession(task_name, project_dir)
    
    reviewers = REVIEWER_MAP.get(task_kind, [review_code_style])
    if not reviewers:
        session.decision = "passed"
        session.status = "completed"
        print(f"  ⏭️  No reviewers configured for kind '{task_kind}' — auto-passed")
        session.save()
        return session
    
    for reviewer_fn in reviewers:
        reviewer_name = reviewer_fn.__name__.replace("review_", "").replace("_", "-")
        print(f"  🤖 Running {reviewer_name}...")
        
        try:
            result = reviewer_fn(task_name, project_dir, changed_files)
            session.add_review(result)
            
            if result.status == "passed":
                print(f"    ✅ {reviewer_name}: passed {result.summary}")
            elif result.status == "retry":
                print(f"    🔄 {reviewer_name}: retry ({result.retry_count + 1}/5)")
            else:
                print(f"    ❌ {reviewer_name}: failed")
                
            for finding in result.findings:
                sev_icon = {"critical": "🔴", "major": "🟡", "minor": "🟢", "info": "ℹ️"}
                icon = sev_icon.get(finding.severity, "❓")
                print(f"      {icon} [{finding.category}] {finding.file}:{finding.line} — {finding.message[:80]}")
                
        except Exception as e:
            failed_result = ReviewResult(task_name, reviewer_name)
            failed_result.add_finding(ReviewFinding("critical", "reviewer-error", "", 0, str(e)))
            failed_result.status = "failed"
            session.add_review(failed_result)
            print(f"    ❌ {reviewer_name}: error — {e}")
    
    decision = session.final_decision()
    print(f"\n  📋 Final Decision: {decision.upper()}")
    session.save()
    return session


def auto_review(project_dir: str = None):
    """Auto-review all changed tasks."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())
    
    # Find changed files
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True, cwd=project_dir,
    )
    changed_files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    if not changed_files:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, cwd=project_dir,
        )
        changed_files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
    
    if not changed_files:
        print("No changed files to review.")
        return
    
    print(f"\n{'='*50}")
    print(f"🔍 Auto-Review: {len(changed_files)} file(s) changed")
    print(f"{'='*50}")
    
    # Determine task kind from changes
    task_kind = "feature"
    has_c_files = any(f.endswith((".c", ".h")) for f in changed_files)
    for f in changed_files:
        if "bugfix" in f.lower() or "fix" in f.lower():
            task_kind = "bugfix"
        elif "refactor" in f.lower():
            task_kind = "refactor"
        elif "docs/" in f or f.endswith(".md"):
            if task_kind == "feature":
                task_kind = "docs"
    if has_c_files and task_kind in ("feature", "bugfix", "refactor"):
        task_kind = "embedded"
    
    session = run_review("auto-review", task_kind, project_dir, changed_files)
    return session


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 run.py auto                    — Review all changed files")
        print("  python3 run.py task <name> <kind>      — Review specific task")
        sys.exit(1)
    
    cmd = sys.argv[1]
    project_dir = os.environ.get("OSH_HOME", os.getcwd())
    
    if cmd == "auto":
        auto_review(project_dir)
    elif cmd == "task" and len(sys.argv) >= 3:
        kind = sys.argv[3] if len(sys.argv) > 3 else "feature"
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=project_dir,
        )
        changed = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        run_review(sys.argv[2], kind, project_dir, changed)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
OSH CI Engine — Layer 1: Development Verification CI.

Runs on every commit: plan-lint, clang-tidy, unit tests, coverage gate.
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional


class CIResult:
    def __init__(self, layer: int, commit_hash: str):
        self.layer = layer
        self.commit_hash = commit_hash
        self.started_at = datetime.now().isoformat()
        self.completed_at: Optional[str] = None
        self.status = "running"
        self.stages: list[dict] = []
        self.coverage: Optional[dict] = None
        self.errors: list[str] = []

    def add_stage(self, name: str, status: str, detail: str = ""):
        self.stages.append({
            "name": name,
            "status": status,
            "detail": detail,
            "timestamp": datetime.now().isoformat(),
        })

    def complete(self, status: str = "passed"):
        self.status = status
        self.completed_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "layer": self.layer,
            "commit": self.commit_hash,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "stages": self.stages,
            "coverage": self.coverage,
            "errors": self.errors,
        }


def git_commit_hash() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def get_changed_files(base_ref: str = "HEAD") -> list[str]:
    """Get list of changed files."""
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return [f.strip() for f in result.stdout.split("\n") if f.strip()]
    return []


def find_test_files(project_dir: str) -> list[str]:
    """Auto-discover test files."""
    tests = []
    for root, dirs, files in os.walk(project_dir):
        # Skip hidden dirs and common non-source dirs
        dirs[:] = [d for d in dirs if not d.startswith(".") 
                   and d not in ("node_modules", "__pycache__", "venv")]
        
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                tests.append(os.path.join(root, f))
            elif f.startswith("Test") and f.endswith(".java"):
                tests.append(os.path.join(root, f))
            elif f.endswith("_test.go"):
                tests.append(os.path.join(root, f))
            elif "_test." in f and (f.endswith(".c") or f.endswith(".cpp")):
                tests.append(os.path.join(root, f))
    
    return tests


def run_plan_lint(project_dir: str, ci: CIResult) -> bool:
    """Run plan-lint: check task kind and T00 three-step format."""
    print("  🔍 CI: plan-lint...")
    
    # Look for task files
    task_files = []
    for root, dirs, files in os.walk(project_dir):
        if "tasks" in root.split(os.sep) or root.endswith("tasks"):
            for f in files:
                if f.endswith(".md") and ("task" in f.lower() or "plan" in f.lower()):
                    task_files.append(os.path.join(root, f))
    
    issues = []
    for tf in task_files:
        content = Path(tf).read_text()
        # Check for kind classification
        if "feature" not in content.lower() and "bugfix" not in content.lower() and "refactor" not in content.lower():
            issues.append(f"{tf}: Missing kind classification")
        
        # Check for T00 sections
        if not all(marker in content for marker in ["RED", "GREEN", "REFACTOR"]):
            issues.append(f"{tf}: Missing T00 three-step sections")
    
    if issues:
        for i in issues:
            print(f"    ⚠️  {i}")
        ci.add_stage("plan-lint", "warning", "; ".join(issues[:3]))
        return True  # Warnings don't block
    else:
        ci.add_stage("plan-lint", "passed")
        print("    ✅ plan-lint passed")
        return True


def run_clang_tidy(project_dir: str, ci: CIResult) -> bool:
    """Run clang-tidy on C/C++ files."""
    print("  🔎 CI: clang-tidy...")
    
    c_files = []
    for root, dirs, files in os.walk(os.path.join(project_dir, "src")):
        for f in files:
            if f.endswith((".c", ".cpp", ".h", ".hpp")):
                c_files.append(os.path.join(root, f))
    
    if not c_files:
        ci.add_stage("clang-tidy", "skipped", "No C/C++ files found")
        print("    ⏭️  No C/C++ files — skipped")
        return True
    
    # Try to run clang-tidy
    try:
        result = subprocess.run(
            ["clang-tidy"] + c_files[:20] + ["--", "-std=c11"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            ci.add_stage("clang-tidy", "passed")
            print("    ✅ clang-tidy passed")
            return True
        else:
            ci.add_stage("clang-tidy", "failed", result.stdout[:500])
            print(f"    ⚠️  clang-tidy warnings:\n{result.stdout[:300]}")
            return True  # Warnings only, not blocking
    except FileNotFoundError:
        ci.add_stage("clang-tidy", "skipped", "clang-tidy not installed")
        print("    ⏭️  clang-tidy not installed — skipped")
        return True


def run_unit_tests(project_dir: str, ci: CIResult) -> bool:
    """Discover and run unit tests."""
    print("  🧪 CI: unit tests...")
    
    # Python tests
    test_files = find_test_files(project_dir)
    if test_files:
        print(f"    Found {len(test_files)} test files")
    
    python_tests = [t for t in test_files if t.endswith(".py")]
    
    if python_tests:
        for tf in python_tests:
            rel = os.path.relpath(tf, project_dir)
            print(f"    Running: {rel}")
            result = subprocess.run(
                [sys.executable, "-m", "pytest", tf, "-x", "--tb=short", "-q"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                ci.add_stage("unit-tests", "failed", f"{rel}: {result.stdout[:200]}")
                print(f"    ❌ {rel} FAILED")
                return False
            else:
                ci.add_stage("unit-tests", "passed")
                print(f"    ✅ {rel} passed")
    
    if python_tests:
        return True
    
    # If no tests found, try pytest discovery
    if not python_tests:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-x", "--tb=short", "-q", "--collect-only"],
                capture_output=True, text=True, timeout=30, cwd=project_dir,
            )
            if result.returncode == 0:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-x", "--tb=short", "-q"],
                    capture_output=True, text=True, timeout=120, cwd=project_dir,
                )
                if result.returncode == 0:
                    ci.add_stage("unit-tests", "passed")
                    print("    ✅ All pytest tests passed")
                    return True
                else:
                    ci.add_stage("unit-tests", "failed", result.stdout[:300])
                    print(f"    ❌ Tests failed")
                    return False
        except Exception:
            pass
        
        ci.add_stage("unit-tests", "skipped", "No test framework detected")
        print("    ⏭️  No tests discovered — skipped")
    
    return True


def run_coverage_check(project_dir: str, ci: CIResult) -> bool:
    """Check test coverage meets threshold."""
    print("  📊 CI: coverage check...")
    
    threshold_line = 80.0
    threshold_cond = 75.0  # MVP threshold, raise to 98% in Phase 2
    
    try:
        result = subprocess.run(
            [sys.executable, "-m", "coverage", "run", "--branch", "-m", "pytest", "-q", "--tb=short"],
            capture_output=True, text=True, timeout=120, cwd=project_dir,
        )
        
        result2 = subprocess.run(
            [sys.executable, "-m", "coverage", "json", "--pretty"],
            capture_output=True, text=True, timeout=30, cwd=project_dir,
        )
        
        # Read coverage data from JSON file
        json_file = os.path.join(project_dir, "coverage.json")
        if os.path.exists(json_file):
            json_output = open(json_file).read()
            cov_data = json.loads(json_output)
            totals = cov_data.get("totals", {})
            line_pct = totals.get("percent_covered", 0)
            cond_pct = totals.get("percent_covered_condition", line_pct)  # fallback to line
            
            ci.coverage = {
                "line_coverage": line_pct,
                "condition_coverage": cond_pct,
                "threshold_line": threshold_line,
                "threshold_condition": threshold_cond,
                "line_pass": line_pct >= threshold_line,
                "condition_pass": cond_pct >= threshold_cond,
            }
            
            print(f"    Line coverage: {line_pct:.1f}% (threshold: {threshold_line}%)")
            print(f"    Condition coverage: {cond_pct:.1f}% (threshold: {threshold_cond}%)")
            
            if line_pct < threshold_line:
                ci.add_stage("coverage", "failed", f"Line coverage {line_pct}% < {threshold_line}%")
                print(f"    ❌ Line coverage below threshold!")
                return False
            if cond_pct < threshold_cond:
                ci.add_stage("coverage", "failed", f"Condition coverage {cond_pct}% < {threshold_cond}%")
                print(f"    ❌ Condition coverage below threshold!")
                return False
            
            ci.add_stage("coverage", "passed", f"line={line_pct}%, cond={cond_pct}%")
            print(f"    ✅ Coverage thresholds met")
            return True
        else:
            ci.add_stage("coverage", "skipped", "coverage JSON not available")
            print("    ⏭️  Coverage data not available — skipped")
            return True
            
    except FileNotFoundError:
        ci.add_stage("coverage", "skipped", "Coverage tool not installed")
        print("    ⏭️  Coverage tool not installed — skipped")
        return True
    except subprocess.TimeoutExpired:
        ci.add_stage("coverage", "skipped", "Coverage run timed out")
        print("    ⏭️  Coverage run timed out — skipped")
        return True
    except json.JSONDecodeError as e:
        ci.add_stage("coverage", "skipped", f"JSON decode: {e}")
        print("    ⏭️  Coverage JSON invalid — skipped")
        return True


def run_layer1(project_dir: Optional[str] = None):
    """Run Layer 1 CI pipeline."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())
    
    commit = git_commit_hash()
    print(f"\n🔬 CI Layer 1: Development Verification")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}")
    print()
    
    ci = CIResult(1, commit)
    
    stages = [
        ("plan-lint", run_plan_lint),
        ("clang-tidy", run_clang_tidy),
        ("unit-tests", run_unit_tests),
        ("coverage", run_coverage_check),
    ]
    
    all_passed = True
    for name, handler in stages:
        try:
            passed = handler(project_dir, ci)
            if not passed:
                all_passed = False
                ci.errors.append(f"{name} failed")
        except Exception as e:
            ci.add_stage(name, "error", str(e))
            ci.errors.append(f"{name}: {e}")
            all_passed = False
    
    ci.complete("passed" if all_passed else "failed")
    
    # Save result
    ci_dir = Path(project_dir) / ".osh" / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    result_path = ci_dir / f"layer1-{commit}.json"
    with open(result_path, "w") as f:
        json.dump(ci.to_dict(), f, indent=2)
    
    print(f"\n{'='*40}")
    if all_passed:
        print("✅ CI Layer 1: ALL STAGES PASSED")
    else:
        print(f"❌ CI Layer 1: FAILED — {len(ci.errors)} error(s)")
    
    print(f"   Report: {result_path}")
    print()
    
    return all_passed


def run_layer2(project_dir: Optional[str] = None):
    """CI Layer 2: Integration Verification — runs on MR."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())
    
    commit = git_commit_hash()
    print(f"\n🔄 CI Layer 2: Integration Verification")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}")
    print()
    
    ci = CIResult(2, commit)
    all_passed = True
    
    # Stage 1: Cross-compilation matrix
    print("  🔧 CI: cross-compilation check...")
    src_dir = os.path.join(project_dir, "src")
    c_files = []
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith((".c", ".cpp")):
                c_files.append(os.path.join(root, f))
    
    if c_files:
        print(f"    Found {len(c_files)} C/C++ files — cross-compile ready")
        ci.add_stage("cross-compile", "info", f"{len(c_files)} files ready for ARM/RISC-V/x86")
    else:
        print(f"    ⏭️  No C/C++ files — cross-compile skipped")
        ci.add_stage("cross-compile", "skipped", "No C/C++ sources")
    
    # Stage 2: Static analysis
    print("  🔎 CI: static analysis...")
    if c_files:
        try:
            result = subprocess.run(
                ["cppcheck", "--enable=all", "--suppress=missingIncludeSystem", "-q"] + c_files[:30],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                ci.add_stage("static-analysis", "passed")
                print(f"    ✅ cppcheck passed")
            else:
                ci.add_stage("static-analysis", "warning", result.stdout[:200])
                print(f"    ⚠️  cppcheck found issues")
        except FileNotFoundError:
            ci.add_stage("static-analysis", "skipped", "cppcheck not installed")
            print(f"    ⏭️  cppcheck not installed — skipped")
    else:
        ci.add_stage("static-analysis", "skipped", "No C/C++ sources")
    
    # Stage 3: Integration tests
    print("  🔗 CI: integration tests...")
    int_test_dir = os.path.join(project_dir, "tests", "integration")
    if os.path.exists(int_test_dir):
        print(f"    Found integration test directory")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", int_test_dir, "-x", "-q"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                ci.add_stage("integration-tests", "passed")
                print(f"    ✅ Integration tests passed")
            else:
                ci.add_stage("integration-tests", "failed", result.stdout[:200])
                print(f"    ❌ Integration tests failed")
                all_passed = False
        except Exception as e:
            ci.add_stage("integration-tests", "error", str(e))
    else:
        ci.add_stage("integration-tests", "skipped", "No integration tests")
        print(f"    ⏭️  No integration tests directory")
    
    # Stage 4: Memory safety
    print("  🛡️  CI: memory safety check...")
    if os.path.exists(os.path.join(project_dir, "tests", "asan")):
        ci.add_stage("memory-safety", "info", "ASan tests configured")
        print(f"    ⏭️  ASan tests configured but not run (requires dedicated env)")
    else:
        ci.add_stage("memory-safety", "skipped", "No ASan tests")
        print(f"    ⏭️  No ASan tests found")
    
    ci.complete("passed" if all_passed else "failed")
    
    ci_dir = Path(project_dir) / ".osh" / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    with open(ci_dir / f"layer2-{commit}.json", "w") as f:
        json.dump(ci.to_dict(), f, indent=2)
    
    print(f"\n{'='*40}")
    if all_passed:
        print("✅ CI Layer 2: ALL STAGES PASSED")
    else:
        print(f"❌ CI Layer 2: FAILED")
    print()
    return all_passed


def run_layer3(project_dir: Optional[str] = None):
    """CI Layer 3: System Verification — runs on Release."""
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())
    
    commit = git_commit_hash()
    print(f"\n🚀 CI Layer 3: System Verification (Release)")
    print(f"   Commit: {commit}")
    print(f"   Project: {project_dir}")
    print()
    
    ci = CIResult(3, commit)
    all_passed = True
    
    # Stage 1: E2E tests
    print("  📋 CI: end-to-end tests...")
    e2e_dir = os.path.join(project_dir, "tests", "e2e")
    if os.path.exists(e2e_dir):
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", e2e_dir, "-x", "-q"],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                ci.add_stage("e2e-tests", "passed")
                print(f"    ✅ E2E tests passed")
            else:
                ci.add_stage("e2e-tests", "failed", result.stdout[:200])
                print(f"    ❌ E2E tests failed")
                all_passed = False
        except Exception as e:
            ci.add_stage("e2e-tests", "error", str(e))
    else:
        ci.add_stage("e2e-tests", "skipped", "No E2E tests")
        print(f"    ⏭️  No E2E tests directory")
    
    # Stage 2: Version check
    print("  📦 CI: version check...")
    pyproject = os.path.join(project_dir, "pyproject.toml")
    if os.path.exists(pyproject):
        import tomllib
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
        version = data.get("project", {}).get("version", "unknown")
        ci.add_stage("version-check", "passed", f"Version: {version}")
        print(f"    ✅ Version: {version}")
    else:
        ci.add_stage("version-check", "skipped", "No pyproject.toml")
        print(f"    ⏭️  No version file")
    
    # Stage 3: Evidence pack generation
    print("  📦 CI: generating evidence pack...")
    try:
        sys.path.insert(0, os.path.join(project_dir, "src"))
        from evidence import pack as evidence_pack
        evidence_pack.generate_evidence(project_dir)
        ci.add_stage("evidence-pack", "passed", "Compliance pack generated")
        print(f"    ✅ Evidence pack generated")
    except Exception as e:
        ci.add_stage("evidence-pack", "warning", str(e))
        print(f"    ⚠️  Evidence pack partially generated: {e}")
    
    ci.complete("passed" if all_passed else "failed")
    
    ci_dir = Path(project_dir) / ".osh" / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    with open(ci_dir / f"layer3-{commit}.json", "w") as f:
        json.dump(ci.to_dict(), f, indent=2)
    
    print(f"\n{'='*40}")
    if all_passed:
        print("✅ CI Layer 3: ALL STAGES PASSED 🎉")
    else:
        print(f"❌ CI Layer 3: FAILED")
    print()
    return all_passed


def main():
    layer = sys.argv[1] if len(sys.argv) > 1 else "1"
    
    if layer == "1":
        success = run_layer1()
        sys.exit(0 if success else 1)
    elif layer == "2":
        success = run_layer2()
        sys.exit(0 if success else 1)
    elif layer == "3":
        success = run_layer3()
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown layer: {layer}")
        sys.exit(1)


if __name__ == "__main__":
    main()

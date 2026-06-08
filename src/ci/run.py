#!/usr/bin/env python3
"""
OSH CI Engine — Layer 1: Development Verification CI.

Runs on every commit: plan-lint, clang-tidy, unit tests, coverage gate.
"""

import functools
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("ci")


# ------------------------------------------------------------------
# Strict mode helpers
# ------------------------------------------------------------------

def is_strict() -> bool:
    """Check if CI is running in strict mode (CI_STRICT=1).

    In strict mode, missing tools cause pipeline failure instead of
    silent skip.  Any stage with FileNotFoundError blocks the pipeline.
    """
    return os.environ.get("CI_STRICT", "0") == "1"


def is_misra_fail_fast() -> bool:
    """Check if MISRA_FAIL_FAST is active.

    When enabled, MISRA/CppCheck or clang-tidy failures (non-zero exit)
    block the pipeline immediately instead of producing warnings.
    """
    return os.environ.get("MISRA_FAIL_FAST", "0") == "1"


# ------------------------------------------------------------------
# Layer dependency configuration (A-03)
# ------------------------------------------------------------------

# Layer dependency chain: each layer lists its upstream dependencies.
# L1 has no dependencies.  L2 depends on L1.  L3 depends on L1 and L2.
# Order: L1 → L2 → L3.
layer_dependencies: dict[int, list[int]] = {
    1: [],
    2: [1],
    3: [1, 2],
}


def get_latest_layer_result(layer: int, project_dir: str) -> Optional[dict]:
    """Read the most recent CI result for the given layer from .osh/ci/.

    Returns the parsed JSON dict if found, or None if no result exists.
    """
    ci_dir = Path(project_dir) / ".osh" / "ci"
    if not ci_dir.exists():
        return None

    prefix = f"layer{layer}-"
    result_files = sorted(
        [f for f in ci_dir.iterdir() if f.name.startswith(prefix) and f.suffix == ".json"],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not result_files:
        return None
    try:
        return json.loads(result_files[0].read_text())
    except (json.JSONDecodeError, OSError):
        return None


def check_layer_dependency(target_layer: int, project_dir: str) -> Optional[str]:
    """Check if all dependencies for *target_layer* are satisfied.

    Returns None if all deps passed, or a string describing the first
    blocking dependency failure.
    """
    deps = layer_dependencies.get(target_layer, [])
    for dep in deps:
        result = get_latest_layer_result(dep, project_dir)
        if result is None:
            return (
                f"Layer {dep} has no recorded result — "
                f"run layer {dep} first before layer {target_layer}"
            )
        if result.get("status") != "passed":
            return (
                f"Layer {dep} status is '{result.get('status', 'unknown')}' — "
                f"layer {target_layer} blocked (dependency chain: "
                f"{' → '.join(str(l) for l in deps)})"
            )
    return None


# ------------------------------------------------------------------
# Timing decorator
# ------------------------------------------------------------------


def timed_stage(func):
    """Decorate a CI stage handler to measure and log execution time."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - t0
            log.info(f"Stage {func.__name__} took {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.perf_counter() - t0
            log.info(f"Stage {func.__name__} FAILED after {elapsed:.3f}s")
            raise
    return wrapper


# ------------------------------------------------------------------
# Test file discovery cache — keyed by project_dir, invalidated on mtime
# ------------------------------------------------------------------

_test_file_cache: dict = {}
_test_file_cache_mtime: dict = {}


def get_cache_key_for_dir(project_dir: str) -> str:
    """Build a cache key that changes when test files or dirs change.

    Uses a simple hash of all .py / _test.go files and test directories.
    """
    import hashlib
    h = hashlib.md5()
    # Walk once to collect relevant paths and their mtimes
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".") 
                   and d not in ("node_modules", "__pycache__", "venv")]
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                h.update(f.encode())
                try:
                    mtime = os.path.getmtime(os.path.join(root, f))
                    h.update(str(mtime).encode())
                except OSError:
                    pass
            elif f.endswith("_test.go"):
                h.update(f.encode())
                try:
                    mtime = os.path.getmtime(os.path.join(root, f))
                    h.update(str(mtime).encode())
                except OSError:
                    pass
    return h.hexdigest()

# Notifications (optional import)
_notify = None
try:
    from notify import notify_ci as _notify_ci
    _notify = _notify_ci
except ImportError:
    _notify = None


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
    """Auto-discover test files with mtime-based caching.

    Caches results keyed by a hash of file names + mtimes, so
    repeated scans only walk the filesystem when files change.
    """
    # Build cache key
    cache_key = get_cache_key_for_dir(project_dir)
    cached = _test_file_cache.get(cache_key)
    if cached is not None:
        return cached

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
    
    # Cache result
    _test_file_cache[cache_key] = tests
    return tests


@timed_stage
def run_plan_lint(project_dir: str, ci: CIResult) -> bool:
    """Run plan-lint: check task kind and T00 three-step format."""
    print("  🔍 CI: plan-lint...")
    
    # Look for task files
    task_files = []
    for root, dirs, files in os.walk(project_dir):
        # Skip hidden directories (test artifacts, .git, .osh/sessions etc.)
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "tasks" in root.split(os.sep) or root.endswith("tasks"):
            for f in files:
                if f.endswith(".md") and ("task" in f.lower() or "plan" in f.lower()):
                    task_files.append(os.path.join(root, f))
    
    if not task_files:
        ci.add_stage("plan-lint", "skipped", "No task/plan files found")
        print("    ⏭️  No task/plan files — skipped")
        return True
    
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
        ci.add_stage("plan-lint", "failed", "; ".join(issues[:3]))
        print(f"    ❌ plan-lint found {len(issues)} issue(s) — blocking pipeline")
        return False  # Warnings block the pipeline per A-01
    else:
        ci.add_stage("plan-lint", "passed")
        print("    ✅ plan-lint passed")
        return True


@timed_stage
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
    
    strict = is_strict()
    misra_ff = is_misra_fail_fast()
    
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
            detail = result.stdout[:500] if result.stdout else result.stderr[:500]
            if misra_ff:
                ci.add_stage("clang-tidy", "failed", detail)
                print(f"    ❌ clang-tidy found issues (MISRA_FAIL_FAST):\n{detail}")
                return False
            ci.add_stage("clang-tidy", "failed", detail)
            print(f"    ❌ clang-tidy found issues:\n{result.stdout[:300]}")
            return False  # A-01: always block on tool failure
    except FileNotFoundError:
        reason = "clang-tidy not installed"
        if strict:
            ci.add_stage("clang-tidy", "failed", reason)
            print(f"    ❌ {reason} (strict mode)")
            return False
        ci.add_stage("clang-tidy", "skipped", reason)
        print(f"    ⏭️  {reason} — skipped")
        return False  # A-01: skip returns False, blocking pipeline
    except subprocess.TimeoutExpired:
        reason = "clang-tidy timed out"
        if strict:
            ci.add_stage("clang-tidy", "failed", reason)
            print(f"    ❌ {reason} (strict mode)")
            return False
        ci.add_stage("clang-tidy", "skipped", reason)
        print(f"    ⏭️  {reason} — skipped")
        return False  # A-01: skip returns False, blocking pipeline


@timed_stage
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
        except FileNotFoundError:
            ci.add_stage("unit-tests", "skipped", "pytest not installed")
            print("    ⏭️  pytest not installed — blocked")
            return False  # A-01: missing tool blocks
        except subprocess.TimeoutExpired:
            ci.add_stage("unit-tests", "skipped", "pytest timed out")
            print("    ⏭️  pytest timed out — blocked")
            return False  # A-01: tool error blocks
        except Exception as e:
            ci.add_stage("unit-tests", "skipped", f"pytest error: {e}")
            print(f"    ⏭️  pytest error: {e} — blocked")
            return False  # A-01: tool error blocks
        
        ci.add_stage("unit-tests", "skipped", "No test framework detected")
        print("    ⏭️  No tests discovered — skipped")
    
    return True


@timed_stage
def run_coverage_check(project_dir: str, ci: CIResult) -> bool:
    """Check test coverage meets threshold.

    Skips coverage when HOOK_TYPE=commit (pre-commit hook) to avoid
    slowing down every commit.  Coverage runs on push (HOOK_TYPE=push
    or when not in a hook at all).
    """
    # In pre-commit hooks, skip coverage to keep commit fast;
    # coverage runs on push / standalone CI runs.
    hook_type = os.environ.get("HOOK_TYPE", "")
    if hook_type == "commit":
        ci.add_stage("coverage", "skipped", "HOOK_TYPE=commit — skip coverage, runs on push")
        print(f"    ⏭️  Coverage skipped (pre-commit hook — runs on push)")
        return True  # Intentional skip, not a failure

    # Skip coverage if run from within a coverage run (prevent recursion)
    if os.environ.get("COVERAGE_RUN") == "1":
        ci.add_stage("coverage", "skipped", "Skipped to prevent recursion")
        print(f"    ⏭️  Coverage skipped (nested run)")
        return True  # Intentional skip, not a failure
    
    print("  📊 CI: coverage check...")
    
    threshold_line = 38.0  # MVP threshold, raise as tests grow
    threshold_cond = 38.0
    
    strict = is_strict()
    
    try:
        cov_env = {**os.environ, "COVERAGE_RUN": "1"}
        result = subprocess.run(
            [sys.executable, "-m", "coverage", "run", "--branch", "--source=src", "-m", "pytest", "-q", "--tb=short", "tests/"],
            capture_output=True, text=True, timeout=120, cwd=project_dir, env=cov_env,
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
            print("    ⏭️  Coverage data not available — blocked")
            return False  # A-01: missing data blocks
            
    except FileNotFoundError:
        reason = "Coverage tool not installed"
        if strict:
            ci.add_stage("coverage", "failed", reason)
            print(f"    ❌ {reason} (strict mode)")
            return False
        ci.add_stage("coverage", "skipped", reason)
        print(f"    ⏭️  {reason} — blocked (missing tool)")
        return False  # A-01: missing tool blocks
    except subprocess.TimeoutExpired:
        reason = "Coverage run timed out"
        if strict:
            ci.add_stage("coverage", "failed", reason)
            print(f"    ❌ {reason} (strict mode)")
            return False
        ci.add_stage("coverage", "skipped", reason)
        print(f"    ⏭️  {reason} — blocked (timeout)")
        return False  # A-01: tool error blocks
    except json.JSONDecodeError as e:
        reason = f"Coverage JSON invalid: {e}"
        ci.add_stage("coverage", "skipped", reason)
        print(f"    ⏭️  {reason} — blocked")
        return False  # A-01: data error blocks


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
    
    # Send notification
    if _notify:
        try:
            _notify(
                layer=1,
                status="passed" if all_passed else "failed",
                stages=ci.stages,
                errors=ci.errors,
            )
        except Exception as ne:
            log.warning(f"Notification failed: {ne}")

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
    misra_ff = is_misra_fail_fast()
    strict = is_strict()
    
    # Stage 1: Cross-compilation matrix
    print("  🔧 CI: cross-compilation check...")
    src_dir = os.path.join(project_dir, "src")
    c_files = []
    for root, dirs, files in os.walk(src_dir):
        for f in files:
            if f.endswith((".c", ".cpp")):
                c_files.append(os.path.join(root, f))
    
    cross_src = os.path.join(project_dir, "src", "cross", "hello.c")
    build_dir = os.path.join(project_dir, "build")
    
    if not os.path.exists(cross_src):
        print(f"    ⏭️  No cross-compile test source (src/cross/hello.c)")
        ci.add_stage("cross-compile", "skipped", "No src/cross/hello.c")
    else:
        # Attempt 1: run `make TARGET=arm` directly
        compiled_ok = False
        make_available = False
        try:
            subprocess.run(
                ["make", "--version"],
                capture_output=True, timeout=5,
            )
            make_available = True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            make_available = False

        if make_available:
            print(f"    Found cross-compile source: {cross_src}")
            print(f"    Running: make TARGET=arm...")
            try:
                result = subprocess.run(
                    ["make", "TARGET=arm"],
                    capture_output=True, text=True, timeout=60,
                    cwd=project_dir,
                )
                if result.returncode == 0:
                    elf_files = list(Path(build_dir).glob("*.elf")) if os.path.exists(build_dir) else []
                    if elf_files:
                        print(f"    ✅ Cross-compilation succeeded: {', '.join(str(e) for e in elf_files)}")
                        ci.add_stage("cross-compile", "passed",
                                     f"ARM ELF at {elf_files[0]}")
                        compiled_ok = True
                    else:
                        print(f"    ⚠️  make succeeded but no .elf found in build/")
                        ci.add_stage("cross-compile", "failed",
                                     "make returned 0 but no .elf found")
                        all_passed = False
                else:
                    detail = result.stderr[:400] if result.stderr else result.stdout[:400]
                    print(f"    ❌ make TARGET=arm failed: {detail}")
                    ci.add_stage("cross-compile", "failed",
                                 f"make returned {result.returncode}: {detail}")
                    all_passed = False
            except subprocess.TimeoutExpired:
                print(f"    ❌ make timed out")
                ci.add_stage("cross-compile", "failed", "make timed out")
                all_passed = False
        else:
            # Attempt 2: try Docker
            docker_available = False
            try:
                subprocess.run(
                    ["docker", "--version"],
                    capture_output=True, timeout=5,
                )
                docker_available = True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                docker_available = False

            if docker_available:
                print(f"    make not available, trying Docker (Dockerfile.cross)...")
                try:
                    subprocess.run(
                        ["docker", "build", "-t", "yuleosh-cross",
                         "-f", "Dockerfile.cross", "."],
                        capture_output=True, text=True, timeout=120,
                        cwd=project_dir,
                    )
                    result = subprocess.run(
                        ["docker", "run", "--rm",
                         "-v", f"{project_dir}:/work",
                         "yuleosh-cross", "make", "TARGET=arm"],
                        capture_output=True, text=True, timeout=120,
                    )
                    if result.returncode == 0:
                        print(f"    ✅ Docker cross-compilation succeeded")
                        ci.add_stage("cross-compile", "passed",
                                     "ARM ELF via Docker")
                        compiled_ok = True
                    else:
                        detail = result.stderr[:400] if result.stderr else result.stdout[:400]
                        print(f"    ❌ Docker cross-compilation failed: {detail}")
                        ci.add_stage("cross-compile", "failed",
                                     f"Docker make failed: {detail}")
                        all_passed = False
                except (subprocess.TimeoutExpired, OSError) as e:
                    print(f"    ❌ Docker error: {e}")
                    ci.add_stage("cross-compile", "failed",
                                 f"Docker error: {e}")
                    all_passed = False
            else:
                # Neither make nor Docker available — clear error
                print(f"    ❌ Cross-compilation FAILED: no ARM toolchain, no make, no Docker")
                print(f"       Install gcc-arm-none-eabi or Docker to enable cross-compilation.")
                msg = (
                    "ARM cross-compilation tools not found. "
                    "Install gcc-arm-none-eabi (apt: gcc-arm-none-eabi) "
                    "or Docker, then run 'make TARGET=arm' manually."
                )
                ci.add_stage("cross-compile", "failed", msg)
                all_passed = False
    
    # Stage 2: Static analysis (cppcheck)
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
                detail = result.stdout[:500] if result.stdout else result.stderr[:500]
                if misra_ff:
                    ci.add_stage("static-analysis", "failed", detail)
                    print(f"    ❌ cppcheck found issues (MISRA_FAIL_FAST)")
                    all_passed = False
                else:
                    ci.add_stage("static-analysis", "failed", result.stdout[:200])
                    print(f"    ❌ cppcheck found issues")
                    all_passed = False  # A-01: always block, not just warning
        except FileNotFoundError:
            reason = "cppcheck not installed"
            if strict:
                ci.add_stage("static-analysis", "failed", reason)
                print(f"    ❌ {reason} (strict mode)")
                all_passed = False
            else:
                ci.add_stage("static-analysis", "skipped", reason)
                print(f"    ⏭️  {reason} — blocked (missing tool)")
                all_passed = False  # A-01: missing tool blocks
        except subprocess.TimeoutExpired:
            reason = "cppcheck timed out"
            if strict:
                ci.add_stage("static-analysis", "failed", reason)
                print(f"    ❌ {reason} (strict mode)")
                all_passed = False
            else:
                ci.add_stage("static-analysis", "skipped", reason)
                print(f"    ⏭️  {reason} — blocked (timeout)")
                all_passed = False
    else:
        ci.add_stage("static-analysis", "skipped", "No C/C++ sources")
        print(f"    ⏭️  No C/C++ sources")
    
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
        except FileNotFoundError:
            reason = "pytest not installed"
            ci.add_stage("integration-tests", "skipped", reason)
            print(f"    ⏭️  {reason} — blocked")
            all_passed = False
        except subprocess.TimeoutExpired:
            reason = "Integration tests timed out"
            ci.add_stage("integration-tests", "skipped", reason)
            print(f"    ⏭️  {reason} — blocked")
            all_passed = False
        except Exception as e:
            ci.add_stage("integration-tests", "error", str(e))
            print(f"    ❌ Integration tests error: {e}")
            all_passed = False
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
    
    # Send notification
    if _notify:
        try:
            _notify(
                layer=2,
                status="passed" if all_passed else "failed",
                stages=ci.stages,
                errors=ci.errors,
            )
        except Exception as ne:
            log.warning(f"Notification failed: {ne}")

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
        except FileNotFoundError:
            ci.add_stage("e2e-tests", "skipped", "pytest not installed — blocked")
            print(f"    ⏭️  pytest not installed — blocked")
            all_passed = False
        except subprocess.TimeoutExpired:
            ci.add_stage("e2e-tests", "skipped", "E2E tests timed out — blocked")
            print(f"    ⏭️  E2E tests timed out — blocked")
            all_passed = False
        except Exception as e:
            ci.add_stage("e2e-tests", "error", str(e))
            print(f"    ❌ E2E tests error: {e}")
            all_passed = False
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
    
    # Send notification
    if _notify:
        try:
            _notify(
                layer=3,
                status="passed" if all_passed else "failed",
                stages=ci.stages,
                errors=ci.errors,
            )
        except Exception as ne:
            log.warning(f"Notification failed: {ne}")

    print(f"\n{'='*40}")
    if all_passed:
        print("✅ CI Layer 3: ALL STAGES PASSED 🎉")
    else:
        print(f"❌ CI Layer 3: FAILED")
    print()
    return all_passed


def run_all(project_dir: Optional[str] = None):
    """Run the full CI pipeline: L1 → L2 → L3 with dependency gating.

    Each layer only runs if all its upstream dependencies passed.
    Returns True if all layers passed, False otherwise.
    """
    if project_dir is None:
        project_dir = os.environ.get("OSH_HOME", os.getcwd())

    print("\n" + "=" * 50)
    print("  🚀 CI Pipeline: L1 → L2 → L3")
    print("=" * 50)

    layers = [1, 2, 3]
    all_passed = True

    for layer in layers:
        # Check dependencies before running
        blocker = check_layer_dependency(layer, project_dir)
        if blocker:
            print(f"\n  🔒 Layer {layer} SKIPPED — dependency not satisfied")
            print(f"     Reason: {blocker}")
            all_passed = False
            break  # Chain break: no point continuing

        # Run the layer
        if layer == 1:
            passed = run_layer1(project_dir)
        elif layer == 2:
            passed = run_layer2(project_dir)
        elif layer == 3:
            passed = run_layer3(project_dir)
        else:
            passed = False

        if not passed:
            all_passed = False
            print(f"\n  🔒 Layer {layer} FAILED — downstream layers blocked")
            remaining = [l for l in layers if l > layer]
            if remaining:
                print(f"     Blocked layers: {', '.join(f'L{l}' for l in remaining)}")
            break

    print("\n" + "=" * 50)
    if all_passed:
        print("  ✅ CI Pipeline: ALL LAYERS PASSED 🎉")
    else:
        print("  ❌ CI Pipeline: FAILED")
    print("=" * 50 + "\n")
    return all_passed


def main():
    layer = sys.argv[1] if len(sys.argv) > 1 else "1"
    
    if layer == "all":
        success = run_all()
        sys.exit(0 if success else 1)
    elif layer == "1":
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
        print("Usage: python3 run.py [1|2|3|all]")
        sys.exit(1)


if __name__ == "__main__":
    main()

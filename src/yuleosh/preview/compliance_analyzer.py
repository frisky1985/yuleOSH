"""
yuleOSH AI Preview — Compliance risk analyzer.

Provides ``_scan_risks()`` which detects compliance risk factors such as
dynamic memory allocation, recursion, unbounded loops, missing assertions,
and documentation gaps.
"""

import re
from pathlib import Path


def _scan_risks(source_dir: Path, complexity: dict) -> list[dict]:
    """Scan for compliance risk factors (PREVIEW-REQ-004.2)."""
    risks = []

    # 1. Dynamic memory allocation in embedded C
    malloc_count = 0
    free_count = 0
    new_count = 0

    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        malloc_count += len(re.findall(r'\bmalloc\s*\(', content))
        free_count += len(re.findall(r'\bfree\s*\(', content))
        new_count += len(re.findall(r'\bnew\s+', content))

    if malloc_count > 0:
        risk_level = "high" if malloc_count > 10 else "medium"
        risks.append({
            "risk_level": risk_level,
            "description": f"Dynamic memory allocation detected ({malloc_count} malloc/free calls). Not recommended for safety-critical embedded systems.",
            "occurrences": malloc_count + free_count,
            "recommendation": "Replace dynamic allocation with static pool allocation. Use pre-allocated buffers or memory pools.",
        })

    # 2. Recursion detection
    recursion_count = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        recursion_count += len(re.findall(r'(\w+)\s*\([^)]*\)\s*\n?\{[^}]*\1\s*\(', content, re.DOTALL))

    if recursion_count > 0:
        risks.append({
            "risk_level": "high" if recursion_count > 3 else "medium",
            "description": f"Recursive function calls detected ({recursion_count} instances). Recursion is not recommended for safety-critical embedded systems.",
            "occurrences": recursion_count,
            "recommendation": "Replace recursive algorithms with iterative equivalents. Ensure bounded recursion depth if unavoidable.",
        })

    # 3. Unbounded loops (while(1) / for(;;) with no break/return)
    unbounded_count = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        unbounded_count += len(re.findall(r'while\s*\(1\)', content))
        unbounded_count += len(re.findall(r'for\s*\(\s*;\s*;', content))

    if unbounded_count > 0:
        risks.append({
            "risk_level": "medium",
            "description": f"Unbounded loops detected ({unbounded_count} instances). Ensure loops have deterministic exit conditions for safety-critical contexts.",
            "occurrences": unbounded_count,
            "recommendation": "Add explicit exit conditions or timeout counters to all loops. For while(1), ensure watchdog refresh is present.",
        })

    # 4. Lack of assertions
    assert_count = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
        except Exception:
            continue
        assert_count += len(re.findall(r'\bassert\s*\(', content))

    if assert_count == 0:
        risks.append({
            "risk_level": "medium",
            "description": "No assertions found. Defensive programming practices are recommended.",
            "occurrences": 0,
            "recommendation": "Add assertions for preconditions, postconditions, and invariant checks.",
        })

    # 5. Function length
    if complexity.get("max_function_lines", 0) > 100:
        risks.append({
            "risk_level": "low",
            "description": f"Overly long functions found (max {complexity['max_function_lines']} lines). Long functions reduce readability and testability.",
            "occurrences": 1,
            "recommendation": "Refactor long functions into smaller units following the Single Responsibility Principle.",
        })

    # 6. High function count warning
    if complexity.get("total_functions", 0) > 100:
        risks.append({
            "risk_level": "low",
            "description": f"Large number of functions detected ({complexity['total_functions']}). Consider modularization for maintainability.",
            "occurrences": complexity["total_functions"],
            "recommendation": "Organize functions into logical modules and ensure consistent naming conventions.",
        })

    # 7. Spec/evidence maturity
    has_specs = any(f.name == "spec.md" for f in source_dir.rglob("*") if f.is_file())
    has_trace = any("trace" in f.stem.lower() for f in source_dir.rglob("*") if f.is_file())

    if not has_specs:
        risks.append({
            "risk_level": "high",
            "description": "No OpenSpec specification file (spec.md) found. ASPICE compliance requires traceable requirements.",
            "occurrences": 0,
            "recommendation": "Create a spec.md file with SHALL statements following the yuleOSH OpenSpec format.",
        })

    if not has_trace:
        risks.append({
            "risk_level": "medium",
            "description": "No traceability matrix found. Evidence traceability is required for ASPICE compliance.",
            "occurrences": 0,
            "recommendation": "Generate a traceability matrix linking requirements to test cases.",
        })

    # 8. Nesting depth risk
    max_nesting = complexity.get("max_nesting_depth", 0)
    if max_nesting > 5:
        risks.append({
            "risk_level": "medium",
            "description": f"Deep nesting detected (depth {max_nesting}). Deeply nested code is harder to test and review.",
            "occurrences": max_nesting,
            "recommendation": "Refactor deeply nested blocks into separate functions. Use early-return pattern to reduce nesting.",
        })

    # 9. Comment deficiency
    total_source = 0
    total_comments = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
            for line in content.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                total_source += 1
                if stripped.startswith(("//", "/*", "*")):
                    total_comments += 1
        except Exception:
            pass

    comment_ratio = total_comments / max(total_source, 1)
    if comment_ratio < 0.05 and total_source > 50:
        risks.append({
            "risk_level": "low",
            "description": f"Low comment-to-code ratio ({round(comment_ratio * 100, 1)}%). Code readability may be impacted.",
            "occurrences": total_source,
            "recommendation": "Add function-level doc comments and inline explanations for complex logic.",
        })

    return risks

"""
yuleOSH AI Preview — Coverage prediction module.

Provides ``_predict_coverage()`` which estimates current and projected
code coverage based on test infrastructure, density, and complexity.
"""


def _predict_coverage(test_density: float, test_framework: str,
                      complexity_score: float) -> dict:
    """Predict current and projected coverage (PREVIEW-REQ-004.1).

    Uses a heuristic model:
      coverage_estimate = f(test_density, code_complexity, test_maturity)
    """
    # Base estimate from test density
    if test_framework == "none":
        base = 5.0
        confidence = "low"
        maturity = 0.0
    elif test_framework == "unknown":
        base = 25.0
        confidence = "low"
        maturity = 1.0
    elif test_framework in ("Unity", "CUnit"):
        base = 40.0 + (test_density * 30.0)
        confidence = "medium"
        maturity = 2.0
    elif test_framework in ("CMock",):
        base = 50.0 + (test_density * 25.0)
        confidence = "medium"
        maturity = 2.5
    elif test_framework in ("Google Test", "pytest", "unittest", "Catch2"):
        base = 55.0 + (test_density * 25.0)
        confidence = "medium"
        maturity = 2.0
    else:
        base = 30.0
        confidence = "low"
        maturity = 1.0

    # Penalize complexity
    if complexity_score > 50:
        penalty = 10.0
    elif complexity_score > 30:
        penalty = 5.0
    else:
        penalty = 0.0

    current = max(0, min(100, round(base - penalty, 1)))

    # Projected coverage after yuleOSH
    projected = min(100, round(current + 30.0 + (maturity * 5.0), 1))

    # Bottleneck files (simulated — real analysis would use per-file results)
    bottleneck_files = []
    if current < 50:
        bottleneck_files.append("src/main.c (estimated < 30% coverage)")
    if current < 60:
        bottleneck_files.append("src/hal/gpio.c (estimated < 40% coverage)")

    return {
        "current_coverage_estimate": current,
        "projected_coverage_after_yuleosh": projected,
        "confidence": confidence,
        "bottleneck_files": bottleneck_files[:5],
    }

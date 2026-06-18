"""
yuleOSH Preview — Score engine.

Provides scoring and estimation functions used by the preview analyzer:
language detection, documentation assessment, effort estimation, and
maturity rating.
"""

import re
from pathlib import Path

# Language mapping for source files
LANGUAGE_MAP = {
    ".c": "C", ".h": "C Header", ".cpp": "C++", ".hpp": "C++ Header",
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript React", ".md": "Markdown", ".json": "JSON",
    ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
}


def _count_total_lines(files: list[Path]) -> int:
    total = 0
    for f in files:
        try:
            total += len(f.read_text(errors="replace").splitlines())
        except Exception:
            pass
    return total


def _count_by_extension(files: list[Path]) -> dict:
    counts: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower()
        counts[ext] = counts.get(ext, 0) + 1
    return counts


def _extract_lines(files: list[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower()
        try:
            counts[ext] = counts.get(ext, 0) + len(f.read_text(errors="replace").splitlines())
        except Exception:
            pass
    return counts


def _detect_languages(all_files: list[Path], source_dir: Path) -> dict:
    """Detect programming language distribution in the project."""
    lang_counts: dict[str, int] = {}
    lang_lines: dict[str, int] = {}

    for f in all_files:
        ext = f.suffix.lower()
        lang = LANGUAGE_MAP.get(ext, "Other")
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        try:
            lang_lines[lang] = lang_lines.get(lang, 0) + len(f.read_text(errors="replace").splitlines())
        except Exception:
            pass

    total = max(sum(lang_counts.values()), 1)
    return {
        "distribution": {
            lang: {
                "file_count": lang_counts.get(lang, 0),
                "total_lines": lang_lines.get(lang, 0),
                "percentage": round(lang_counts.get(lang, 0) / total * 100, 1),
            }
            for lang in sorted(lang_counts.keys())
        },
        "primary_language": max(lang_counts, key=lang_counts.get) if lang_counts else "Unknown",
    }


def _assess_documentation(source_dir: Path) -> dict:
    """Assess documentation quality (README, docstrings, code comments)."""
    has_readme = False
    readme_quality = 0
    for f in source_dir.rglob("*"):
        if f.is_file() and f.name.lower().startswith("readme"):
            has_readme = True
            try:
                lines = f.read_text(errors="replace").splitlines()
                content_lines = [l for l in lines if l.strip() and not l.startswith("#")]
                readme_quality = min(100, len(content_lines) * 5)
            except Exception:
                pass
            break

    comment_lines = 0
    code_lines = 0
    for f in sorted(source_dir.rglob("*.c")):
        try:
            content = f.read_text(errors="replace")
            for line in content.split("\n"):
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
                    comment_lines += 1
                else:
                    code_lines += 1
        except Exception:
            pass

    comment_ratio = round(comment_lines / max(code_lines, 1), 3)

    docstring_count = 0
    for f in sorted(source_dir.rglob("*.py")):
        try:
            content = f.read_text(errors="replace")
            docstring_count += len(re.findall(r'"""', content)) // 2
        except Exception:
            pass

    has_spec = any(f.name == "spec.md" for f in source_dir.rglob("*") if f.is_file())

    score = 0
    if has_readme:
        score += 25
    if comment_ratio >= 0.15:
        score += 25
    elif comment_ratio >= 0.1:
        score += 15
    elif comment_ratio >= 0.05:
        score += 5
    if docstring_count >= 5:
        score += 25
    elif docstring_count >= 2:
        score += 15
    if has_spec:
        score += 25

    return {
        "has_readme": has_readme,
        "readme_quality": readme_quality,
        "comment_to_code_ratio": comment_ratio,
        "docstring_count": docstring_count,
        "has_spec": has_spec,
        "doc_score": min(100, score),
    }


def _estimate_effort(all_files: list[Path], frameworks: list[dict],
                     complexity: dict) -> dict:
    """Estimate person-hours based on code volume and complexity."""
    total_lines = _count_total_lines(all_files)
    source_exts = {".c", ".cpp", ".py", ".js", ".ts", ".tsx"}
    source_lines = 0
    for f in all_files:
        if f.suffix.lower() in source_exts:
            try:
                source_lines += len(f.read_text(errors="replace").splitlines())
            except Exception:
                pass

    base_hours = source_lines / 50.0

    avg_lpf = complexity.get("avg_lines_per_function", 0)
    if avg_lpf > 40:
        complexity_mult = 1.4
    elif avg_lpf > 25:
        complexity_mult = 1.2
    else:
        complexity_mult = 1.0

    has_autosar = any(f["name"] == "AUTOSAR" for f in frameworks)
    framework_mult = 1.4 if has_autosar else 1.0

    estimated = round(base_hours * complexity_mult * framework_mult, 1)

    return {
        "estimated_person_hours": estimated,
        "source_lines_of_code": source_lines,
        "lines_per_hour_assumption": 50,
        "complexity_multiplier": complexity_mult,
        "framework_multiplier": framework_mult,
    }


def _compute_maturity(test_framework: str, test_density: float,
                      test_file_count: int, complexity: dict,
                      doc_quality: dict, frameworks: list[dict],
                      coverage: dict) -> dict:
    """Compute overall project maturity rating (0-100)."""
    score = 0

    if test_framework not in ("none", "unknown"):
        score += 15
    if test_density >= 0.5:
        score += 15
    elif test_density >= 0.25:
        score += 10
    elif test_density > 0:
        score += 5
    if test_file_count >= 5:
        score += 10
    elif test_file_count >= 2:
        score += 5

    score += min(25, doc_quality.get("doc_score", 0) * 0.25)

    avg_lpf = complexity.get("avg_lines_per_function", 0)
    if avg_lpf > 50:
        score -= 15
    elif avg_lpf > 30:
        score -= 10
    elif avg_lpf > 20:
        score -= 5

    cov_est = coverage.get("current_coverage_estimate", 0)
    if cov_est >= 70:
        score += 10
    elif cov_est >= 50:
        score += 5

    for fw in frameworks:
        if fw["name"] == "AUTOSAR":
            score -= 5
            break

    score = max(0, min(100, score))

    if score >= 80:
        rating = "excellent"
    elif score >= 60:
        rating = "good"
    elif score >= 40:
        rating = "fair"
    elif score >= 20:
        rating = "developing"
    else:
        rating = "initial"

    return {
        "score": score,
        "rating": rating,
        "test_maturity_score": min(40, max(0, score)),
        "documentation_score": doc_quality.get("doc_score", 0),
    }

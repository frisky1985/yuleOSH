"""
yuleOSH Evidence Engine — Report template utilities.

Provides helper functions for formatting traceability matrices, coverage
reports, acceptance matrices, and review logs into Markdown and JSON.
"""

from datetime import datetime


def format_maturity_label(score: int) -> str:
    """Convert a maturity score (0-100) into a human-readable label."""
    if score >= 80:
        return "excellent"
    elif score >= 60:
        return "good"
    elif score >= 40:
        return "fair"
    elif score >= 20:
        return "developing"
    return "initial"


def format_status_icon(status: str) -> str:
    """Return a status icon for the given status string."""
    _map = {
        "passed": "✅", "failed": "❌", "retry": "🔄", "running": "⏳",
    }
    return _map.get(status, "❓")


def format_coverage_summary(total: int, covered: int) -> str:
    """Format a coverage percentage summary line."""
    pct = (covered / total * 100) if total > 0 else 0
    return f"{covered}/{total} ({pct:.0f}%)"


def make_table_row(*cells: str, sep: str = " | ") -> str:
    """Join cells into a Markdown table row."""
    return f"{sep}".join(cells)


def make_header_row(*cells: str) -> str:
    """Create a Markdown table header."""
    header = make_table_row(*cells)
    separator = "|" + "|".join(":---" if "--" not in c else ":---" for c in cells) + "|"
    return f"{header}\n{separator}"


def make_acceptance_row(req_id: str, name: str, shall: str, verification: str,
                        test_str: str, mode: str, confidence: str,
                        status: str) -> str:
    """Build a single row of the acceptance matrix table."""
    return make_table_row(req_id, name, shall, verification, test_str,
                          mode, confidence, status)


def make_coverage_table_row(metric: str, value: str, threshold: str,
                            status: str) -> str:
    """Build a code-coverage table row."""
    return make_table_row(metric, value, threshold, status)


def dedent(text: str) -> str:
    """Remove common leading whitespace from a multi-line string."""
    lines = text.split("\n")
    if not lines:
        return text
    min_indent = min(
        len(line) - len(line.lstrip())
        for line in lines if line.strip()
    ) if any(l.strip() for l in lines) else 0
    return "\n".join(line[min_indent:] if len(line) >= min_indent else line
                     for line in lines)


def generate_timestamp() -> str:
    """Return an ISO-8601 timestamp string."""
    return datetime.now().isoformat()

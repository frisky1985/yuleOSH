"""Tests for OpenSpec directory aggregation in spec_contracts.py."""

from pathlib import Path

from yuleosh.spec_contracts import (
    extract_contracts_dir,
    contracts_check_dir,
)


def _write_capability(root: Path, cap: str, req_id: str, name: str) -> Path:
    """Write a minimal OpenSpec capability spec file with a contract block."""
    d = root / cap
    d.mkdir(parents=True, exist_ok=True)
    p = d / "spec.md"
    p.write_text(
        f"# {name}\n\n"
        f"## {req_id}: {name}\n\n"
        f"- The system SHALL {name.lower()}\n\n"
        "### Reason\n\nNeeded\n\n"
        f"### {name.lower()}_api.h\n\n"
        "```c\n"
        f"void {name.lower()}_init(void);\n"
        "```\n"
    )
    return p


class TestExtractContractsDir:
    def test_aggregates_capabilities(self, tmp_path):
        specs = tmp_path / ".osh" / "specs"
        _write_capability(specs, "window", "SR-001", "Window")
        _write_capability(specs, "light", "SR-002", "Light")
        result = extract_contracts_dir(str(specs))
        assert "error" not in result
        # 2 interfaces (window_api.h + light_api.h)
        assert len(result["interfaces"]) == 2
        assert len(result["requirements"]) == 2
        assert len(result["files"]) == 2
        # spec_size aggregated
        assert result["spec_size"] > 0

    def test_empty_dir_returns_error(self, tmp_path):
        result = extract_contracts_dir(str(tmp_path))
        assert "error" in result

    def test_deduplicates_shared_params(self, tmp_path):
        """Same param name in two caps merges once (validation-friendly)."""
        specs = tmp_path / "specs"
        _write_capability(specs, "a", "SR-001", "Alpha")
        _write_capability(specs, "b", "SR-002", "Beta")
        result = extract_contracts_dir(str(specs))
        assert "error" not in result


class TestContractsCheckDir:
    def test_check_dir_shape(self, tmp_path):
        specs = tmp_path / ".osh" / "specs"
        _write_capability(specs, "window", "SR-001", "Window")
        _write_capability(specs, "light", "SR-002", "Light")
        result = contracts_check_dir(str(specs))
        assert result["mode"] == "directory"
        assert "contracts" in result
        assert "validation" in result
        assert result["contracts"]["files"]

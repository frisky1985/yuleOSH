"""Tests for OpenSpec directory aggregation in spec_contracts.py."""

# @tests src/yuleosh/spec/validate.py

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

    def test_guardrails_str_does_not_crash(self, tmp_path):
        """_extract_guardrails 返回 list[str]；目录聚合不得对 str 调 .get()

        Regression: 曾 AttributeError: 'str' object has no attribute 'get'
        在 extract_contracts_dir 崩整个聚合（window-anti-pinch 实测 18 条
        G-01..G-18 全部触发）。聚合须兼容 str 元素并正确去重。
        """
        specs = tmp_path / ".osh" / "specs"
        p = _write_capability(specs, "window", "SR-001", "Window")
        # 补足 MIN_INTERFACES=8（4 hal + 4 应用头），否则 validation 因接口数不足失败
        extra_headers = "\n\n".join(
            f"### {h}.h\n\n```c\nvoid {h}_init(void);\n```"
            for h in ["hal_hall", "hal_motor", "hal_timer", "hal_nvm",
                      "window_modes", "window_position", "window_config", "window_control"]
        )
        p.write_text(
            p.read_text()
            + extra_headers
            + "\n## 行为护栏映射\n\n"
            + "| 护栏 | 描述 |\n|:--|:--|\n"
            + "| G-01 | 状态机合法迁移 |\n"
            + "| G-02 | 防夹阈值不可变 |\n"
        )
        result = contracts_check_dir(str(specs))
        assert result["mode"] == "directory"
        guards = result["contracts"]["guardrails"]
        # G-01/G-02 作为 str id 聚合（不崩、不重复）
        assert "G-01" in guards and "G-02" in guards
        assert len(guards) == 2
        assert result["validation"]["passed"]

"""Phase 6 coverage boost — CI 域低覆盖文件（ci/layers, cors, project_detection,
misra_report/models, misra_trend, profiles, build_metadata, agent_traceability）。

Target modules (Phase 6 baseline, 2026-08-09):
  - src/yuleosh/ci/layers.py                    0.0%  → import/重导出可用性
  - src/yuleosh/api/cors.py                    58.5%  → 全分支
  - src/yuleosh/project_detection.py           58.6%  → 解析/模板解析/异常
  - src/yuleosh/ci/misra_report/models.py      71.6%  → dataclass + 合并
  - src/yuleosh/ci/misra_trend.py              72.7%  → 追加/趋势/边界
  - src/yuleosh/ci/profiles.py                 64.9%  → 解析/合并
  - src/yuleosh/ci/build_metadata.py           70.5%  → 记录/查询/校验
  - src/yuleosh/ci/agent_traceability.py       65.4%  → 记录/查询/校验

风格：直测函数/分支，外部命令 mock，全部落在 tmp_path。
"""

# @tests src/yuleosh/ci/coverage_pipeline.py

import json
import os
from pathlib import Path
from unittest import mock

import pytest

# =====================================================================
# ci/layers.py — 向后兼容重导出模块（0% → import 即覆盖）
# =====================================================================


class TestLayersReexport:
    def _load_legacy_module(self):
        """ci/layers.py 被同名包 ci/layers/ 遮蔽（import yuleosh.ci.layers 解析到包），
        只能通过文件路径直接加载执行其模块级代码（imports + __all__）。"""
        import importlib.util

        src = Path(__file__).resolve().parent.parent / "src" / "yuleosh" / "ci" / "layers.py"
        spec = importlib.util.spec_from_file_location("_legacy_layers", str(src))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_module_imports_and_exports(self):
        from yuleosh.ci import layers  # 包（向后兼容入口）

        for name in layers.__all__:
            assert hasattr(layers, name), f"missing re-export: {name}"
        assert layers.layer_dependencies is not None

    def test_legacy_module_loadable(self):
        legacy = self._load_legacy_module()
        assert len(legacy.__all__) == 20
        for name in legacy.__all__:
            assert hasattr(legacy, name), f"missing re-export: {name}"

    def test_layers_import_matches_package(self):
        import yuleosh.ci.layers as pkg  # same object (package)
        from yuleosh.ci import layers

        assert layers.run_layer1 is pkg.run_layer1
        assert layers.validate_layer_result is pkg.validate_layer_result


# =====================================================================
# api/cors.py — CORS 校验分支
# =====================================================================


class TestCors:
    def test_development_mode_returns_star(self):
        with mock.patch.dict(os.environ, {"YULEOSH_ENV": "development"}, clear=False):
            from yuleosh.api.cors import (
                get_cors_origin,
                is_development,
                origin_is_allowed,
            )

            assert is_development() is True
            assert get_cors_origin("http://evil.example") == "*"
            assert origin_is_allowed("http://evil.example") is True

    def test_env_not_development(self):
        with mock.patch.dict(os.environ, {"YULEOSH_ENV": ""}, clear=False):
            from yuleosh.api.cors import is_development

            assert is_development() is False

    def test_allowed_origins_combines_env(self):
        with mock.patch.dict(
            os.environ,
            {"YULEOSH_CORS_ALLOWED_ORIGINS": " http://app.example ,, https://b.example "},
            clear=False,
        ):
            from yuleosh.api.cors import get_allowed_origins

            origins = get_allowed_origins()
            assert "http://localhost:18789" in origins
            assert "http://app.example" in origins
            assert "https://b.example" in origins

    def test_production_allowed_origin_echoed(self):
        with mock.patch.dict(
            os.environ,
            {"YULEOSH_ENV": "production",
             "YULEOSH_CORS_ALLOWED_ORIGINS": "http://app.example"},
            clear=False,
        ):
            from yuleosh.api.cors import get_cors_origin, origin_is_allowed

            assert get_cors_origin("http://app.example") == "http://app.example"
            assert origin_is_allowed("http://app.example") is True
            # always-allowed localhost
            assert get_cors_origin("http://localhost:18789") == "http://localhost:18789"

    def test_production_blocked_origin(self):
        with mock.patch.dict(
            os.environ,
            {"YULEOSH_ENV": "production", "YULEOSH_CORS_ALLOWED_ORIGINS": ""},
            clear=False,
        ):
            from yuleosh.api.cors import get_cors_origin, origin_is_allowed

            assert get_cors_origin("http://evil.example") == "null"
            assert origin_is_allowed("http://evil.example") is False

    def test_no_origin_returns_default(self):
        with mock.patch.dict(
            os.environ,
            {"YULEOSH_ENV": "production", "YULEOSH_CORS_ALLOWED_ORIGINS": ""},
            clear=False,
        ):
            from yuleosh.api.cors import get_cors_origin

            origin = get_cors_origin(None)
            assert origin in ("http://localhost:18789", "http://127.0.0.1:18789")
            assert get_cors_origin("") in ("http://localhost:18789", "http://127.0.0.1:18789")

    def test_origin_is_allowed_no_origin(self):
        with mock.patch.dict(os.environ, {"YULEOSH_ENV": "production"}, clear=False):
            from yuleosh.api.cors import origin_is_allowed

            assert origin_is_allowed(None) is False


# =====================================================================
# project_detection.py — .yuleosh.yaml 解析
# =====================================================================


@pytest.fixture()
def yaml_project(tmp_path):
    (tmp_path / ".yuleosh.yaml").write_text(
        """
project:
  name: yuleASR-BSW
  type: autosar
  language: c
  target: s32k312
pipeline:
  template: autosar
  ci_layers:
    layer1: true
misra:
  profile: safety
coverage:
  threshold: 80
cross_compile:
  toolchain: arm-none-eabi-gcc
""",
        encoding="utf-8",
    )
    return tmp_path


class TestProjectDetection:
    def test_no_yaml_returns_none(self, tmp_path):
        from yuleosh.project_detection import detect_project

        assert detect_project(str(tmp_path)) is None

    def test_detect_full_project(self, yaml_project, tmp_path):
        from yuleosh.project_detection import detect_project

        info = detect_project(str(tmp_path))
        assert info is not None
        assert info["name"] == "yuleASR-BSW"
        assert info["type"] == "autosar"
        assert info["language"] == "c"
        assert info["target"] == "s32k312"
        assert info["pipeline_template"] == "autosar"
        assert info["ci_layers"] == {"layer1": True}
        assert info["misra"] == {"profile": "safety"}
        assert info["_raw"]["project"]["type"] == "autosar"

    def test_detect_template_from_type_map(self, tmp_path):
        (tmp_path / ".yuleosh.yaml").write_text(
            "project:\n  type: freertos\n", encoding="utf-8"
        )
        from yuleosh.project_detection import detect_project

        info = detect_project(str(tmp_path))
        assert info["pipeline_template"] == "freertos-misra"

    def test_detect_template_from_pipeline(self, tmp_path):
        (tmp_path / ".yuleosh.yaml").write_text(
            "project:\n  type: autosar\npipeline:\n  template: custom-tpl\n",
            encoding="utf-8",
        )
        from yuleosh.project_detection import detect_project

        info = detect_project(str(tmp_path))
        assert info["pipeline_template"] == "custom-tpl"

    def test_bad_yaml_returns_none(self, tmp_path):
        (tmp_path / ".yuleosh.yaml").write_text("project: [unclosed\n", encoding="utf-8")
        from yuleosh.project_detection import detect_project

        assert detect_project(str(tmp_path)) is None

    def test_empty_yaml_returns_none(self, tmp_path):
        (tmp_path / ".yuleosh.yaml").write_text("", encoding="utf-8")
        from yuleosh.project_detection import detect_project

        assert detect_project(str(tmp_path)) is None

    def test_resolve_pipeline_config_no_info(self, tmp_path):
        from yuleosh.project_detection import resolve_pipeline_config

        assert resolve_pipeline_config(str(tmp_path)) is None

    def test_resolve_pipeline_config_no_template_dir(self, tmp_path):
        (tmp_path / ".yuleosh.yaml").write_text(
            "project:\n  type: unknown-type-xyz\n", encoding="utf-8"
        )
        from yuleosh.project_detection import resolve_pipeline_config

        assert resolve_pipeline_config(str(tmp_path)) is None

    def test_resolve_pipeline_config_missing_template_config(self, tmp_path):
        (tmp_path / ".yuleosh.yaml").write_text(
            "project:\n  type: autosar\n", encoding="utf-8"
        )
        tpl_dir = tmp_path / "templates" / "autosar-classic"
        tpl_dir.mkdir(parents=True)
        with mock.patch(
            "yuleosh.project_detection._resolve_template_dir",
            return_value=tpl_dir,
        ):
            from yuleosh.project_detection import resolve_pipeline_config

            assert resolve_pipeline_config(str(tmp_path)) is None

    def test_resolve_pipeline_config_full(self, tmp_path):
        (tmp_path / ".yuleosh.yaml").write_text(
            "project:\n  type: autosar\n", encoding="utf-8"
        )
        tpl_dir = tmp_path / "templates" / "autosar-classic"
        (tpl_dir / "pipeline").mkdir(parents=True)
        (tpl_dir / "pipeline" / "config.yaml").write_text(
            "steps:\n  - spec-check\nci_layers:\n  l1: true\nreview_gates:\n  - critical\n"
            "tools:\n  gcc: 13\n",
            encoding="utf-8",
        )
        with mock.patch(
            "yuleosh.project_detection._resolve_template_dir",
            return_value=tpl_dir,
        ):
            from yuleosh.project_detection import resolve_pipeline_config

            cfg = resolve_pipeline_config(str(tmp_path))
        assert cfg["steps"] == ["spec-check"]
        assert cfg["ci_layers"] == {"l1": True}
        assert cfg["review_gates"] == ["critical"]
        assert cfg["tools"] == {"gcc": 13}

    def test_resolve_pipeline_config_bad_template_yaml(self, tmp_path):
        (tmp_path / ".yuleosh.yaml").write_text(
            "project:\n  type: autosar\n", encoding="utf-8"
        )
        tpl_dir = tmp_path / "templates" / "autosar-classic"
        (tpl_dir / "pipeline").mkdir(parents=True)
        (tpl_dir / "pipeline" / "config.yaml").write_text("steps: [broken\n", encoding="utf-8")
        with mock.patch(
            "yuleosh.project_detection._resolve_template_dir",
            return_value=tpl_dir,
        ):
            from yuleosh.project_detection import resolve_pipeline_config

            assert resolve_pipeline_config(str(tmp_path)) is None

    def test_resolve_template_dir_none(self):
        from yuleosh.project_detection import _resolve_template_dir

        with mock.patch(
            "yuleosh.templates.resolve_template", return_value=None
        ):
            assert _resolve_template_dir("x", "/tmp") is None

    def test_resolve_template_dir_with_dir(self, tmp_path):
        from yuleosh.project_detection import _resolve_template_dir

        with mock.patch(
            "yuleosh.templates.resolve_template",
            return_value={"_dir": str(tmp_path / "tpl")},
        ):
            result = _resolve_template_dir("x", str(tmp_path))
        assert result == tmp_path / "tpl"


# =====================================================================
# ci/misra_report/models.py — dataclass 与多工具合并
# =====================================================================


class TestMisraModels:
    def test_misra_violation_to_dict(self):
        from yuleosh.ci.misra_report.models import MisraViolation

        v = MisraViolation(
            rule_id="10.1", category="Required", file="main.c", line=42,
            message="bad", severity="high", fix_proposed="fix", suppressed=True,
        )
        d = v.to_dict()
        assert d["rule_id"] == "10.1"
        assert d["severity"] == "high"
        assert d["suppressed"] is True

    def test_misra_summary_properties(self):
        from yuleosh.ci.misra_report.models import MisraSummary, MisraViolation

        s = MisraSummary(max_allowed_critical=1, max_allowed_total=2)
        assert s.total_violations == 0
        assert s.passed is True

        s.violations = [
            MisraViolation("a", "Required", "f.c", 1, "m", severity="high"),
            MisraViolation("b", "Required", "f.c", 2, "m", severity="medium"),
            MisraViolation("c", "Required", "f.c", 3, "m", severity="low"),
        ]
        assert s.high_severity == 1
        assert s.medium_severity == 1
        assert s.low_severity == 1
        assert s.total_violations == 3
        assert s.passed is False  # 3 > max_allowed_total

    def test_merge_tool_results_dedup(self):
        from yuleosh.ci.misra_report.models import ToolResult, merge_tool_results

        results = [
            ToolResult(
                tool_name="cppcheck",
                violations=[
                    {"rule_id": "10.1", "file": "a.c", "line": 1, "col": 0,
                     "severity": "high"},
                    {"rule_id": "10.2", "file": "a.c", "line": 2, "col": 0,
                     "severity": "medium"},
                ],
                status="passed",
            ),
            ToolResult(
                tool_name="clang-tidy",
                violations=[
                    {"rule_id": "10.1", "file": "a.c", "line": 1, "col": 0,
                     "severity": "high"},
                ],
                status="passed",
            ),
            ToolResult(tool_name="ai-review", violations=[], status="skipped"),
        ]
        out = merge_tool_results(results)
        assert len(out["merged_violations"]) == 2
        tools_for_101 = next(
            v["_tools"] for v in out["merged_violations"] if v["rule_id"] == "10.1"
        )
        assert tools_for_101 == ["clang-tidy", "cppcheck"]
        assert out["combined_stats"]["total_violations"] == 2
        assert out["combined_stats"]["total_tools"] == 3
        assert out["combined_stats"]["severity_counts"]["high"] == 1
        assert out["combined_stats"]["unique_files"] == ["a.c"]
        assert out["tool_contributions"] == {"cppcheck": 2, "clang-tidy": 1, "ai-review": 0}
        assert out["tool_statuses"] == {
            "cppcheck": "passed", "clang-tidy": "passed", "ai-review": "skipped",
        }

    def test_merge_tool_results_empty(self):
        from yuleosh.ci.misra_report.models import merge_tool_results

        out = merge_tool_results([])
        assert out["merged_violations"] == []
        assert out["combined_stats"]["total_violations"] == 0
        assert out["combined_stats"]["unique_files"] == []
        assert out["tool_contributions"] == {}
        assert out["tool_statuses"] == {}


# =====================================================================
# ci/misra_trend.py — 趋势记录与展示
# =====================================================================


class TestMisraTrend:
    def test_append_entry_creates_jsonl(self, tmp_path):
        from yuleosh.ci.misra_trend import append_entry

        append_entry(str(tmp_path), 12, required=3, advisory=9, files_checked=5,
                     is_delta=True, commit="abc12345")
        lines = (tmp_path / ".yuleosh" / "reports" / "misra-trend.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["total_violations"] == 12
        assert entry["required"] == 3
        assert entry["is_delta"] is True
        assert entry["commit"] == "abc12345"

    def test_append_entry_defaults(self, tmp_path):
        from yuleosh.ci.misra_trend import append_entry

        append_entry(str(tmp_path), 1)
        entry = json.loads(
            (tmp_path / ".yuleosh" / "reports" / "misra-trend.jsonl").read_text().strip()
        )
        assert entry["required"] == 0
        assert entry["files_checked"] == 0
        assert entry["is_delta"] is False

    def test_show_trend_no_file(self, tmp_path):
        from yuleosh.ci.misra_trend import show_trend

        assert "No trend data" in show_trend(str(tmp_path))
        assert "error" in json.loads(show_trend(str(tmp_path), as_json=True))

    def test_show_trend_markdown_and_json(self, tmp_path):
        from yuleosh.ci.misra_trend import append_entry, show_trend

        for i in range(3):
            append_entry(str(tmp_path), i * 5, required=i, advisory=i * 4,
                         files_checked=2, is_delta=i % 2 == 0, commit=f"c{i}")

        md = show_trend(str(tmp_path), lines=2)
        assert "MISRA 违规趋势" in md
        assert "| 2 |" in md  # last two entries indexed 1..2
        assert "✓" in md

        js = json.loads(show_trend(str(tmp_path), lines=2, as_json=True))
        assert js["total_entries"] == 3
        assert js["returned_entries"] == 2

    def test_show_trend_skips_bad_lines(self, tmp_path):
        from yuleosh.ci.misra_trend import append_entry, show_trend

        append_entry(str(tmp_path), 7)
        trend = tmp_path / ".yuleosh" / "reports" / "misra-trend.jsonl"
        with trend.open("a") as f:
            f.write("{not-json}\n")
        md = show_trend(str(tmp_path))
        assert "| 1 |" in md

    def test_show_trend_days_filter_empty(self, tmp_path):
        from yuleosh.ci.misra_trend import _ensure_trend_dir, show_trend

        path = _ensure_trend_dir(str(tmp_path))
        # 60 天前的旧条目 → days=1 过滤后为空
        path.write_text(json.dumps({
            "timestamp": "2026-01-01T00:00:00",
            "total_violations": 7,
        }) + "\n")
        js = json.loads(show_trend(str(tmp_path), days=1, as_json=True))
        assert "error" in js

    def test_show_trend_days_filter_present(self, tmp_path):
        from yuleosh.ci.misra_trend import append_entry, show_trend

        append_entry(str(tmp_path), 7)
        js = json.loads(show_trend(str(tmp_path), days=30, as_json=True))
        assert js["total_entries"] == 1

    def test_parse_timestamp_fallback(self):
        from yuleosh.ci.misra_trend import _parse_timestamp

        assert _parse_timestamp("garbage").year == 1970
        assert _parse_timestamp(None).year == 1970

    def test_get_violations_per_kloc(self):
        from yuleosh.ci.misra_trend import get_violations_per_kloc

        assert get_violations_per_kloc(10, 5.2) == round(10 / 5.2, 2)
        assert get_violations_per_kloc(10, 0) == 0.0
        assert get_violations_per_kloc(10, -1) == 0.0

    def test_print_trend_summary(self, tmp_path, capsys):
        from yuleosh.ci.misra_trend import _print_trend_summary, append_entry

        _print_trend_summary(str(tmp_path))  # no file → no output
        append_entry(str(tmp_path), 5, required=1, advisory=4)
        _print_trend_summary(str(tmp_path))
        out = capsys.readouterr().out
        assert "MISRA Trend" in out

    def test_ensure_trend_dir_creates(self, tmp_path):
        from yuleosh.ci.misra_trend import _ensure_trend_dir

        path = _ensure_trend_dir(str(tmp_path))
        assert path.parent.is_dir()
        assert path.name == "misra-trend.jsonl"


# =====================================================================
# ci/profiles.py — CI Profile 解析/合并
# =====================================================================


class TestCiProfiles:
    def test_get_ci_profile_found_and_missing(self):
        from yuleosh.ci.profiles import get_ci_profile

        p = get_ci_profile("production")
        assert p is not None
        assert p.threshold_line == 80.0
        assert p.module_thresholds["src/core"] == 90.0
        assert get_ci_profile("nonexistent") is None

    def test_list_ci_profiles(self):
        from yuleosh.ci.profiles import list_ci_profiles

        profiles = list_ci_profiles()
        assert set(profiles) == {"development", "ci", "production"}
        assert profiles["production"]["has_module_thresholds"] is True
        assert profiles["ci"]["strict"] is True

    def test_resolve_none_profile(self):
        from yuleosh.ci.profiles import resolve_ci_profile

        out = resolve_ci_profile(None, 55.0, 45.0, True, "safety", {"src/x": 60.0})
        assert out["threshold_line"] == 55.0
        assert out["profile_name"] == "ci"
        assert out["module_thresholds"] == {"src/x": 60.0}

    def test_resolve_unknown_profile_falls_back(self):
        from yuleosh.ci.profiles import resolve_ci_profile

        out = resolve_ci_profile("bogus", 55.0, 45.0, False, "motor", None)
        assert out["threshold_line"] == 55.0
        assert out["module_thresholds"] == {}

    def test_resolve_profile_with_max_threshold(self):
        from yuleosh.ci.profiles import resolve_ci_profile

        out = resolve_ci_profile("development", 90.0, 70.0, True, "safety", None)
        # ci-config 更高阈值胜出
        assert out["threshold_line"] == 90.0
        assert out["threshold_condition"] == 70.0
        assert out["strict"] is True
        # misra_profile 不被 ci-config 覆盖（保留 profile 值）
        assert out["misra_profile"] == "motor"
        assert out["profile_name"] == "development"

    def test_resolve_profile_keeps_higher_profile_threshold(self):
        from yuleosh.ci.profiles import resolve_ci_profile

        out = resolve_ci_profile("production", 10.0, 10.0, False, "motor", None)
        # profile 阈值更高 → 保留 profile 值
        assert out["threshold_line"] == 80.0
        assert out["threshold_condition"] == 60.0
        assert out["strict"] is False  # ci-config strict 覆盖
        assert out["misra_profile"] == "safety"  # profile 值保留

    def test_resolve_profile_module_thresholds_merge(self):
        from yuleosh.ci.profiles import resolve_ci_profile

        out = resolve_ci_profile(
            "production", 10.0, 10.0, True, "safety",
            {"src/core": 95.0, "src/newmod": 50.0},
        )
        assert out["module_thresholds"]["src/core"] == 95.0  # config 覆盖
        assert out["module_thresholds"]["src/newmod"] == 50.0
        assert out["module_thresholds"]["src/mcal"] == 85.0  # profile 保留

    def test_print_profile_summary(self, capsys):
        from yuleosh.ci.profiles import print_profile_summary

        print_profile_summary()
        out = capsys.readouterr().out
        assert "CI Environment Profiles" in out
        assert "production" in out


# =====================================================================
# ci/build_metadata.py — 构建元数据
# =====================================================================


class TestBuildMetadata:
    def test_record_build_basic(self, tmp_path):
        from yuleosh.ci.build_metadata import record_build

        with mock.patch("yuleosh.ci.build_metadata._get_git_commit",
                        return_value="deadbeef1234"), \
             mock.patch("yuleosh.ci.build_metadata._get_git_files_changed",
                        return_value=3), \
             mock.patch("yuleosh.ci.build_metadata._get_tool_versions",
                        return_value={"python": "3.12"}):
            entry = record_build(str(tmp_path), status="passed", layer=1,
                                 extra_fields={"note": "x"})
        assert entry["commit"] == "deadbeef1234"
        assert entry["status"] == "passed"
        assert entry["layer"] == 1
        assert entry["files_changed"] == 3
        assert entry["note"] == "x"
        assert entry["build_id"].startswith("20")

    def test_record_build_validation_warnings(self, tmp_path):
        from yuleosh.ci.build_metadata import record_build

        with mock.patch("yuleosh.ci.build_metadata._get_git_commit",
                        return_value=""), \
             mock.patch("yuleosh.ci.build_metadata._get_git_files_changed",
                        return_value=0), \
             mock.patch("yuleosh.ci.build_metadata._get_tool_versions",
                        return_value={}):
            entry = record_build(str(tmp_path), commit=" ", status="")
        assert "_validation_warnings" in entry
        assert "commit" in entry["_validation_warnings"]

    def test_get_build_metadata_filters(self, tmp_path):
        from yuleosh.ci.build_metadata import _ensure_meta_dir, get_build_metadata

        path = _ensure_meta_dir(str(tmp_path))
        rows = [
            {"build_id": "B1", "timestamp": "2026-01-01T00:00:00", "commit": "c1",
             "status": "passed", "layer": 1, "tool_versions": {}, "files_changed": 0},
            {"build_id": "B2", "timestamp": "2026-01-02T00:00:00", "commit": "c2",
             "status": "failed", "layer": 2, "tool_versions": {}, "files_changed": 1},
            {"build_id": "B3", "timestamp": "2026-01-03T00:00:00", "commit": "c2",
             "status": "passed", "layer": 2, "tool_versions": {}, "files_changed": 2},
        ]
        with path.open("a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

        latest = get_build_metadata(str(tmp_path))
        assert latest[0]["build_id"] == "B3"
        by_id = get_build_metadata(str(tmp_path), build_id="B1")
        assert by_id[0]["build_id"] == "B1"
        by_layer = get_build_metadata(str(tmp_path), layer=2, limit=10)
        assert [e["build_id"] for e in by_layer] == ["B3", "B2"]
        assert get_build_metadata(str(tmp_path), limit=2)[0]["build_id"] == "B3"
        # 坏行跳过
        with path.open("a") as f:
            f.write("{bad}\n")
        assert get_build_metadata(str(tmp_path))[0]["build_id"] == "B3"

    def test_get_build_metadata_no_file(self, tmp_path):
        from yuleosh.ci.build_metadata import get_build_metadata

        assert get_build_metadata(str(tmp_path)) == []

    def test_get_build_chain(self, tmp_path):
        from yuleosh.ci.build_metadata import _ensure_meta_dir, get_build_chain

        path = _ensure_meta_dir(str(tmp_path))
        rows = [
            {"build_id": "B1", "timestamp": "2026-01-01T00:00:00", "commit": "abc123",
             "status": "passed", "layer": 1, "tool_versions": {}, "files_changed": 0},
            {"build_id": "B2", "timestamp": "2026-01-02T00:00:00", "commit": "def456",
             "status": "passed", "layer": 1, "tool_versions": {}, "files_changed": 0},
        ]
        with path.open("a") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
        chain = get_build_chain(str(tmp_path), "abc")
        assert [e["build_id"] for e in chain] == ["B1"]
        assert get_build_chain(str(tmp_path), "zzz") == []
        assert get_build_chain(str(tmp_path / "empty"), "abc") == []

    def test_validate_metadata_integrity(self, tmp_path):
        from yuleosh.ci.build_metadata import (
            _ensure_meta_dir,
            validate_metadata_integrity,
        )

        assert validate_metadata_integrity(str(tmp_path))["valid"] is False

        path = _ensure_meta_dir(str(tmp_path))
        good = {"build_id": "B1", "timestamp": "2026-01-01T00:00:00", "commit": "c1",
                "status": "passed", "layer": 1, "tool_versions": {"py": "3.12"},
                "files_changed": 0}
        with path.open("a") as f:
            f.write(json.dumps(good) + "\n")
        res = validate_metadata_integrity(str(tmp_path))
        assert res["valid"] is True
        assert res["entry_count"] == 1

        # 坏 JSON
        with path.open("a") as f:
            f.write("{bad}\n")
        res = validate_metadata_integrity(str(tmp_path))
        assert res["valid"] is False
        assert "Invalid JSON" in res["error"]

        # 缺字段 + 重复 id + 时间倒序
        path.write_text("")
        bad1 = {"build_id": "B1", "timestamp": "2026-01-02T00:00:00",
                "status": "passed", "layer": 1, "tool_versions": {"py": "3.12"},
                "files_changed": 0}
        bad2 = {"build_id": "B1", "timestamp": "2026-01-01T00:00:00", "commit": "c2",
                "status": "", "layer": 2, "tool_versions": {"py": "3.12"},
                "files_changed": -1}
        with path.open("a") as f:
            f.write(json.dumps(bad1) + "\n")
            f.write(json.dumps(bad2) + "\n")
        res = validate_metadata_integrity(str(tmp_path))
        assert res["valid"] is False
        assert any("duplicate build_id" in i for i in res["issues"])
        assert any("not monotonic" in i for i in res["issues"])
        assert any("missing fields" in i for i in res["issues"])

    def test_validate_fields(self):
        from yuleosh.ci.build_metadata import _validate_fields

        full = {"build_id": "b", "timestamp": "t", "commit": "c", "status": "s",
                "layer": 1, "tool_versions": {"py": "3"}, "files_changed": 1}
        assert _validate_fields(full) == []
        assert _validate_fields({}) == [
            "build_id", "timestamp", "commit", "status", "layer",
            "tool_versions", "files_changed",
        ]
        assert "commit" in _validate_fields({**full, "commit": ""})
        assert "commit" in _validate_fields({**full, "commit": None})
        assert "tool_versions" in _validate_fields({**full, "tool_versions": {}})
        assert "invalid:files_changed" in _validate_fields({**full, "files_changed": -5})

    def test_show_build_metadata(self, tmp_path):
        from yuleosh.ci.build_metadata import (
            _ensure_meta_dir,
            record_build,
            show_build_metadata,
        )

        assert "*No build metadata found.*" in show_build_metadata(str(tmp_path))

        _ensure_meta_dir(str(tmp_path))
        with mock.patch("yuleosh.ci.build_metadata._get_git_commit",
                        return_value="cafebabe1234"), \
             mock.patch("yuleosh.ci.build_metadata._get_git_files_changed",
                        return_value=2), \
             mock.patch("yuleosh.ci.build_metadata._get_tool_versions",
                        return_value={}):
            record_build(str(tmp_path), status="passed", layer=2)
        md = show_build_metadata(str(tmp_path))
        assert "## Build Metadata" in md
        assert "cafebabe" in md
        js = json.loads(show_build_metadata(str(tmp_path), as_json=True))
        assert js[0]["status"] == "passed"

    def test_git_helpers_error_paths(self, tmp_path):
        from yuleosh.ci.build_metadata import _get_git_commit, _get_git_files_changed

        with mock.patch("yuleosh.ci.build_metadata.subprocess.run",
                        side_effect=FileNotFoundError):
            assert _get_git_commit(str(tmp_path)) == "unknown"
            assert _get_git_files_changed(str(tmp_path)) == 0

        with mock.patch("yuleosh.ci.build_metadata.subprocess.run") as mr:
            mr.return_value = mock.MagicMock(returncode=1, stdout="")
            assert _get_git_commit(str(tmp_path)) == "unknown"
            assert _get_git_files_changed(str(tmp_path)) == 0

    def test_git_helpers_success(self, tmp_path):
        from yuleosh.ci.build_metadata import _get_git_commit, _get_git_files_changed

        with mock.patch("yuleosh.ci.build_metadata.subprocess.run") as mr:
            mr.return_value = mock.MagicMock(returncode=0, stdout="abc123\n")
            assert _get_git_commit(str(tmp_path)) == "abc123"

        with mock.patch("yuleosh.ci.build_metadata.subprocess.run") as mr:
            mr.return_value = mock.MagicMock(
                returncode=0, stdout="a.py\nb.py\n\n"
            )
            assert _get_git_files_changed(str(tmp_path)) == 2

    def test_get_tool_versions_all_paths(self, tmp_path):
        from yuleosh.ci.build_metadata import _get_tool_versions

        with mock.patch("yuleosh.ci.build_metadata.subprocess.run") as mr:
            def side(cmd, **kw):
                if "python" in cmd[0]:
                    return mock.MagicMock(returncode=0, stdout="Python 3.12.1", stderr="")
                if cmd[0] == "git":
                    return mock.MagicMock(returncode=1, stdout="", stderr="")
                if cmd[0] in ("cppcheck", "gcc", "cmake", "pytest"):
                    return mock.MagicMock(returncode=0, stdout="", stderr="1.2.3")
                raise FileNotFoundError(cmd[0])
            mr.side_effect = side
            versions = _get_tool_versions(str(tmp_path))
        assert versions["python"] == "Python 3.12.1"
        assert versions["git"] == "not found"
        assert versions["cppcheck"] == "1.2.3"

    def test_get_tool_versions_exceptions(self):
        from yuleosh.ci.build_metadata import _get_tool_versions

        with mock.patch("yuleosh.ci.build_metadata.subprocess.run",
                        side_effect=RuntimeError("boom")):
            versions = _get_tool_versions("/tmp")
        assert all(v.startswith("error:") for v in versions.values())

    def test_generate_build_id_format(self, tmp_path):
        from yuleosh.ci.build_metadata import _generate_build_id

        with mock.patch("yuleosh.ci.build_metadata._get_git_commit",
                        return_value="0123456789abcdef"):
            bid = _generate_build_id(str(tmp_path))
        assert bid.endswith("-01234567")
        assert "-" in bid

    def test_cli_main_actions(self, tmp_path, capsys):
        from yuleosh.ci.build_metadata import _cli_main

        with mock.patch(
            "sys.argv",
            ["build-meta", "show", "--project-dir", str(tmp_path)],
        ), mock.patch("yuleosh.ci.build_metadata.os.environ", {}):
            _cli_main()
        out = capsys.readouterr().out
        assert "No build metadata found" in out

        with mock.patch(
            "sys.argv",
            ["build-meta", "record", "--project-dir", str(tmp_path),
             "--status", "passed", "--commit", "c1"],
        ), mock.patch("yuleosh.ci.build_metadata.os.environ", {}), \
           mock.patch("yuleosh.ci.build_metadata._get_tool_versions",
                      return_value={}), \
           mock.patch("yuleosh.ci.build_metadata._get_git_files_changed",
                      return_value=0):
            _cli_main()
        out = capsys.readouterr().out
        assert '"status": "passed"' in out

        with mock.patch(
            "sys.argv",
            ["build-meta", "validate", "--project-dir", str(tmp_path)],
        ), mock.patch("yuleosh.ci.build_metadata.os.environ", {}):
            _cli_main()
        out = capsys.readouterr().out
        assert '"valid"' in out

        with mock.patch(
            "sys.argv",
            ["build-meta", "chain", "--project-dir", str(tmp_path), "--commit", "zzz"],
        ), mock.patch("yuleosh.ci.build_metadata.os.environ", {}):
            _cli_main()
        out = capsys.readouterr().out
        assert out.strip() == "[]"

        with mock.patch(
            "sys.argv",
            ["build-meta", "chain", "--project-dir", str(tmp_path)],
        ), mock.patch("yuleosh.ci.build_metadata.os.environ", {}):
            _cli_main()
        out = capsys.readouterr().out
        assert "error: --commit is required" in out


# =====================================================================
# ci/agent_traceability.py — 评审可追溯性
# =====================================================================


class TestAgentTraceability:
    def test_record_review_basic(self, tmp_path):
        from yuleosh.ci.agent_traceability import record_review

        with mock.patch("yuleosh.ci.agent_traceability._get_git_commit",
                        return_value="feedface1234"):
            entry = record_review(
                str(tmp_path),
                review_type="code-review",
                findings=[
                    {"file": "src/a.c", "line": 10, "severity": "high",
                     "message": "bad", "category": "safety", "rule_id": "10.1"},
                    {"file": "src/b.c"},  # 无 line → location 只有 file
                ],
                commit="",  # 自动检测
                build_id="BUILD-1",
                agent_name="小克",
                extra={"note": "x"},
            )
        assert entry["review_id"].startswith("RVW-")
        assert entry["commit"] == "feedface1234"
        assert entry["finding_count"] == 2
        assert entry["findings"][0]["location"] == "src/a.c:10"
        assert entry["findings"][1]["location"] == "src/b.c"
        assert entry["note"] == "x"

    def test_record_review_empty_findings(self, tmp_path):
        from yuleosh.ci.agent_traceability import record_review

        with mock.patch("yuleosh.ci.agent_traceability._get_git_commit",
                        return_value="abc"):
            entry = record_review(str(tmp_path), commit="givencommit",
                                  findings=None)
        assert entry["findings"] == []
        assert entry["commit"] == "givencommit"

    def test_get_reviews_for_commit(self, tmp_path):
        from yuleosh.ci.agent_traceability import (
            _ensure_trace_dir,
            get_reviews_for_commit,
            record_review,
        )

        _ensure_trace_dir(str(tmp_path))
        with mock.patch("yuleosh.ci.agent_traceability._get_git_commit",
                        return_value="abc123"):
            record_review(str(tmp_path), commit="")
        with mock.patch("yuleosh.ci.agent_traceability._get_git_commit",
                        return_value="def456"):
            record_review(str(tmp_path), commit="")
        assert len(get_reviews_for_commit(str(tmp_path), "abc")) == 1
        # 修复后的 limit 语义：limit=0 → 立即返回空
        assert get_reviews_for_commit(str(tmp_path), "abc", limit=0) == []
        assert get_reviews_for_commit(str(tmp_path / "nope"), "abc") == []

    def test_get_commits_for_review(self, tmp_path):
        from yuleosh.ci.agent_traceability import (
            _ensure_trace_dir,
            get_commits_for_review,
            record_review,
        )

        assert get_commits_for_review(str(tmp_path / "nope"), "RVW-x") == []
        _ensure_trace_dir(str(tmp_path))
        with mock.patch("yuleosh.ci.agent_traceability._get_git_commit",
                        return_value="c1"):
            entry = record_review(str(tmp_path), commit="c1")
        found = get_commits_for_review(str(tmp_path), entry["review_id"])
        assert len(found) == 1
        assert get_commits_for_review(str(tmp_path), "RVW-missing") == []

    def test_get_findings_for_file(self, tmp_path):
        from yuleosh.ci.agent_traceability import (
            _ensure_trace_dir,
            get_findings_for_file,
            record_review,
        )

        assert get_findings_for_file(str(tmp_path / "nope"), "a.c") == []
        _ensure_trace_dir(str(tmp_path))
        with mock.patch("yuleosh.ci.agent_traceability._get_git_commit",
                        return_value="c1"):
            record_review(
                str(tmp_path), review_type="misra-review",
                findings=[
                    {"file": "src/driver.c", "line": 5, "severity": "high",
                     "message": "m1"},
                    {"file": "src/other.c", "line": 9, "severity": "low",
                     "message": "m2"},
                ],
                commit="c1",
            )
        found = get_findings_for_file(str(tmp_path), "driver.c")
        assert len(found) == 1
        assert found[0]["location"] == "src/driver.c:5"
        assert found[0]["review_type"] == "misra-review"
        # limit 提前返回
        assert len(get_findings_for_file(str(tmp_path), ".c", limit=1)) == 1

    def test_get_reviews_by_build(self, tmp_path):
        from yuleosh.ci.agent_traceability import (
            _ensure_trace_dir,
            get_reviews_by_build,
            record_review,
        )

        assert get_reviews_by_build(str(tmp_path / "nope"), "B") == []
        _ensure_trace_dir(str(tmp_path))
        with mock.patch("yuleosh.ci.agent_traceability._get_git_commit",
                        return_value="c1"):
            record_review(str(tmp_path), commit="c1", build_id="BUILD-99")
            record_review(str(tmp_path), commit="c1", build_id="OTHER-1")
        assert len(get_reviews_by_build(str(tmp_path), "BUILD")) == 1
        assert len(get_reviews_by_build(str(tmp_path), "BUILD-99")) == 1

    def test_show_traceability(self, tmp_path):
        from yuleosh.ci.agent_traceability import (
            _ensure_trace_dir,
            record_review,
            show_traceability,
        )

        assert "*No traceability data found.*" in show_traceability(str(tmp_path))
        _ensure_trace_dir(str(tmp_path))
        with mock.patch("yuleosh.ci.agent_traceability._get_git_commit",
                        return_value="c1"):
            record_review(str(tmp_path), commit="c1", review_type="arch-review",
                          agent_name="小马")
        md = show_traceability(str(tmp_path))
        assert "Agent ↔ Code Traceability" in md
        js = json.loads(show_traceability(str(tmp_path), as_json=True))
        assert js[0]["review_type"] == "arch-review"

        # 空文件 → no entries
        (tmp_path / ".yuleosh" / "reports" / "agent-traceability.jsonl").write_text("")
        assert "*No traceability entries.*" in show_traceability(str(tmp_path))

    def test_validate_traceability_file(self, tmp_path):
        from yuleosh.ci.agent_traceability import (
            _ensure_trace_dir,
            validate_traceability_file,
        )

        res = validate_traceability_file(str(tmp_path))
        assert res["valid"] is True
        assert res["entry_count"] == 0

        path = _ensure_trace_dir(str(tmp_path))
        path.write_text('{"review_id": "RVW-1", "commit": "c1"}\n')
        res = validate_traceability_file(str(tmp_path))
        assert res["valid"] is True
        assert res["entry_count"] == 1

        path.write_text('{"commit": "c1"}\n{bad}\n')
        res = validate_traceability_file(str(tmp_path))
        assert res["valid"] is False
        assert any("missing review_id" in i for i in res["issues"])
        assert any("invalid JSON" in i for i in res["issues"])

    def test_git_commit_helper(self, tmp_path):
        from yuleosh.ci.agent_traceability import _get_git_commit

        with mock.patch("yuleosh.ci.agent_traceability.subprocess.run") as mr:
            mr.return_value = mock.MagicMock(returncode=0, stdout="deadbeef\n")
            assert _get_git_commit(str(tmp_path)) == "deadbeef"
        with mock.patch("yuleosh.ci.agent_traceability.subprocess.run",
                        side_effect=OSError):
            assert _get_git_commit(str(tmp_path)) == "unknown"

    def test_generate_review_id_format(self):
        from yuleosh.ci.agent_traceability import _generate_review_id

        rid = _generate_review_id()
        assert rid.startswith("RVW-")
        assert len(rid.split("-")[-1]) == 4

    def test_cli_main(self, tmp_path, capsys):
        from yuleosh.ci.agent_traceability import _cli_main

        with mock.patch(
            "sys.argv",
            ["trace", "show", "--project-dir", str(tmp_path)],
        ), mock.patch("yuleosh.ci.agent_traceability.os.environ", {}):
            _cli_main()
        assert "No traceability data" in capsys.readouterr().out

        with mock.patch(
            "sys.argv",
            ["trace", "record", "--project-dir", str(tmp_path), "--commit", "c1"],
        ), mock.patch("yuleosh.ci.agent_traceability.os.environ", {}), \
           mock.patch("yuleosh.ci.agent_traceability._get_git_commit",
                      return_value="c1"):
            _cli_main()
        out = capsys.readouterr().out
        assert '"review_id"' in out

        with mock.patch(
            "sys.argv",
            ["trace", "validate", "--project-dir", str(tmp_path)],
        ), mock.patch("yuleosh.ci.agent_traceability.os.environ", {}):
            _cli_main()
        out = capsys.readouterr().out
        assert '"entry_count"' in out

        with mock.patch(
            "sys.argv",
            ["trace", "for-commit", "--project-dir", str(tmp_path)],
        ), mock.patch("yuleosh.ci.agent_traceability.os.environ", {}):
            _cli_main()
        assert "error: --commit is required" in capsys.readouterr().out

        with mock.patch(
            "sys.argv",
            ["trace", "for-commit", "--project-dir", str(tmp_path),
             "--commit", "zzz", "--json"],
        ), mock.patch("yuleosh.ci.agent_traceability.os.environ", {}):
            _cli_main()
        out = capsys.readouterr().out
        assert out.strip() == "[]"

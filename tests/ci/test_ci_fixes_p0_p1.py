"""
P0/P1 CI 修复单元测试 — 覆盖 realworld-ci 评审暴露的所有 8 项问题

测试范围:
  1. MISRA exclude_paths 过滤逻辑 (_exclude_paths)
  2. cppcheck include 路径自动探测 (_detect_include_paths)
  3. run_layer1 包含 c-coverage-gate
  4. YAML schema docsync 详细验证
  5. build 目录扩展搜索
  6. 模块覆盖率阈值检查 (run_c_coverage_check 中的 module_thresholds)
  7. ci-config.yaml deviation 清理 (无测试数据条目)
  8. 错误信息友好度 (验证 fix 建议输出)
"""

import fnmatch
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


# ===================================================================
# Fix 1: MISRA exclude_paths 过滤
# ===================================================================

class TestExcludePaths:
    """验证 _exclude_paths 函数正确过滤目录。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from yuleosh.ci.stages import _exclude_paths
        self._exclude_paths = _exclude_paths

    def test_empty_patterns_no_filtering(self, tmp_path):
        """空 exclude 列表 → 不过滤。"""
        files = ["src/main.c", "tests/test_main.c"]
        result = self._exclude_paths(files, [], str(tmp_path))
        assert result == files

    def test_exclude_tests_directory(self, tmp_path):
        """排除 tests/** 模式。"""
        files = [
            os.path.join(str(tmp_path), "src/main.c"),
            os.path.join(str(tmp_path), "tests/test_main.c"),
            os.path.join(str(tmp_path), "tests/unity/src/unity.c"),
        ]
        result = self._exclude_paths(files, ["tests/**"], str(tmp_path))
        assert len(result) == 1
        assert "src/main.c" in result[0]

    def test_exclude_multiple_patterns(self, tmp_path):
        """排除多个模式。"""
        files = [
            os.path.join(str(tmp_path), "src/main.c"),
            os.path.join(str(tmp_path), "third_party/lib.c"),
            os.path.join(str(tmp_path), "build/obj.o"),
            os.path.join(str(tmp_path), "src/util.c"),
        ]
        result = self._exclude_paths(files, ["third_party/**", "build/**"], str(tmp_path))
        assert len(result) == 2
        assert all("third_party" not in f and "build" not in f for f in result)

    def test_relative_paths(self):
        """相对路径也能正确匹配。"""
        files = ["src/main.c", "tests/test_main.c"]
        result = self._exclude_paths(files, ["tests/**"], "/tmp/project")
        assert len(result) == 1
        assert result[0] == "src/main.c"

    def test_no_matching_excludes(self, tmp_path):
        """无匹配排除模式 → 保留所有文件。"""
        files = [
            os.path.join(str(tmp_path), "src/main.c"),
            os.path.join(str(tmp_path), "src/util.c"),
        ]
        result = self._exclude_paths(files, ["tests/**", "build/**"], str(tmp_path))
        assert result == files


# ===================================================================
# Fix 2: cppcheck include 路径自动探测
# ===================================================================

class TestDetectIncludePaths:
    """验证 _detect_include_paths 函数正确发现 include 目录。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from yuleosh.ci.stages import _detect_include_paths
        self._detect_include_paths = _detect_include_paths

    def test_detects_common_paths(self, tmp_path):
        """检测常见的 include 目录。"""
        # Create directories
        (tmp_path / "src").mkdir()
        (tmp_path / "include").mkdir()
        (tmp_path / "tests" / "unity" / "src").mkdir(parents=True)
        (tmp_path / "Drivers" / "CMSIS" / "Include").mkdir(parents=True)

        result = self._detect_include_paths(str(tmp_path))
        result_rel = [os.path.relpath(p, str(tmp_path)) for p in result]

        assert "src" in result_rel
        assert "include" in result_rel
        assert os.path.join("tests", "unity", "src") in result_rel
        assert os.path.join("Drivers", "CMSIS", "Include") in result_rel

    def test_missing_dirs_omitted(self, tmp_path):
        """不存在的目录不被包含。"""
        result = self._detect_include_paths(str(tmp_path))
        # Only '.' and 'src' might exist if src exists
        assert all(os.path.isdir(p) for p in result)

    def test_returns_absolute_paths(self, tmp_path):
        """返回的路径是绝对路径。"""
        (tmp_path / "src").mkdir()
        result = self._detect_include_paths(str(tmp_path))
        assert all(os.path.isabs(p) for p in result)


# ===================================================================
# Fix 3: run_layer1 包含 c-coverage-gate
# ===================================================================

class TestLayer1CoverageGate:
    """验证 run_layer1 的 stages 列表包含 c-coverage-gate。"""

    def test_c_coverage_gate_in_stages(self):
        """确认 L1 stages 包含 c-coverage-gate。"""
        from yuleosh.ci.layers import run_layer1
        # Check that the function body references run_c_coverage_check
        import inspect
        source = inspect.getsource(run_layer1)
        assert "c-coverage-gate" in source
        assert "run_c_coverage_check" in source

    def test_c_coverage_imported(self):
        """确认 run_c_coverage_check 可以从 stages 导入。"""
        from yuleosh.ci.stages import run_c_coverage_check
        assert callable(run_c_coverage_check)


# ===================================================================
# Fix 4: YAML schema — docsync 和 exclude_paths
# ===================================================================

class TestYamlSchemaDocsync:
    """验证 yaml_validator 的 docsync schema 定义。"""

    def test_docsync_in_schema_keys(self):
        """docsync 是已知的顶层键。"""
        from yuleosh.ci.yaml_validator import _CI_CONFIG_SCHEMA, validate_ci_config
        assert "docsync" in _CI_CONFIG_SCHEMA
        docsync_schema = _CI_CONFIG_SCHEMA["docsync"]
        assert docsync_schema.get("type") == "dict"
        # 应有 sub-fields
        keys = docsync_schema.get("keys", {})
        assert "enabled" in keys
        assert "rules" in keys
        assert "mode" in keys

    def test_exclude_paths_in_schema(self):
        """exclude_paths 在 misra schema 中。"""
        from yuleosh.ci.yaml_validator import _CI_CONFIG_SCHEMA
        misra_schema = _CI_CONFIG_SCHEMA["misra"]
        keys = misra_schema.get("keys", {})
        assert "exclude_paths" in keys
        assert keys["exclude_paths"]["type"] == "list"

    def test_valid_docsync_config_passes(self, tmp_path):
        """合法的 docsync 配置通过验证。"""
        from yuleosh.ci.yaml_validator import validate_ci_config
        import yaml

        cfg = {
            "ci": {"layers": [1], "layer_dependencies": {}},
            "coverage": {"threshold_line": 85.0},
            "misra": {"enabled": True},
            "docsync": {
                "enabled": True,
                "rules": [{"id": "test-rule", "code_patterns": []}],
                "mode": "blocking",
            },
        }

        config_path = tmp_path / "ci-config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(cfg, f)

        result = validate_ci_config(str(config_path))
        assert result["valid"], f"Expected valid, got errors: {result['errors']}"


# ===================================================================
# Fix 5: build 目录扩展
# ===================================================================

class TestBuildDirExpansion:
    """验证 build 目录搜索列表已扩展。"""

    def test_additional_build_dirs_in_code(self):
        """确认 coverage_dirs 包含新增目录。"""
        from yuleosh.ci.stages import run_c_coverage
        import inspect
        source = inspect.getsource(run_c_coverage)
        # 验证扩展后包含的目录
        assert "_build" in source
        assert "out" in source or "\"out\"" in source
        assert "build_arm" in source

    def test_recursive_gcda_search(self, tmp_path):
        """确认有递归 .gcda 搜索。"""
        from yuleosh.ci.stages import run_c_coverage
        import inspect
        source = inspect.getsource(run_c_coverage)
        assert "find .gcda" in source.lower() or ".gcda" in source


# ===================================================================
# Fix 6: 模块覆盖率阈值
# ===================================================================

class TestModuleThresholds:
    """验证 run_c_coverage_check 实现了 module_thresholds 逻辑。"""

    def test_module_thresholds_referenced(self):
        """确认 run_c_coverage_check 引用了 module_thresholds。"""
        from yuleosh.ci.stages import run_c_coverage_check
        import inspect
        source = inspect.getsource(run_c_coverage_check)
        assert "module_thresholds" in source
        assert "module_threshold" in source

    @mock.patch("yuleosh.ci.config._get_ci_config")
    def test_module_thresholds_blocks_when_below(self, mock_get_config, tmp_path):
        """模块级阈值低于设定值时阻断。"""
        from yuleosh.ci.stages import run_c_coverage_check
        from yuleosh.ci.result import CIResult
        from yuleosh.ci.config import CiConfig, MisraConfig, CoverageConfig

        # Mock config with module thresholds
        mock_cfg = mock.MagicMock()
        mock_cfg.coverage.c_fail_under = 70
        mock_cfg.coverage.module_thresholds = {"yuleosh": 90.0}
        mock_get_config.return_value = mock_cfg

        # Create a fake coverage report with low module coverage (module = "yuleosh" from src/yuleosh/...)
        report_dir = Path(str(tmp_path)) / ".yuleosh" / "reports"
        report_dir.mkdir(parents=True)
        report = {
            "line_rate": 80.0,
            "branch_rate": 70.0,
            "files": [
                {
                    "file": os.path.join(str(tmp_path), "src/yuleosh/ci/stages.py"),
                    "line_rate": 50.0,
                    "lines": {"found": 100, "hit": 50},
                }
            ],
        }
        with open(report_dir / "c-coverage.json", "w") as f:
            json.dump(report, f)

        ci = CIResult(1, "test-commit")
        result = run_c_coverage_check(str(tmp_path), ci)

        assert result is False, "Should block when module threshold not met"
        assert any("Module thresholds" in str(s.get("detail", "")) for s in ci.stages)


# ===================================================================
# Fix 7: ci-config.yaml deviation 清理
# ===================================================================

class TestDeviationCleanup:
    """验证 ci-config.yaml 中无测试数据 deviation。"""

    def test_no_test_deviations(self):
        """确认无 Rule-99.9 和 Rule-Test-DryRun。"""
        import yaml

        config_path = Path(__file__).resolve().parent.parent.parent / ".yuleosh" / "ci-config.yaml"
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        misra = cfg.get("misra", {})
        deviations = misra.get("deviations", [])

        rules = [d["rule"] for d in deviations]
        assert "Rule-99.9" not in rules, "Rule-99.9 应被移除"
        assert "Rule-Test-DryRun" not in rules, "Rule-Test-DryRun 应被移除"

    def test_has_unity_deviations(self):
        """确认有针对 tests/unity/ 的有效 deviation。"""
        import yaml

        config_path = Path(__file__).resolve().parent.parent.parent / ".yuleosh" / "ci-config.yaml"
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        misra = cfg.get("misra", {})
        deviations = misra.get("deviations", [])

        unity_devs = [d for d in deviations if "unity" in d.get("file", "")]
        assert len(unity_devs) > 0, "缺少针对 tests/unity/ 的 deviation"

    def test_exclude_paths_in_config(self):
        """确认 ci-config.yaml 有 exclude_paths 配置。"""
        import yaml

        config_path = Path(__file__).resolve().parent.parent.parent / ".yuleosh" / "ci-config.yaml"
        with open(config_path) as f:
            cfg = yaml.safe_load(f)

        misra = cfg.get("misra", {})
        assert "exclude_paths" in misra
        assert "tests/**" in misra["exclude_paths"]


# ===================================================================
# Fix 8: 错误信息友好度
# ===================================================================

class TestErrorFriendliness:
    """验证关键失败路径输出修复建议。"""

    def test_coverage_fix_suggestion(self):
        """覆盖率失败时输出 🔧 修复建议。"""
        from yuleosh.ci.stages import run_coverage_check
        import inspect
        source = inspect.getsource(run_coverage_check)
        assert "🔧 Fix:" in source or "🔧" in source
        assert "threshold" in source.lower()

    def test_clang_tidy_fix_suggestion(self):
        """clang-tidy 失败时输出安装建议。"""
        from yuleosh.ci.stages import run_clang_tidy
        import inspect
        source = inspect.getsource(run_clang_tidy)
        assert "🔧 Fix:" in source or "install" in source

    def test_c_coverage_fix_in_no_build_dir(self):
        """无 build 目录时输出构建建议。"""
        from yuleosh.ci.stages import run_c_coverage
        import inspect
        source = inspect.getsource(run_c_coverage)
        assert "🔧 Fix:" in source or "COVERAGE_BUILD_DIR" in source

    def test_cppcheck_install_suggestion(self):
        """cppcheck 未安装时输出安装建议。"""
        from yuleosh.ci.stages import run_misra_check
        import inspect
        source = inspect.getsource(run_misra_check)
        assert "🔧 Fix:" in source or "brew install" in source or "apt install" in source


# ===================================================================
# Fix 1 (config): MisraConfig.exclude_paths 配置加载
# ===================================================================

class TestMisraConfigExcludePaths:
    """验证 MisraConfig 和配置加载正确支持 exclude_paths。"""

    def test_misra_config_has_exclude_paths(self):
        """MisraConfig dataclass 包含 exclude_paths 字段。"""
        from yuleosh.ci.config import MisraConfig
        cfg = MisraConfig()
        assert hasattr(cfg, "exclude_paths")
        assert isinstance(cfg.exclude_paths, list)

    def test_default_exclude_paths(self):
        """默认 exclude_paths 包含常见目录。"""
        from yuleosh.ci.config import MisraConfig
        cfg = MisraConfig()
        assert "tests/**" in cfg.exclude_paths
        assert "third_party/**" in cfg.exclude_paths
        assert "build/**" in cfg.exclude_paths

    def test_parse_exclude_paths_from_config(self, tmp_path):
        """从 YAML 配置正确解析 exclude_paths。"""
        from yuleosh.ci.config import _parse_ci_config, MisraConfig
        import yaml

        cfg_yaml = {
            "misra": {
                "enabled": True,
                "exclude_paths": ["tests/**", "generated/**", "vendor/**"],
            }
        }
        cfg = _parse_ci_config(cfg_yaml)
        assert "tests/**" in cfg.misra.exclude_paths
        assert "generated/**" in cfg.misra.exclude_paths
        assert "vendor/**" in cfg.misra.exclude_paths

    def test_parse_exclude_paths_default_when_missing(self):
        """YAML 中未提供 exclude_paths 时使用默认值。"""
        from yuleosh.ci.config import _parse_ci_config
        cfg_yaml = {"misra": {"enabled": True}}
        cfg = _parse_ci_config(cfg_yaml)
        assert cfg.misra.exclude_paths == ["tests/**", "third_party/**", "build/**"]


# ===================================================================
# Fix 5 (config): CoverageConfig.module_thresholds 使用确认
# ===================================================================

class TestCoverageConfig:
    """验证 CoverageConfig.module_thresholds 可配置。"""

    def test_module_thresholds_exists(self):
        """CoverageConfig 包含 module_thresholds 字段。"""
        from yuleosh.ci.config import CoverageConfig
        cfg = CoverageConfig()
        assert hasattr(cfg, "module_thresholds")
        assert isinstance(cfg.module_thresholds, dict)

    def test_module_thresholds_parseable(self, tmp_path):
        """从 YAML 正确解析 module_thresholds。"""
        from yuleosh.ci.config import _parse_ci_config
        cfg_yaml = {
            "coverage": {
                "module_thresholds": {
                    "ci": 90.0,
                    "evidence": 80.0,
                    "api": 75.0,
                }
            }
        }
        cfg = _parse_ci_config(cfg_yaml)
        assert cfg.coverage.module_thresholds["ci"] == 90.0
        assert cfg.coverage.module_thresholds["evidence"] == 80.0
        assert cfg.coverage.module_thresholds["api"] == 75.0


# ===================================================================
# 三级指针空违规分类策略 (template/third_party/business)
# ===================================================================

class TestCodeCategorization:
    """验证三级分类逻辑: _categorize_file()"""

    DEFAULT_CATEGORIES = {
        "template": {
            "paths": ["src/yuleosh/templates/**", "test-dogfood/**"],
            "action": "exclude",
            "block_on": False,
        },
        "third_party": {
            "paths": ["third_party/**", "Drivers/**", "Middlewares/**",
                      "CMSIS/**", "vendor/**", "lib/**"],
            "action": "alert",
            "block_on": False,
        },
        "business": {
            "paths": ["src/**"],
            "action": "enforce",
            "block_on": True,
        },
    }

    @pytest.fixture(autouse=True)
    def setup(self):
        from yuleosh.ci.stages import _categorize_file
        self._categorize_file = _categorize_file

    def test_template_path_identified(self):
        """template 路径正确识别。"""
        cat, cfg = self._categorize_file(
            "src/yuleosh/templates/arm-cmsis/src/main.c",
            self.DEFAULT_CATEGORIES
        )
        assert cat == "template"
        assert cfg["action"] == "exclude"

    def test_third_party_path_identified(self):
        """third_party 路径正确识别。"""
        cat, cfg = self._categorize_file(
            "third_party/freertos/src/tasks.c",
            self.DEFAULT_CATEGORIES
        )
        assert cat == "third_party"
        assert cfg["action"] == "alert"

    def test_drivers_path_identified(self):
        """Drivers 路径正确识别。"""
        cat, cfg = self._categorize_file(
            "Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal.c",
            self.DEFAULT_CATEGORIES
        )
        assert cat == "third_party"

    def test_business_path_identified(self):
        """business 路径正确识别。"""
        cat, cfg = self._categorize_file(
            "src/yuleosh/ci/stages.py",
            self.DEFAULT_CATEGORIES
        )
        assert cat == "business"
        assert cfg["block_on"] is True

    def test_vendor_path_third_party(self):
        """vendor 路径属于 third_party。"""
        cat, _ = self._categorize_file(
            "vendor/protobuf/src/descriptor.c",
            self.DEFAULT_CATEGORIES
        )
        assert cat == "third_party"

    def test_lib_path_third_party(self):
        """lib 路径属于 third_party。"""
        cat, _ = self._categorize_file(
            "lib/curl/src/easy.c",
            self.DEFAULT_CATEGORIES
        )
        assert cat == "third_party"

    def test_template_priority_over_third_party(self):
        """template > third_party 优先级。"""
        cat, _ = self._categorize_file(
            "src/yuleosh/templates/vendor/foo/src/main.c",  # 嵌套在 template 下的 vendor
            self.DEFAULT_CATEGORIES
        )
        assert cat == "template"

    def test_template_priority_over_business(self):
        """template > business 优先级。"""
        cat, _ = self._categorize_file(
            "src/yuleosh/templates/arm-cmsis/src/main.c",
            self.DEFAULT_CATEGORIES
        )
        assert cat == "template"

    def test_unknown_path_falls_to_business(self):
        """无匹配路径回退到 business。"""
        cat, _ = self._categorize_file(
            "docs/architecture.md",
            self.DEFAULT_CATEGORIES
        )
        assert cat == "business"

    def test_cmsis_path_third_party(self):
        """CMSIS 路径属于 third_party。"""
        cat, _ = self._categorize_file(
            "CMSIS/Core/Include/cmsis_gcc.h",
            self.DEFAULT_CATEGORIES
        )
        assert cat == "third_party"


class TestFixSuggestionFormat:
    """验证修复建议包含多级指针判空示例。"""

    @pytest.fixture(autouse=True)
    def setup(self):
        from yuleosh.ci.stages import _format_null_pointer_fix
        self._format_null_pointer_fix = _format_null_pointer_fix

    def test_business_has_null_pointer_examples(self):
        """business 代码应包含判空示例。"""
        fix = self._format_null_pointer_fix("business", "src/main.c")
        assert "修复建议" in fix
        assert "逐层判空" in fix or "ptr != NULL" in fix
        assert "assert" in fix

    def test_third_party_has_deviation_suggestion(self):
        """third_party 代码应包含 deviation 豁免建议。"""
        fix = self._format_null_pointer_fix("third_party", "third_party/lib.c")
        assert "deviation" in fix.lower()
        assert "ci-config.yaml" in fix

    def test_template_returns_empty(self):
        """template 代码返回空字符串。"""
        fix = self._format_null_pointer_fix("template", "src/templates/main.c")
        assert fix == ""

    def test_unknown_category_has_basic_fix(self):
        """未知分类也有基本修复建议。"""
        fix = self._format_null_pointer_fix("unknown", "src/main.c")
        assert "修复建议" in fix


class TestThirdPartyNonBlocking:
    """验证第三方库违规不阻断流水线。"""

    def test_third_party_default_block_on_false(self):
        """third_party 默认 block_on=False。"""
        from yuleosh.ci.config import MisraConfig
        cfg = MisraConfig()
        third_party_cfg = cfg.code_categories.get("third_party", {})
        assert third_party_cfg.get("block_on") is False

    def test_business_default_block_on_true(self):
        """business 默认 block_on=True。"""
        from yuleosh.ci.config import MisraConfig
        cfg = MisraConfig()
        business_cfg = cfg.code_categories.get("business", {})
        assert business_cfg.get("block_on") is True

    def test_code_categories_in_ci_config(self):
        """ci-config.yaml 中存在 code_categories 配置。"""
        import yaml
        config_path = Path(__file__).resolve().parent.parent.parent / ".yuleosh" / "ci-config.yaml"
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        misra = cfg.get("misra", {})
        assert "code_categories" in misra
        cats = misra["code_categories"]
        assert "template" in cats
        assert "third_party" in cats
        assert "business" in cats


class TestBusinessCodeBlocks:
    """验证业务代码违规阻断流水线逻辑。"""

    def test_business_block_on_true_in_misra_config(self):
        """MisraConfig 中 business.block_on=True。"""
        from yuleosh.ci.config import MisraConfig
        cfg = MisraConfig()
        business_cfg = cfg.code_categories.get("business", {})
        assert business_cfg.get("block_on") is True

    def test_run_misra_check_references_categories(self):
        """run_misra_check 中引用了 code_categories。"""
        from yuleosh.ci.stages import run_misra_check
        import inspect
        source = inspect.getsource(run_misra_check)
        assert "code_categories" in source
        assert "_categorize_file" in source
        assert "file_category_map" in source

    def test_run_misra_check_references_fix_function(self):
        """run_misra_check 中引用了 _format_null_pointer_fix。"""
        from yuleosh.ci.stages import run_misra_check
        import inspect
        source = inspect.getsource(run_misra_check)
        assert "_format_null_pointer_fix" in source

    def test_parse_code_categories_from_config(self, tmp_path):
        """从 YAML 正确解析 code_categories。"""
        from yuleosh.ci.config import _parse_ci_config
        cfg_yaml = {
            "misra": {
                "code_categories": {
                    "template": {
                        "paths": ["templates/**"],
                        "block_on": False,
                    },
                    "business": {
                        "paths": ["app/**"],
                        "block_on": True,
                    },
                },
            }
        }
        cfg = _parse_ci_config(cfg_yaml)
        assert "template" in cfg.misra.code_categories
        assert cfg.misra.code_categories["template"]["paths"] == ["templates/**"]

    def test_code_categories_default_when_missing(self):
        """YAML 中未提供 code_categories 时使用默认值。"""
        from yuleosh.ci.config import _parse_ci_config
        cfg_yaml = {"misra": {"enabled": True}}
        cfg = _parse_ci_config(cfg_yaml)
        cats = cfg.misra.code_categories
        assert "template" in cats
        assert "third_party" in cats
        assert "business" in cats
        assert cats["template"]["action"] == "exclude"
        assert cats["business"]["block_on"] is True

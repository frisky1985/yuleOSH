"""AUD-ASPICE-001 NC-11 回归：平台模式由元数据驱动。

撤销 ``project_meta`` 接线（prompt 不再注入平台硬规则、engine 不再做平台
布局校验）后，本文件的用例会失败。
"""

# @tests src/yuleosh/project_meta.py, src/yuleosh/codegen/prompts.py, src/yuleosh/codegen/engine.py

from yuleosh.codegen.engine import CodegenEngine
from yuleosh.codegen.prompts import build_codegen_prompt
from yuleosh.project_meta import (
    PLATFORM_AUTOSAR_CP,
    PLATFORM_AUTO,
    PLATFORM_BARE_METAL,
    PLATFORM_HOST_SIM,
    ProjectMeta,
    normalize_platform,
    validate_platform_layout,
)


class TestPlatformResolution:
    def test_aliases_are_normalised(self):
        assert normalize_platform("bare-metal") == PLATFORM_BARE_METAL
        assert normalize_platform("mcu") == PLATFORM_BARE_METAL
        assert normalize_platform("autosar") == PLATFORM_AUTOSAR_CP
        assert normalize_platform("host") == PLATFORM_HOST_SIM

    def test_unknown_defaults_to_auto(self):
        assert normalize_platform("") == PLATFORM_AUTO
        assert normalize_platform("POSIX-1990") == PLATFORM_AUTO

    def test_env_overrides_yaml(self, tmp_path, monkeypatch):
        (tmp_path / ".yuleosh.yaml").write_text("platform: AUTOSAR_CP\n")
        monkeypatch.setenv("OSH_PLATFORM", "BARE_METAL_MCU")
        assert ProjectMeta.load(tmp_path).platform == PLATFORM_BARE_METAL

    def test_yaml_is_read(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OSH_PLATFORM", raising=False)
        monkeypatch.delenv("OSH_ASIL_LEVEL", raising=False)
        (tmp_path / ".yuleosh.yaml").write_text(
            "project:\n  platform: BARE_METAL_MCU\n  asil_level: B\n"
        )
        meta = ProjectMeta.load(tmp_path)
        assert meta.platform == PLATFORM_BARE_METAL
        assert meta.asil_level == "ASIL-B"

    def test_missing_yaml_is_auto(self, tmp_path, monkeypatch):
        monkeypatch.delenv("OSH_PLATFORM", raising=False)
        monkeypatch.delenv("OSH_ASIL_LEVEL", raising=False)
        meta = ProjectMeta.load(tmp_path)
        assert meta.platform == PLATFORM_AUTO
        assert meta.asil_level == "QM"


class TestPlatformRules:
    def test_bare_metal_rules_forbid_autosar(self):
        rules = ProjectMeta(platform=PLATFORM_BARE_METAL).prompt_rules()
        assert "PLATFORM HARD RULE (BARE_METAL_MCU)" in rules
        assert "Rte_" in rules and "SchM" in rules and "arxml" in rules

    def test_auto_has_no_extra_rules(self):
        assert ProjectMeta(platform=PLATFORM_AUTO).prompt_rules() == ""

    def test_bare_metal_forbidden_patterns(self):
        errors = validate_platform_layout(
            ["src/rte/Rte_Led.c", "src/SchM.c", "demo.arxml"], PLATFORM_BARE_METAL,
        )
        assert len(errors) == 3

    def test_clean_bare_metal_layout_passes(self):
        assert validate_platform_layout(
            ["src/led_blink.c", "include/led_blink.h", "CMakeLists.txt"],
            PLATFORM_BARE_METAL,
        ) == []

    def test_host_sim_forbids_autosar_artifacts(self):
        assert validate_platform_layout(["src/rte/Rte.c"], PLATFORM_HOST_SIM)

    def test_autosar_platform_has_no_forbidden_list(self):
        assert validate_platform_layout(["src/rte/Rte_Led.c"], PLATFORM_AUTOSAR_CP) == []


class TestCodegenPromptPlatform:
    SPEC = "# LED\n\n### SR-001\n- The system SHALL blink every 1000 ms via HAL.\n"

    def test_bare_metal_prompt_drops_autosar_rules(self):
        system, _ = build_codegen_prompt(
            spec_content=self.SPEC, spec_name="spec.md",
            target_language="c", platform=PLATFORM_BARE_METAL,
        )
        assert "PLATFORM HARD RULE (BARE_METAL_MCU)" in system
        assert "AUTOSAR CLASSIC LAYERING HARD RULE" not in system

    def test_autosar_prompt_keeps_layering(self):
        system, _ = build_codegen_prompt(
            spec_content=self.SPEC, spec_name="spec.md",
            target_language="c", platform=PLATFORM_AUTOSAR_CP,
        )
        assert "PLATFORM HARD RULE (AUTOSAR_CP)" in system
        assert "AUTOSAR CLASSIC LAYERING HARD RULE" in system

    def test_auto_platform_keeps_legacy_behaviour(self):
        system, _ = build_codegen_prompt(
            spec_content=self.SPEC, spec_name="spec.md", target_language="c",
        )
        assert "PLATFORM HARD RULE" not in system
        assert "AUTOSAR CLASSIC LAYERING HARD RULE" in system


class TestCodegenEnginePlatformCheck:
    def test_bare_metal_engine_flags_rte(self, tmp_path):
        engine = CodegenEngine(platform=PLATFORM_BARE_METAL)
        rte = tmp_path / "src" / "rte"
        rte.mkdir(parents=True)
        (rte / "Rte_Led.c").write_text("int x;\n", encoding="utf-8")
        assert "PLATFORM VIOLATION" in engine._check_platform_layout(tmp_path)

    def test_clean_output_passes(self, tmp_path):
        engine = CodegenEngine(platform=PLATFORM_BARE_METAL)
        (tmp_path / "led.c").write_text("int led(void){return 0;}\n", encoding="utf-8")
        assert engine._check_platform_layout(tmp_path) == ""

    def test_auto_platform_never_flags(self, tmp_path):
        engine = CodegenEngine(platform=PLATFORM_AUTO)
        rte = tmp_path / "src" / "rte"
        rte.mkdir(parents=True)
        (rte / "Rte_Led.c").write_text("int x;\n", encoding="utf-8")
        assert engine._check_platform_layout(tmp_path) == ""

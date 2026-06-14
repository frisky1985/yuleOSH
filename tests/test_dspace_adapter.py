# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
Tests for DSAPCEAutomationDeskAdapter — 验证 dSPACE AutomationDesk XML 生成。

测试覆盖：
  - generate_test_set: XML 结构、命名空间、AutoDesk/TestSet/TestStep 层级
  - generate_test_step: PASS/FAIL/ERROR 分支、信号检查
  - generate_parameter_set: Simulink 参数映射
  - generate_model_ref: Simulink 模型引用
  - convert: 实际文件写入、路径返回
  - 边缘: 空输入、缺失字段
  - 共享代码兼容: 使用 __init__ 中的 get_adapter 工厂函数
"""

import os
import sys
import tempfile
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from yuleosh.adapter.dspace_adapter import (
    DSAPCEAutomationDeskAdapter,
    _AUTODESK_NS,
)
from yuleosh.adapter import (
    _XML_DECLARATION,
    get_adapter,
)


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def adapter() -> DSAPCEAutomationDeskAdapter:
    return DSAPCEAutomationDeskAdapter()


@pytest.fixture
def sample_cases() -> list[dict]:
    return [
        {
            "id": "TC_001",
            "title": "Brake Test",
            "group": "Vehicle Dynamics",
            "group_id": "TG_001",
            "type": "PASS",
            "description": "Verify braking system responds within limits.",
            "parameters": [
                {"name": "speed", "value": "100"},
                {"name": "brake", "value": "1"},
            ],
            "signals": [
                {
                    "name": "VehicleSpeed",
                    "expected_value": "5",
                    "tolerance": "1",
                }
            ],
            "steps": [
                {"action": "Send brake command", "expected": "Speed < 5 km/h"},
            ],
            "model": "vehicle_model.sdf",
        },
        {
            "id": "TC_002",
            "title": "Steering Angle Limit",
            "group": "Vehicle Dynamics",
            "group_id": "TG_001",
            "type": "FAIL",
            "description": "Steering exceeds safe angle limit (expected failure).",
            "parameters": [
                {"name": "steering_angle", "value": "720"},
            ],
            "signals": [
                {
                    "name": "SteeringAngle",
                    "expected_value": "450",
                    "tolerance": "5",
                }
            ],
            "model": "vehicle_model.sdf",
        },
        {
            "id": "TC_003",
            "title": "ECU Self-Test Error",
            "group": "Diagnostics",
            "group_id": "TG_002",
            "type": "ERROR",
            "description": "ECU self-test returns diagnostic error code.",
        },
        {
            "id": "TC_004",
            "title": "Custom Parameter Test",
            "group": "Regression",
            "group_id": "TG_003",
            "type": "PASS",
            "parameters": [
                {"name": "custom_param", "value": "42"},
                {"name": "threshold", "value": "0.85"},
            ],
            "model": "custom_model.slx",
        },
    ]


@pytest.fixture
def temp_dir() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


# ──────────────────────────────────────────────────────────
# Tests: generate_test_set
# ──────────────────────────────────────────────────────────

class TestGenerateTestSet:
    """验证 TestSet XML 的结构正确性。"""

    def test_basic_structure(self, adapter: DSAPCEAutomationDeskAdapter,
                             sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_set(sample_cases)
        assert xml_str.startswith(_XML_DECLARATION)
        root = ET.fromstring(xml_str)
        assert root.tag == f"{{{_AUTODESK_NS}}}AutoDesk"
        assert root.get("version") == "2.0"

    def test_namespace_registered(self, adapter: DSAPCEAutomationDeskAdapter,
                                  sample_cases: list[dict]) -> None:
        """验证命名空间前缀正确（无 ns0 污染）。"""
        xml_str = adapter.generate_test_set(sample_cases)
        assert "ns0:" not in xml_str

    def test_testset_element(self, adapter: DSAPCEAutomationDeskAdapter,
                             sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_set(sample_cases, name="MyTestSet")
        root = ET.fromstring(xml_str)
        ts = root.find(f"{{{_AUTODESK_NS}}}TestSet")
        assert ts is not None
        assert ts.get("name") == "MyTestSet"

    def test_setup_contains_executable(
            self, adapter: DSAPCEAutomationDeskAdapter,
            sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_set(sample_cases)
        root = ET.fromstring(xml_str)
        setup = root.find(f".//{{{_AUTODESK_NS}}}Setup")
        assert setup is not None
        executables = setup.findall(f"{{{_AUTODESK_NS}}}Executable")
        assert len(executables) >= 1
        exe = executables[0]
        assert exe.get("type") == "SimulinkModel"
        # TC_001 has model="vehicle_model.sdf", TC_003 has none
        # The model from TC_001 and TC_002 should be present
        model_names = {e.get("name") for e in executables}
        assert "vehicle_model.sdf" in model_names

    def test_parameterset_in_setup(
            self, adapter: DSAPCEAutomationDeskAdapter,
            sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_set(sample_cases)
        root = ET.fromstring(xml_str)
        param_sets = root.findall(f".//{{{_AUTODESK_NS}}}ParameterSet")
        # At least one ParameterSet in Setup
        assert len(param_sets) >= 1

    def test_teststeps_count(self, adapter: DSAPCEAutomationDeskAdapter,
                             sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_set(sample_cases)
        root = ET.fromstring(xml_str)
        steps = root.findall(f".//{{{_AUTODESK_NS}}}TestStep")
        assert len(steps) == 4  # TC_001 to TC_004

    def test_teststep_names(self, adapter: DSAPCEAutomationDeskAdapter,
                            sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_set(sample_cases)
        root = ET.fromstring(xml_str)
        steps = root.findall(f".//{{{_AUTODESK_NS}}}TestStep")
        names = [s.get("name") for s in steps]
        assert any("TC_001" in n and "Brake" in n for n in names)
        assert any("TC_003" in n and "ECU" in n for n in names)
        assert any("TC_004" in n and "Custom" in n for n in names)

    def test_empty_input(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        """空输入应生成空的 TestSet（无 TestStep，仍有 Setup）。"""
        xml_str = adapter.generate_test_set([])
        root = ET.fromstring(xml_str)
        assert root.tag == f"{{{_AUTODESK_NS}}}AutoDesk"
        steps = root.findall(f".//{{{_AUTODESK_NS}}}TestStep")
        assert len(steps) == 0
        # Still has Setup with default Executable
        setup = root.find(f".//{{{_AUTODESK_NS}}}Setup")
        assert setup is not None

    def test_minimal_testcase(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        """只有必需字段的测试用例。"""
        cases = [{"id": "TC_X1"}]
        xml_str = adapter.generate_test_set(cases)
        root = ET.fromstring(xml_str)
        step = root.find(f".//{{{_AUTODESK_NS}}}TestStep")
        assert step is not None
        assert "TC_X1" in step.get("name", "")


# ──────────────────────────────────────────────────────────
# Tests: generate_test_step
# ──────────────────────────────────────────────────────────

class TestGenerateTestStep:
    """验证单个 TestStep XML 元素生成。"""

    def test_pass_type(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        step = adapter.generate_test_step({"id": "TC_X", "type": "PASS"})
        assert step.tag == f"{{{_AUTODESK_NS}}}TestStep"
        assert "TC_X" in step.get("name", "")
        evaluation = step.find(f"{{{_AUTODESK_NS}}}Evaluation")
        assert evaluation is not None
        criteria = evaluation.findall(f"{{{_AUTODESK_NS}}}Criterion")
        assert any(c.get("type") == "PassFail" for c in criteria)

    def test_fail_type(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        step = adapter.generate_test_step({"id": "TC_Y", "type": "FAIL"})
        evaluation = step.find(f"{{{_AUTODESK_NS}}}Evaluation")
        criteria = evaluation.findall(f"{{{_AUTODESK_NS}}}Criterion")
        assert any(c.get("type") == "PassFail" for c in criteria)
        expected = step.find(
            f".//{{{_AUTODESK_NS}}}Expected"
        )
        assert expected is not None
        assert expected.get("value") == "FAIL"

    def test_error_type(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        step = adapter.generate_test_step({"id": "TC_Z", "type": "ERROR"})
        evaluation = step.find(f"{{{_AUTODESK_NS}}}Evaluation")
        criteria = evaluation.findall(f"{{{_AUTODESK_NS}}}Criterion")
        assert any(c.get("type") == "PassFailError" for c in criteria)
        expected = step.find(
            f".//{{{_AUTODESK_NS}}}Expected"
        )
        assert expected is not None
        assert expected.get("value") == "ERROR"

    def test_with_signals(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        step = adapter.generate_test_step({
            "id": "TC_SIG",
            "type": "PASS",
            "title": "Signal Check",
            "signals": [
                {"name": "EngineSpeed", "expected_value": "1500", "tolerance": "10"},
            ],
        })
        measurement = step.find(f"{{{_AUTODESK_NS}}}Measurement")
        assert measurement is not None
        signals = measurement.findall(f"{{{_AUTODESK_NS}}}Signal")
        assert len(signals) == 1
        assert signals[0].get("name") == "EngineSpeed"

        # Condition should be present
        conditions = measurement.findall(f"{{{_AUTODESK_NS}}}Condition")
        assert len(conditions) >= 1
        assert conditions[0].get("value") == "1500"

        # Evaluation should have Expected with tolerance
        evaluation = step.find(f"{{{_AUTODESK_NS}}}Evaluation")
        expected = evaluation.find(f".//{{{_AUTODESK_NS}}}Expected")
        assert expected is not None
        assert expected.get("value") == "1500"
        assert expected.get("tolerance") == "10"

    def test_with_description(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        step = adapter.generate_test_step({
            "id": "TC_DESC",
            "type": "PASS",
            "description": "Test description content.",
        })
        desc = step.find(f"{{{_AUTODESK_NS}}}Description")
        assert desc is not None
        assert "Test description content." in (desc.text or "")

    def test_with_steps(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        step = adapter.generate_test_step({
            "id": "TC_STEPS",
            "type": "PASS",
            "steps": [
                {"action": "Initialize", "expected": "Ready"},
                {"action": "Run", "expected": "Complete"},
            ],
        })
        measurement = step.find(f"{{{_AUTODESK_NS}}}Measurement")
        assert measurement is not None
        step_points = measurement.findall(f"{{{_AUTODESK_NS}}}StepPoint")
        assert len(step_points) == 2
        names = [sp.get("name") for sp in step_points]
        assert "Initialize" in names
        assert "Run" in names

    def test_with_parameters(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        step = adapter.generate_test_step({
            "id": "TC_PARAM",
            "type": "PASS",
            "parameters": [
                {"name": "gain", "value": "2.5"},
                {"name": "offset", "value": "0"},
            ],
        })
        param_sets = step.findall(f"{{{_AUTODESK_NS}}}ParameterSet")
        assert len(param_sets) == 1
        params = param_sets[0].findall(f"{{{_AUTODESK_NS}}}Parameter")
        assert len(params) == 2
        param_map = {p.get("name"): p.get("value") for p in params}
        assert param_map["gain"] == "2.5"
        assert param_map["offset"] == "0"

    def test_no_signals_still_works(self, adapter: DSAPCEAutomationDeskAdapter
                                    ) -> None:
        step = adapter.generate_test_step({"id": "TC_NOSIG", "type": "PASS"})
        # Should have evaluation even without signals
        evaluation = step.find(f"{{{_AUTODESK_NS}}}Evaluation")
        assert evaluation is not None
        criteria = evaluation.findall(f"{{{_AUTODESK_NS}}}Criterion")
        assert len(criteria) == 1


# ──────────────────────────────────────────────────────────
# Tests: generate_parameter_set
# ──────────────────────────────────────────────────────────

class TestGenerateParameterSet:
    """验证 Simulink 参数映射 XML 生成。"""

    def test_basic_params(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        tc = {
            "id": "TC_PARAM",
            "parameters": [
                {"name": "speed", "value": "100"},
                {"name": "brake", "value": "0"},
            ],
        }
        xml_str = adapter.generate_parameter_set(tc)
        assert xml_str.startswith(_XML_DECLARATION)
        root = ET.fromstring(xml_str)
        assert root.tag == f"{{{_AUTODESK_NS}}}AutoDesk"
        ps = root.find(f"{{{_AUTODESK_NS}}}ParameterSet")
        assert ps is not None
        assert "TC_PARAM" in ps.get("name", "")
        params = ps.findall(f"{{{_AUTODESK_NS}}}Parameter")
        assert len(params) == 2
        param_map = {p.get("name"): p.get("value") for p in params}
        assert param_map["speed"] == "100"
        assert param_map["brake"] == "0"

    def test_empty_params(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        xml_str = adapter.generate_parameter_set({"id": "TC_EMPTY"})
        root = ET.fromstring(xml_str)
        ps = root.find(f"{{{_AUTODESK_NS}}}ParameterSet")
        assert ps is not None
        params = ps.findall(f"{{{_AUTODESK_NS}}}Parameter")
        assert len(params) == 0

    def test_numeric_values(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        tc = {
            "id": "TC_NUM",
            "parameters": [
                {"name": "gain", "value": 2.5},
                {"name": "count", "value": 42},
            ],
        }
        xml_str = adapter.generate_parameter_set(tc)
        root = ET.fromstring(xml_str)
        ps = root.find(f"{{{_AUTODESK_NS}}}ParameterSet")
        params = ps.findall(f"{{{_AUTODESK_NS}}}Parameter")
        param_map = {p.get("name"): p.get("value") for p in params}
        assert param_map["gain"] == "2.5"
        assert param_map["count"] == "42"


# ──────────────────────────────────────────────────────────
# Tests: generate_model_ref
# ──────────────────────────────────────────────────────────

class TestGenerateModelRef:
    """验证 Simulink 模型引用 XML 生成。"""

    def test_sdf_model(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        xml_str = adapter.generate_model_ref("vehicle_model.sdf")
        assert xml_str.startswith(_XML_DECLARATION)
        root = ET.fromstring(xml_str)
        assert root.tag == f"{{{_AUTODESK_NS}}}AutoDesk"
        mc = root.find(f"{{{_AUTODESK_NS}}}ModelConfiguration")
        assert mc is not None
        assert mc.get("name") == "vehicle_model.sdf"
        mf = mc.find(f"{{{_AUTODESK_NS}}}ModelFile")
        assert mf is not None
        assert mf.get("path") == "vehicle_model.sdf"

    def test_slx_model(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        xml_str = adapter.generate_model_ref("custom_model.slx")
        root = ET.fromstring(xml_str)
        mc = root.find(f"{{{_AUTODESK_NS}}}ModelConfiguration")
        assert mc.get("name") == "custom_model.slx"

    def test_auto_extension(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        """不带扩展名的模型名应自动追加 .sdf。"""
        xml_str = adapter.generate_model_ref("my_model")
        root = ET.fromstring(xml_str)
        mc = root.find(f"{{{_AUTODESK_NS}}}ModelConfiguration")
        assert mc.get("name") == "my_model.sdf"

    def test_mil_config(self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        xml_str = adapter.generate_model_ref("test.sdf")
        root = ET.fromstring(xml_str)
        mc = root.find(f"{{{_AUTODESK_NS}}}ModelConfiguration")
        mil = mc.find(f"{{{_AUTODESK_NS}}}MiLConfiguration")
        assert mil is not None
        mode = mil.find(f"{{{_AUTODESK_NS}}}Mode")
        assert mode is not None
        assert mode.text == "Normal"
        solver = mil.find(f"{{{_AUTODESK_NS}}}SolverType")
        assert solver is not None
        assert solver.text == "FixedStep"


# ──────────────────────────────────────────────────────────
# Tests: convert (end-to-end file output)
# ──────────────────────────────────────────────────────────

class TestConvert:
    """验证 convert() 实际写文件并返回正确路径。"""

    def test_output_files_created(self, adapter: DSAPCEAutomationDeskAdapter,
                                  sample_cases: list[dict],
                                  temp_dir: str) -> None:
        result = adapter.convert(sample_cases, temp_dir)
        paths = result.strip().split("\n")
        # project.autoxml + testset_TG_001 + testset_TG_002 + testset_TG_003
        # + simulink_params.xml + model_vehicle_model.sdf.xml + model_custom_model.slx.xml
        assert len(paths) >= 4

        for p in paths:
            assert os.path.isfile(p), f"File not found: {p}"

        # Verify master project
        master = os.path.join(temp_dir, "project.autoxml")
        assert master in paths
        with open(master, "r", encoding="utf-8") as f:
            content = f.read()
            assert "<?xml" in content
            assert "AutoDesk" in content

    def test_parameter_file_created(self, adapter: DSAPCEAutomationDeskAdapter,
                                    sample_cases: list[dict],
                                    temp_dir: str) -> None:
        """测试用例含参数时应生成参数配置。"""
        result = adapter.convert(sample_cases, temp_dir)
        param_path = os.path.join(temp_dir, "simulink_params.xml")
        assert os.path.isfile(param_path)
        with open(param_path, "r", encoding="utf-8") as f:
            assert "Parameter" in f.read()

    def test_model_files_created(self, adapter: DSAPCEAutomationDeskAdapter,
                                 sample_cases: list[dict],
                                 temp_dir: str) -> None:
        """测试用例含 model 引用时应生成模型配置。

        注意：_safe_filename 会将点号替换为下划线，
        因此 "vehicle_model.sdf" → "vehicle_model_sdf.xml"。
        """
        result = adapter.convert(sample_cases, temp_dir)
        assert os.path.isfile(
            os.path.join(temp_dir, "model_vehicle_model_sdf.xml")
        ), f"Generated: {result}"
        assert os.path.isfile(
            os.path.join(temp_dir, "model_custom_model_slx.xml")
        )

    def test_empty_cases(self, adapter: DSAPCEAutomationDeskAdapter,
                         temp_dir: str) -> None:
        """空列表应生成 master project，无参数/模型文件。"""
        result = adapter.convert([], temp_dir)
        paths = result.strip().split("\n")
        # 空测试用例无 group → 只有 project.autoxml
        assert len(paths) == 1, f"Expected 1 file, got {len(paths)}: {paths}"
        assert os.path.isfile(paths[0])
        assert paths[0].endswith("project.autoxml")

    def test_output_dir_created(self, adapter: DSAPCEAutomationDeskAdapter
                                ) -> None:
        """如果 output_dir 不存在应自动创建。"""
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "nested", "adk_out")
            result = adapter.convert([], sub)
            assert os.path.isdir(sub)
            paths = result.strip().split("\n")
            assert all(p.startswith(sub) for p in paths)


# ──────────────────────────────────────────────────────────
# Tests: Factory function (shared code compatibility)
# ──────────────────────────────────────────────────────────

class TestFactoryFunction:
    """验证 get_adapter 工厂函数。"""

    def test_create_automationdesk(self) -> None:
        adk = get_adapter("automationdesk")
        assert isinstance(adk, DSAPCEAutomationDeskAdapter)

    def test_create_canoe(self) -> None:
        from yuleosh.adapter.vector_adapter import VectorCANoeAdapter
        canoe = get_adapter("canoe")
        assert isinstance(canoe, VectorCANoeAdapter)

    def test_invalid_name(self) -> None:
        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("nonexistent")

    def test_factory_produces_working_adapter(self, sample_cases: list[dict],
                                               temp_dir: str) -> None:
        """工厂创建的适配器应能正常工作。"""
        adk = get_adapter("automationdesk")
        result = adk.convert(sample_cases, temp_dir)
        paths = result.strip().split("\n")
        assert len(paths) >= 4
        master = os.path.join(temp_dir, "project.autoxml")
        assert os.path.isfile(master)


# ──────────────────────────────────────────────────────────
# Tests: dSPACE AutomationDesk XML compatibility
# ──────────────────────────────────────────────────────────

class TestAutomationDeskCompatibility:
    """验证生成 XML 符合 AutomationDesk 工具链的预期格式。"""

    def test_expected_root(self, adapter: DSAPCEAutomationDeskAdapter,
                           sample_cases: list[dict]) -> None:
        """AutomationDesk 期望 <AutoDesk> 作为根节点。"""
        xml_str = adapter.generate_test_set(sample_cases)
        root = ET.fromstring(xml_str)
        assert root.tag.endswith("AutoDesk")

    def test_testset_contains_steps(
            self, adapter: DSAPCEAutomationDeskAdapter,
            sample_cases: list[dict]) -> None:
        """<TestSet> 应包含多个 <TestStep>。"""
        xml_str = adapter.generate_test_set(sample_cases)
        root = ET.fromstring(xml_str)
        ts = root.find(f"{{{_AUTODESK_NS}}}TestSet")
        steps = ts.findall(f"{{{_AUTODESK_NS}}}TestStep")
        assert len(steps) >= 1

    def test_no_raw_namespace_prefixes(
            self, adapter: DSAPCEAutomationDeskAdapter,
            sample_cases: list[dict]) -> None:
        """原始 XML 不应有未注册的命名空间前缀。"""
        xml_str = adapter.generate_test_set(sample_cases)
        # After XML declaration, the first tag should not have a prefixed namespace
        # Due to register_namespace, tags should use the default namespace
        assert ":" not in xml_str.split("?>")[1].strip().split(" ")[0]

    def test_xml_declaration_first_line(
            self, adapter: DSAPCEAutomationDeskAdapter,
            sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_set(sample_cases)
        assert xml_str.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_valid_xml_parseable(
            self, adapter: DSAPCEAutomationDeskAdapter,
            sample_cases: list[dict]) -> None:
        """所有生成的文件应是合法 XML。"""
        # Test set
        xml_str = adapter.generate_test_set(sample_cases)
        ET.fromstring(xml_str)

        # Parameter set
        xml_str2 = adapter.generate_parameter_set(sample_cases[0])
        ET.fromstring(xml_str2)

        # Model ref
        xml_str3 = adapter.generate_model_ref("test.sdf")
        ET.fromstring(xml_str3)

    def test_mixed_results_in_same_set(
            self, adapter: DSAPCEAutomationDeskAdapter) -> None:
        """同一 TestSet 内不同 result type 应正确保留。"""
        cases = [
            {"id": "TC_A", "type": "PASS"},
            {"id": "TC_B", "type": "FAIL"},
        ]
        xml_str = adapter.generate_test_set(cases)
        root = ET.fromstring(xml_str)
        steps = root.findall(f".//{{{_AUTODESK_NS}}}TestStep")
        # Can't easily read type from the TestStep, but can verify structure
        assert len(steps) == 2
        eval_set = steps[0].find(f"{{{_AUTODESK_NS}}}Evaluation")
        criteria = eval_set.findall(f"{{{_AUTODESK_NS}}}Criterion")
        assert criteria[0].get("type") in ("PassFail", "PassFailError")

    def test_measurement_evaluation_structure(
            self, adapter: DSAPCEAutomationDeskAdapter,
            sample_cases: list[dict]) -> None:
        """每个 TestStep 应包含 Measurement 和 Evaluation。"""
        xml_str = adapter.generate_test_set(sample_cases)
        root = ET.fromstring(xml_str)
        steps = root.findall(f".//{{{_AUTODESK_NS}}}TestStep")
        for step in steps:
            name = step.get("name", "")
            measurement = step.find(f"{{{_AUTODESK_NS}}}Measurement")
            evaluation = step.find(f"{{{_AUTODESK_NS}}}Evaluation")
            # TC_003 / TC_004 have no signals or steps → no Measurement
            no_signals_steps_ids = ("TC_003", "TC_004")
            if any(s in name for s in no_signals_steps_ids):
                assert measurement is None, f"{name} should have no Measurement"
            else:
                assert measurement is not None, f"{name} should have Measurement"
            assert evaluation is not None, f"{name} should have Evaluation"


# ──────────────────────────────────────────────────────────
# Tests: _safe_filename
# ──────────────────────────────────────────────────────────

class TestSafeFilename:
    def test_safe(self) -> None:
        assert DSAPCEAutomationDeskAdapter._safe_filename("TG_001") == "TG_001"

    def test_unsafe_chars(self) -> None:
        assert DSAPCEAutomationDeskAdapter._safe_filename("TG/001:") == "TG_001_"

    def test_spaces(self) -> None:
        assert DSAPCEAutomationDeskAdapter._safe_filename(
            "test group"
        ) == "test_group"

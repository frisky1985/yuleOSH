"""
Tests for VectorCANoeAdapter — 验证 CANoe XML Test Feature 生成。

测试覆盖：
  - generate_test_module: XML 结构、命名空间、标签层级
  - generate_capl: PASS/FAIL/ERROR 分支、信号检查
  - generate_dbc_map: 信号映射 XML
  - convert: 实际文件写入、路径返回
  - 边缘: 空输入、缺失字段
"""

import os
import sys
import tempfile
import xml.etree.ElementTree as ET

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from adapter.vector_adapter import (
    VectorCANoeAdapter,
    _CANOE_NS,
    _XML_DECLARATION,
)


# ──────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────

@pytest.fixture
def adapter() -> VectorCANoeAdapter:
    return VectorCANoeAdapter()


@pytest.fixture
def sample_cases() -> list[dict]:
    return [
        {
            "id": "TC_001",
            "title": "CAN Bus Communication",
            "group": "Smoke Tests",
            "group_id": "TG_001",
            "type": "PASS",
            "description": "Verify CAN bus sends and receives messages.",
            "signals": [
                {
                    "name": "EngineSpeed",
                    "dbc": "engine.dbc",
                    "expected_value": "1500",
                }
            ],
            "steps": [
                {"action": "Send CAN message 0x100", "expected": "ACK received"},
            ],
        },
        {
            "id": "TC_002",
            "title": "LIN Bus Timeout",
            "group": "Smoke Tests",
            "group_id": "TG_001",
            "type": "FAIL",
            "description": "LIN slave does not respond within timeout.",
            "signals": [
                {
                    "name": "LIN_Status",
                    "dbc": "lin.dbc",
                    "expected_value": "0x01",
                }
            ],
        },
        {
            "id": "TC_003",
            "title": "ECU Self-Test",
            "group": "Diagnostics",
            "group_id": "TG_002",
            "type": "ERROR",
            "description": "ECU self-test returns diagnostic error.",
        },
        {
            "id": "TC_004",
            "title": "Custom CAPL Test",
            "group": "Regression",
            "group_id": "TG_003",
            "type": "PASS",
            "capl": """
void TC_004() {
  TestStep("Custom", "Running custom CAPL logic");
  testStepPass();
}
""",
        },
    ]


@pytest.fixture
def temp_dir() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


# ──────────────────────────────────────────────────────────
# Tests: generate_test_module
# ──────────────────────────────────────────────────────────

class TestGenerateTestModule:
    """验证 Test Module XML 的结构正确性。"""

    def test_basic_structure(self, adapter: VectorCANoeAdapter,
                             sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_module(sample_cases)
        assert xml_str.startswith(_XML_DECLARATION)
        root = ET.fromstring(xml_str)
        assert root.tag == f"{{{_CANOE_NS}}}testmodule"

    def test_namespace_registered(self, adapter: VectorCANoeAdapter,
                                  sample_cases: list[dict]) -> None:
        """验证命名空间前缀正确（无 ns0 污染）。"""
        xml_str = adapter.generate_test_module(sample_cases)
        # No unregistered namespace prefix should appear
        assert "ns0:" not in xml_str

    def test_group_structure(self, adapter: VectorCANoeAdapter,
                             sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_module(sample_cases)
        root = ET.fromstring(xml_str)
        groups = root.findall(f"{{{_CANOE_NS}}}testgroup")
        assert len(groups) == 3  # TG_001, TG_002, TG_003

        tg1 = groups[0]
        assert tg1.get("ident") == "TG_001"
        assert tg1.get("title") == "Smoke Tests"

    def test_testcase_attributes(self, adapter: VectorCANoeAdapter,
                                 sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_module(sample_cases)
        root = ET.fromstring(xml_str)
        all_cases = root.findall(f".//{{{_CANOE_NS}}}testcase")
        ids = [tc.get("ident") for tc in all_cases]
        titles = [tc.get("title") for tc in all_cases]

        assert "TC_001" in ids
        assert "TC_002" in ids
        assert "TC_003" in ids
        assert "CAN Bus Communication" in titles
        assert "ECU Self-Test" in titles

    def test_testcase_types(self, adapter: VectorCANoeAdapter,
                            sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_module(sample_cases)
        root = ET.fromstring(xml_str)

        def find_type(tc_id: str) -> str | None:
            for tc in root.findall(f".//{{{_CANOE_NS}}}testcase"):
                if tc.get("ident") == tc_id:
                    return tc.get("type")
            return None

        assert find_type("TC_001") == "PASS"
        assert find_type("TC_002") == "FAIL"
        assert find_type("TC_003") == "ERROR"

    def test_description_embedded(self, adapter: VectorCANoeAdapter,
                                  sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_module(sample_cases)
        root = ET.fromstring(xml_str)
        desc = root.find(
            f".//{{{_CANOE_NS}}}testcase[@ident='TC_001']/"
            f"{{{_CANOE_NS}}}description"
        )
        assert desc is not None
        assert "CAN bus sends and receives" in (desc.text or "")

    def test_capl_embedded(self, adapter: VectorCANoeAdapter,
                           sample_cases: list[dict]) -> None:
        """验证自定义 CAPL 被嵌入 XML。"""
        xml_str = adapter.generate_test_module(sample_cases)
        root = ET.fromstring(xml_str)
        capl = root.find(
            f".//{{{_CANOE_NS}}}testcase[@ident='TC_004']/"
            f"{{{_CANOE_NS}}}capl"
        )
        assert capl is not None
        assert "TC_004()" in (capl.text or "")

    def test_steps_embedded(self, adapter: VectorCANoeAdapter,
                            sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_module(sample_cases)
        root = ET.fromstring(xml_str)
        steps_el = root.find(
            f".//{{{_CANOE_NS}}}testcase[@ident='TC_001']/"
            f"{{{_CANOE_NS}}}steps"
        )
        assert steps_el is not None
        steps = steps_el.findall(f"{{{_CANOE_NS}}}step")
        assert len(steps) == 1
        assert steps[0].get("index") == "1"

    def test_empty_input(self, adapter: VectorCANoeAdapter) -> None:
        """空输入应生成空 testmodule。"""
        xml_str = adapter.generate_test_module([])
        root = ET.fromstring(xml_str)
        assert root.tag == f"{{{_CANOE_NS}}}testmodule"
        groups = root.findall(f"{{{_CANOE_NS}}}testgroup")
        assert len(groups) == 0

    def test_minimal_testcase(self, adapter: VectorCANoeAdapter) -> None:
        """只有必需字段的测试用例。"""
        cases = [{"id": "TC_X1"}]
        xml_str = adapter.generate_test_module(cases)
        root = ET.fromstring(xml_str)
        tc = root.find(f".//{{{_CANOE_NS}}}testcase")
        assert tc is not None
        assert tc.get("ident") == "TC_X1"
        assert tc.get("title") == "Untitled"


# ──────────────────────────────────────────────────────────
# Tests: generate_capl
# ──────────────────────────────────────────────────────────

class TestGenerateCapl:
    """验证 CAPL 脚本生成。"""

    def test_pass_type(self, adapter: VectorCANoeAdapter) -> None:
        code = adapter.generate_capl({"id": "TC_X", "type": "PASS"})
        assert "testStepPass()" in code
        assert "TC_X()" in code

    def test_fail_type(self, adapter: VectorCANoeAdapter) -> None:
        code = adapter.generate_capl({"id": "TC_Y", "type": "FAIL"})
        assert "testStepFail()" in code
        assert "FAILED" in code

    def test_error_type(self, adapter: VectorCANoeAdapter) -> None:
        code = adapter.generate_capl({"id": "TC_Z", "type": "ERROR"})
        assert "testStepFail()" in code
        assert "ERROR" in code

    def test_custom_capl_returned_as_is(self, adapter: VectorCANoeAdapter
                                         ) -> None:
        custom = "void MyTest() { testStepPass(); }"
        code = adapter.generate_capl({
            "id": "TC_CUSTOM",
            "capl": custom,
        })
        assert code == custom

    def test_with_signals(self, adapter: VectorCANoeAdapter) -> None:
        code = adapter.generate_capl({
            "id": "TC_SIG",
            "type": "PASS",
            "signals": [
                {"name": "EngineSpeed", "expected_value": "1500"},
            ],
        })
        assert "${EngineSpeed}" in code
        assert "1500" in code
        assert "testStepPass()" in code

    def test_no_signals_still_works(self, adapter: VectorCANoeAdapter) -> None:
        code = adapter.generate_capl({"id": "TC_NOSIG", "type": "PASS"})
        assert "TC_NOSIG()" in code
        assert "testStepPass()" in code


# ──────────────────────────────────────────────────────────
# Tests: generate_dbc_map
# ──────────────────────────────────────────────────────────

class TestGenerateDbcMap:
    """验证 DBC 信号映射 XML 生成。"""

    def test_basic_map(self, adapter: VectorCANoeAdapter) -> None:
        signals = [
            {
                "name": "EngineSpeed",
                "message": "ECU_Data",
                "start_bit": 0,
                "length": 16,
                "factor": 1.0,
                "offset": 0,
                "min": 0,
                "max": 8000,
                "unit": "rpm",
            },
            {
                "name": "VehicleSpeed",
                "message": "ECU_Data",
                "start_bit": 16,
                "length": 16,
                "factor": 0.01,
                "offset": 0,
            },
        ]
        xml_str = adapter.generate_dbc_map(signals)
        assert xml_str.startswith(_XML_DECLARATION)
        root = ET.fromstring(xml_str)
        assert root.tag == f"{{{_CANOE_NS}}}dbc_map"
        sig_els = root.findall(f"{{{_CANOE_NS}}}signal")
        assert len(sig_els) == 2

        first = sig_els[0]
        assert first.get("name") == "EngineSpeed"
        assert first.get("message") == "ECU_Data"
        length = first.find(f"{{{_CANOE_NS}}}length")
        assert length is not None
        assert length.text == "16"

    def test_empty_signals(self, adapter: VectorCANoeAdapter) -> None:
        xml_str = adapter.generate_dbc_map([])
        root = ET.fromstring(xml_str)
        sig_els = root.findall(f"{{{_CANOE_NS}}}signal")
        assert len(sig_els) == 0

    def test_no_optional_fields(self, adapter: VectorCANoeAdapter) -> None:
        signals = [{"name": "SIG_A", "message": "MSG_1"}]
        xml_str = adapter.generate_dbc_map(signals)
        root = ET.fromstring(xml_str)
        sig = root.find(f"{{{_CANOE_NS}}}signal")
        assert sig is not None
        assert sig.get("name") == "SIG_A"
        # No optional child elements present
        assert len(list(sig)) == 0


# ──────────────────────────────────────────────────────────
# Tests: convert (end-to-end file output)
# ──────────────────────────────────────────────────────────

class TestConvert:
    """验证 convert() 实际写文件并返回正确路径。"""

    def test_output_files_created(self, adapter: VectorCANoeAdapter,
                                  sample_cases: list[dict],
                                  temp_dir: str) -> None:
        result = adapter.convert(sample_cases, temp_dir)
        paths = result.strip().split("\n")
        assert len(paths) >= 2  # test_module.can + simulation_setup.xml

        for p in paths:
            assert os.path.isfile(p)

        # Verify contents
        with open(paths[0], "r", encoding="utf-8") as f:
            content = f.read()
            assert "<?xml" in content
            assert "testmodule" in content

    def test_capl_files_extracted(self, adapter: VectorCANoeAdapter,
                                  sample_cases: list[dict],
                                  temp_dir: str) -> None:
        """自定义 CAPL 应生成独立 .can 文件。"""
        result = adapter.convert(sample_cases, temp_dir)
        # TC_004 has custom CAPL → should produce TC_004.can
        capl_path = os.path.join(temp_dir, "TC_004.can")
        assert os.path.isfile(capl_path)
        with open(capl_path, "r", encoding="utf-8") as f:
            assert "TC_004()" in f.read()

    def test_empty_cases(self, adapter: VectorCANoeAdapter,
                         temp_dir: str) -> None:
        """空列表应生成 test_module 和 sim_setup，没有独立 CAPL。"""
        result = adapter.convert([], temp_dir)
        paths = result.strip().split("\n")
        assert len(paths) == 2
        assert os.path.isfile(paths[0])
        assert os.path.isfile(paths[1])

    def test_output_dir_created(self, adapter: VectorCANoeAdapter) -> None:
        """如果 output_dir 不存在应自动创建。"""
        with tempfile.TemporaryDirectory() as tmp:
            sub = os.path.join(tmp, "nested", "canoe_out")
            result = adapter.convert([], sub)
            assert os.path.isdir(sub)
            paths = result.strip().split("\n")
            assert all(p.startswith(sub) for p in paths)


# ──────────────────────────────────────────────────────────
# Tests: Simulation Setup
# ──────────────────────────────────────────────────────────

class TestSimulationSetup:
    """验证 Simulation Setup XML 生成。"""

    def test_defaults(self, adapter: VectorCANoeAdapter) -> None:
        """没有信号时生成基础配置。"""
        xml_str = adapter._generate_simulation_setup([])
        root = ET.fromstring(xml_str)
        assert root.tag == f"{{{_CANOE_NS}}}simulation_setup"
        # Default CAN bus
        can_config = root.find(f".//{{{_CANOE_NS}}}can")
        assert can_config is not None
        assert can_config.get("baudrate") == "500000"

    def test_dbc_references(self, adapter: VectorCANoeAdapter,
                            sample_cases: list[dict]) -> None:
        signals = adapter._collect_signals(sample_cases)
        xml_str = adapter._generate_simulation_setup(signals)
        root = ET.fromstring(xml_str)
        dbs = root.findall(f".//{{{_CANOE_NS}}}database")
        assert len(dbs) == 2  # engine.dbc, lin.dbc
        db_paths = {db.get("path") for db in dbs}
        assert "engine.dbc" in db_paths
        assert "lin.dbc" in db_paths


# ──────────────────────────────────────────────────────────
# Tests: Canonical CANoe XML compatibility
# ──────────────────────────────────────────────────────────

class TestCANoeCompatibility:
    """验证生成 XML 符合 CANoe 工具链的预期格式。"""

    def test_canoe_expected_root(self, adapter: VectorCANoeAdapter,
                                 sample_cases: list[dict]) -> None:
        """CANoe 期望 <testmodule> 作为根节点。"""
        xml_str = adapter.generate_test_module(sample_cases)
        root = ET.fromstring(xml_str)
        assert root.tag.endswith("testmodule")

    def test_groups_contain_cases(self, adapter: VectorCANoeAdapter,
                                  sample_cases: list[dict]) -> None:
        """<testgroup> 应包含多个 <testcase>。"""
        xml_str = adapter.generate_test_module(sample_cases)
        root = ET.fromstring(xml_str)
        for group in root.findall(f"{{{_CANOE_NS}}}testgroup"):
            cases = group.findall(f"{{{_CANOE_NS}}}testcase")
            assert len(cases) >= 1

    def test_no_raw_namespace_prefixes(self, adapter: VectorCANoeAdapter,
                                       sample_cases: list[dict]) -> None:
        """原始 XML 不应有未注册的命名空间前缀。"""
        xml_str = adapter.generate_test_module(sample_cases)
        # All tags should use the registered default namespace
        assert ":" not in xml_str.split("?>")[1].strip().split(" ")[0]

    def test_xml_declaration_first_line(self, adapter: VectorCANoeAdapter,
                                        sample_cases: list[dict]) -> None:
        xml_str = adapter.generate_test_module(sample_cases)
        assert xml_str.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_valid_xml_parseable(self, adapter: VectorCANoeAdapter,
                                 sample_cases: list[dict]) -> None:
        """所有生成的文件应是合法 XML。"""
        # Test module
        xml_str = adapter.generate_test_module(sample_cases)
        ET.fromstring(xml_str)  # raises on invalid

        # DBC map
        xml_str2 = adapter.generate_dbc_map(sample_cases[0].get("signals", []))
        ET.fromstring(xml_str2)

        # Simulation setup
        signals = adapter._collect_signals(sample_cases)
        xml_str3 = adapter._generate_simulation_setup(signals)
        ET.fromstring(xml_str3)

    def test_mixed_results_in_same_group(self, adapter: VectorCANoeAdapter
                                         ) -> None:
        """同一组内不同 result type 的测试用例应正确保留。"""
        cases = [
            {"id": "TC_A", "group": "Mixed", "group_id": "TG_MIX", "type": "PASS"},
            {"id": "TC_B", "group": "Mixed", "group_id": "TG_MIX", "type": "FAIL"},
        ]
        xml_str = adapter.generate_test_module(cases)
        root = ET.fromstring(xml_str)
        types = {
            tc.get("ident"): tc.get("type")
            for tc in root.findall(f".//{{{_CANOE_NS}}}testcase")
        }
        assert types["TC_A"] == "PASS"
        assert types["TC_B"] == "FAIL"


# ──────────────────────────────────────────────────────────
# Tests: _safe_filename
# ──────────────────────────────────────────────────────────

class TestSafeFilename:
    def test_safe(self) -> None:
        assert VectorCANoeAdapter._safe_filename("TC_001") == "TC_001"

    def test_unsafe_chars(self) -> None:
        assert VectorCANoeAdapter._safe_filename("TC/001:") == "TC_001_"

    def test_spaces(self) -> None:
        assert VectorCANoeAdapter._safe_filename("hello world") == "hello_world"

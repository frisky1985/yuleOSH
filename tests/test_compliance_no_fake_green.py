"""假绿修复测试：compliance_checker KG 分支阈值 + SRS SHALL 接线。

对应 sprint-contract-fake-green-hardening T3/T4：
- T3: KG total_covers>0 不再即通过（需 >=3 边 + 测试文件）
- T4: 无 SHALL 语句的需求文档不再算通过（_srs_has_shall_statements 接线）
"""

# @tests src/yuleosh/compliance/compliance_checker.py
import json
import pathlib
from unittest.mock import MagicMock, patch

from yuleosh.compliance.compliance_checker import ComplianceChecker


class TestKgCoverageThreshold:
    def _make_checker(self, tmp_path):
        return ComplianceChecker(project_dir=str(tmp_path))

    def _mock_kg(self, total_covers=0, files=()):
        kg = MagicMock()
        cov = {
            "unit": {"total_covers": total_covers, "files": list(files)},
            "integration": {"total_covers": 0, "files": []},
            "sil": {"total_covers": 0, "files": []},
            "hil": {"total_covers": 0, "files": []},
            "system": {"total_covers": 0, "files": []},
        }
        kg_store = MagicMock()
        return kg, kg_store, cov

    def test_single_covers_edge_not_enough(self, tmp_path):
        """T3: 1 条 covers 边不算覆盖率达标。"""
        c = self._make_checker(tmp_path)
        _, kg_store, cov = self._mock_kg(total_covers=1, files=["test_a.py"])
        with patch("yuleosh.knowledge_graph.queries.get_aspice_coverage", return_value=cov):
            result = c._check_with_kg("Coverage report meets threshold", kg_store)
        assert result is False

    def test_three_edges_with_files_passes(self, tmp_path):
        """T3: >=3 条 covers 边 + 测试文件 → 通过。"""
        c = self._make_checker(tmp_path)
        _, kg_store, cov = self._mock_kg(total_covers=4, files=["test_a.py", "test_b.py"])
        with patch("yuleosh.knowledge_graph.queries.get_aspice_coverage", return_value=cov):
            result = c._check_with_kg("Coverage report meets threshold", kg_store)
        assert result is True

    def test_edges_without_files_not_enough(self, tmp_path):
        """T3: 有边但无测试文件 → 不通过。"""
        c = self._make_checker(tmp_path)
        _, kg_store, cov = self._mock_kg(total_covers=10, files=[])
        with patch("yuleosh.knowledge_graph.queries.get_aspice_coverage", return_value=cov):
            result = c._check_with_kg("Coverage report meets threshold", kg_store)
        assert result is False

    def test_unit_verification_needs_three_edges(self, tmp_path):
        """T3: unit verification 同标准。"""
        c = self._make_checker(tmp_path)
        _, kg_store, cov = self._mock_kg(total_covers=2, files=["test_a.py"])
        with patch("yuleosh.knowledge_graph.queries.get_aspice_coverage", return_value=cov):
            result = c._check_with_kg("Unit tests verify the software (unit verification)", kg_store)
        assert result is False

    def test_qualification_empty_layer_not_pass(self, tmp_path):
        """T3: integration/sil 层空（无文件）不算验收证据。"""
        c = self._make_checker(tmp_path)
        _, kg_store, cov = self._mock_kg(total_covers=0, files=[])
        cov["integration"] = {"total_covers": 5, "files": []}
        with patch("yuleosh.knowledge_graph.queries.get_aspice_coverage", return_value=cov):
            result = c._check_with_kg("Qualification tests demonstrate acceptance", kg_store)
        assert result is False

    def test_qualification_with_files_passes(self, tmp_path):
        """T3: integration 层有边+文件 → 验收证据通过。"""
        c = self._make_checker(tmp_path)
        _, kg_store, cov = self._mock_kg(total_covers=0, files=[])
        cov["integration"] = {"total_covers": 5, "files": ["test_integration.py"]}
        with patch("yuleosh.knowledge_graph.queries.get_aspice_coverage", return_value=cov):
            result = c._check_with_kg("Qualification tests demonstrate acceptance", kg_store)
        assert result is True


class TestSrsShallWiring:
    def test_srs_without_shall_not_pass(self, tmp_path):
        """T4: 需求文档存在但无 SHALL 语句 → FAIL。"""
        d = pathlib.Path(tmp_path)
        (d / "docs").mkdir(exist_ok=True)
        (d / "docs" / "requirements.md").write_text(
            "# Requirements\n\nThis document describes the system requirements. "
            "The system should provide a feature. " * 3  # >100 chars, no SHALL
        )
        c = ComplianceChecker(project_dir=str(d))
        assert c._srs_has_shall_statements() is False

    def test_srs_with_shall_passes(self, tmp_path):
        """T4: 含 SHALL 语句的文档 → PASS。"""
        d = pathlib.Path(tmp_path)
        (d / "docs").mkdir(exist_ok=True)
        (d / "docs" / "requirements.md").write_text(
            "# Requirements\n\nREQ-001: The system SHALL do X. "
            "REQ-002: The system SHALL do Y."
        )
        c = ComplianceChecker(project_dir=str(d))
        assert c._srs_has_shall_statements() is True

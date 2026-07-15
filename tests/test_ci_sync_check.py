"""Tests for ci/sync_check.py — Document Sync Gate (E05/E06)."""
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from yuleosh.ci.sync_check import (
    load_sync_gate_config, get_changed_files, check_mtime_freshness,
    run_sync_check, save_sync_evidence, validate_doc_yaml_schema,
    run_sync_check_gate, print_sync_result, DOC_YAML_SCHEMAS,
    DEFAULT_GATE_FILE,
)


class TestDOC_YAML_SCHEMAS:
    def test_has_expected_keys(self):
        assert "architecture" in DOC_YAML_SCHEMAS
        assert "interface" in DOC_YAML_SCHEMAS
        assert "requirement" in DOC_YAML_SCHEMAS

    def test_architecture_has_required_fields(self):
        assert "module_name" in DOC_YAML_SCHEMAS["architecture"]["required_fields"]
        assert "version" in DOC_YAML_SCHEMAS["architecture"]["required_fields"]
        assert "last_updated" in DOC_YAML_SCHEMAS["architecture"]["required_fields"]


class TestLoadSyncGateConfig:
    def test_no_config_file(self):
        with tempfile.TemporaryDirectory() as td:
            config = load_sync_gate_config(td)
            assert config == []

    def test_valid_config(self):
        with tempfile.TemporaryDirectory() as td:
            docs_dir = Path(td) / "docs"
            docs_dir.mkdir()
            (docs_dir / ".sync-gate.yaml").write_text("""tracking:
  - code_path: "src/*"
    docs: ["docs/api.md"]
    reason: "API changes must update docs"
""")
            config = load_sync_gate_config(td)
            assert len(config) == 1
            assert config[0]["code_path"] == "src/*"

    def test_invalid_yaml(self):
        with tempfile.TemporaryDirectory() as td:
            docs_dir = Path(td) / "docs"
            docs_dir.mkdir()
            (docs_dir / ".sync-gate.yaml").write_text("{{invalid: yaml: [")
            config = load_sync_gate_config(td)
            assert config == []


class TestGetChangedFiles:
    def test_git_diff_success(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value.returncode = 0
                mock_run.return_value.stdout = "src/main.c\ndocs/README.md\n"
                mock_run.return_value.stderr = ""
                files = get_changed_files(td)
                assert len(files) == 2
                assert "src/main.c" in files

    def test_git_diff_empty_falls_back_to_status(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=""),
                    MagicMock(returncode=0, stdout=" M staged.py\n"),
                ]
                files = get_changed_files(td)
                assert files == ["staged.py"]

    def test_git_not_available(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("subprocess.run", side_effect=FileNotFoundError("git")):
                files = get_changed_files(td)
                assert files == []

    def test_git_timeout(self):
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
                files = get_changed_files(td)
                assert files == []


class TestCheckMtimeFreshness:
    def test_file_not_exists(self):
        with tempfile.TemporaryDirectory() as td:
            assert check_mtime_freshness("nonexistent.md", td) is False

    def test_recent_file(self):
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "recent.md"
            fp.write_text("content")
            assert check_mtime_freshness("recent.md", td) is True

    def test_old_file(self):
        import os
        import time
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "old.md"
            fp.write_text("old")
            # Set mtime to 31 days ago
            old = time.time() - 31 * 86400
            os.utime(str(fp), (old, old))
            assert check_mtime_freshness("old.md", td) is False


class TestRunSyncCheck:
    def test_no_rules(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_sync_check(td)
            assert result["status"] == "warning"
            assert "No sync gate rules" in result["summary"]

    def test_no_changed_files(self):
        with tempfile.TemporaryDirectory() as td:
            docs_dir = Path(td) / "docs"
            docs_dir.mkdir()
            (docs_dir / ".sync-gate.yaml").write_text("tracking:\n  - code_path: \"src/*\"\n    docs: [\"docs/api.md\"]\n    reason: \"test\"\n")
            with patch("yuleosh.ci.sync_check.get_changed_files", return_value=[]):
                result = run_sync_check(td)
                assert result["status"] == "passed"
                assert "No changed files" in result["summary"]

    def test_matched_file_but_doc_exists(self):
        with tempfile.TemporaryDirectory() as td:
            docs_dir = Path(td) / "docs"
            docs_dir.mkdir()
            (docs_dir / ".sync-gate.yaml").write_text("tracking:\n  - code_path: \"src/main.c\"\n    docs: [\"docs/api.md\"]\n    reason: \"test\"\n")
            (docs_dir / "api.md").write_text("# API docs")
            with patch("yuleosh.ci.sync_check.get_changed_files", return_value=["src/main.c"]):
                result = run_sync_check(td)
                assert result["status"] == "passed"

    def test_matched_file_but_doc_missing(self):
        with tempfile.TemporaryDirectory() as td:
            docs_dir = Path(td) / "docs"
            docs_dir.mkdir()
            (docs_dir / ".sync-gate.yaml").write_text("tracking:\n  - code_path: \"src/main.c\"\n    docs: [\"docs/api.md\"]\n    reason: \"test\"\n")
            with patch("yuleosh.ci.sync_check.get_changed_files", return_value=["src/main.c"]):
                result = run_sync_check(td)
                assert result["status"] == "failed"
                assert len(result["rule_results"]) >= 1


class TestSaveSyncEvidence:
    def test_saves_file(self):
        with tempfile.TemporaryDirectory() as td:
            result = {"status": "passed", "summary": "ok"}
            path = save_sync_evidence(td, result)
            assert path.endswith("docsync-evidence.json")
            assert Path(path).exists()
            data = json.loads(Path(path).read_text())
            assert data["status"] == "passed"


class TestValidateDocYamlSchema:
    def test_no_matching_files(self):
        with tempfile.TemporaryDirectory() as td:
            findings = validate_doc_yaml_schema(td)
            assert len(findings) == 3  # one for each doc type

    def test_valid_yaml_doc(self):
        with tempfile.TemporaryDirectory() as td:
            arch_dir = Path(td) / "docs" / "architecture"
            arch_dir.mkdir(parents=True, exist_ok=True)
            (arch_dir / "module.yaml").write_text(
                "module_name: test\nversion: 1.0\nlast_updated: '2026-01-01'\ncode_path: src/\n"
            )
            findings = validate_doc_yaml_schema(td)
            arch_findings = [f for f in findings if f.get("rule") == "schema-architecture"]
            assert any("All required fields present" in f.get("message", "") for f in arch_findings)

    def test_invalid_yaml_parse_error(self):
        with tempfile.TemporaryDirectory() as td:
            arch_dir = Path(td) / "docs" / "architecture"
            arch_dir.mkdir(parents=True, exist_ok=True)
            (arch_dir / "bad.yaml").write_text("invalid: [yaml: :::")
            findings = validate_doc_yaml_schema(td)
            arch_errors = [f for f in findings if f.get("rule") == "schema-architecture" and f.get("severity") == "error"]
            assert len(arch_errors) >= 1

    def test_missing_required_fields(self):
        with tempfile.TemporaryDirectory() as td:
            arch_dir = Path(td) / "docs" / "architecture"
            arch_dir.mkdir(parents=True, exist_ok=True)
            (arch_dir / "incomplete.yaml").write_text("name: only_this\n")
            findings = validate_doc_yaml_schema(td)
            arch_errors = [
                f for f in findings
                if f.get("rule") == "schema-architecture" and f.get("severity") == "error"
            ]
            missing_fields = [f for f in arch_errors if "Missing required" in f.get("message", "")]
            assert any("Missing required" in f.get("message", "") for f in arch_errors)


class TestRunSyncCheckGate:
    def test_runs_both_checks(self):
        with tempfile.TemporaryDirectory() as td:
            result = run_sync_check_gate(td)
            assert "tracking_results" in result
            assert "schema_results" in result
            assert result["status"] in ("passed", "warning", "failed")


class TestPrintSyncResult:
    def test_prints_without_error(self):
        result = {"status": "passed", "summary": "ok"}
        # Should not raise
        print_sync_result(result)

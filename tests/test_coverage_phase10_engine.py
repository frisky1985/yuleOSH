"""Phase 10 coverage tests — engine/spec 域低覆盖文件分支补齐。

覆盖目标（只测本组 5 个文件，不依赖外部服务/真实子进程）:
  1. src/yuleosh/spec/merge.py        — delta 解析错误/多场景 flush/冲突/合并错误分支/CLI
  2. src/yuleosh/llm/fallback.py      — 降级链各级失败分支/重试/模板 KeyError/abort
  3. src/yuleosh/engine/subprocess_executor.py — worker 错误路径/产物交接/超时/坏输出
  4. src/yuleosh/ci/sync_check.py     — git 回退/过期文档 warning/非 dict YAML/门禁状态
  5. src/yuleosh/autosar/parser.py    — 端口方向推断/COM-SPECS/事件/runnalbe 边界

隔离约定: tmp_path / monkeypatch，无 sys.path.insert，无 YULEOSH_JWT_SECRET 干预。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from xml.etree import ElementTree as ET

from yuleosh.spec.merge import (
    Conflict,
    DeltaParseResult,
    DeltaStatement,
    cmd_spec_merge,
    detect_conflicts,
    merge_delta,
    parse_delta_file,
    validate_delta_format,
    _build_merged_spec,
    _generate_diff_text,
)
from yuleosh.llm.fallback import (
    FallbackResult,
    apply_fallback_chain,
    _FallbackState,
    _detect_contradictions,
    _level_1_schema,
    _level_2_content,
    _level_3_semantic,
    _level_4_template,
    _retry_llm,
)
from yuleosh.engine.subprocess_executor import (
    _find_step,
    _make_worker_session,
    _resolve_session_dir,
    _run_step_in_subprocess,
    worker_main,
)
from yuleosh.engine.handler_adapter import StepResult
from yuleosh.ci.sync_check import (
    check_mtime_freshness,
    get_changed_files,
    print_sync_result,
    run_sync_check,
    run_sync_check_gate,
    validate_doc_yaml_schema,
)
from yuleosh.autosar.parser import (
    ARXMLParser,
    _getattr,
    _local,
    _ns,
)


# ===========================================================================
# 1. spec/merge.py — 未覆盖分支
# ===========================================================================


class TestSpecMergeParseEdge:
    def test_parse_delta_read_oserror(self, tmp_path, monkeypatch):
        """delta 文件存在但读取抛 OSError → 进 errors。"""
        delta_path = tmp_path / "delta.md"
        delta_path.write_text("# x", encoding="utf-8")

        def boom(self, *a, **kw):
            raise OSError("read denied")

        monkeypatch.setattr(Path, "read_text", boom)
        result = parse_delta_file(str(delta_path))
        assert len(result.errors) == 1
        assert "Cannot read delta file" in result.errors[0]

    def test_parse_multi_scenario_flushes_previous(self, tmp_path):
        """第二个 Scenario 头出现时 flush 前一个；末尾 flush 最后一个。"""
        text = (
            "# Delta\n"
            "## Sec\n"
            "### Scenario: First\n"
            "- GIVEN a\n"
            "- WHEN b\n"
            "- THEN c\n"
            "### Scenario: Second\n"
            "- GIVEN x\n"
            "- THEN y\n"
        )
        p = tmp_path / "multi.md"
        p.write_text(text, encoding="utf-8")
        result = parse_delta_file(str(p))
        assert len(result.scenarios) == 2
        assert result.scenarios[0]["name"] == "First"
        assert result.scenarios[1]["name"] == "Second"

    def test_parse_then_embedded_shall_with_prefix(self, tmp_path):
        """THEN 内嵌 SHALL 且语句已带 'the system SHALL' 前缀 → 原样保留。"""
        text = (
            "# Delta\n"
            "## Sec\n"
            "### Scenario: S\n"
            "- GIVEN g\n"
            "- THEN SHALL the system SHALL retry 3 times\n"
        )
        p = tmp_path / "pref.md"
        p.write_text(text, encoding="utf-8")
        result = parse_delta_file(str(p))
        assert len(result.statements) == 1
        assert result.statements[0].text == "the system SHALL retry 3 times"

    def test_parse_shall_inside_scenario_is_skipped(self, tmp_path):
        """场景块内非 GIVEN/WHEN/THEN 的 SHALL 行被跳过（不重复提取）。"""
        text = (
            "# Delta\n"
            "## Sec\n"
            "### Scenario: S\n"
            "- GIVEN g\n"
            "- SHALL do something directly\n"
            "- THEN t\n"
        )
        p = tmp_path / "skip.md"
        p.write_text(text, encoding="utf-8")
        result = parse_delta_file(str(p))
        # THEN 't' 无 SHALL；直接 SHALL 行在场景内被跳过
        assert result.statements == []


class TestSpecMergeConflictBranches:
    def test_negation_topic_empty_returns_none(self):
        """SHALL NOT 后无主题 → 无法比对 → 无冲突。"""
        delta = DeltaParseResult()
        delta.statements.append(
            DeltaStatement("SHALL", "The system SHALL NOT", "S", 1)
        )
        conflicts = detect_conflicts(
            delta, "# Spec\n- The system SHALL do X.\n"
        )
        assert conflicts == []

    def test_negation_low_word_overlap_returns_none(self):
        """极性相反但主题词重叠 < 3 → 不判冲突。"""
        delta = DeltaParseResult()
        delta.statements.append(
            DeltaStatement(
                "SHALL", "The system SHALL NOT reboot the device quickly", "S", 1
            )
        )
        conflicts = detect_conflicts(
            delta, "# Spec\n- The system SHALL access memory and storage.\n"
        )
        assert conflicts == []

    def test_negation_high_overlap_is_error(self):
        """极性相反且主题词重叠 >= 3 → error 冲突。"""
        delta = DeltaParseResult()
        delta.statements.append(
            DeltaStatement(
                "SHALL",
                "The system SHALL NOT access memory and storage",
                "S",
                1,
            )
        )
        conflicts = detect_conflicts(
            delta, "# Spec\n- The system SHALL access memory and storage.\n"
        )
        assert len(conflicts) == 1
        assert conflicts[0].severity == "error"


class TestSpecMergeDeltaBranches:
    def _setup_project(self, tmp_path, spec_text="# Spec\n\n> **Version**: 1.0.0\n\n- SHALL x\n"):
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "spec.md").write_text(spec_text, encoding="utf-8")

    def _write_delta(self, tmp_path, body):
        p = tmp_path / "delta.md"
        p.write_text(body, encoding="utf-8")
        return str(p)

    def test_merge_uses_osh_home_when_no_project_dir(self, tmp_path, monkeypatch):
        """project_dir=None → 用 OSH_HOME 定位项目。"""
        self._setup_project(tmp_path)
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        delta = self._write_delta(
            tmp_path, "# D\n\n**Version**: 1.0.0\n\n- The system SHALL do Y.\n"
        )
        result = merge_delta(delta, dry_run=True)
        assert result["status"] == "dry-run"

    def test_merge_delta_parse_error(self, tmp_path):
        """delta 文件不存在 → errors 直通。"""
        result = merge_delta(str(tmp_path / "missing.md"), str(tmp_path))
        assert result["status"] == "error"
        assert any("not found" in e for e in result["errors"])

    def test_merge_spec_read_oserror(self, tmp_path):
        """spec 路径是目录 → 读取抛 OSError → error。"""
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "spec.md").mkdir()  # 目录冒充文件
        delta = self._write_delta(
            tmp_path, "# D\n\n- The system SHALL do Y.\n"
        )
        result = merge_delta(delta, str(tmp_path))
        assert result["status"] == "error"
        assert any("Cannot read spec file" in e for e in result["errors"])

    def test_merge_target_version_greater(self, tmp_path):
        """delta 目标版本 > 当前 → 采用 delta 版本。"""
        self._setup_project(tmp_path)
        delta = self._write_delta(
            tmp_path, "# D\n\n**Version**: 1.2.0\n\n- The system SHALL do Y.\n"
        )
        result = merge_delta(delta, str(tmp_path), dry_run=True)
        assert result["version"] == "1.2.0"

    def test_merge_target_version_equal_autobump(self, tmp_path):
        """delta 目标版本 == 当前 → auto-bump。"""
        self._setup_project(tmp_path)
        delta = self._write_delta(
            tmp_path, "# D\n\n**Version**: 1.0.0\n\n- The system SHALL do Y.\n"
        )
        result = merge_delta(delta, str(tmp_path), dry_run=True)
        assert result["version"] == "1.1.0"

    def test_merge_target_version_lower_autobump(self, tmp_path):
        """delta 目标版本 < 当前 → 以当前为基 auto-bump。"""
        self._setup_project(tmp_path)
        delta = self._write_delta(
            tmp_path, "# D\n\n**Version**: 0.9.0\n\n- The system SHALL do Y.\n"
        )
        result = merge_delta(delta, str(tmp_path), dry_run=True)
        assert result["version"] == "1.1.0"

    def test_merge_blocked_by_error_conflict(self, tmp_path, monkeypatch):
        """error 级冲突 → merge blocked（detect_conflicts 返回 error 冲突）。"""
        self._setup_project(tmp_path)
        delta = self._write_delta(
            tmp_path, "# D\n\n- The system SHALL do Y.\n"
        )
        import yuleosh.spec.merge as m

        fake_conflict = Conflict(
            delta_statement=DeltaStatement("SHALL", "do Y", "S", 1),
            existing_shall="the system shall do y",
            severity="error",
            description="Contradiction with existing spec",
        )
        monkeypatch.setattr(m, "detect_conflicts", lambda d, t: [fake_conflict])
        result = merge_delta(delta, str(tmp_path))
        assert result["status"] == "error"
        assert any("Merge blocked" in e for e in result["errors"])
        assert result["conflicts"][0]["severity"] == "error"

    def test_merge_backup_oserror(self, tmp_path, monkeypatch):
        """备份失败 → error。"""
        self._setup_project(tmp_path)
        delta = self._write_delta(
            tmp_path, "# D\n\n- The system SHALL do Y.\n"
        )

        def boom(src, dst):
            raise OSError("backup denied")

        import yuleosh.spec.merge as m

        monkeypatch.setattr(m.shutil, "copy2", boom)
        result = merge_delta(delta, str(tmp_path))
        assert result["status"] == "error"
        assert any("Cannot create backup" in e for e in result["errors"])

    def test_merge_write_spec_oserror(self, tmp_path, monkeypatch):
        """写 merged spec 失败 → error（delta 读取不受影响）。"""
        self._setup_project(tmp_path)
        delta = self._write_delta(
            tmp_path, "# D\n\n- The system SHALL do Y.\n"
        )
        spec_path = str(tmp_path / "docs" / "spec.md")
        orig_write_text = Path.write_text

        def selective_write(self, data, *a, **kw):
            if str(self) == spec_path:
                raise OSError("write denied")
            return orig_write_text(self, data, *a, **kw)

        monkeypatch.setattr(Path, "write_text", selective_write)
        result = merge_delta(delta, str(tmp_path))
        assert result["status"] == "error"
        assert any("Cannot write merged spec" in e for e in result["errors"])

    def test_merge_version_write_failure(self, tmp_path, monkeypatch):
        """write_spec_version 返回 False → error。"""
        self._setup_project(tmp_path)
        delta = self._write_delta(
            tmp_path, "# D\n\n- The system SHALL do Y.\n"
        )
        import yuleosh.spec.merge as m

        monkeypatch.setattr(m, "write_spec_version", lambda *a, **kw: False)
        result = merge_delta(delta, str(tmp_path))
        assert result["status"] == "error"
        assert any("Failed to write spec version file" in e for e in result["errors"])

    def test_merge_no_target_version_header(self, tmp_path):
        """delta 无版本头 → 走默认 auto-bump 分支。"""
        self._setup_project(tmp_path)
        delta = self._write_delta(tmp_path, "# D\n\n- The system SHALL do Y.\n")
        result = merge_delta(delta, str(tmp_path), dry_run=True)
        assert result["version"] == "1.1.0"


class TestSpecMergeBuildDiff:
    def test_build_merged_no_version_no_h1(self):
        """spec 无 **Version** 也无 '# ' 标题 → 不插入版本行。"""
        delta = DeltaParseResult()
        delta.statements.append(DeltaStatement("SHALL", "do Y", "S", 1))
        merged = _build_merged_spec(
            "## Sec\n\n- SHALL x\n", delta, "2.0.0"
        )
        assert "Merged from Spec-Delta" in merged
        assert "### S" in merged

    def test_build_merged_h1_is_last_line(self):
        """'# ' 是最后一行（无下一行可插）→ 跳过插入。"""
        delta = DeltaParseResult()
        delta.statements.append(DeltaStatement("SHALL", "do Y", "S", 1))
        merged = _build_merged_spec("# Only Heading", delta, "2.0.0")
        assert "Merged from Spec-Delta" in merged

    def test_build_merged_with_scenarios(self):
        """带 scenarios → 输出 GIVEN/WHEN/THEN 场景块。"""
        delta = DeltaParseResult()
        delta.scenarios.append(
            {"name": "Boot", "given": ["power on"], "when": ["start"], "then": ["run"]}
        )
        merged = _build_merged_spec(
            "# Spec\n\n> **Version**: 1.0.0\n\n- SHALL x\n", delta, "1.1.0"
        )
        assert "GIVEN/WHEN/THEN Scenarios" in merged
        assert "#### Scenario: Boot" in merged
        assert "- GIVEN power on" in merged

    def test_diff_text_scenarios_only(self):
        """无 statements、有 scenarios → 只输出场景摘要。"""
        delta = DeltaParseResult()
        delta.scenarios.append({"name": "S1", "given": ["g"], "when": [], "then": ["t"]})
        text = _generate_diff_text(delta, "1.1.0", "1.0.0")
        assert "### Scenarios" in text
        assert "S1 (1 GIVEN, 0 WHEN, 1 THEN)" in text
        assert "### Statements" not in text

    def test_validate_delta_format_read_oserror(self, tmp_path):
        """读取抛 OSError（目录冒充文件）→ issues。"""
        d = tmp_path / "delta.md"
        d.mkdir()
        issues = validate_delta_format(str(d))
        assert any("Cannot read file" in i for i in issues)


class TestSpecMergeCli:
    def test_cmd_missing_delta_returns_false(self, capsys):
        assert cmd_spec_merge("/nonexistent/delta.md") is False
        out = capsys.readouterr().out
        assert "Delta format validation failed" in out

    def test_cmd_merge_error_returns_false(self, tmp_path, capsys):
        delta = tmp_path / "delta.md"
        delta.write_text("# D\n\n- The system SHALL do Y.\n", encoding="utf-8")
        with patch(
            "yuleosh.spec.merge.merge_delta",
            return_value={"errors": ["boom"], "conflicts": []},
        ):
            assert cmd_spec_merge(str(delta), str(tmp_path)) is False
        assert "Merge failed" in capsys.readouterr().out

    def test_cmd_dry_run_success(self, tmp_path, capsys):
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "spec.md").write_text(
            "# Spec\n\n> **Version**: 1.0.0\n\n- SHALL x\n", encoding="utf-8"
        )
        delta = tmp_path / "delta.md"
        delta.write_text("# D\n\n- The system SHALL do Y.\n", encoding="utf-8")
        assert cmd_spec_merge(str(delta), str(tmp_path), dry_run=True) is True
        out = capsys.readouterr().out
        assert "Dry run" in out
        assert "Spec Merge Summary" in out

    def test_cmd_full_success(self, tmp_path, capsys):
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "spec.md").write_text(
            "# Spec\n\n> **Version**: 1.0.0\n\n- SHALL x\n",
            encoding="utf-8",
        )
        delta = tmp_path / "delta.md"
        delta.write_text(
            "# D\n\n**Version**: 1.1.0\n\n- The system SHALL do Y.\n",
            encoding="utf-8",
        )
        assert cmd_spec_merge(str(delta), str(tmp_path)) is True
        out = capsys.readouterr().out
        assert "Merge complete" in out
        assert "Version: 1.1.0" in out
        assert "Backup:" in out
        assert "Output:" in out

    def test_cmd_warning_conflict_prints(self, tmp_path, capsys):
        """merge 结果带 warning 冲突 → 打印 Non-blocking warnings 块。"""
        delta = tmp_path / "delta.md"
        delta.write_text("# D\n\n- The system SHALL do Y.\n", encoding="utf-8")
        fake_result = {
            "status": "ok",
            "version": "1.1.0",
            "statements_added": 1,
            "scenarios_added": 0,
            "conflicts": [
                {
                    "severity": "warning",
                    "description": "Duplicate SHALL statement (line 1): '...' already exists",
                }
            ],
            "errors": [],
            "diff_text": "## Spec Merge Summary\n",
            "backup_path": "/tmp/bak.json",
            "output_path": "/tmp/spec.md",
        }
        with patch("yuleosh.spec.merge.merge_delta", return_value=fake_result):
            assert cmd_spec_merge(str(delta), str(tmp_path)) is True
        out = capsys.readouterr().out
        assert "Non-blocking warnings" in out
        assert "Duplicate SHALL statement" in out

    def test_cmd_parse_errors_returns_false(self, tmp_path, capsys):
        """validate 通过但 parse 报错 → 打印 Parse errors 并返回 False。"""
        delta = tmp_path / "delta.md"
        delta.write_text("# D\n\n- The system SHALL do Y.\n", encoding="utf-8")
        fake_result = DeltaParseResult(errors=["parse boom"])
        with patch("yuleosh.spec.merge.parse_delta_file", return_value=fake_result):
            assert cmd_spec_merge(str(delta), str(tmp_path)) is False
        out = capsys.readouterr().out
        assert "Parse errors" in out
        assert "parse boom" in out

    def test_cmd_misra_profiles_ok_skips_warning(self, tmp_path, capsys, monkeypatch):
        """MISRA profile 校验通过 → 不打印 ⚠️ 块。"""
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "spec.md").write_text(
            "# Spec\n\n> **Version**: 1.0.0\n\n- SHALL x\n", encoding="utf-8"
        )
        delta = tmp_path / "delta.md"
        delta.write_text("# D\n\n- The system SHALL do Y.\n", encoding="utf-8")
        import yuleosh.ci.config as cicfg

        monkeypatch.setattr(cicfg, "validate_misra_profiles", lambda cfg: [])
        assert cmd_spec_merge(str(delta), str(tmp_path), dry_run=True) is True
        out = capsys.readouterr().out
        assert "MISRA profile validation" not in out

    def test_cmd_misra_profile_load_raises_ignored(self, tmp_path, capsys, monkeypatch):
        """load_ci_config 抛异常 → 被吞掉，merge 继续。"""
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "spec.md").write_text(
            "# Spec\n\n> **Version**: 1.0.0\n\n- SHALL x\n", encoding="utf-8"
        )
        delta = tmp_path / "delta.md"
        delta.write_text("# D\n\n- The system SHALL do Y.\n", encoding="utf-8")
        import yuleosh.ci.config as cicfg

        def boom(*a, **kw):
            raise RuntimeError("cfg boom")

        monkeypatch.setattr(cicfg, "load_ci_config", boom)
        assert cmd_spec_merge(str(delta), str(tmp_path), dry_run=True) is True
        out = capsys.readouterr().out
        assert "Dry run" in out

    def test_cmd_conflicts_without_warnings(self, tmp_path, capsys):
        """conflicts 非空但无 warning 级 + 无 backup/output → 跳过对应打印块。"""
        delta = tmp_path / "delta.md"
        delta.write_text("# D\n\n- The system SHALL do Y.\n", encoding="utf-8")
        fake_result = {
            "status": "ok",
            "version": "1.1.0",
            "statements_added": 1,
            "scenarios_added": 0,
            "conflicts": [{"severity": "info", "description": "informational"}],
            "errors": [],
            "diff_text": "## Spec Merge Summary\n",
            "backup_path": None,
            "output_path": None,
        }
        with patch("yuleosh.spec.merge.merge_delta", return_value=fake_result):
            assert cmd_spec_merge(str(delta), str(tmp_path)) is True
        out = capsys.readouterr().out
        assert "Non-blocking warnings" not in out
        assert "Merge complete" in out


# ===========================================================================
# 2. llm/fallback.py — 未覆盖分支
# ===========================================================================


class TestFallbackStateInternals:
    def test_find_yuleosh_dir_none_session(self):
        state = _FallbackState("s", None)
        assert state._find_yuleosh_dir() is None

    def test_find_yuleosh_dir_walks_up(self, tmp_path):
        (tmp_path / ".yuleosh").mkdir()
        session_dir = tmp_path / "a" / "b" / "c"
        session_dir.mkdir(parents=True)
        state = _FallbackState("s", session_dir)
        assert state._find_yuleosh_dir() == (tmp_path / ".yuleosh")

    def test_log_failure_writes_jsonl(self, tmp_path):
        (tmp_path / ".yuleosh").mkdir()
        session_dir = tmp_path / "sess"
        session_dir.mkdir()
        state = _FallbackState("step-x", session_dir)
        state.log_failure(2, "schema failed")
        failures = (
            tmp_path / ".yuleosh" / "reports" / "llm-validation-failures.jsonl"
        )
        assert failures.exists()
        entry = json.loads(failures.read_text().strip())
        assert entry["step"] == "step-x"
        assert entry["level"] == 2
        assert entry["error"] == "schema failed"
        assert entry["retries"] == state.retries
        assert entry["elapsed_s"] >= 0.0  # get_elapsed 被调用

    def test_get_elapsed_direct(self):
        state = _FallbackState("s", None)
        assert state.get_elapsed() >= 0.0


class TestFallbackLevelBranches:
    def test_level_1_no_schema_returns_raw(self):
        state = _FallbackState("s", None)
        state.output = "raw"
        state.schema = {}
        result = _level_1_schema(state)
        assert result.status == "ok"
        assert result.level == 0

    def test_level_2_fails_all_attempts(self):
        """content 校验三次全败（含两次重试）→ fallback level 2。"""
        state = _FallbackState("s", None)
        state.output = "short"
        state.schema = {"type": "string", "min_length": 50}
        state.llm_call = lambda prompt: "still too short"
        result = _level_2_content(state)
        assert result.status == "fallback"
        assert result.level == 2
        assert result.retries == 2
        assert any("Content validation failed" in e for e in result.errors)

    def test_level_3_contradiction_fails(self):
        """语义矛盾检测命中 → 重试后 fallback level 3。"""
        state = _FallbackState("s", None)
        state.output = "The system SHALL do X. The system shall not do X."
        state.schema = {"shalls_required": True}
        state.llm_call = lambda prompt: "The system SHALL do X. The system shall not do X."
        result = _level_3_semantic(state)
        assert result.status == "fallback"
        assert result.level == 3
        assert result.retries == 1

    def test_level_4_template_keyerror_falls_back_default(self):
        """自定义模板缺 context key → 用默认模板。"""
        state = _FallbackState("s", None)
        state.template = "# {missing_key}"
        state.template_ctx = {"title": "T"}
        result = _level_4_template(state)
        assert result.status == "fallback"
        assert "template fallback" in result.output.lower()

    def test_level_5_abort_when_template_empty(self):
        """模板输出为空 → level 5 abort。"""
        result = apply_fallback_chain(
            step_name="s",
            llm_output="",
            schema={"type": "json", "required_fields": ["k"]},
            template="{title}",
            template_ctx={"title": ""},
        )
        assert result.status == "abort"
        assert result.level == 5
        assert result.output == ""


class TestFallbackRetry:
    def test_retry_llm_none_callable(self):
        state = _FallbackState("s", None)
        state.original_prompt = "p"
        state.errors = ["e1"]
        assert _retry_llm(state) == ""

    def test_retry_llm_dict_result(self):
        state = _FallbackState("s", None)
        state.original_prompt = "p"
        state.errors = ["e1"]
        state.llm_call = lambda prompt: {"content": "fixed"}
        assert _retry_llm(state) == "fixed"

    def test_retry_llm_str_result(self):
        state = _FallbackState("s", None)
        state.original_prompt = "p"
        state.llm_call = lambda prompt: "plain string"
        assert _retry_llm(state) == "plain string"

    def test_retry_llm_raises(self):
        state = _FallbackState("s", None)
        state.original_prompt = "p"

        def boom(prompt):
            raise RuntimeError("llm down")

        state.llm_call = boom
        assert _retry_llm(state) == ""

    def test_retry_prompt_includes_errors(self):
        state = _FallbackState("s", None)
        state.original_prompt = "orig"
        state.errors = ["err-a", "err-b"]
        captured = {}

        def capture(p):
            captured["prompt"] = p
            return {"content": "x"}

        state.llm_call = capture
        _retry_llm(state)
        prompt = captured.get("prompt") or ""
        assert "orig" in prompt
        assert "err-a" in prompt
        assert "err-b" in prompt


class TestFallbackContradictions:
    def test_must_not_flagged(self):
        out = "The system must run. The system must not stop."
        assert len(_detect_contradictions(out, {})) >= 1

    def test_no_shalls_required_skips_block(self):
        out = "SHALL x shall not y"
        assert _detect_contradictions(out, {}) == []

    def test_must_not_sentence_only_no_error(self):
        # 只含 must not 的句子（无正向 must 同句）→ 仍被保守标记
        out = "You must not delete data."
        assert len(_detect_contradictions(out, {})) >= 1


class TestFallbackChainStartLevel:
    def test_empty_output_no_schema_falls_to_template(self):
        """l0 ok 但输出空 → 继续链到 level 4。"""
        result = apply_fallback_chain(step_name="spec", llm_output="")
        assert result.status == "fallback"
        assert result.level == 4

    def test_start_level_3_skips_lower_levels(self):
        """start_level=3 → 跳过 l0/l1/l2，从语义开始。"""
        result = apply_fallback_chain(
            step_name="spec",
            llm_output="",
            schema={"type": "json"},
            start_level=3,
        )
        assert result.status == "fallback"
        assert result.level == 4

    def test_start_level_4_skips_l3(self):
        """start_level=4 → 直接模板 fallback。"""
        result = apply_fallback_chain(
            step_name="spec",
            llm_output="",
            schema={"type": "json"},
            start_level=4,
        )
        assert result.status == "fallback"
        assert result.level == 4

    def test_level1_retry_then_ok(self):
        """schema 校验第一次失败、重试后通过 → ok level 1 retries=1。"""
        calls = {"n": 0}
        good_output = (
            "# Title\n\nThe system SHALL do this. "
            + "padding " * 15
        )

        def llm_call(prompt):
            # llm_call 只在重试时被调用：第一次重试即返回合法输出
            calls["n"] += 1
            return {"content": good_output}

        result = apply_fallback_chain(
            step_name="spec",
            llm_output="short",
            schema={"type": "string", "min_length": 50, "shalls_required": True},
            llm_call=llm_call,
            original_prompt="orig",
        )
        assert result.status == "ok"
        assert result.level == 1
        assert result.retries == 1


# ===========================================================================
# 3. engine/subprocess_executor.py — 未覆盖分支
# ===========================================================================


class TestSubprocessExecutorUnits:
    def test_resolve_session_dir_with_run_id(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        p = _resolve_session_dir(str(tmp_path), run_id="rid123")
        assert p == tmp_path / ".osh" / "sessions" / "rid123"

    def test_resolve_session_dir_default_name(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        p = _resolve_session_dir(str(tmp_path))
        assert p.parent == tmp_path / ".osh" / "sessions"
        assert p.name.startswith("agent-pipeline-")

    def test_find_step_loop_branch(self):
        """查找非首个 step → 覆盖循环 continue 分支。"""
        step_key, step_name, handler = _find_step("super-analysis")
        assert step_key == "super-analysis"
        assert step_name

    def test_find_step_unknown_raises(self):
        with pytest.raises(ValueError, match="not found"):
            _find_step("no-such-step")

    def test_make_worker_session_mock_mode(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session = _make_worker_session(
            str(tmp_path),
            {"step_id": "s1", "name": "n"},
            mock_mode=True,
            run_id="rid1",
        )
        assert session.mock_mode is True
        assert session.llm_client is not None
        assert session.run_id == "rid1"

    def test_make_worker_session_default_spec_path(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OSH_HOME", str(tmp_path))
        session = _make_worker_session(
            str(tmp_path), {"step_id": "s1", "name": "n"}, run_id="rid2"
        )
        assert session.spec_path.endswith("docs/spec.md")


class TestWorkerMainErrorPaths:
    def test_worker_main_unknown_step(self, tmp_path, capsys):
        rc = worker_main(["--step-id", "no-such", "--project-dir", str(tmp_path)])
        assert rc == 1
        payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert payload["verdict"] == "failed"
        assert "not found" in payload["error"]

    def _patch_worker_deps(self, monkeypatch, session, handler_result=None):
        import yuleosh.engine.subprocess_executor as spe

        def fake_handler(session):
            if handler_result is not None:
                if isinstance(handler_result, Exception):
                    raise handler_result
                return handler_result
            return StepResult(verdict="passed", output_path="/tmp/out.json")

        monkeypatch.setattr(
            spe, "_find_step", lambda sid: ("fake-step", "Fake Step", fake_handler)
        )
        monkeypatch.setattr(spe, "_make_worker_session", lambda *a, **kw: session)
        return spe

    def test_worker_main_loads_artifacts(self, tmp_path, capsys, monkeypatch):
        import yuleosh.engine.subprocess_executor as spe

        session_dir = tmp_path / ".osh" / "sessions" / "rid"
        session_dir.mkdir(parents=True)
        (session_dir / "artifacts.json").write_text(
            json.dumps({"prev": "/tmp/prev.json"}), encoding="utf-8"
        )
        session = SimpleNamespace(
            session_dir=session_dir, artifacts={},
            project_dir=str(tmp_path), mock_mode=True, llm_client=None,
            step_id="s", step_name="S", agent="",
        )
        self._patch_worker_deps(monkeypatch, session)
        rc = worker_main(
            ["--step-id", "fake-step", "--project-dir", str(tmp_path),
             "--session-name", "sess", "--run-id", "rid"]
        )
        assert rc == 0
        assert session.artifacts == {"prev": "/tmp/prev.json"}
        payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert payload["verdict"] == "passed"

    def test_worker_main_bad_artifacts_json(self, tmp_path, capsys, monkeypatch):
        session_dir = tmp_path / ".osh" / "sessions" / "rid"
        session_dir.mkdir(parents=True)
        (session_dir / "artifacts.json").write_text("{not json", encoding="utf-8")
        session = SimpleNamespace(
            session_dir=session_dir, artifacts={},
            project_dir=str(tmp_path), mock_mode=True, llm_client=None,
            step_id="s", step_name="S", agent="",
        )
        self._patch_worker_deps(monkeypatch, session)
        rc = worker_main(
            ["--step-id", "fake-step", "--project-dir", str(tmp_path),
             "--session-name", "sess", "--run-id", "rid"]
        )
        assert rc == 0
        assert session.artifacts == {}

    def test_worker_main_handler_raises(self, tmp_path, capsys, monkeypatch):
        session = SimpleNamespace(
            session_dir=tmp_path, artifacts={},
            project_dir=str(tmp_path), mock_mode=True, llm_client=None,
            step_id="s", step_name="S", agent="",
        )
        self._patch_worker_deps(
            monkeypatch, session, handler_result=RuntimeError("handler boom")
        )
        rc = worker_main(["--step-id", "fake-step", "--project-dir", str(tmp_path)])
        assert rc == 1
        payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert payload["verdict"] == "failed"
        assert "handler boom" in payload["error"]


class TestRunStepInSubprocess:
    def _fake_proc(self, stdout="", stderr="", returncode=0):
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    def test_success_parses_last_line(self, tmp_path, monkeypatch):
        import yuleosh.engine.subprocess_executor as spe

        out = "handler log\n{\"verdict\": \"passed\", \"output_path\": \"/o.json\", \"fallback_stamped\": true}"
        monkeypatch.setattr(spe.subprocess, "run", lambda *a, **kw: self._fake_proc(out))
        result = _run_step_in_subprocess(
            {"step_id": "s1"}, str(tmp_path), mock_mode=False, spec_path=None,
            session_name=None, run_id=None,
        )
        assert result.verdict == "passed"
        assert result.output_path == "/o.json"
        assert result.fallback_stamped is True

    def test_no_output_fails(self, tmp_path, monkeypatch):
        import yuleosh.engine.subprocess_executor as spe

        monkeypatch.setattr(
            spe.subprocess, "run",
            lambda *a, **kw: self._fake_proc(stdout="", stderr="boom", returncode=1),
        )
        result = _run_step_in_subprocess({"step_id": "s1"}, str(tmp_path), False, None)
        assert result.verdict == "failed"
        assert "无输出" in (result.error or "")

    def test_bad_json_fails(self, tmp_path, monkeypatch):
        import yuleosh.engine.subprocess_executor as spe

        monkeypatch.setattr(
            spe.subprocess, "run",
            lambda *a, **kw: self._fake_proc(stdout="line\nnot json"),
        )
        result = _run_step_in_subprocess({"step_id": "s1"}, str(tmp_path), False, None)
        assert result.verdict == "failed"
        assert "非 JSON" in (result.error or "")

    def test_timeout_fails(self, tmp_path, monkeypatch):
        import yuleosh.engine.subprocess_executor as spe

        def boom(*a, **kw):
            raise subprocess.TimeoutExpired("cmd", 5)

        monkeypatch.setattr(spe.subprocess, "run", boom)
        result = _run_step_in_subprocess(
            {"step_id": "s1"}, str(tmp_path), False, None, timeout_s=5
        )
        assert result.verdict == "failed"
        assert "timed out after 5s" in (result.error or "")

    def test_spawn_oserror_fails(self, tmp_path, monkeypatch):
        import yuleosh.engine.subprocess_executor as spe

        def boom(*a, **kw):
            raise OSError("spawn failed")

        monkeypatch.setattr(spe.subprocess, "run", boom)
        result = _run_step_in_subprocess({"step_id": "s1"}, str(tmp_path), False, None)
        assert result.verdict == "failed"
        assert "subprocess spawn failed" in (result.error or "")

    def test_mock_and_run_id_flags(self, tmp_path, monkeypatch):
        import yuleosh.engine.subprocess_executor as spe

        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            captured["cwd"] = kw.get("cwd")
            return self._fake_proc(
                '{"verdict": "passed", "output_path": null, "error": null, "fallback_stamped": false}'
            )

        monkeypatch.setattr(spe.subprocess, "run", fake_run)
        _run_step_in_subprocess(
            {"step_id": "s1"}, str(tmp_path), mock_mode=True, spec_path="/sp.md",
            session_name="sess", run_id="rid9",
        )
        cmd = captured["cmd"]
        assert "--mock" in cmd
        assert "--spec-path" in cmd and "/sp.md" in cmd
        assert "--session-name" in cmd and "sess" in cmd
        assert "--run-id" in cmd and "rid9" in cmd
        assert captured["cwd"] == str(tmp_path)

    def test_artifacts_written_to_session_dir(self, tmp_path, monkeypatch):
        import yuleosh.engine.subprocess_executor as spe

        # 防御 test_api.py 模块级 setdefault("OSH_HOME", repo根) 的存量泄漏：
        # _resolve_session_dir 优先读 OSH_HOME，泄漏时 artifacts.json 会写到别处。
        monkeypatch.delenv("OSH_HOME", raising=False)
        monkeypatch.setattr(spe.subprocess, "run", lambda *a, **kw: self._fake_proc())
        _run_step_in_subprocess(
            {"step_id": "s1"}, str(tmp_path), False, None,
            session_name="sess", run_id="ridA", artifacts={"k": "/v"},
        )
        af = tmp_path / ".osh" / "sessions" / "ridA" / "artifacts.json"
        assert json.loads(af.read_text(encoding="utf-8")) == {"k": "/v"}

    def test_artifacts_write_oserror_warns(self, tmp_path, monkeypatch):
        import yuleosh.engine.subprocess_executor as spe

        # 用文件占位 session 目录 → mkdir 抛 FileExistsError(OSError)
        blocker = tmp_path / ".osh" / "sessions" / "ridB"
        blocker.parent.mkdir(parents=True)
        blocker.write_text("file", encoding="utf-8")
        monkeypatch.setattr(spe.subprocess, "run", lambda *a, **kw: self._fake_proc())
        result = _run_step_in_subprocess(
            {"step_id": "s1"}, str(tmp_path), False, None,
            session_name="sess", run_id="ridB", artifacts={"k": "/v"},
        )
        # OSError 被吞掉（仅 warning），子进程结果照常解析
        assert result.verdict == "failed"  # 无 stdout → 无输出失败


# ===========================================================================
# 4. ci/sync_check.py — 未覆盖分支
# ===========================================================================


class TestSyncCheckGitFallbacks:
    def test_git_diff_nonzero_falls_back_to_status(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                SimpleNamespace(returncode=1, stdout="", stderr=""),
                SimpleNamespace(returncode=0, stdout=" M staged.py\n", stderr=""),
            ]
            files = get_changed_files(str(tmp_path))
            assert files == ["staged.py"]

    def test_status_skips_single_part_line(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                SimpleNamespace(returncode=1, stdout="", stderr=""),
                SimpleNamespace(returncode=0, stdout=" M a.py\n??\n", stderr=""),
            ]
            files = get_changed_files(str(tmp_path))
            assert files == ["a.py"]

    def test_both_commands_fail_returns_empty(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                SimpleNamespace(returncode=1, stdout="", stderr=""),
                SimpleNamespace(returncode=1, stdout="", stderr=""),
            ]
            assert get_changed_files(str(tmp_path)) == []


class TestSyncCheckRunBranches:
    def _gate(self, tmp_path, body):
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / ".sync-gate.yaml").write_text(body, encoding="utf-8")

    def test_rule_not_matching_changed_file(self, tmp_path):
        """code_path 不匹配任何变更文件 → 跳过该规则。"""
        self._gate(
            tmp_path,
            "tracking:\n"
            "  - code_path: \"src/other.c\"\n"
            "    docs: [\"docs/api.md\"]\n"
            "    reason: \"r\"\n",
        )
        with patch(
            "yuleosh.ci.sync_check.get_changed_files",
            return_value=["src/main.c"],
        ):
            result = run_sync_check(str(tmp_path))
        assert result["status"] == "passed"
        assert result["rule_results"] == []

    def test_stale_doc_gives_warning(self, tmp_path):
        """文档存在但超过 30 天未更新 → warning 状态。"""
        self._gate(
            tmp_path,
            "tracking:\n"
            "  - code_path: \"src/main.c\"\n"
            "    docs: [\"docs/api.md\"]\n"
            "    reason: \"r\"\n",
        )
        api = tmp_path / "docs" / "api.md"
        api.write_text("# API", encoding="utf-8")
        old = 31 * 86400
        import os
        import time

        os.utime(str(api), (time.time() - old, time.time() - old))
        with patch(
            "yuleosh.ci.sync_check.get_changed_files",
            return_value=["src/main.c"],
        ):
            result = run_sync_check(str(tmp_path))
        assert result["status"] == "warning"
        assert "warning(s)" in result["summary"]
        assert result["rule_results"][0]["severity"] == "warning"

    def test_doc_missing_is_failure(self, tmp_path):
        self._gate(
            tmp_path,
            "tracking:\n"
            "  - code_path: \"src/main.c\"\n"
            "    docs: [\"docs/api.md\"]\n"
            "    reason: \"r\"\n",
        )
        with patch(
            "yuleosh.ci.sync_check.get_changed_files",
            return_value=["src/main.c"],
        ):
            result = run_sync_check(str(tmp_path))
        assert result["status"] == "failed"
        assert result["summary"].startswith("Sync gate FAILED")


class TestSyncCheckSchema:
    def test_yaml_doc_not_a_mapping(self, tmp_path):
        """YAML 文档是列表 → error 'Expected a YAML mapping'。"""
        arch = tmp_path / "docs" / "architecture"
        arch.mkdir(parents=True)
        (arch / "list.yaml").write_text("- a\n- b\n", encoding="utf-8")
        findings = validate_doc_yaml_schema(str(tmp_path))
        errs = [
            f for f in findings
            if f.get("rule") == "schema-architecture" and f.get("severity") == "error"
        ]
        assert any("Expected a YAML mapping" in f.get("message", "") for f in errs)


class TestSyncCheckGateStatus:
    def test_gate_warning_status(self, tmp_path):
        """tracking warning（无规则）+ schema 无 error → 整体 warning。"""
        result = run_sync_check_gate(str(tmp_path))
        assert result["status"] == "warning"
        assert "tracking_results" in result

    def test_gate_passed_status(self, tmp_path):
        """tracking passed + schema 仅 info → 整体 passed。"""
        docs = tmp_path / "docs"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / ".sync-gate.yaml").write_text(
            "tracking:\n"
            "  - code_path: \"src/main.c\"\n"
            "    docs: [\"docs/api.md\"]\n"
            "    reason: \"r\"\n",
            encoding="utf-8",
        )
        (docs / "api.md").write_text("# API", encoding="utf-8")
        arch = tmp_path / "docs" / "architecture"
        arch.mkdir(parents=True)
        (arch / "m.yaml").write_text(
            "module_name: m\nversion: '1.0'\nlast_updated: '2026-01-01'\ncode_path: src/\n",
            encoding="utf-8",
        )
        with patch(
            "yuleosh.ci.sync_check.get_changed_files",
            return_value=["src/main.c"],
        ):
            result = run_sync_check_gate(str(tmp_path))
        assert result["status"] == "passed"


class TestPrintSyncResultVariants:
    def test_print_failed_with_errors_and_schema(self, capsys):
        result = {
            "status": "failed",
            "generated_at": "2026-08-11T00:00:00",
            "tracking_results": {
                "changed_files": ["src/a.c"],
                "rule_results": [
                    {
                        "rule_id": "src/a.c → docs/a.md",
                        "severity": "error",
                        "reason": "r",
                        "message": "Document does not exist",
                        "matched_files": ["src/a.c"],
                    }
                ],
            },
            "schema_results": [
                {"rule": "schema-architecture", "severity": "error",
                 "message": "Missing required field(s): version", "file": "x.yaml"},
                {"rule": "schema-interface", "severity": "warning",
                 "message": "w", "file": "i.yaml"},
                {"rule": "schema-requirement", "severity": "info", "message": "i"},
            ],
            "_evidence_path": "/tmp/evidence.json",
        }
        print_sync_result(result)
        out = capsys.readouterr().out
        assert "❌" in out
        assert "[ERROR]" in out
        assert "[WARNING]" in out
        assert "1 schema error(s)" in out
        assert "Evidence saved" in out
        assert "← src/a.c" in out

    def test_print_warning_status(self, capsys):
        result = {
            "status": "warning",
            "tracking_results": {
                "changed_files": [],
                "rule_results": [
                    {"rule_id": "r1", "severity": "warning",
                     "reason": "x", "message": "stale"}
                ],
            },
            "schema_results": [],
        }
        print_sync_result(result)
        out = capsys.readouterr().out
        assert "⚠️" in out

    def test_print_passed_no_rules_no_schema(self, capsys):
        result = {
            "status": "passed",
            "tracking_results": {"changed_files": [], "rule_results": []},
            "schema_results": [],
        }
        print_sync_result(result)
        out = capsys.readouterr().out
        assert "✅" in out
        assert "No schema validation issues" in out


# ===========================================================================
# 5. autosar/parser.py — 未覆盖分支
# ===========================================================================


class TestAutosarHelpers:
    def test_ns_wraps_tag(self):
        assert _ns("SHORT-NAME") == "{http://autosar.org/schema/r4.0}SHORT-NAME"

    def test_safe_tag_returns_tag(self):
        parser = ARXMLParser()
        assert parser._safe_tag("TAG") == "TAG"

    def test_has_ns_uuid_only(self):
        root = ET.fromstring('<AUTOSAR UUID="abc-123"><X/></AUTOSAR>')
        assert ARXMLParser()._has_ns(root) is True

    def test_has_ns_neither(self):
        root = ET.fromstring("<AUTOSAR><X/></AUTOSAR>")
        assert ARXMLParser()._has_ns(root) is False

    def test_getattr_plain_attr(self):
        elem = ET.fromstring('<X UUID="plain-uuid"/>')
        assert _getattr(elem, "UUID") == "plain-uuid"

    def test_getattr_default(self):
        elem = ET.fromstring("<X/>")
        assert _getattr(elem, "UUID", default="dflt") == "dflt"

    def test_local_strips_namespace(self):
        assert _local("{http://autosar.org/schema/r4.0}SHORT-NAME") == "SHORT-NAME"
        assert _local("PLAIN") == "PLAIN"

    def test_extract_ref_empty_and_whitespace(self):
        assert ARXMLParser._extract_ref_name("") == ""
        assert ARXMLParser._extract_ref_name("/pkg/ Port ") == "Port"


class TestAutosarParseBranches:
    def test_swc_directly_in_package(self, tmp_path):
        """SWC 直接挂在 AR-PACKAGE 下（无 ELEMENTS 包装）。"""
        arxml = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="http://autosar.org/schema/r4.0">
  <AR-PACKAGE>
    <SHORT-NAME>Pkg</SHORT-NAME>
    <APPLICATION-SW-COMPONENT-TYPE>
      <SHORT-NAME>DirectSwc</SHORT-NAME>
    </APPLICATION-SW-COMPONENT-TYPE>
  </AR-PACKAGE>
</AUTOSAR>"""
        f = tmp_path / "direct.arxml"
        f.write_text(arxml, encoding="utf-8")
        swcs = ARXMLParser().parse_swc(str(f))
        assert len(swcs) == 1
        assert swcs[0].short_name == "DirectSwc"
        assert swcs[0].package_refs == ["Pkg"]

    def test_port_direction_from_tag(self):
        """未传 direction → 从 tag 推断 R=in / P=out。"""
        parser = ARXMLParser()
        r = ET.fromstring("<R-PORT-PROTOTYPE><SHORT-NAME>Rx</SHORT-NAME></R-PORT-PROTOTYPE>")
        p = ET.fromstring("<P-PORT-PROTOTYPE><SHORT-NAME>Tx</SHORT-NAME></P-PORT-PROTOTYPE>")
        assert parser._parse_port(r).direction == "in"
        assert parser._parse_port(p).direction == "out"

    def test_port_kind_detection_variants(self):
        """interface ref 包含 ClientServer/ModeSwitch/Trigger → kind 推断。"""
        parser = ARXMLParser()
        for word, expected in [
            ("ClientServerInterface", "ClientServer"),
            ("ModeSwitchInterface", "ModeSwitch"),
            ("TriggerInterface", "Trigger"),
        ]:
            elem = ET.fromstring(
                f"<P-PORT-PROTOTYPE><SHORT-NAME>P</SHORT-NAME>"
                f"<PROVIDED-INTERFACE><PORT-INTERFACE-REF>/pkg/{word}</PORT-INTERFACE-REF>"
                f"</PROVIDED-INTERFACE></P-PORT-PROTOTYPE>"
            )
            port = parser._parse_port(elem)
            assert port.kind == expected, word

    def test_port_interface_ref_empty_text(self):
        """PORT-INTERFACE-REF 文本为空 → interface_ref 保持空。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<R-PORT-PROTOTYPE><SHORT-NAME>P</SHORT-NAME>"
            "<REQUIRED-INTERFACE><PORT-INTERFACE-REF></PORT-INTERFACE-REF>"
            "</REQUIRED-INTERFACE></R-PORT-PROTOTYPE>"
        )
        port = parser._parse_port(elem)
        assert port.interface_ref == ""

    def test_required_com_specs_parsed(self):
        """REQUIRED-COM-SPECS → ComSpec properties + INIT-VALUE。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<R-PORT-PROTOTYPE><SHORT-NAME>P</SHORT-NAME>"
            "<REQUIRED-COM-SPECS>"
            "<DATA-ELEMENT-REF>/pkg/Signal</DATA-ELEMENT-REF>"
            "<DATA-ELEMENT-INIT-VALUE>42</DATA-ELEMENT-INIT-VALUE>"
            "</REQUIRED-COM-SPECS>"
            "<INIT-VALUE>7</INIT-VALUE>"
            "</R-PORT-PROTOTYPE>"
        )
        port = parser._parse_port(elem)
        assert port.com_spec is not None
        assert port.com_spec.properties.get("DATA-ELEMENT-INIT-VALUE") == "42"
        assert port.com_spec.init_value == "7"

    def test_provided_com_specs_parsed(self):
        """PROVIDED-COM-SPECS → ComSpec properties。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<P-PORT-PROTOTYPE><SHORT-NAME>P</SHORT-NAME>"
            "<PROVIDED-COM-SPECS><DATA-ELEMENT-REF>/pkg/S</DATA-ELEMENT-REF>"
            "<QUEUE-LENGTH>4</QUEUE-LENGTH></PROVIDED-COM-SPECS>"
            "</P-PORT-PROTOTYPE>"
        )
        port = parser._parse_port(elem)
        assert port.com_spec is not None
        assert port.com_spec.properties.get("QUEUE-LENGTH") == "4"

    def test_internal_behavior_mode_machine(self):
        """MODE-MACHINE → mode_machine_name；无 SHORT-NAME 的排他区被跳过。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<SWC-INTERNAL-BEHAVIOR><SHORT-NAME>IB</SHORT-NAME>"
            "<EXCLUSIVE-AREA></EXCLUSIVE-AREA>"
            "<EXCLUSIVE-AREA><SHORT-NAME>Area1</SHORT-NAME></EXCLUSIVE-AREA>"
            "<MODE-MACHINE><SHORT-NAME>ModeM</SHORT-NAME></MODE-MACHINE>"
            "</SWC-INTERNAL-BEHAVIOR>"
        )
        ib = parser._parse_internal_behavior(elem)
        assert ib.mode_machine_name == "ModeM"
        assert ib.exclusive_areas == ["Area1"]

    def test_runnable_cbic_true_and_bad_msi(self):
        """CAN-BE-INVOKED-CONCURRENTLY=TRUE；MINIMUM-START-INTERVAL 非法 → 忽略。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<RUNNABLE-ENTITY><SHORT-NAME>R</SHORT-NAME>"
            "<CAN-BE-INVOKED-CONCURRENTLY>TRUE</CAN-BE-INVOKED-CONCURRENTLY>"
            "<MINIMUM-START-INTERVAL>abc</MINIMUM-START-INTERVAL>"
            "</RUNNABLE-ENTITY>"
        )
        r = parser._parse_runnable(elem)
        assert r.can_be_invoked_concurrently is True
        assert r.minimum_start_interval_ms is None

    def test_runnable_port_refs_and_server_call(self):
        """DATA-READ/WRITE-ACCESS 里的 PORT-PROTOTYPE-REF + SERVER-CALL-POINT。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<RUNNABLE-ENTITY><SHORT-NAME>R</SHORT-NAME>"
            "<DATA-READ-ACCESS><PORT-PROTOTYPE-REF>/pkg/SWC/RxPort</PORT-PROTOTYPE-REF></DATA-READ-ACCESS>"
            "<DATA-WRITE-ACCESS><PORT-PROTOTYPE-REF>/pkg/SWC/TxPort</PORT-PROTOTYPE-REF></DATA-WRITE-ACCESS>"
            "<SERVER-CALL-POINT><SHORT-NAME>CallGet</SHORT-NAME></SERVER-CALL-POINT>"
            "</RUNNABLE-ENTITY>"
        )
        r = parser._parse_runnable(elem)
        assert "RxPort" in r.data_read_access
        assert "TxPort" in r.data_write_access
        assert r.server_call_points == ["CallGet"]

    def test_runnable_empty_target_refs_skipped(self):
        """TARGET 文本为空 → 跳过 append。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<RUNNABLE-ENTITY><SHORT-NAME>R</SHORT-NAME>"
            "<DATA-READ-ACCESS><TARGET></TARGET></DATA-READ-ACCESS>"
            "<DATA-WRITE-ACCESS><TARGET></TARGET></DATA-WRITE-ACCESS>"
            "</RUNNABLE-ENTITY>"
        )
        r = parser._parse_runnable(elem)
        assert r.data_read_access == []
        assert r.data_write_access == []

    def test_runnable_mode_switch_event(self):
        """MODE-SWITCH-EVENT → mode_switch_events。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<RUNNABLE-ENTITY><SHORT-NAME>R</SHORT-NAME>"
            "<EVENT><MODE-SWITCH-EVENT>"
            "<TARGET>/pkg/IB/EventMode</TARGET>"
            "</MODE-SWITCH-EVENT></EVENT>"
            "</RUNNABLE-ENTITY>"
        )
        r = parser._parse_runnable(elem)
        assert "EventMode" in r.mode_switch_events

    def test_runnable_level_timing_event_legacy(self):
        """老式 ARXML：TIMING-EVENT 直接在 runnable 层。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<RUNNABLE-ENTITY><SHORT-NAME>R</SHORT-NAME>"
            "<TIMING-EVENT><PERIOD>0.02</PERIOD></TIMING-EVENT>"
            "</RUNNABLE-ENTITY>"
        )
        r = parser._parse_runnable(elem)
        assert r.period_ms == pytest.approx(20.0)
        assert r.timing_event == "TimingEvent_20ms"

    def test_runnable_invalid_period_does_not_crash(self):
        """非法 PERIOD → 不抛异常、不设置 timing_event（防 int(None) 回归）。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<RUNNABLE-ENTITY><SHORT-NAME>R</SHORT-NAME>"
            "<EVENT><TIMING-EVENT><PERIOD>not-a-number</PERIOD></TIMING-EVENT></EVENT>"
            "</RUNNABLE-ENTITY>"
        )
        r = parser._parse_runnable(elem)
        assert r.period_ms is None
        assert r.timing_event is None

    def test_data_received_event_empty_target(self):
        """DATA-RECEIVED-EVENT 的 TARGET 为空 → 跳过。"""
        parser = ARXMLParser()
        elem = ET.fromstring(
            "<RUNNABLE-ENTITY><SHORT-NAME>R</SHORT-NAME>"
            "<EVENT><DATA-RECEIVED-EVENT><TARGET></TARGET></DATA-RECEIVED-EVENT></EVENT>"
            "</RUNNABLE-ENTITY>"
        )
        r = parser._parse_runnable(elem)
        assert r.data_received_events == []


class TestAutosarToMarkdown:
    def test_markdown_full_and_empty_swc(self):
        from yuleosh.autosar.models import PortPrototype, RunnableEntity, SWCComponent

        full = SWCComponent(short_name="Full", component_type="APPLICATION-SW-COMPONENT-TYPE")
        full.ports.append(PortPrototype(short_name="P1", direction="in", kind="SenderReceiver"))
        r = RunnableEntity(short_name="R1", symbol="R1", period_ms=10.0,
                           can_be_invoked_concurrently=True)
        r.timing_event = "TimingEvent_10ms"
        full.runnables.append(r)
        empty = SWCComponent(short_name="Empty")
        md = ARXMLParser().to_markdown([full, empty])
        assert "## SWC: Full" in md
        assert "| P1 | in | SenderReceiver |  |" in md
        assert "| R1 | R1 | 10.0 | Yes | TimingEvent_10ms |" in md
        assert "## SWC: Empty" in md

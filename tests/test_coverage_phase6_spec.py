"""Phase 6 coverage boost — Spec 域 5 个 0% 覆盖文件。

Target modules (Phase 6 baseline, 2026-08-10, 均为 0.0%):
  - src/yuleosh/pipeline/step_handlers/spec.py    (92 行)  → step_spec_check 全分支 + _spec_validator_env
  - src/yuleosh/api/spec.py                      (98 行)  → handle_spec/_validate/_diff 全分支
  - src/yuleosh/pipeline/stages/spec.py         (240 行)  → spec 缓存/mtime/需求与场景解析/Hermes JSON
  - src/yuleosh/loop_engine/spec_delta_gen.py   (278 行)  → SpecDelta dataclass + Generator 全方法
  - src/yuleosh/knowledge_graph/spec_diff.py    (349 行)  → SHALL 提取/diff/store 应用/git 对比

风格：直测函数/分支，外部命令（subprocess）全部 mock，文件 IO 全部落在 tmp_path，
JWT 装饰器通过 sanctioned bypass（current_user kwarg）穿透。
"""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from yuleosh.knowledge_graph import spec_diff as kg_spec_diff_mod
from yuleosh.loop_engine.spec_delta_gen import ChangeType, SpecDelta, SpecDeltaGenerator
from yuleosh.pipeline.session import PipelineStepError
from yuleosh.pipeline.stages import spec as stages_spec_mod
from yuleosh.pipeline.step_handlers import spec as step_spec_mod

# =====================================================================
# pipeline/step_handlers/spec.py — OpenSpec 合规检查 step handler
# =====================================================================


class TestStepHandlerSpec:
    """step_spec_check 全分支 + _spec_validator_env 的 PYTHONPATH 注入。"""

    def _make_session(self, tmp_path):
        session = mock.Mock()
        session.spec_path = str(tmp_path / "specs" / "brake.spec.md")
        session.session_dir = tmp_path
        return session

    def _run(self, result, tmp_path):
        session = self._make_session(tmp_path)
        with mock.patch.object(step_spec_mod.subprocess, "run", return_value=result) as m:
            out = step_spec_mod.step_spec_check(session)
        return out, m

    def test_success_writes_stdout_and_returns_path(self, tmp_path):
        """returncode=0 + 合法 JSON + error_count=0 → 写 spec-check.json 并返回路径。

        契约完整性检查 (contracts_check, 2026-08-16 方案 A) 是独立模块
        (test_spec_contracts.py 覆盖)；此处 mock 其通过结果，只验证
        step_spec_check 的 stdout 写入/返回路径/subprocess 契约。
        """
        payload = json.dumps({"error_count": 0, "issues": [], "coverage": {"score": 92.5}})
        result = mock.Mock(returncode=0, stdout=payload, stderr="")
        session = self._make_session(tmp_path)
        cc_passed = {
            "validation": {"passed": True, "missing": [], "details": {}},
            "contracts": {},
        }
        with mock.patch.object(step_spec_mod.subprocess, "run", return_value=result) as m, \
             mock.patch.object(step_spec_mod, "contracts_check", return_value=cc_passed) as m_cc:
            out = step_spec_mod.step_spec_check(session)

        assert out == str(tmp_path / "spec-check.json")
        assert (tmp_path / "spec-check.json").read_text() == payload
        m_cc.assert_called_once()
        # subprocess 调用契约：python -m yuleosh.spec.validate <path> --json + env 注入
        args, kwargs = m.call_args
        assert args[0][:3] == [sys.executable, "-m", "yuleosh.spec.validate"]
        assert args[0][-1] == "--json"
        assert kwargs["timeout"] == 60
        assert kwargs["capture_output"] is True
        assert "PYTHONPATH" in kwargs["env"]
        assert kwargs["env"]["PYTHONPATH"]  # 非空

    def test_nonzero_exit_raises_with_stderr(self, tmp_path):
        """returncode!=0 → PipelineStepError，且 stdout 为空时文件写入 stderr。"""
        result = mock.Mock(returncode=1, stdout="", stderr="boom: invalid spec")
        with pytest.raises(PipelineStepError, match="Spec validation failed"):
            self._run(result, tmp_path)
        assert (tmp_path / "spec-check.json").read_text() == "boom: invalid spec"

    def test_nonzero_exit_uses_stdout_fallback(self, tmp_path):
        """returncode!=0 且 stderr 为空 → 错误信息回退到 stdout。"""
        result = mock.Mock(returncode=2, stdout="stdout-err", stderr="")
        with pytest.raises(PipelineStepError, match="stdout-err"):
            self._run(result, tmp_path)

    def test_non_json_stdout_raises(self, tmp_path):
        """returncode=0 但 stdout 不是 JSON → PipelineStepError（含 raw 预览）。"""
        result = mock.Mock(returncode=0, stdout="not json at all", stderr="")
        with pytest.raises(PipelineStepError, match="not valid JSON"):
            self._run(result, tmp_path)

    def test_non_json_empty_output_raises(self, tmp_path):
        """stdout/stderr 均为空 → 非 JSON 错误使用 '(empty output)' 占位。"""
        result = mock.Mock(returncode=0, stdout="", stderr="")
        with pytest.raises(PipelineStepError, match="not valid JSON") as excinfo:
            self._run(result, tmp_path)
        assert "(empty output)" in str(excinfo.value)

    def test_error_count_gt_zero_raises_with_issues(self, tmp_path):
        """JSON 中 error_count>0 → 汇总所有 ERROR severity 的 issue message。"""
        payload = json.dumps({
            "error_count": 2,
            "issues": [
                {"message": "missing SHALL", "severity": "ERROR"},
                {"message": "bad id", "severity": "ERROR"},
                {"message": "warn only", "severity": "WARN"},
            ],
        })
        result = mock.Mock(returncode=0, stdout=payload, stderr="")
        with pytest.raises(PipelineStepError, match=r"Spec has 2 error\(s\): missing SHALL; bad id"):
            self._run(result, tmp_path)

    def test_timeout_expired_raises(self, tmp_path):
        """subprocess.run 抛 TimeoutExpired → 'Spec validation timed out'。"""
        session = self._make_session(tmp_path)
        with mock.patch.object(
            step_spec_mod.subprocess, "run",
            side_effect=subprocess.TimeoutExpired("cmd", 60),
        ), pytest.raises(PipelineStepError, match="timed out"):
            step_spec_mod.step_spec_check(session)

    def test_called_process_error_raises(self, tmp_path):
        """subprocess.run 抛 CalledProcessError → 子进程失败包装。"""
        session = self._make_session(tmp_path)
        with mock.patch.object(
            step_spec_mod.subprocess, "run",
            side_effect=subprocess.CalledProcessError(1, "cmd"),
        ), pytest.raises(PipelineStepError, match="subprocess failed"):
            step_spec_mod.step_spec_check(session)

    def test_unexpected_exception_raises(self, tmp_path):
        """其他任意异常 → 'Spec validation unexpected error'。"""
        session = self._make_session(tmp_path)
        with mock.patch.object(step_spec_mod.subprocess, "run", side_effect=ValueError("boom")), \
                pytest.raises(PipelineStepError, match="unexpected error"):
            step_spec_mod.step_spec_check(session)

    def test_pipeline_step_error_passthrough(self, tmp_path):
        """PipelineStepError 原样透传（except PipelineStepError: raise）。"""
        session = self._make_session(tmp_path)
        with mock.patch.object(
            step_spec_mod.subprocess, "run",
            side_effect=PipelineStepError("inner"),
        ), pytest.raises(PipelineStepError, match="inner"):
            step_spec_mod.step_spec_check(session)

    # ---- _spec_validator_env ----

    def test_validator_env_injects_pythonpath(self):
        """已有 PYTHONPATH 时：pkg_root 置首并保留原值。"""
        import yuleosh

        pkg_root = str(Path(yuleosh.__file__).resolve().parent.parent)
        with mock.patch.object(step_spec_mod.os, "environ", {"PYTHONPATH": "/existing", "HOME": "/h"}):
            env = step_spec_mod._spec_validator_env()
        parts = env["PYTHONPATH"].split(os.pathsep)
        assert parts[0] == pkg_root
        assert "/existing" in parts
        assert env["HOME"] == "/h"

    def test_validator_env_without_pythonpath(self):
        """无 PYTHONPATH 时：只注入 pkg_root。"""
        import yuleosh

        pkg_root = str(Path(yuleosh.__file__).resolve().parent.parent)
        with mock.patch.object(step_spec_mod.os, "environ", {"HOME": "/h"}):
            env = step_spec_mod._spec_validator_env()
        assert env["PYTHONPATH"] == pkg_root


# =====================================================================
# api/spec.py — OpenSpec validate / diff 端点
# =====================================================================


class TestApiSpec:
    """handle_spec / _validate / _diff：认证装饰器用 current_user kwarg 穿透。"""

    @staticmethod
    def _handle(method, path_tail, body, query=None):
        from yuleosh.api.spec import handle_spec

        return handle_spec(
            method=method,
            path_tail=path_tail,
            body=body,
            query=query or {},
            current_user={"user_id": 1, "org_id": 1, "email": "t@example.com", "role": "admin"},
        )

    def test_unknown_resource_404(self):
        """未知子资源 → 404。"""
        payload, status = self._handle("GET", "unknown", {})
        assert status == 404
        assert payload == {"ok": False, "error": "Unknown spec resource: unknown"}

    def test_validate_wrong_method_405(self):
        """validate 非 POST → 405。"""
        payload, status = self._handle("GET", "validate", {})
        assert status == 405
        assert payload["error"] == "Use POST to validate"

    def test_validate_missing_path_400(self):
        """validate 缺 'path' → 400。"""
        payload, status = self._handle("POST", "validate", {})
        assert status == 400
        assert payload["error"] == "'path' is required"

    def test_validate_relative_traversal_403(self, tmp_path):
        """相对路径 '../' 逃逸项目根 → 403 守卫。"""
        with mock.patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            payload, status = self._handle("POST", "validate", {"path": "../evil.md"})
        assert status == 403
        assert "within project directory" in payload["error"]

    def test_validate_absolute_outside_403(self, tmp_path):
        """绝对路径指向项目根之外 → 403 守卫。"""
        with mock.patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            payload, status = self._handle("POST", "validate", {"path": "/etc/passwd"})
        assert status == 403
        assert "within project directory" in payload["error"]

    def test_validate_file_not_found(self, tmp_path):
        """项目根内但文件不存在 → 400。"""
        with mock.patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            payload, status = self._handle("POST", "validate", {"path": "specs/missing.md"})
        assert status == 400
        assert "Spec file not found" in payload["error"]

    def test_validate_success(self, tmp_path):
        """validate 成功：parse_spec/validate_spec/_compute_coverage 被调用并汇总结果。"""
        spec_file = tmp_path / "specs" / "brake.spec.md"
        spec_file.parent.mkdir(parents=True)
        spec_file.write_text("# spec\n", encoding="utf-8")

        doc = mock.Mock()
        doc.requirements = [mock.Mock(name="R1", shall=["s1", "s2"]), mock.Mock(name="R2", shall=[])]
        doc.scenarios = [mock.Mock(name="SC1")]
        issues = [{"severity": "ERROR", "message": "no reason"}]

        with mock.patch("yuleosh.api.OSH_HOME", str(tmp_path)), \
                mock.patch("yuleosh.spec.validate.parse_spec", return_value=doc) as m_parse, \
                mock.patch("yuleosh.spec.validate.validate_spec", return_value=issues), \
                mock.patch("yuleosh.spec.validate._compute_coverage", return_value={"score": 42.0}):
            payload, status = self._handle("POST", "validate", {"path": "specs/brake.spec.md"})

        assert status == 200
        assert payload["ok"] is True
        data = payload["data"]
        assert data["file"].endswith("brake.spec.md")
        assert data["requirements"] == 2
        assert data["scenarios"] == 1
        assert data["total_shall"] == 2
        assert data["issue_count"] == 1
        assert data["error_count"] == 1
        assert data["coverage"] == {"score": 42.0}
        m_parse.assert_called_once_with(str(spec_file))

    def test_diff_wrong_method_405(self):
        """diff 非 POST → 405。"""
        payload, status = self._handle("GET", "diff", {})
        assert status == 405
        assert payload["error"] == "Use POST to diff"

    def test_diff_missing_paths_400(self):
        """diff 缺 old/new → 400。"""
        payload, status = self._handle("POST", "diff", {"old": "a.md"})
        assert status == 400
        assert payload["error"] == "'old' and 'new' paths are required"

    def test_diff_old_not_found(self, tmp_path):
        """old 文件不存在 → 400。"""
        new_file = tmp_path / "new.md"
        new_file.write_text("# n", encoding="utf-8")
        with mock.patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            payload, status = self._handle("POST", "diff", {"old": "old.md", "new": "new.md"})
        assert status == 400
        assert payload["error"].startswith("Old spec not found")

    def test_diff_new_not_found(self, tmp_path):
        """new 文件不存在 → 400。"""
        old_file = tmp_path / "old.md"
        old_file.write_text("# o", encoding="utf-8")
        with mock.patch("yuleosh.api.OSH_HOME", str(tmp_path)):
            payload, status = self._handle("POST", "diff", {"old": "old.md", "new": "new.md"})
        assert status == 400
        assert payload["error"].startswith("New spec not found")

    def test_diff_success_relative_paths(self, tmp_path):
        """相对路径 diff 成功：相对 OSH_HOME 解析并返回 diff_specs 结果。"""
        (tmp_path / "old.md").write_text("# o", encoding="utf-8")
        (tmp_path / "new.md").write_text("# n", encoding="utf-8")
        delta = {"added": ["RS-002"], "removed": [], "modified": []}
        with mock.patch("yuleosh.api.OSH_HOME", str(tmp_path)), \
                mock.patch("yuleosh.spec.validate.diff_specs", return_value=delta) as m_diff:
            payload, status = self._handle("POST", "diff", {"old": "old.md", "new": "new.md"})
        assert status == 200
        assert payload == {"ok": True, "data": delta}
        args = m_diff.call_args.args
        assert args[0] == str((tmp_path / "old.md").resolve())
        assert args[1] == str((tmp_path / "new.md").resolve())

    def test_diff_success_absolute_paths(self, tmp_path):
        """绝对路径 diff 成功：不经过 OSH_HOME 拼接。"""
        old_file = tmp_path / "old.md"
        new_file = tmp_path / "new.md"
        old_file.write_text("# o", encoding="utf-8")
        new_file.write_text("# n", encoding="utf-8")
        with mock.patch("yuleosh.spec.validate.diff_specs", return_value={"added": []}) as m_diff:
            payload, status = self._handle(
                "POST", "diff", {"old": str(old_file), "new": str(new_file)}
            )
        assert status == 200
        assert payload["ok"] is True
        m_diff.assert_called_once_with(str(old_file), str(new_file))


# =====================================================================
# pipeline/stages/spec.py — spec 解析与缓存
# =====================================================================


class TestPipelineStagesSpec:
    """_get_spec_mtime / _parse_spec 缓存 / _parse_requirements / _parse_scenarios /
    _try_parse_hermes_json 全分支。"""

    def test_module_import_failure_falls_back_to_none(self):
        """store 导入失败分支：sys.modules['store']=None 强制 ImportError → _store=None。"""
        with mock.patch.dict(sys.modules, {"store": None}):
            importlib.reload(stages_spec_mod)
        assert stages_spec_mod._store is None

    def test_get_spec_mtime_real_file(self, tmp_path):
        """存在文件 → 返回真实 mtime（>0）。"""
        f = tmp_path / "spec.md"
        f.write_text("# spec", encoding="utf-8")
        assert stages_spec_mod._get_spec_mtime(str(f)) > 0

    def test_get_spec_mtime_missing_file(self, tmp_path):
        """文件不存在（OSError）→ 返回 0.0。"""
        assert stages_spec_mod._get_spec_mtime(str(tmp_path / "nope.md")) == 0.0

    def test_parse_spec_cache_hit(self, tmp_path):
        """缓存命中：直接返回缓存结果，不触发重新解析。"""
        cached = {"requirements": [{"name": "R1"}], "scenarios": ["S1"]}
        store = mock.Mock()
        store.get_cached_spec_parse.return_value = cached
        with mock.patch.object(stages_spec_mod, "_store", store):
            result = stages_spec_mod._parse_spec(str(tmp_path / "spec.md"))
        assert result is cached
        store.cache_spec_parse.assert_not_called()

    def test_parse_spec_cache_miss_reparses(self, tmp_path):
        """缓存未命中：重新解析并写入缓存。"""
        store = mock.Mock()
        store.get_cached_spec_parse.return_value = None
        with mock.patch.object(stages_spec_mod, "_store", store), \
                mock.patch.object(stages_spec_mod, "_parse_requirements", return_value=[{"name": "R1"}]), \
                mock.patch.object(stages_spec_mod, "_parse_scenarios", return_value=["S1"]):
            result = stages_spec_mod._parse_spec(str(tmp_path / "spec.md"))
        assert result == {"requirements": [{"name": "R1"}], "scenarios": ["S1"]}
        store.cache_spec_parse.assert_called_once()

    def test_parse_spec_cache_read_error_reparses(self, tmp_path):
        """缓存读取抛异常 → 警告后重新解析（非致命）。"""
        store = mock.Mock()
        store.get_cached_spec_parse.side_effect = RuntimeError("db locked")
        with mock.patch.object(stages_spec_mod, "_store", store), \
                mock.patch.object(stages_spec_mod, "_parse_requirements", return_value=[]), \
                mock.patch.object(stages_spec_mod, "_parse_scenarios", return_value=[]):
            result = stages_spec_mod._parse_spec(str(tmp_path / "spec.md"))
        assert result["requirements"] == []
        store.cache_spec_parse.assert_called_once()

    def test_parse_spec_cache_write_error_non_fatal(self, tmp_path):
        """缓存写入抛异常 → 警告但仍返回解析结果。"""
        store = mock.Mock()
        store.get_cached_spec_parse.return_value = None
        store.cache_spec_parse.side_effect = RuntimeError("write fail")
        with mock.patch.object(stages_spec_mod, "_store", store), \
                mock.patch.object(stages_spec_mod, "_parse_requirements", return_value=[{"name": "R1"}]), \
                mock.patch.object(stages_spec_mod, "_parse_scenarios", return_value=[]):
            result = stages_spec_mod._parse_spec(str(tmp_path / "spec.md"))
        assert result["requirements"] == [{"name": "R1"}]

    def test_parse_spec_without_store(self, tmp_path):
        """_store 为 None → 跳过缓存直接解析。"""
        with mock.patch.object(stages_spec_mod, "_store", None), \
                mock.patch.object(stages_spec_mod, "_parse_requirements", return_value=[]), \
                mock.patch.object(stages_spec_mod, "_parse_scenarios", return_value=["GIVEN x"]):
            result = stages_spec_mod._parse_spec(str(tmp_path / "spec.md"))
        assert result == {"requirements": [], "scenarios": ["GIVEN x"]}

    # ---- _parse_requirements ----

    def test_parse_requirements_success(self, tmp_path):
        """解析 ### Req-* / OpenSpec SR-* 头 + SHALL/SHOULD 条目，遇非 Req 的 ### 节结束当前需求。

        2026-08-16 (a966991d): OpenSpec 风格头只取编号 (``SR-001``) 作为
        稳定契约 — 标题是展示文本, 编号才是下游引用/追溯的标识。
        """
        f = tmp_path / "spec.md"
        f.write_text(
            "### Req-001: First requirement\n"
            "- The system SHALL do X.\n"
            "- The system SHOULD do Y.\n"
            "- unrelated bullet\n"
            "### Scenario: Normal\n"
            "- GIVEN something\n"
            "### SR-002: Second requirement\n"
            "- The system SHALL do Z.\n",
            encoding="utf-8",
        )
        result = stages_spec_mod._parse_requirements(str(f))
        assert len(result) == 2
        assert result[0]["name"] == "Req-001"
        assert result[0]["shall_statements"] == ["- The system SHALL do X.", "- The system SHOULD do Y."]
        assert result[1]["name"] == "SR-002"
        assert result[1]["shall_statements"] == ["- The system SHALL do Z."]

    def test_parse_requirements_missing_file(self, tmp_path):
        """spec 文件不存在 → 返回空列表。"""
        assert stages_spec_mod._parse_requirements(str(tmp_path / "nope.md")) == []

    def test_parse_requirements_read_error(self, tmp_path):
        """read_text 抛异常 → 返回空列表（不向上抛）。"""
        f = tmp_path / "spec.md"
        f.write_text("# spec", encoding="utf-8")
        with mock.patch.object(stages_spec_mod.Path, "read_text", side_effect=OSError("boom")):
            assert stages_spec_mod._parse_requirements(str(f)) == []

    # ---- _parse_scenarios ----

    def test_parse_scenarios_success(self, tmp_path):
        """提取 ### GIVEN/WHEN/THEN 场景标题。"""
        f = tmp_path / "spec.md"
        f.write_text(
            "### GIVEN a valid system\n"
            "### WHEN the brake is pressed\n"
            "### THEN the light activates\n"
            "### OTHER heading\n",
            encoding="utf-8",
        )
        assert stages_spec_mod._parse_scenarios(str(f)) == [
            "GIVEN a valid system",
            "WHEN the brake is pressed",
            "THEN the light activates",
        ]

    def test_parse_scenarios_missing_file(self, tmp_path):
        """spec 文件不存在 → 返回空列表。"""
        assert stages_spec_mod._parse_scenarios(str(tmp_path / "nope.md")) == []

    def test_parse_scenarios_read_error(self, tmp_path):
        """read_text 抛异常 → 返回空列表。"""
        f = tmp_path / "spec.md"
        f.write_text("# spec", encoding="utf-8")
        with mock.patch.object(stages_spec_mod.Path, "read_text", side_effect=OSError("boom")):
            assert stages_spec_mod._parse_scenarios(str(f)) == []

    # ---- _try_parse_hermes_json ----

    def test_hermes_json_bare_valid(self):
        """纯 JSON 直接解析。"""
        assert stages_spec_mod._try_parse_hermes_json('{"session": "s1"}', "s1") == {"session": "s1"}

    def test_hermes_json_markdown_fence(self):
        """```json 代码围栏包裹的 JSON。"""
        raw = 'prefix\n```json\n{"a": 1}\n```\nsuffix'
        assert stages_spec_mod._try_parse_hermes_json(raw, "s") == {"a": 1}

    def test_hermes_json_plain_fence(self):
        """无语言标注的 ``` 围栏。"""
        raw = '```\n{"b": 2}\n```'
        assert stages_spec_mod._try_parse_hermes_json(raw, "s") == {"b": 2}

    def test_hermes_json_multiple_blocks_first_invalid(self):
        """多个代码块：第一个非法 JSON，回退到第二个。"""
        raw = '```json\nnot json\n```\n```json\n{"c": 3}\n```'
        assert stages_spec_mod._try_parse_hermes_json(raw, "s") == {"c": 3}

    def test_hermes_json_non_json_fence_then_brace(self):
        """非 JSON 语言围栏被跳过，随后用大括号匹配兜底解析。"""
        raw = '```python\nx = 1\n```\nthen {"d": 4}'
        assert stages_spec_mod._try_parse_hermes_json(raw, "s") == {"d": 4}

    def test_hermes_json_leading_text(self):
        """前导说明文字 + 尾部 JSON 块。"""
        raw = 'Explanation:\n{"e": 5}'
        assert stages_spec_mod._try_parse_hermes_json(raw, "s") == {"e": 5}

    def test_hermes_json_invalid_candidates_then_fallback(self):
        """大括号匹配：首个候选非法 → continue；后续候选仍非法 → 回退 retry。"""
        raw = '{"x": } and {"f": 6}'
        result = stages_spec_mod._try_parse_hermes_json(raw, "s")
        assert result["status"] == "retry"
        assert result["session"] == "s"

    def test_hermes_json_unclosed_braces_fallback(self):
        """花括号无法闭合（bare 非法 + 无围栏）→ 回退 retry 字典。"""
        result = stages_spec_mod._try_parse_hermes_json('{"g": ', "sess-1")
        assert result["status"] == "retry"
        assert result["session"] == "sess-1"
        assert result["_raw_llm_output"] == '{"g": '
        assert result["findings"][0]["severity"] == "major"
        assert result["finding_breakdown"] == {"critical": 0, "major": 1, "minor": 0, "info": 0}

    def test_hermes_json_garbage_fallback(self):
        """完全无 JSON → 回退 retry 字典（含原始输出）。"""
        result = stages_spec_mod._try_parse_hermes_json("no json here", "sess-2")
        assert result["status"] == "retry"
        assert result["session"] == "sess-2"
        assert "no json here" in result["_raw_llm_output"]


# =====================================================================
# loop_engine/spec_delta_gen.py — SpecDelta 数据类 + 生成器
# =====================================================================


class TestSpecDeltaGen:
    """ChangeType / SpecDelta dataclass / SpecDeltaGenerator 全方法。"""

    def test_change_type_values(self):
        assert ChangeType.MODIFIED.value == "modified"
        assert ChangeType.ADDED.value == "added"
        assert ChangeType.REMOVED.value == "removed"
        assert ChangeType.NEEDS_REVIEW.value == "needs_review"
        assert ChangeType("added") is ChangeType.ADDED

    def test_spec_delta_post_init_timestamp_and_coercion(self):
        """空 timestamp 自动填充；字符串 change_type 转枚举。"""
        d = SpecDelta(req_id="RS-001-01", change_type="modified")
        assert d.change_type is ChangeType.MODIFIED
        assert d.timestamp  # 非空即自动生成

    def test_spec_delta_invalid_change_type(self):
        """非法 change_type 字符串 → ValueError。"""
        with pytest.raises(ValueError):
            SpecDelta(req_id="R", change_type="bogus")

    def test_spec_delta_to_dict(self):
        d = SpecDelta(
            req_id="RS-001", change_type=ChangeType.ADDED, reason="why",
            attributed_test="t1", attributed_source="ci", previous_text="old",
            new_text="new", timestamp="2026-01-01T00:00:00+00:00",
            tags=["a"], evidence_ref="ev.md", metadata={"k": "v"},
        )
        dd = d.to_dict()
        assert dd["req_id"] == "RS-001"
        assert dd["change_type"] == "added"
        assert dd["attributed_test"] == "t1"
        assert dd["previous_text"] == "old"
        assert dd["tags"] == ["a"]
        assert dd["evidence_ref"] == "ev.md"
        assert dd["metadata"] == {"k": "v"}
        assert dd["generator_version"] == "2.5.0"

    def test_spec_delta_to_markdown_full(self):
        d = SpecDelta(
            req_id="RS-001-01", change_type=ChangeType.MODIFIED, reason="because",
            attributed_test="test_x", attributed_source="ci.failure",
            tags=["t1", "t2"], evidence_ref="evidence.md",
            previous_text="old text", new_text="new text", timestamp="TS",
        )
        md = d.to_markdown()
        assert md.startswith("### RS-001-01 [modified]")
        assert "- **原因**: because" in md
        assert "- **归因测试**: `test_x`" in md
        assert "- **来源**: ci.failure" in md
        assert "- **时间戳**: TS" in md
        assert "- **标签**: t1, t2" in md
        assert "- **证据**: evidence.md" in md
        assert "- **变更前**: old text" in md
        assert "- **变更后**: new text" in md

    def test_spec_delta_to_markdown_minimal(self):
        """无可选字段 → 只输出标题 + 时间戳。"""
        md = SpecDelta(req_id="R1", change_type=ChangeType.ADDED, timestamp="TS").to_markdown()
        assert md.startswith("### R1 [added]")
        assert "原因" not in md
        assert "归因测试" not in md
        assert "- **时间戳**: TS" in md

    def test_spec_delta_to_markdown_truncates_200(self):
        """previous/new 文本截断到 200 字符。"""
        long_text = "x" * 300
        md = SpecDelta(
            req_id="R", change_type="added", previous_text=long_text,
            new_text=long_text, timestamp="TS",
        ).to_markdown()
        assert f"- **变更前**: {'x' * 200}" in md
        assert f"- **变更后**: {'x' * 200}" in md

    def test_spec_delta_repr(self):
        d = SpecDelta(req_id="RS-001", change_type=ChangeType.REMOVED, timestamp="TS")
        assert repr(d) == "<SpecDelta RS-001 [removed]>"

    def test_generator_init_defaults_and_custom(self):
        g = SpecDeltaGenerator()
        assert g.output_dir == "."
        assert g.default_tags == []
        g2 = SpecDeltaGenerator(output_dir="/tmp/x", default_tags=["ci"])
        assert g2.output_dir == "/tmp/x"
        assert g2.default_tags == ["ci"]

    def test_generate_merges_tags_and_metadata(self):
        g = SpecDeltaGenerator(default_tags=["base"])
        d = g.generate(req_id="RS-001", change_type="added", reason="r", tags=["extra"], custom="v")
        assert d.change_type is ChangeType.ADDED
        assert d.tags == ["base", "extra"]
        assert d.metadata == {"custom": "v"}

    def test_generate_without_extra_tags(self):
        g = SpecDeltaGenerator(default_tags=["base"])
        d = g.generate(req_id="RS-002", change_type=ChangeType.MODIFIED)
        assert d.tags == ["base"]
        assert d.metadata == {}

    def test_generate_from_test_failure(self):
        d = SpecDeltaGenerator().generate_from_test_failure(
            "test_brake", "RS-001", "assert failed: xyz", evidence_ref="ev"
        )
        assert d.change_type is ChangeType.NEEDS_REVIEW
        assert d.attributed_test == "test_brake"
        assert d.attributed_source == "ci.failure"
        assert "test_brake" in d.reason
        assert "assert failed: xyz" in d.reason
        assert d.evidence_ref == "ev"
        assert d.tags == ["ci_failure", "needs_review", "defect_backprop"]

    def test_generate_from_test_failure_no_evidence(self):
        d = SpecDeltaGenerator().generate_from_test_failure("t", "RS-002", "err")
        assert d.evidence_ref is None

    def test_append_to_file_new_creates_header(self, tmp_path):
        """新文件 → 先写文件头再追加条目。"""
        g = SpecDeltaGenerator(output_dir=str(tmp_path))
        d = g.generate("RS-001", "added", reason="r", timestamp="TS")
        path = g.append_to_file(d)
        assert path == str(tmp_path / "spec-delta.md")
        content = (tmp_path / "spec-delta.md").read_text(encoding="utf-8")
        assert "# Spec Delta — Automated Change Log" in content
        assert "yuleOSH Loop Engine v2.5.0" in content
        assert "### RS-001 [added]" in content

    def test_append_to_file_existing_appends(self, tmp_path):
        """已有文件 → 不重复写头，直接追加。"""
        target = tmp_path / "delta.md"
        target.write_text("# existing\n", encoding="utf-8")
        g = SpecDeltaGenerator(output_dir=str(tmp_path))
        d = g.generate("RS-002", "removed", timestamp="TS")
        path = g.append_to_file(d, filepath=str(target))
        assert path == str(target)
        content = target.read_text(encoding="utf-8")
        assert "# existing" in content
        assert "### RS-002 [removed]" in content
        assert "Automated Change Log" not in content

    def test_append_to_file_bare_filename(self, tmp_path, monkeypatch):
        """filepath 无目录部分 → os.path.dirname 为空时落到 '.'。"""
        monkeypatch.chdir(tmp_path)
        g = SpecDeltaGenerator()
        d = g.generate("RS-003", "added", timestamp="TS")
        path = g.append_to_file(d, filepath="bare.md")
        assert path == "bare.md"
        assert (tmp_path / "bare.md").exists()

    def test_to_json(self):
        g = SpecDeltaGenerator()
        d1 = g.generate("RS-001", "added", timestamp="TS")
        d2 = g.generate("RS-002", "modified", timestamp="TS")
        parsed = json.loads(g.to_json([d1, d2]))
        assert len(parsed) == 2
        assert parsed[0]["req_id"] == "RS-001"
        assert parsed[0]["change_type"] == "added"
        assert parsed[1]["req_id"] == "RS-002"

    def test_from_test_failure_simple(self):
        d = SpecDeltaGenerator.from_test_failure_simple("test_x", "RS-009", "boom")
        assert d.change_type is ChangeType.NEEDS_REVIEW
        assert d.attributed_test == "test_x"
        assert "test_x" in d.reason


# =====================================================================
# knowledge_graph/spec_diff.py — SHALL 变更检测
# =====================================================================


class TestKnowledgeGraphSpecDiff:
    """extract_shall_statements / analyze_spec_changes / store 应用 / git 对比。"""

    def test_extract_shall_statements_empty(self):
        assert kg_spec_diff_mod.extract_shall_statements("") == []
        assert kg_spec_diff_mod.extract_shall_statements("   \n  ") == []

    def test_extract_pattern1_bullet_with_section(self):
        """标准 bullet 格式 + 节标题 + // 注释。"""
        text = (
            "## Section A\n"
            "* [RS-001-01] The system SHALL brake. // comment\n"
            "* [SWR-002.1-01] The system SHALL light."
        )
        result = kg_spec_diff_mod.extract_shall_statements(text)
        assert len(result) == 2
        assert result[0]["shall_id"] == "RS-001-01"
        assert result[0]["statement"] == "The system SHALL brake."
        assert result[0]["section"] == "Section A"
        assert result[0]["line_number"] == 2
        assert result[1]["shall_id"] == "SWR-002.1-01"
        assert result[1]["section"] == "Section A"

    def test_extract_pattern2_dash_formats(self):
        """dash 格式：冒号分隔与破折号分隔。"""
        text = "- RS-002-01: The system SHALL accelerate.\n- RS-003-01 - The system SHALL steer."
        result = kg_spec_diff_mod.extract_shall_statements(text)
        assert len(result) == 2
        assert result[0]["shall_id"] == "RS-002-01"
        assert result[0]["statement"] == "The system SHALL accelerate."
        assert result[1]["shall_id"] == "RS-003-01"
        assert result[1]["statement"] == "The system SHALL steer."

    def test_extract_pattern3_inline_and_skips(self):
        """行内 ID 捕获；SHALL ID: 引用跳过；无语句的 ID 跳过。"""
        text = (
            "See RS-004-01: the system SHALL do X.\n"
            "SHALL ID: RS-005-01\n"
            "RS-006-01:"
        )
        result = kg_spec_diff_mod.extract_shall_statements(text)
        assert [r["shall_id"] for r in result] == ["RS-004-01"]

    def test_extract_shall_ids(self):
        text = "* [RS-001-01] A\n- RS-002-01: B"
        assert kg_spec_diff_mod.extract_shall_ids(text) == ["RS-001-01", "RS-002-01"]

    def test_normalize_statement(self):
        assert kg_spec_diff_mod._normalize_statement("  The System SHALL  Do X.  ") == "the system shall do x"

    def test_analyze_changes_full(self):
        """同时覆盖 added / modified / deleted / unchanged。"""
        old = (
            "## S1\n"
            "* [RS-001-01] The system SHALL brake.\n"
            "* [RS-002-01] The system SHALL accelerate.\n"
            "* [RS-003-01] The system SHALL steer."
        )
        new = (
            "## S1\n"
            "* [RS-001-01] The system SHALL brake.\n"
            "* [RS-002-01] The system SHALL decelerate.\n"
            "* [RS-004-01] The system SHALL reverse."
        )
        changes = kg_spec_diff_mod.analyze_spec_changes(old, new)
        assert [c["shall_id"] for c in changes["added"]] == ["RS-004-01"]
        assert [c["shall_id"] for c in changes["modified"]] == ["RS-002-01"]
        assert [c["shall_id"] for c in changes["deleted"]] == ["RS-003-01"]
        assert [c["shall_id"] for c in changes["unchanged"]] == ["RS-001-01"]
        # 尾部句号被 _SHALL_LINE_RE 的可选后缀组消费，statement 不含句号
        assert changes["modified"][0]["old_statement"] == "The system SHALL accelerate"
        assert changes["modified"][0]["new_statement"] == "The system SHALL decelerate"
        assert changes["modified"][0]["section"] == "S1"
        assert "1 added" in changes["summary"]
        assert "1 modified" in changes["summary"]
        assert "1 deleted" in changes["summary"]
        assert "1 unchanged" in changes["summary"]
        assert "(from 3 total SHALLs)" in changes["summary"]

    def test_analyze_changes_empty_old(self):
        """old 为空 → 全部视为 added。"""
        changes = kg_spec_diff_mod.analyze_spec_changes("", "* [RS-001-01] The system SHALL brake.")
        assert len(changes["added"]) == 1
        assert changes["deleted"] == []
        assert changes["modified"] == []

    def test_analyze_changes_empty_new(self):
        """new 为空 → 全部视为 deleted。"""
        changes = kg_spec_diff_mod.analyze_spec_changes("* [RS-001-01] The system SHALL brake.", "")
        assert len(changes["deleted"]) == 1
        assert changes["added"] == []

    def test_analyze_changes_both_empty(self):
        changes = kg_spec_diff_mod.analyze_spec_changes("", "")
        assert changes["summary"] == "No spec changes detected"

    def test_analyze_changes_normalized_unchanged(self):
        """仅标点/空白差异 → 归一化后视为 unchanged。"""
        old = "* [RS-001-01] The system SHALL brake."
        new = "* [RS-001-01] The system SHALL brake. "
        changes = kg_spec_diff_mod.analyze_spec_changes(old, new)
        assert len(changes["unchanged"]) == 1
        assert changes["modified"] == []

    def test_analyze_spec_file_changes(self, tmp_path):
        """磁盘文件对比 + 缺失文件按空文本处理。"""
        old_f = tmp_path / "old.spec.md"
        new_f = tmp_path / "new.spec.md"
        old_f.write_text("* [RS-001-01] The system SHALL brake.", encoding="utf-8")
        new_f.write_text(
            "* [RS-001-01] The system SHALL brake.\n* [RS-002-01] The system SHALL steer.",
            encoding="utf-8",
        )
        changes = kg_spec_diff_mod.analyze_spec_file_changes(str(old_f), str(new_f))
        assert len(changes["added"]) == 1
        assert changes["added"][0]["shall_id"] == "RS-002-01"
        # old 缺失 → 新文件所有 SHALL 均视为新增
        missing = kg_spec_diff_mod.analyze_spec_file_changes(str(tmp_path / "nope.md"), str(new_f))
        assert len(missing["added"]) == 2

    def test_detect_spec_files_in_changes(self):
        """仅匹配 *.spec.md 后缀或含 '/spec/' 路径段（'spec/...' 无前导斜杠不匹配）。"""
        files = [
            "docs/spec/a.spec.md",
            "project/spec/b.md",
            "src/main.c",
            "docs\\spec\\win.md",
            "spec/c.md",  # 无前导 '/' → 不匹配
            "notes.md",
        ]
        assert kg_spec_diff_mod.detect_spec_files_in_changes(files) == [
            "docs/spec/a.spec.md",
            "project/spec/b.md",
            "docs\\spec\\win.md",
        ]

    def test_apply_changes_empty(self):
        store = mock.Mock()
        assert kg_spec_diff_mod.apply_spec_changes_to_store(store, {}) == {
            "created": 0, "updated": 0, "deleted": 0,
        }

    def test_apply_changes_full(self):
        """added 建节点 / modified 更新(含 has_pending_changes) / deleted 软删除。"""
        store = mock.Mock()

        def fake_get(entity_type, entity_id):
            if entity_id == "RS-002":  # modified：已存在 → 更新
                return mock.Mock(properties={"statement": "old"}, is_active=True)
            if entity_id == "RS-003":  # deleted：active → 软删除
                return mock.Mock(properties={"statement": "d1"}, is_active=True)
            if entity_id == "RS-004":  # deleted：inactive → 跳过
                return mock.Mock(properties={}, is_active=False)
            return None  # RS-001 added / RS-005 不存在

        store.get_node.side_effect = fake_get
        changes = {
            "added": [{"shall_id": "RS-001", "statement": "new stmt", "section": "S1"}],
            "modified": [{"shall_id": "RS-002", "old_statement": "old", "new_statement": "new", "section": "S2"}],
            "deleted": [
                {"shall_id": "RS-003", "statement": "d1", "section": "S3"},
                {"shall_id": "RS-004", "statement": "d2", "section": "S3"},
                {"shall_id": "RS-005", "statement": "d3", "section": "S3"},
            ],
        }
        summary = kg_spec_diff_mod.apply_spec_changes_to_store(store, changes)
        assert summary == {"created": 1, "updated": 1, "deleted": 1}

        calls = store.upsert_node.call_args_list
        node_added = calls[0].args[0]
        assert node_added.entity_type == "requirement"
        assert node_added.entity_id == "RS-001"
        assert node_added.properties["change_type"] == "added"
        assert node_added.properties["testable"] is True
        assert node_added.properties["source"] == "spec_diff"

        node_updated = calls[1].args[0]
        assert node_updated.entity_id == "RS-002"
        # 源码把新文本写入 properties["statement"]，旧文本写入 "old_statement"
        assert node_updated.properties["statement"] == "new"
        assert node_updated.properties["old_statement"] == "old"
        assert node_updated.properties["has_pending_changes"] is True
        assert node_updated.properties["change_type"] == "modified"
        assert node_updated.is_active is True

        node_deleted = calls[2].args[0]
        assert node_deleted.entity_id == "RS-003"
        assert node_deleted.properties["change_type"] == "deleted"
        assert node_deleted.is_active is False

    def test_apply_changes_modified_missing_node(self):
        """modified 但节点不存在 → 不更新不计数。"""
        store = mock.Mock()
        store.get_node.return_value = None
        changes = {
            "added": [],
            "modified": [{"shall_id": "RS-002", "old_statement": "o", "new_statement": "n", "section": "S"}],
            "deleted": [],
        }
        assert kg_spec_diff_mod.apply_spec_changes_to_store(store, changes) == {
            "created": 0, "updated": 0, "deleted": 0,
        }

    def test_get_spec_changes_from_git_success(self, tmp_path):
        """git show 成功：old 来自 git，new 来自磁盘。"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text(
            "* [RS-001-01] The system SHALL brake.\n* [RS-002-01] The system SHALL steer.",
            encoding="utf-8",
        )
        result = mock.Mock(returncode=0, stdout="* [RS-001-01] The system SHALL brake.")
        with mock.patch("subprocess.run", return_value=result) as m:
            changes = kg_spec_diff_mod.get_spec_changes_from_git("HEAD~1", str(spec_file))
        assert len(changes["added"]) == 1
        assert changes["added"][0]["shall_id"] == "RS-002-01"
        args, kwargs = m.call_args
        assert args[0] == ["git", "show", f"HEAD~1:{spec_file}"]
        assert kwargs["timeout"] == 30

    def test_get_spec_changes_from_git_nonzero(self, tmp_path):
        """git 返回非零 → old 视为空，全部 SHALL 为 added。"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("* [RS-001-01] The system SHALL brake.", encoding="utf-8")
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=1, stdout="")):
            changes = kg_spec_diff_mod.get_spec_changes_from_git("HEAD~1", str(spec_file))
        assert len(changes["added"]) == 1

    def test_get_spec_changes_from_git_timeout(self, tmp_path):
        """git 超时 → 错误 summary。"""
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("* [RS-001-01] The system SHALL brake.", encoding="utf-8")
        with mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 30)):
            changes = kg_spec_diff_mod.get_spec_changes_from_git("HEAD~1", str(spec_file))
        assert changes["summary"] == "Error reading git spec"
        assert changes["added"] == []

    def test_get_spec_changes_from_git_file_missing(self, tmp_path):
        """磁盘 spec 文件缺失（open 抛 FileNotFoundError）→ 错误 summary。"""
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout="* [RS-001-01] Old")):
            changes = kg_spec_diff_mod.get_spec_changes_from_git("HEAD~1", str(tmp_path / "missing.md"))
        assert changes["summary"] == "Error reading git spec"

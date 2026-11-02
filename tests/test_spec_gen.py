# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Tests for yuleosh.spec.gen — natural language → OpenSpec generation."""

import pytest

from yuleosh.spec.gen import (
    _extract_markdown,
    _split_intents,
    generate_spec,
)
from yuleosh.spec.validate import parse_spec, validate_spec


# ── engine: mock mode ────────────────────────────────────────────────────────

def test_mock_generates_validator_clean_spec(tmp_path):
    r = generate_spec(
        "车辆点火且环境光暗时自动打开近光灯；熄火后30秒自动熄灭；故障时点亮示警灯。",
        mock=True, title="近光灯控制器需求规范",
    )
    assert r["error_count"] == 0, r["issues"]
    assert r["stats"]["requirements"] == 3
    assert r["stats"]["scenarios"] == 3
    assert r["stats"]["total_shall"] == 3
    assert r["mock"] is True

    # round-trip through the real file-based validator
    spec = tmp_path / "spec.md"
    spec.write_text(r["markdown"], encoding="utf-8")
    doc = parse_spec(str(spec))
    assert validate_spec(doc) == []
    assert [req.req_id for req in doc.requirements] == ["REQ-001", "REQ-002", "REQ-003"]


def test_mock_respects_prefix_and_title():
    r = generate_spec("收到字符立即回显。每5秒输出心跳日志。",
                      mock=True, prefix="swr", title="UART Demo")
    assert r["error_count"] == 0
    assert r["markdown"].startswith("# UART Demo")
    assert "### SWR-001:" in r["markdown"]
    assert "### SWR-002:" in r["markdown"]


def test_mock_single_intent_fallback():
    r = generate_spec("短", mock=True)
    # too-short segment falls back to a single placeholder requirement
    assert r["stats"]["requirements"] == 1
    assert r["error_count"] == 0


def test_empty_input_rejected():
    with pytest.raises(ValueError):
        generate_spec("   ", mock=True)


def test_invalid_prefix_rejected():
    with pytest.raises(ValueError):
        generate_spec("需求描述文本", mock=True, prefix="1BAD")


# ── helpers ──────────────────────────────────────────────────────────────────

def test_extract_markdown_strips_fences_and_preamble():
    content = "Here is the spec:\n```markdown\n# T\n\n### REQ-001: A\n- The system SHALL x\n```\n"
    md = _extract_markdown(content)
    assert md.startswith("# T")
    assert "```" not in md


def test_split_intents_chinese_punctuation():
    parts = _split_intents("点火自动开灯；熄火延时关闭。故障降级, 手动覆盖")
    assert parts == ["点火自动开灯", "熄火延时关闭", "故障降级, 手动覆盖"]


# ── engine: LLM mode with injected fake ─────────────────────────────────────

_VALID_MD = """# 近光灯控制器

### REQ-001: 点火联动自动开启
- The system SHALL 在 IGNITION=ON 且环境光照低于阈值时自动开启近光灯

#### Reason
提升夜间行车安全，避免驾驶员忘记开灯。

## Scenarios

#### Scenario: 暗光点火自动开灯
- GIVEN 环境光照低于阈值
- WHEN IGNITION 信号由 OFF 变为 ON
- THEN 近光灯输出在 500ms 内置为 ON
"""

_INVALID_MD = """# 坏文档

没有合法需求条目。
"""


def test_llm_mode_uses_injected_fn():
    calls = []

    def fake_llm(system, user):
        calls.append((system, user))
        return {"content": _VALID_MD, "model": "fake-model"}

    r = generate_spec("点火时自动开灯", llm_fn=fake_llm)
    assert r["error_count"] == 0
    assert r["repairs"] == 0
    assert r["model"] == "fake-model"
    assert len(calls) == 1
    assert "REQ-001" in calls[0][0]  # prefix embedded in system prompt


def test_llm_repair_loop_recovers_from_invalid_output():
    outputs = [_INVALID_MD, _VALID_MD]

    def fake_llm(system, user):
        return {"content": outputs.pop(0), "model": "fake-model"}

    r = generate_spec("点火时自动开灯", llm_fn=fake_llm)
    assert r["repairs"] == 1
    assert r["error_count"] == 0
    assert "### REQ-001:" in r["markdown"]


def test_llm_repair_loop_gives_up_after_max_repairs():
    def fake_llm(system, user):
        return {"content": _INVALID_MD, "model": "fake-model"}

    r = generate_spec("点火时自动开灯", llm_fn=fake_llm, max_repairs=2)
    assert r["repairs"] == 2
    assert r["error_count"] > 0  # surfaced, not hidden


# ── CLI ──────────────────────────────────────────────────────────────────────

def test_cli_spec_gen_writes_validated_file(tmp_path, capsys):
    from yuleosh.cli.commands.misc import cmd_spec_gen

    out = tmp_path / "docs" / "spec.md"
    cmd_spec_gen(["点火自动开灯；", "熄火延时关闭。"], output=str(out),
                 mock=True, title="T")
    assert out.exists()
    doc = parse_spec(str(out))
    assert validate_spec(doc) == []
    captured = capsys.readouterr().out
    assert "✅ Spec generated" in captured
    assert "pipeline run" in captured


def test_cli_spec_gen_refuses_overwrite_without_force(tmp_path):
    from yuleosh.cli.commands.misc import cmd_spec_gen

    out = tmp_path / "spec.md"
    out.write_text("# existing", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        cmd_spec_gen(["新需求文本内容"], output=str(out), mock=True)
    assert exc.value.code == 2
    assert out.read_text(encoding="utf-8") == "# existing"


def test_cli_spec_gen_stdout_mode(tmp_path, capsys):
    from yuleosh.cli.commands.misc import cmd_spec_gen

    cmd_spec_gen(["点火自动开灯。"], mock=True, stdout=True)
    out = capsys.readouterr().out
    assert "### REQ-001:" in out
    assert not (tmp_path / "docs").exists()


def test_cli_spec_gen_empty_input_exits_2(monkeypatch):
    import io
    from yuleosh.cli.commands.misc import cmd_spec_gen

    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr(sys_stdin_isatty_target(), "isatty", lambda: False)
    with pytest.raises(SystemExit) as exc:
        cmd_spec_gen([], mock=True)
    assert exc.value.code == 2


def sys_stdin_isatty_target():
    import sys
    return sys.stdin


# ── API ──────────────────────────────────────────────────────────────────────

def test_api_gen_returns_markdown_without_write():
    from yuleosh.api.spec import _gen

    data, status = _gen("POST", {"prompt": "点火时自动开灯；熄火延时关闭。",
                                 "mock": True})
    assert status == 200
    assert data["ok"] is True
    assert data["data"]["spec_path"] is None
    assert data["data"]["stats"]["requirements"] == 2
    assert data["data"]["error_count"] == 0


def test_api_gen_requires_prompt():
    from yuleosh.api.spec import _gen

    data, status = _gen("POST", {"prompt": "  ", "mock": True})
    assert status == 400
    assert data["ok"] is False


def test_api_gen_wrong_method():
    from yuleosh.api.spec import _gen

    _, status = _gen("GET", {"prompt": "x"})
    assert status == 405


def test_api_gen_writes_within_project(tmp_path, monkeypatch):
    import yuleosh.api as api_pkg
    from yuleosh.api import spec as spec_api

    monkeypatch.setattr(api_pkg, "OSH_HOME", str(tmp_path))
    # OSH_HOME is imported lazily inside _gen via `from . import OSH_HOME`
    data, status = spec_api._gen("POST", {
        "prompt": "点火时自动开灯。", "mock": True,
        "output": "docs/spec.md", "title": "T",
    })
    assert status == 200
    written = tmp_path / "docs" / "spec.md"
    assert written.exists()
    assert validate_spec(parse_spec(str(written))) == []
    # conflict without force → 409
    data, status = spec_api._gen("POST", {
        "prompt": "另一条需求描述。", "mock": True, "output": "docs/spec.md",
    })
    assert status == 409
    # path traversal blocked
    data, status = spec_api._gen("POST", {
        "prompt": "需求描述文本。", "mock": True, "output": "../escape.md",
    })
    assert status == 403

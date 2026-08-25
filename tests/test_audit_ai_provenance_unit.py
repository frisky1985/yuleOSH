"""Unit tests for AI generation provenance in the audit SHA-256 hash chain.

合规专家 P1: AI 输出是「草稿」不是「证据」——证据包必须补模型版本 +
prompt hash + 人工评审签署记录入 SHA-256 链。

Covers:
  - record_ai_generation() writes model / prompt_hash (+ optional human
    review fields) into a hash-chained ``ai.generation`` event
  - AI 溯源字段参与事件 hash：prompt_hash / model 被篡改 → verify() 失败
  - legacy 旧格式事件（无 AI 字段）仍可验证（向后兼容）
  - sign_ai_generation() 追加链上人工评审签署事件（草稿 → 证据）
  - AuditEvent to_dict/from_dict 往返：旧事件 byte 级一致
  - LLMClient.call 接线：成功调用 → ai.generation 事件（model + prompt_hash）
    入审计链；失败调用 / audit_ai=False 不写
"""

# @tests src/yuleosh/audit/model.py

import json

import pytest

from yuleosh.audit.model import (
    AuditEvent,
    AuditLog,
    EVENT_AI_GENERATION,
    EVENT_AI_SIGN,
    compute_event_hash,
    compute_prompt_hash,
)
from yuleosh.llm.client import LLMClient
from yuleosh.llm.providers.base import LLMConfig, LLMResponse
from yuleosh.llm.providers.mock import MockProvider


def _write_event(path, event_dict: dict):
    """Append a raw event dict (bypassing record()) for tamper tests."""
    with open(path, "a") as f:
        f.write(json.dumps(event_dict, ensure_ascii=False) + "\n")


class TestComputePromptHash:
    def test_deterministic_and_64_hex(self):
        h1 = compute_prompt_hash("Generate a UART driver")
        h2 = compute_prompt_hash("Generate a UART driver")
        assert h1 == h2
        assert len(h1) == 64
        int(h1, 16)  # valid hex

    def test_different_prompt_different_hash(self):
        assert compute_prompt_hash("prompt A") != compute_prompt_hash("prompt B")


class TestRecordAiGeneration:
    def test_records_model_and_prompt_hash(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        ev = log.record_ai_generation(
            actor="system",
            target="artifact:uart.c",
            model="deepseek-v4",
            prompt="Generate a UART driver",
            tenant="org-a",
        )
        assert ev.action == EVENT_AI_GENERATION
        assert ev.model == "deepseek-v4"
        assert ev.prompt_hash == compute_prompt_hash("Generate a UART driver")
        assert ev.reviewed_by is None  # 未签署
        assert ev.prev_hash == ""      # 链锚点
        assert len(ev.hash) == 64
        result = log.verify(tenant="org-a")
        assert result["valid"] is True
        assert result["checked"] == 1

    def test_explicit_prompt_hash_wins(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        ev = log.record_ai_generation(
            actor="system",
            model="deepseek-v4",
            prompt="ignored prompt",
            prompt_hash="a" * 64,
        )
        assert ev.prompt_hash == "a" * 64

    def test_optional_human_review_fields(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        ev = log.record_ai_generation(
            actor="system",
            target="artifact:main.c",
            model="deepseek-v4",
            prompt="generate main.c",
            reviewed_by="user:42",
            reviewed_at="2026-08-13T10:00:00",
        )
        assert ev.reviewed_by == "user:42"
        assert ev.reviewed_at == "2026-08-13T10:00:00"
        # 签署字段参与 hash：篡改即断链
        result = log.verify()
        assert result["valid"] is True

    def test_ai_events_link_into_hash_chain(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        e1 = log.record_ai_generation(
            actor="system", model="deepseek-v4", prompt="first draft")
        e2 = log.record_ai_generation(
            actor="system", model="deepseek-v4", prompt="second draft")
        e3 = log.record("user:1", "review.create", "review:r1")
        assert e2.prev_hash == e1.hash
        assert e3.prev_hash == e2.hash
        assert e1.hash != e2.hash != e3.hash
        result = log.verify()
        assert result["valid"] is True
        assert result["checked"] == 3


class TestAiProvenanceTamperDetection:
    def test_prompt_hash_tamper_breaks_chain(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        log.record("user:1", "a1", tenant="")
        gen = log.record_ai_generation(
            actor="system", model="deepseek-v4",
            prompt="generate code", tenant="")
        assert gen.prompt_hash
        # 篡改已落盘事件的 prompt_hash（换一个不同的合法 sha256）
        path = log._get_file_path()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        data = json.loads(lines[1])
        data["prompt_hash"] = "f" * 64
        lines[1] = json.dumps(data, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = log.verify()
        assert result["valid"] is False
        assert result["broken_at"] == 2
        assert "hash mismatch" in result["reason"]

    def test_model_tamper_breaks_chain(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        log.record_ai_generation(
            actor="system", model="deepseek-v4", prompt="generate code")
        path = log._get_file_path()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        data = json.loads(lines[0])
        data["model"] = "gpt-4o"  # 换模型 = 换证据
        lines[0] = json.dumps(data, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = log.verify()
        assert result["valid"] is False
        assert "hash mismatch" in result["reason"]


class TestLegacyBackwardCompat:
    def test_legacy_events_still_verify(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        # 旧格式：无 model / prompt_hash / reviewed_* 字段
        _write_event(log._get_file_path(), {
            "actor": "user:0", "action": "legacy.old", "target": "",
            "timestamp": "2026-01-01T00:00:00", "tenant": "", "detail": {},
        })
        gen = log.record_ai_generation(
            actor="system", model="deepseek-v4", prompt="draft")
        assert gen.prev_hash  # legacy 行仍可作链锚点
        result = log.verify()
        assert result["valid"] is True
        assert result["legacy"] == 1
        assert result["checked"] == 2

    def test_mixed_legacy_ai_legacy_chain(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        _write_event(log._get_file_path(), {
            "actor": "user:0", "action": "legacy.one", "target": "",
            "timestamp": "2026-01-01T00:00:00", "tenant": "", "detail": {},
        })
        gen = log.record_ai_generation(
            actor="system", model="deepseek-v4", prompt="draft")
        _write_event(log._get_file_path(), {
            "actor": "user:0", "action": "legacy.two", "target": "",
            "timestamp": "2026-01-02T00:00:00", "tenant": "", "detail": {},
            "prev_hash": gen.hash,  # legacy 行显式链接到 ai 事件
        })
        result = log.verify()
        assert result["valid"] is True
        assert result["legacy"] == 2
        assert result["checked"] == 3

    def test_legacy_event_roundtrip_byte_identical(self):
        legacy = {
            "actor": "user:0", "action": "legacy.old", "target": "",
            "timestamp": "2026-01-01T00:00:00", "tenant": "", "detail": {},
            "hash": "abc", "prev_hash": "",
        }
        ev = AuditEvent.from_dict(legacy)
        assert ev.model is None
        assert ev.prompt_hash is None
        assert ev.reviewed_by is None
        assert ev.reviewed_at is None
        # to_dict 不得引入新键 —— 旧格式序列化保持 byte 级一致
        assert ev.to_dict() == legacy

    def test_ai_event_roundtrip_preserves_fields(self):
        data = {
            "actor": "system", "action": EVENT_AI_GENERATION,
            "target": "artifact:uart.c", "timestamp": "2026-08-13T10:00:00",
            "tenant": "", "detail": {},
            "model": "deepseek-v4", "prompt_hash": "b" * 64,
            "reviewed_by": "user:42", "reviewed_at": "2026-08-13T11:00:00",
            "hash": "c" * 64, "prev_hash": "d" * 64,
        }
        ev = AuditEvent.from_dict(data)
        out = ev.to_dict()
        assert out["model"] == "deepseek-v4"
        assert out["prompt_hash"] == "b" * 64
        assert out["reviewed_by"] == "user:42"
        assert out["reviewed_at"] == "2026-08-13T11:00:00"
        assert out["hash"] == "c" * 64
        assert out["prev_hash"] == "d" * 64


class TestSignAiGeneration:
    def test_sign_off_appends_chained_event(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        gen = log.record_ai_generation(
            actor="system", target="artifact:main.c",
            model="deepseek-v4", prompt="generate main.c")
        sign = log.sign_ai_generation(
            reviewer="user:42",
            target="artifact:main.c",
            prompt_hash=gen.prompt_hash,
            note="MISRA 复核通过",
        )
        assert sign.action == EVENT_AI_SIGN
        assert sign.reviewed_by == "user:42"
        assert sign.reviewed_at
        assert sign.prompt_hash == gen.prompt_hash
        assert sign.prev_hash == gen.hash  # 签署事件链在生成事件之后
        result = log.verify()
        assert result["valid"] is True
        assert result["checked"] == 2

    def test_sign_off_reviewer_is_actor_by_default(self, tmp_path):
        log = AuditLog(data_root=str(tmp_path))
        sign = log.sign_ai_generation(
            reviewer="user:42", prompt_hash="a" * 64)
        assert sign.actor == "user:42"


class TestLLMClientAuditWiring:
    def setup_method(self):
        LLMClient.reset()

    def _call(self, prompt: str, **cfg_overrides) -> LLMResponse:
        import asyncio
        cfg = LLMConfig(
            provider="mock",
            model="test-model",
            rag_enabled=False,
            memory_enabled=False,
        )
        for k, v in cfg_overrides.items():
            setattr(cfg, k, v)
        LLMClient.configure_providers({"mock": MockProvider()})
        return asyncio.run(LLMClient.call(prompt=prompt, config=cfg))

    def _ai_events(self, tmp_path) -> list:
        audit_dir = tmp_path / "audit"
        events = []
        if audit_dir.exists():
            for p in audit_dir.glob("*.jsonl"):
                for line in p.read_text(encoding="utf-8").strip().splitlines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("action") == EVENT_AI_GENERATION:
                        events.append(data)
        return events

    def test_successful_call_records_ai_generation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YULEOSH_AUDIT_ROOT", str(tmp_path))
        prompt = "Generate a UART driver"
        resp = self._call(prompt)
        assert not resp.error

        events = self._ai_events(tmp_path)
        assert len(events) == 1
        ev = events[0]
        assert ev["model"] == "test-model"
        assert ev["prompt_hash"] == compute_prompt_hash(prompt)
        assert ev["detail"]["task_type"] == "unknown"
        # 事件本身在链上且链可验证
        log = AuditLog(data_root=str(tmp_path))
        result = log.verify()
        assert result["valid"] is True
        assert result["checked"] == 1

    def test_failed_call_records_no_ai_event(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YULEOSH_AUDIT_ROOT", str(tmp_path))
        resp = self._call("trigger error please")  # mock 强制失败
        assert resp.error
        assert self._ai_events(tmp_path) == []

    def test_audit_ai_disabled_records_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("YULEOSH_AUDIT_ROOT", str(tmp_path))
        resp = self._call("Generate code", audit_ai=False)
        assert not resp.error
        assert self._ai_events(tmp_path) == []

    def test_ai_event_in_chain_after_tamper_detected(self, tmp_path, monkeypatch):
        """LLMClient 写入的事件同样受 hash 链保护：篡改 prompt_hash 即断链。"""
        monkeypatch.setenv("YULEOSH_AUDIT_ROOT", str(tmp_path))
        self._call("Generate a UART driver")
        audit_dir = tmp_path / "audit"
        path = next(audit_dir.glob("*.jsonl"))
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        data = json.loads(lines[0])
        data["prompt_hash"] = "e" * 64
        lines[0] = json.dumps(data, ensure_ascii=False)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        log = AuditLog(data_root=str(tmp_path))
        result = log.verify()
        assert result["valid"] is False
        assert "hash mismatch" in result["reason"]


class TestComputeEventHashWithAiFields:
    def test_ai_fields_are_hashed(self):
        base = {"actor": "system", "action": EVENT_AI_GENERATION,
                "target": "artifact:x", "timestamp": "2026-08-13T00:00:00",
                "tenant": "", "detail": {},
                "model": "deepseek-v4", "prompt_hash": "a" * 64}
        h1 = compute_event_hash(base, "prev")
        h2 = compute_event_hash({**base, "prompt_hash": "b" * 64}, "prev")
        assert h1 != h2  # prompt_hash 参与 hash 计算

    def test_ai_fields_ignored_chain_metadata_still(self):
        base = {"actor": "system", "action": EVENT_AI_GENERATION,
                "target": "artifact:x", "timestamp": "2026-08-13T00:00:00",
                "tenant": "", "detail": {}, "model": "deepseek-v4",
                "prompt_hash": "a" * 64}
        h1 = compute_event_hash(base, "prev")
        h2 = compute_event_hash(
            {**base, "hash": "stale", "prev_hash": "stale"}, "prev")
        assert h1 == h2

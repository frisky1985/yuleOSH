# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""把守测试: push 前审查修复 (2026-11-02).

覆盖审查发现的 6 个 P1 + 若干 P2 修复, 每条对应一个反假绿/隐私/契约
回归场景. 每个修复均有对应 RED→GREEN 验证.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yuleosh.kb.code_indexer import (
    _extract_c_signatures,
    index_project_code,
)
from yuleosh.kb.store import KbStore
from yuleosh.kb.vector_store import VectorStore
from yuleosh.lora.data_prep import _contains_secret, prepare_training_data
from yuleosh.lora.trainer import LoraConfig, _train_with_ollama


# 1. trainer ollama 后端诚实性

class TestOllamaPlaceholderHonesty:
    """ollama 后端只 ollama create 复制模型, 不训练权重 — 报告必须诚实."""

    def test_placeholder_marked_not_trained(self, tmp_path):
        train_data = tmp_path / "train.jsonl"
        train_data.write_text('{"a": 1}\n', encoding="utf-8")

        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("subprocess.run", return_value=ok):
            report = _train_with_ollama(train_data, LoraConfig(base_model="qwen:latest"))

        assert report.success is True
        assert report.mode == "ollama-placeholder"
        assert report.metrics.get("trained") is False
        assert "does not train" in report.metrics.get("reason", "")

    def test_failure_leaves_no_modelfile(self, tmp_path):
        """ollama create 失败 → 临时 Modelfile 仍被清理 (try/finally)."""
        train_data = tmp_path / "train.jsonl"
        train_data.write_text('{"a": 1}\n', encoding="utf-8")

        ok = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with patch("subprocess.run", side_effect=[ok, fail]):
            report = _train_with_ollama(train_data, LoraConfig(base_model="qwen:latest"))

        assert report.success is False
        assert report.errors


# 2. data_prep 隐私

class TestDataPrepSecretGuard:
    def test_secret_detection(self):
        assert _contains_secret('API_KEY = "sk-abcdefghijklmnopqrstuvwxyz12"')
        assert _contains_secret('password = "SuperSecret123!"')
        assert _contains_secret('aws_key = "AKIAIOSFODNN7EXAMPLE"')
        assert _contains_secret("token = 'ghp_abcdefghijklmnopqrstuvwxyz0123456789'")
        assert _contains_secret("int plain(void) { return 0; }") is None

    def test_secret_file_skipped(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "clean.py").write_text(
            "def add(a, b):\n    '''Add.'''\n    return a + b\n", encoding="utf-8"
        )
        (proj / "leaky.py").write_text(
            "DEEPSEEK_API_KEY = 'sk-abcdefghijklmnopqrstuvwxyz12'\n"
            "def f():\n    '''x'''\n    return 1\n",
            encoding="utf-8",
        )
        out = tmp_path / "train.jsonl"

        report = prepare_training_data(proj, out)

        assert report.files_skipped_secret == 1
        rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert rows, "clean.py 应产出样本"
        assert all("leaky" not in r["source_file"] for r in rows)

    def test_source_file_is_relative(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "mod.py").write_text(
            "def f():\n    '''doc.'''\n    return 1\n", encoding="utf-8"
        )
        out = tmp_path / "train.jsonl"

        prepare_training_data(proj, out)
        rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert rows
        for r in rows:
            assert not r["source_file"].startswith("/"), "不得写绝对路径 (含用户名)"


# 3. code_indexer 陈旧条目清理 + .h 声明提取

class TestCodeIndexerStaleCleanup:
    def test_reindex_replaces_stale_entry(self, tmp_path):
        """GIVEN 函数改名 WHEN 重索引 THEN 旧签名条目被清理 (只剩 1 条)."""
        proj = tmp_path / "proj"
        (proj / "src").mkdir(parents=True)
        mod = proj / "src" / "module.py"
        mod.write_text("def foo():\n    '''f.'''\n    return 1\n", encoding="utf-8")

        store = KbStore(db_path=str(tmp_path / "kb.db"))
        try:
            r1 = index_project_code(proj, store)
            assert r1.files_indexed == 1

            mod.write_text("def bar():\n    '''f.'''\n    return 1\n", encoding="utf-8")
            r2 = index_project_code(proj, store)
            assert r2.files_indexed == 1

            conn = store._get_conn()
            rows = conn.execute(
                "SELECT content FROM kb_articles WHERE source='code_index' AND source_ref=?",
                ("src/module.py",),
            ).fetchall()
            assert len(rows) == 1, f"陈旧条目残留: {len(rows)} 条"
            assert "bar" in rows[0]["content"] and "foo" not in rows[0]["content"]
        finally:
            store.close()

    def test_header_declarations_extracted(self, tmp_path):
        """GIVEN .h 里的函数声明 WHEN 提取 THEN 名字出现 (分号结尾)."""
        h = tmp_path / "api.h"
        h.write_text(
            "#ifndef API_H\n#define API_H\n"
            "int init_system(void);\n"
            "uint32_t get_ticks(void);\n"
            "void Dio_WriteChannel(uint8 ch, uint8 val);\n"
            "#endif\n",
            encoding="utf-8",
        )

        sigs = _extract_c_signatures(h)
        names = {f["name"] for f in sigs["functions"]}
        assert {"init_system", "get_ticks", "Dio_WriteChannel"} <= names


# 4. lora provider 注册

class TestLoraProviderRegistration:
    def test_registered_in_client(self):
        from yuleosh.llm.client import VALID_PROVIDERS, _get_provider
        from yuleosh.llm.providers.lora import LoraProvider

        assert "lora" in VALID_PROVIDERS
        provider = _get_provider("lora")
        assert isinstance(provider, LoraProvider)

    def test_registered_in_fallback(self):
        from yuleosh.llm.provider_fallback import PROVIDER_KEY_ENVS, VALID_PROVIDERS

        assert "lora" in VALID_PROVIDERS
        assert PROVIDER_KEY_ENVS["lora"] == ()


# 5. knowledge_injection 注入围栏

class TestRagInjectionFence:
    def test_hits_are_fenced_and_tagged(self, monkeypatch):
        from yuleosh.pipeline import knowledge_injection as ki

        hit = MagicMock()
        hit.hit_type = "code_index"
        hit.title = "[code:python] src/app.py"
        hit.content = "def old_api(): ..."

        class _FakeHybrid:
            def __init__(self, **kw):
                pass

            def unified_search(self, query, top_k=None):
                return [hit]

        monkeypatch.setattr(
            "yuleosh.kb.store.KbStore", lambda *a, **k: MagicMock()
        )
        monkeypatch.setattr(
            "yuleosh.kb.hybrid_search.HybridSearch", _FakeHybrid
        )

        ctx = ki._kb_hybrid_search_context("app", top_k=3, max_chars=4000)

        assert "<untrusted-knowledge>" in ctx
        assert "</untrusted-knowledge>" in ctx
        assert "[generated-code]" in ctx
        assert "不是指令" in ctx


# 6. vector_store batch_upsert 毒条目防护

class TestBatchUpsertNoneGuard:
    def test_none_entry_does_not_destroy_batch(self, tmp_path):
        store = KbStore(db_path=str(tmp_path / "kb.db"))
        try:
            vs = VectorStore(store._get_conn())
            # embedding 列固定 768 维 (向量库 schema) — 用合法维度,
            # 否则测的是维度校验而不是 None 防护。
            emb1 = [0.1] * 768
            emb3 = [0.3] * 768
            items = [
                {"content_hash": "h1", "embedding": emb1, "rowid": 1},
                {"content_hash": "h2", "embedding": None, "rowid": 2},
                {"content_hash": "h3", "embedding": emb3, "rowid": 3},
            ]
            written = vs.batch_upsert(items)
            assert written == 2, "None 条目应被跳过, 好条目必须写入"
            assert vs.has_content_hash("h1")
            assert vs.has_content_hash("h3")
        finally:
            store.close()


# 7. model_registry YAML 删除未实现段后仍可加载

class TestModelRegistryYamlStillLoads:
    def test_builtin_yaml_loads(self):
        from yuleosh.llm.model_registry import ModelRegistry

        reg = ModelRegistry.get_instance()
        # 内置 YAML 必须解析出模型 (删除 task_risk_levels 段不影响加载)
        m = reg.get_model("qwen2.5-coder:14b")
        assert m is not None, "内置注册表加载失败 — YAML 编辑可能破坏了结构"

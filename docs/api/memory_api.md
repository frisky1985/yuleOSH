# 平台记忆 (`memory`) API 参考

> 代码根:`src/yuleosh/memory/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`memory` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/memory.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `build_memory_subparser` | `(subparsers)` | Add the 'memory' subcommand parser. | `memory/cli.py:27` |
| `handle_memory_command` | `(args)` | Dispatch the memory subcommand. | `memory/cli.py:127` |
| `build_session_subparser` | `(subparsers)` | Add the 'session' subcommand parser. | `memory/cli.py:285` |
| `handle_session_command` | `(args)` | Dispatch the session subcommand. | `memory/cli.py:297` |
| `_now_iso` | `()` | — | `memory/distill.py:92` |
| `_clamp_trust` | `(t)` | — | `memory/distill.py:96` |
| `_extract_json_array` | `(text: str)` | Robustly extract a JSON array from an LLM response. | `memory/distill.py:104` |
| `_coerce_candidate` | `(item: dict, source_session: str)` | Validate/normalize a raw LLM dict into a DistillCandidate. | `memory/distill.py:129` |
| `similarity` | `(a: str, b: str)` | Normalized difflib similarity in [0, 1] (deterministic dedup). | `memory/distill.py:150` |
| `_default_llm_fn` | `(prompt: str)` | 默认蒸馏 LLM：走 LLMClient.call_sync（DeepSeek 等，统一路由）。 | `memory/distill.py:393` |
| `mock_distill_llm` | `(prompt: str)` | 确定性 mock 蒸馏：按信号词抽取句子（无 API key 演示/测试）。 | `memory/distill.py:405` |
| `load_last_candidates` | `(project_dir: str | Path)` | 读取上次 distill 写入的候选（reflect 复用，缺文件返回空列表）。 | `memory/distill.py:438` |
| `record_injection` | `(fact_ids, step_key: str, store: MemoryStore | None)` | 埋点：记录注入的 fact_ids + step_key（usage_log + last_used_at）。 | `memory/feedback.py:35` |
| `apply_step_result` | `(step_key: str, status: str, store: MemoryStore | None)` | 步骤结果回采：调整该 step 注入过的 facts 的 trust。 | `memory/feedback.py:59` |
| `_query_tokens` | `(query: str)` | Extract retrieval-significant tokens from a query/prompt. | `memory/llm_context.py:48` |
| `is_memory_context_enabled` | `()` | Global on/off switch for memory → LLM context injection. | `memory/llm_context.py:57` |
| `get_default_assembler` | `()` | Get or create the default assembler (lazy singleton). | `memory/llm_context.py:285` |
| `assemble_memory_context` | `(query: str, max_facts: int, max_sessions: int, max_chars: int)` | One-shot helper: project memory as a capped context block. | `memory/llm_context.py:293` |
| `_detect_conflict` | `(cand: DistillCandidate, fact: dict, min_sim: float)` | 确定性冲突检测：同 entity + 内容相似但数字或否定语义矛盾。 | `memory/reflect.py:41` |
| `_reliability_rank` | `(value: str | None)` | — | `memory/reflect.py:74` |
| `_rule_id` | `(title: str, source_file: str)` | — | `memory/rule_sink.py:77` |
| `extract_rules_from_diff` | `(original: str, corrected: str, file_path: str, context: str)` | Analyze diff between *original* (LLM output) and *corrected* (human fix). | `memory/rule_sink.py:81` |
| `cli_add_correction` | `(original_path: str, corrected_path: str, project_dir: str)` | CLI convenience: diff two files, extract rules, sink to LEARNED-RULES.md. | `memory/rule_sink.py:256` |
| `_now` | `()` | ISO-8601 UTC timestamp for records. | `memory/store.py:29` |
| `normalize_text` | `(s: str)` | Normalize for similarity comparisons (deterministic dedup support). | `memory/store.py:34` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `DistillCandidate` | `()` | 一条蒸馏候选（LLM 输出 → 去重 → 落库的中间形态）。 | `memory/distill.py:69` |
| `Distiller` | `()` | 蒸馏器：session 文本 → LLM 候选 → 去重 → 批量落库。 | `memory/distill.py:160` |
| `MemoryContextItem` | `()` | A single retrieved memory item (fact or session entry). | `memory/llm_context.py:67` |
| `MemoryContextAssembler` | `()` | Retrieve, de-duplicate and cap project memory for LLM injection. | `memory/llm_context.py:84` |
| `Reflector` | `()` | 反思器：候选 vs 现有 facts → 冲突/过时 → 解决动作 → 应用。 | `memory/reflect.py:78` |
| `ExtractedRule` | `()` | — | `memory/rule_sink.py:66` |
| `RuleSink` | `()` | Writes extracted rules to .yuleosh/agents/LEARNED-RULES.md. | `memory/rule_sink.py:167` |
| `MemoryStore` | `()` | SQLite-backed fact + session memory store. | `memory/store.py:44` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `DistillCandidate.to_dict` | `(self)` | — | `memory/distill.py:81` |
| `DistillCandidate.from_dict` | `(cls, data: dict)` | — | `memory/distill.py:85` |
| `Distiller.__init__` | `(self, store: MemoryStore | None, llm_fn, project_dir: str | Path | None, similarity_threshold: float)` | — | `memory/distill.py:163` |
| `Distiller.collect_session_texts` | `(self, days: int)` | 收集蒸馏输入：session 日志 + session 目录原始产物。 | `memory/distill.py:174` |
| `Distiller.extract_candidates` | `(self, texts: list[str], days: int, source_session: str)` | 对每个文本块调用 LLM 并解析候选。 | `memory/distill.py:268` |
| `Distiller.dedupe` | `(self, candidates: list[DistillCandidate])` | 去重：候选内部 + 与已有 active facts（幂等）。 | `memory/distill.py:296` |
| `Distiller.distill` | `(self, days: int, dry_run: bool)` | 执行一次蒸馏：收集 → 抽取 → 去重 → 落库（dry_run 不写库）。 | `memory/distill.py:337` |
| `MemoryContextAssembler.__init__` | `(self, store: MemoryStore | None, max_facts: int, max_sessions: int, max_chars: int)` | — | `memory/llm_context.py:94` |
| `MemoryContextAssembler.retrieve` | `(self, query: str)` | Retrieve facts + sessions for ``query``. | `memory/llm_context.py:143` |
| `MemoryContextAssembler.format_context` | `(self, items: list[MemoryContextItem])` | Render items as a markdown context block ("" when empty). | `memory/llm_context.py:204` |
| `MemoryContextAssembler.assemble` | `(self, query: str)` | Retrieve + format + enforce ``max_chars`` cap. "" when empty. | `memory/llm_context.py:259` |
| `Reflector.__init__` | `(self, store: MemoryStore | None, llm_judge, project_dir: str | Path | None)` | — | `memory/reflect.py:81` |
| `Reflector.detect_conflicts` | `(self, candidates: list[DistillCandidate], limit: int)` | 候选 vs 同 entity 的现有 active facts 冲突对。 | `memory/reflect.py:89` |
| `Reflector.resolve` | `(self, conflicts: list[dict])` | 按来源可靠性 + 信任解决冲突，产出动作列表。 | `memory/reflect.py:117` |
| `Reflector.detect_obsolete` | `(self, max_age_days: int, limit: int)` | 最近使用为空 + 超阈值天数 → 归档（不删）。 | `memory/reflect.py:164` |
| `Reflector.apply` | `(self, actions: list[dict])` | 执行动作（归档 / 插入新候选 / 降权插入）。 | `memory/reflect.py:184` |
| `Reflector.reflect` | `(self, candidates: list[DistillCandidate], max_age_days: int, dry_run: bool)` | 执行反思：冲突检测 → 解决 + 过时检测 → 应用（dry_run 不写库）。 | `memory/reflect.py:222` |
| `RuleSink.__init__` | `(self, project_dir: str)` | — | `memory/rule_sink.py:170` |
| `RuleSink.add_rules` | `(self, rules: list[ExtractedRule])` | Append new rules (deduplicated by id). Returns count added. | `memory/rule_sink.py:182` |
| `RuleSink.load_rules` | `(self)` | Parse LEARNED-RULES.md back to ExtractedRule structs. | `memory/rule_sink.py:203` |
| `RuleSink.format_for_prompt` | `(self, rules: list[ExtractedRule], max_chars: int)` | Format rules as a DO/DON'T block for LLM system prompts. | `memory/rule_sink.py:222` |
| `RuleSink.record_correction` | `(self, original_file: str, original_content: str, corrected_content: str, context: str)` | Diff two versions, extract rules, sink them, return extracted list. | `memory/rule_sink.py:241` |
| `MemoryStore.__init__` | `(self, db_path: str | None)` | — | `memory/store.py:60` |
| `MemoryStore.close` | `(self)` | — | `memory/store.py:85` |
| `MemoryStore.remember` | `(self, content: str, entity: str, category: str, tags: str, trust: float | None, source: str, source_reliability: str, distilled_at: str | None)` | Store a new fact. Returns the created row dict. | `memory/store.py:208` |
| `MemoryStore.get_fact` | `(self, fact_id: int)` | — | `memory/store.py:241` |
| `MemoryStore.list_facts` | `(self, category: str | None, entity: str | None, limit: int, offset: int, include_archived: bool)` | List facts with optional filters. Ordered by trust DESC, newest first. | `memory/store.py:247` |
| `MemoryStore.recall` | `(self, query: str, entity: str | None, category: str | None, limit: int, reinforce: bool)` | Recall facts matching query text (LIKE over content/tags) with | `memory/store.py:274` |
| `MemoryStore.forget` | `(self, fact_id: int)` | Delete a fact by id. Returns True if a row was removed. | `memory/store.py:317` |
| `MemoryStore.update_trust` | `(self, fact_id: int, trust: float)` | Explicitly set trust for a fact. | `memory/store.py:324` |
| `MemoryStore.adjust_trust` | `(self, fact_id: int, delta: float)` | Adjust trust by a relative delta (H1-2). +0.05 on pipeline success, | `memory/store.py:335` |
| `MemoryStore.adjust_trust_batch` | `(self, fact_ids: list[int], delta: float)` | Batch-adjust trust for multiple facts. Returns count updated. | `memory/store.py:352` |
| `MemoryStore.archive_fact` | `(self, fact_id: int)` | Move a fact to archived (recoverable, never deleted). | `memory/store.py:362` |
| `MemoryStore.unarchive_fact` | `(self, fact_id: int)` | Restore an archived fact (recovery path). | `memory/store.py:373` |
| `MemoryStore.remember_many` | `(self, items: list[dict])` | Batch remember in a single transaction (distillation persist). | `memory/store.py:384` |
| `MemoryStore.find_similar` | `(self, content: str, entity: str, threshold: float, limit: int)` | Find existing *active* facts similar to ``content``. | `memory/store.py:434` |
| `MemoryStore.record_usage` | `(self, fact_id: int, step: str, status: str)` | Log that ``fact_id`` was injected into a pipeline step (P3). | `memory/store.py:477` |
| `MemoryStore.list_usage` | `(self, fact_id: int | None, step: str | None, unsettled_only: bool, limit: int)` | List usage-log rows (optionally for a fact / step / unsettled only). | `memory/store.py:496` |
| `MemoryStore.mark_usage_settled` | `(self, usage_id: int, status: str)` | Settle an injected usage row with the step result (passed/failed/retry). | `memory/store.py:516` |
| `MemoryStore.increment_verified` | `(self, fact_id: int)` | Bump verified_count (each feedback settle = one verification). | `memory/store.py:527` |
| `MemoryStore.record_distill_run` | `(self, days: int, chunks: int, candidates: int, inserted: int, deduped: int, note: str)` | Record a distillation run (observability + idempotency audit). | `memory/store.py:538` |
| `MemoryStore.stats` | `(self)` | Return memory statistics. | `memory/store.py:554` |
| `MemoryStore.log_session` | `(self, content: str, session_key: str, kind: str)` | Record a session/decision log entry (searchable via FTS5). | `memory/store.py:574` |
| `MemoryStore.search_sessions` | `(self, query: str, limit: int)` | Full-text search over session logs using FTS5. | `memory/store.py:588` |
| `MemoryStore.list_session_logs` | `(self, days: int | None, limit: int)` | List recent session logs, newest first (distillation input, P1). | `memory/store.py:616` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `YULEOSH_MEMORY_DB` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.memory import <公共符号>
# 详见 docs/modules/memory.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 8 处生产引用(Grep `yuleosh.memory` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/memory/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

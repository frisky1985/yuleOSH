# 模块设计速写：memory（跨会话结构化记忆服务）

> 包：`src/yuleosh/memory/` ｜ 规模：8 .py ≈ 2327 行
> 关联：有真实生产调用方（llm/client、pipeline/knowledge_injection）；但部分模块为 CLI-only

## 职责
跨会话结构化记忆（事实 facts + 会话 sessions）SQLite 存储 + RAG 式检索，供 LLM 注入项目记忆；含蒸馏（session→fact）、反思（冲突/过期归档）、注入埋点与步骤结果回采反馈环。证据：`memory/__init__.py:4`、`memory/store.py:45`。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `memory/__init__.py` (8) | re-export | `MemoryStore` `:6` |
| `memory/store.py` (637) | SQLite 存储 | `MemoryStore` `:44`；`remember` `:208`；`recall` `:274`；`find_similar` `:434`；`update_trust` `:324`；`archive_fact` `:362`；`log_session` `:574`；`stats` `:554` |
| `memory/llm_context.py` (315) | LLM 注入装配 | `MemoryContextAssembler` `:84`；`assemble_memory_context` `:293`；`is_memory_context_enabled()` `:57` |
| `memory/feedback.py` (99) | 反馈环 | `record_injection` `:35`；`apply_step_result` `:59` |
| `memory/distill.py` (448) | 蒸馏（CLI） | `Distiller` `:160`；`distill` `:337` |
| `memory/reflect.py` (242) | 反思（CLI） | `Reflector` `:78`；`reflect` `:222` |
| `memory/rule_sink.py` (264) | 规则沉淀 | `RuleSink` `:167`；`extract_rules_from_diff` `:81` |
| `memory/cli.py` (314) | CLI | `build_memory_subparser`/`build_session_subparser`；`distill` `:230`/`reflect` `:249` |

## 公共 API / 入口点
- `MemoryStore(db_path=None)`：`remember`/`get_fact`/`list_facts`/`recall`/`forget`/`update_trust`/`adjust_trust_batch`/`archive_fact`/`remember_many`/`find_similar`/`record_usage`/`mark_usage_settled`/`increment_verified`/`record_distill_run`/`stats`/`log_session`/`search_sessions`/`close`
- `MemoryContextAssembler(...)`：`retrieve` `:143` / `assemble`；模块级 `assemble_memory_context(query=, max_chars=)` `:293`
- `record_injection(fact_ids, step_key)`（`feedback.py:35`）；`apply_step_result(step_key, status)` `:59`
- `Distiller` / `Reflector` / `RuleSink`

## 生产接线（真实调用方）
- `llm/client.py:479-490` 装配 system prompt 时：`MemoryContextAssembler(...)` + `assemble(prompt)`（主生产路径，失败非致命 `:497-500`）
- `pipeline/knowledge_injection.py:161-167` `_track_memory_usage` → `record_injection`；`:176-178` `_assemble_memory` → `assemble_memory_context`
- `cli/main.py:334` `build_memory_subparser`/`build_session_subparser`；`:837/:841` 命令分发

## 运行时触发方式
- LLM 请求路径（每次 LLM 调用）；pipeline 知识注入步骤；均无独立后台循环或定时任务。蒸馏/反思仅手动 CLI。

## 环境变量 / 配置
- `YULEOSH_MEMORY_DB`（`store.py:62`，默认 `<repo>/.yuleosh/memory.db` 基于 `__file__` 上溯四级）
- `YULEOSH_MEMORY_LLM_ENABLED`（`llm_context.py:62`，默认 `"1"`）
- 反馈参数常量（非 env）：`FEEDBACK_TRUST_MAX=0.95`、`PASS_DELTA=0.05`、`FAIL_DELTA=-0.1`、`ARCHIVE_TRUST_THRESHOLD=0.1`（`feedback.py:25-30`）

## 存储 / 状态模型
SQLite + WAL，默认 `<repo>/.yuleosh/memory.db`（`store.py:60-72`，线程本地连接 `:76`，`PRAGMA journal_mode=WAL` `:80`）。表：`memory_facts`（含 `trust`/`status`/`source`/`verified_count`/`distilled_at` `:95-112`）、`session_logs`+`session_logs_fts`（FTS5 `:120-145`）、`memory_usage_log`（`:149-156`）、`distill_runs`（`:163-172`）。信任度 `DEFAULT_TRUST=0.5`、`TRUST_DELTA=0.1`（`:53-56`）。

## 偏差 / 孤儿（设计文档必记）
- **D1：`rule_sink.py` 是 ORPHAN**——`RuleSink`/`extract_rules_from_diff`/`cli_add_correction` 全仓仅自身引用，无生产调用方。
- **D2：`apply_step_result`（`feedback.py:59`）无生产调用方**——只在 `memory/cli.py:278` 手动命令用；**生产 pipeline 从未调用**。即「步骤结果→trust 回采→低 trust 自动归档」反馈环在运行时**未闭合**，仅能人工 CLI 触发。这是 memory 反馈闭环最关键缺口。
- **D3：蒸馏/反思仅为 CLI 工具**——`Distiller`/`Reflector` 仅 `memory/cli.py` 调用，生产不自动跑。「session→fact 沉淀」「冲突/过期归档」非自动后台流程。
- `knowledge_injection.py:_track_memory_usage` `:164` 会再 `retrieve` 取 fact_ids，与 `_assemble_memory` `:176` 重复检索（轻微冗余，非阻塞）。

## 规模
8 .py ≈ 2327 行。

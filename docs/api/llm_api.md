# llm API 参考
> 代码根:`src/yuleosh/llm/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述
`llm` 是 yuleOSH 的统一大模型接入子系统:提供统一异步调用入口 `LLMClient`、多 provider 适配器(`anthropic`/`deepseek`/`openai`/`ollama`/`mock`)、provider 级故障降级链、token 预算预检、RAG 上下文装配、5 级输出校验 fallback、KG 锚定防幻觉、流式 SSE 与成本审计。顶层包仅再导出 6 个符号,绝大部分功能经各子模块被 pipeline/review/api 等模块直接 import(`src/yuleosh/llm/__init__.py:17-28`,`src/yuleosh/llm/client.py:39-50`)。

## 2. HTTP 端点
本子系统**不对外暴露任何 REST 端点**。`llm` 是纯库模块;唯一的"端点"形态是 `client.chat_completion`/`providers/*` 内部向外部 LLM 供应商(`LLM_BASE_URL`)发起的 HTTPS POST(`src/yuleosh/llm/client.py:1032`)。对外可观测的 LLM 健康诊断由 `api/dashboard.py` 调用 `diagnose_llm_providers` 提供,但不属于本包契约。

## 3. Python 公共 API

### 3.1 模块级函数
> 说明:带 `_` 前缀者为包内私有/兼容 shim;本表一并列出以便排障,并标注调用状态。

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `resolve_config` | `resolve_config(prompt, system_prompt, task_type, config) -> LLMConfig` | 解析生效配置:provider 优先级(env→agent 路由→TASK_ROUTES)、L3/L4 禁下钻小模型、org 覆盖 | `client.py:256` |
| `set_org_llm_override` | `set_org_llm_override(provider, model) -> None` | 设置当前请求租户钉选的 provider/model(ContextVar,请求级) | `client.py:244` |
| `chat_completion` | `chat_completion(system_prompt, user_prompt, *, temperature=0.3, max_tokens=4096, timeout=…, retries=3) -> dict` | **已废弃** 同步 chat 兼容层;仍被 `pipeline/run.py:93`、`pipeline/stages/llm.py:19` 使用 | `client.py:950` |
| `is_provider_unavailable` | `is_provider_unavailable(exc) -> bool` | 判定异常是否为 provider 不可用(用于 pipeline 优雅降级) | `client.py:1147` |
| `apply_fallback_chain` | `apply_fallback_chain(step_name, llm_output, *, schema=None, template=None, template_ctx=None, session_dir=None, llm_call=None, original_prompt="", start_level=0) -> FallbackResult` | 5 级输出校验 fallback(raw→schema→content→semantic→template→abort) | `fallback.py:490` |
| `validate_llm_output` | `validate_llm_output(output, schema) -> dict` | 按 schema 校验 LLM 输出(类型/必填字段/SHALL/JSON Schema/正则) | `validation.py:45` |
| `check_anchoring` | `check_anchoring(output, task_type, store=None) -> AnchorResult` | Layer1 KG 锚定:检查输出是否引用 KG 已知实体 | `anchoring.py:105` |
| `consistency_vote` | `async consistency_vote(prompt, task_type, config=None, n_variants=3, consensus_threshold=0.7) -> VoteResult` | Layer2 自一致性投票(无锚点时触发) | `anchoring.py:268` |
| `write_consensus_to_kg` | `write_consensus_to_kg(entity_id, output, source="voting-consensus", store=None) -> None` | 将投票共识写回 KG | `anchoring.py:364` |
| `call_with_fallback` | `async call_with_fallback(messages, config, provider_factory=None, *, skip_primary_reason=None) -> LLMResponse` | provider 级降级链执行(传输层失败自动降级) | `provider_fallback.py:306` |
| `fallback_enabled` | `fallback_enabled(config=None) -> bool` | 是否启用 provider 降级(env `YULEOSH_LLM_FALLBACK_ENABLED`,默认 True) | `provider_fallback.py:111` |
| `resolve_fallback_order` | `resolve_fallback_order(config=None) -> list[str]` | 解析降级链顺序(主 provider 优先 + 默认链 + mock 兜底) | `provider_fallback.py:139` |
| `provider_available` | `provider_available(provider_name, provider) -> bool` | 判断某 provider 是否可尝试(mock 恒可用/skeleton 跳过/无 key 跳过) | `provider_fallback.py:191` |
| `is_fallback_eligible` | `is_fallback_eligible(exc) -> bool` | 异常是否可触发降级(网络/5xx/429/4xx账户级/预算;4xx业务错不降级) | `provider_fallback.py:260` |
| `diagnose_llm_providers` | `async diagnose_llm_providers(live=False) -> dict` | 返回 key 安全(掩码)的 provider 健康报告 | `health.py:96` |
| `iter_sse_data` | `iter_sse_data(lines) -> Iterator[str]` | 纯解析:从 SSE 响应行产出 `data:` 载荷(遇 `[DONE]` 停止) | `streaming.py:42` |
| `parse_openai_chunk` | `parse_openai_chunk(payload) -> tuple[str, dict|None]` | 解析单条 OpenAI 兼容 data 帧 → `(delta_text, usage)` | `streaming.py:70` |
| `stream_request` | `stream_request(url, headers, body, *, timeout_s, on_data, max_retries=1, provider="llm") -> None` | urllib 流式 POST,逐 data 载荷回调 | `streaming.py:129` |
| `stream_chat_response` | `stream_chat_response(*, url, headers, body, messages, timeout_s, max_retries, provider, api_model, on_chunk, on_stream_start=None, estimate_cost=None) -> Any` | 同步流式并汇总为 `LLMResponse`(provider 共用) | `streaming.py:182` |
| `estimate_token_usage` | `estimate_token_usage(messages, content) -> dict` | 无 usage 帧时的兜底估算(OpenAI 风格 dict) | `streaming.py:99` |
| `is_local_endpoint` | `is_local_endpoint(base_url) -> bool` | 是否本机/自建端点(Ollama 等),决定是否发 `stream_options` | `streaming.py:113` |
| `emitter_for_current_step` | `emitter_for_current_step(model="", provider="") -> StepStreamEmitter|None` | 按当前 `LLMCallContext` 创建流式发射器;无上下文返回 None | `streaming.py:425` |
| `get_default_engine` | `get_default_engine() -> RAGEngine` | 获取/创建默认 RAG 引擎单例(自动索引 MISRA 规则) | `rag/engine.py:399` |
| `TokenBudgetChecker.estimate_tokens` | `@classmethod estimate_tokens(text) -> int` | 启发式 token 估算(EN 3.5/ CJK 1.5 chars per token) | `token_budget.py:43` |
| `TokenBudgetChecker.check` | `@classmethod check(prompt, config, system_prompt=None) -> BudgetCheckResult` | 调用前 token/预算预检 | `token_budget.py:60` |
| `CostLogger.init` | `@classmethod init(project_dir) -> None` | 设置日志目录(`.osh/logs`) | `cost.py:52` |
| `CostLogger.log_dict` | `@classmethod log_dict(**kwargs) -> None` | 便捷方法:由关键字参数写一条调用记录 | `cost.py:78` |
| `CostLogger.log_fallback_event` | `@classmethod log_fallback_event(from_provider, to_provider, reason, duration_s=0.0, error="") -> None` | 写 provider 降级事件审计 | `cost.py:101` |
| `CostLogger.get_daily_summary` | `@classmethod get_daily_summary(date_str=None) -> dict` | **ORPHAN** 按日聚合调用统计(见 §6) | `cost.py:133` |
| `CostLogger.get_task_cost` | `@classmethod get_task_cost(task_id) -> float` | **ORPHAN** 汇总某 task 的 LLM 成本(见 §6) | `cost.py:204` |

### 3.2 公共类
> `LLMClient` 全部为 classmethod(单例式使用);`CostLogger`/`TokenBudgetChecker` 全为 classmethod。

| 类 | 关键方法(签名) | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `LLMClient` | `call(prompt, system_prompt=None, task_type=None, config=None, messages=None) -> LLMResponse`(异步) | **统一入口**:预算预检→RAG 装配→记忆注入→provider 降级调用→成本审计→锚定门控→AI 溯源 | `client.py:376,399` |
| `LLMClient` | `call_sync(prompt, system_prompt=None, task_type=None, config=None, messages=None) -> dict` | 同步桥接 `call`,适配为 legacy dict 形态 | `client.py:710` |
| `LLMClient` | `configure_providers(providers) / reset()` | 注入/清空自定义 provider(测试隔离) | `client.py:769,775` |
| `RAGEngine` | `index_misra_rules(rules=None) -> int`、`index_best_practices(practices) -> int`、`retrieve(query, sources=None, top_k=5, min_score=0.1) -> list[RAGResult]`(异步)、`retrieve_as_context(query, sources=None, top_k=8) -> str`(异步)、`clear()` | 内存 RAG 检索引擎(v1:字符 n-gram + 关键词) | `rag/engine.py:182` |
| `AbstractProvider` | `abstract async chat(messages, config) -> LLMResponse`、`abstract estimate_cost(prompt_tokens, completion_tokens) -> float`、`abstract property provider_name` | 所有 provider 适配器基类 | `providers/base.py:135` |
| `CostLogger` | 见 §3.1 各 classmethod | LLM 调用审计日志写入与聚合 | `cost.py:45` |
| `TokenBudgetChecker` | 见 §3.1 | 调用前 token/成本估算与预检 | `token_budget.py:35` |
| `DeltaCoalescer` | `__init__(on_flush, *, min_chars=160, max_interval_s=0.15)`、`add(text)`、`flush()`、`reset()` | 高频 delta 合并节流(线程安全) | `streaming.py:264` |
| `StepStreamEmitter` | `__init__(*, run_id, project_dir, step_key, step_index=-1, model="", provider="", …)`、`on_stream_start()`、`on_chunk(text)`、`close()`、`is_closed`(属性) | 把 step 内 LLM 流式输出发为 `llm_delta` 事件 | `streaming.py:327` |

### 3.3 关键数据结构
| 结构 | 说明 | 文件:行 |
| --- | --- | --- |
| `@dataclass LLMConfig` | 单次调用配置(模型/provider/温度/seed/预算/RAG/记忆/降级/审计/锚定/流式回调等全字段) | `providers/base.py:34` |
| `@dataclass LLMResponse` | 标准化响应:`content/model/provider/token_usage/cost/duration_s/error/confidence/anchored/anchor_method/anchor_ids` | `providers/base.py:109` |
| `@dataclass LLMCallLog` | 单条调用审计记录(被 `CostLogger` 持久化) | `cost.py:28` |
| `@dataclass BudgetCheckResult` | 预算预检结果(`passed/reason/estimated_cost/estimated_prompt_tokens/…`) | `token_budget.py:23` |
| `@dataclass FallbackResult` | fallback 链结果(`status/level/retries/errors/confidence`) | `fallback.py:62` |
| `@dataclass AnchorResult` | 锚定结果(`anchored/method/entity_ids/task_type`) | `anchoring.py:38` |
| `@dataclass VoteResult` | 投票共识结果(`consensus/merged_output/agreement/variant_outputs`) | `anchoring.py:48` |
| `@dataclass FallbackEvent` | provider 降级审计事件 | `provider_fallback.py:95` |
| `@dataclass RAGChunk` / `RAGResult` | RAG 知识块 / 检索结果 | `rag/engine.py:34,46` |
| 常量 `PRICING_TABLE` | 单一真源:模型定价与上下文窗口(`providers/base.py:176`) | `providers/base.py:176` |
| 常量 `TASK_BUDGETS` | 任务预算表(与 `AGENT_MODEL_ROUTES` 对齐) | `providers/base.py:232` |
| 常量 `VALID_PROVIDERS` | `("deepseek","anthropic","openai","mock")`(client 层) | `client.py:96` |
| 常量 `PROVIDER_FALLBACK` | `DEFAULT_FALLBACK_ORDER = ("deepseek","anthropic","openai","ollama","mock")` | `provider_fallback.py:67` |
| 路由表 `TASK_ROUTES` / `AGENT_MODEL_ROUTES` / `TASK_RISK_LEVELS` | task→模型 / agent 标签→路由 / task→风险等级(L3/L4 禁下钻) | `client.py:59,138,192` |

## 4. 配置 / 环境变量
| 变量 | 用途 | 文件:行 |
| --- | --- | --- |
| `YULEOSH_LLM_PROVIDER` | 主 provider 覆盖(`deepseek|anthropic|openai|mock`),非法值抛 ValueError | `client.py:295` |
| `LLM_MODEL` | 覆盖模型名(provider 随之推断),L3/L4 下钻小模型被硬规则拦截 | `client.py:304` |
| `YULEOSH_LLM_FALLBACK_ENABLED` | 是否启用 provider 降级,默认 True(`0/false/no/off` 关闭) | `provider_fallback.py:121` |
| `YULEOSH_LLM_FALLBACK_ORDER` | 逗号分隔的自定义降级顺序 | `provider_fallback.py:166` |
| `YULEOSH_LLM_LOCAL_FALLBACK` | 外部不可用→本地 Ollama 自动降级,默认开启 | `client.py:809` |
| `YULEOSH_LLM_LOCAL_TIMEOUT` / `YULEOSH_LLM_TIMEOUT` | 本地/外部调用超时(秒),默认 1800 | `client.py:835,956` |
| `YULEOSH_LLM_LOCAL_MODEL` / `YULEOSH_LLM_LOCAL_CONTEXT_WINDOW` | 本地 Ollama 模型名 / 上下文窗口,默认 `qwen2.5-coder:14b` / `16384` | `client.py:840,844` |
| `YULEOSH_LLM_UNIFIED` | 置 `1` 时 `chat_completion` 走 `LLMClient.call_sync` 统一入口 | `client.py:976` |
| `YULEOSH_LLM_TIMEOUT` / `YULEOSH_LLM_CONTEXT_WINDOW` | `base.py` 读取的全局默认超时 / 本地透传 num_ctx,默认 1800 / 32768 | `providers/base.py:26,31` |
| `LLM_API_KEY` / `LLM_BASE_URL` | 外部 LLM key 与基址(亦回退 `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`) | `client.py:999,1012` |
| `DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | 各 provider 密钥(`health.py`、`provider_fallback.PROVIDER_KEY_ENVS`) | `health.py:25,provider_fallback.py:70` |
| `YULEOSH_AUDIT_ROOT` | AI 生成溯源审计数据根目录(`client.py` → `audit.model.AuditLog`) | `client.py:654` |

## 5. 调用示例

**示例 1 — 统一异步入口(基于 `client.py:399`、`providers/base.py:34`)**
```python
from yuleosh.llm import LLMClient, LLMConfig

resp = await LLMClient.call(
    prompt="生成一段 UART 驱动初始化代码",
    task_type="code_generation",
)
print(resp.content, resp.model, resp.cost, resp.anchored)
```

**示例 2 — 同步桥接(基于 `client.py:710`)**
```python
from yuleosh.llm import LLMClient

legacy = LLMClient.call_sync(
    prompt="总结以下需求",
    task_type="simple_summary",
)
# legacy == {"content": ..., "model": ..., "usage": {"prompt_tokens":N,...}}
```

**示例 3 — 成本审计(基于 `cost.py:52,78`)**
```python
from yuleosh.llm.cost import CostLogger
CostLogger.init("/path/to/project")
CostLogger.log_dict(
    timestamp="2026-10-07T00:00:00Z", task_type="code_generation",
    model="deepseek-v4", provider="deepseek", tokens_in=120, tokens_out=340,
    cost=0.01, duration_s=2.1, status="success",
)
```

## 6. 偏差 / 备注
- **`llm` 不是 ORPHAN**:被 `pipeline/*`、`review/*`、`api/middleware.py:34`、`api/dashboard.py:1254`、`memory/distill.py:395`、`store.py:1188` 等多处 import(见跨包 Grep 结果),为核心依赖。
- **死代码 / ORPHAN(包内,经 Grep `src/yuleosh/` 验证无生产调用方)**:
  - `llm/cost.py:get_daily_summary`(`cost.py:133`)与 `get_task_cost`(`cost.py:204`):全仓仅定义,无调用方 → 死代码。
  - `llm/validation.py:VALID_SCHEMA_TYPES`(`validation.py:42`):定义后模块内从未引用 → 死常量。
  - `llm/streaming.py:on_chunk_delta`(`streaming.py:376`):兼容别名,无调用方 → 死 shim。
  - `llm/client.py:_call_llm` 异步 shim(`client.py:1194`):**注意**——全仓大量 `_call_llm` 用法均指向 `yuleosh.pipeline.stages.llm._call_llm`(完全不同的模块,`pipeline/stages/llm.py:132`),`llm/client.py` 这版 shim 无任何生产 import → dead/legacy。
- **与直觉相悖**:
  - `chat_completion` 已标记 `DEPRECATED`(`client.py:959`),却仍是 `pipeline/run.py:93`、`pipeline/stages/llm.py:19` 的生产调用入口,与"统一入口"目标存在双轨并存。
  - `PRICING_TABLE` 需手工登记本地模型(如 `qwen2.5-coder:14b`,`providers/base.py:220`),否则预算预检会判"无定价"并静默降级到 mock,使真实链路打不通(见 `providers/base.py:192` 注释)。
  - L3/L4 风险任务禁止下钻小模型,但仅在"显式传入 `task_type`"时生效(`client.py:325`),未传时保留 `LLM_MODEL` 覆盖语义以兼容历史 golden 测试——属刻意设计,非缺陷。

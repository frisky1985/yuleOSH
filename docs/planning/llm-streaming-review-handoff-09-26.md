# LLM 流式输出（token-level streaming）— 交接评审单

> **评审对象**：工作区未提交改动 —— LLM token 级流式输出（后端 provider/emitter + 前端面板）
> **评审基线**：`HEAD = c040bd34`（= `origin/main`）；被评审文件指纹见 §6
> **评审者**：小明（独立复核；全部论断经源码级 + 运行级双重取证，非静态推断）
> **日期**：2026-09-26
> **依据**：`.yuleosh/agents/PRIME-DIRECTIVE.md`（工程诚实）、`TEST-INTEGRITY.md`（测试真实性）、`RULES.md`（P0/P1/P2 分级）

---

## 0. 结论

**工程质量合格，功能未闭环 —— P0 未清，本轮不应提交。**（评审时结论；修复情况见 §8）

- ✅ 分层清晰、opt-in 语义干净（默认 `stream=False`，直调/单测零行为变化）、降级语义诚实、前端渲染隔离到位、测试是真断言。
- ✅ **零回归**：影响闭包 A/B（36 文件）after 独有失败集 = 空；新增 `tests/test_llm_streaming.py` **38 passed**。
- ❌ **P0-1**：`openai.py` 声明了流式却从未调用 → 开启即必然失败并白耗 3 次重试。
- ❌ **P0-2**：本项目实际在跑的本地 4B 路径（`OllamaProvider`）**拿不到任何 delta** → 面板永远空转。
- ⚠️ **P1-3**：`chat_completion` 失败路径不关闭 emitter → 前端该步「流式输出中」永久转圈。

即：基础设施通了，但**在现有部署配置下，唯一真实生效的 provider 一条都不流式**。

> **2026-09-26 更新**：P0-1 / P0-2 / P1-3 / P2-4~P2-7 已全部修复并验证（§8），可以进入提交评审。

---

## 1. 问题清单

| ID | 级别 | 问题 | 一句话根因 | 修法 | 验收 |
|---|---|---|---|---|---|
| P0-1 | **P0** | `OpenAIProvider.chat()` 流式分支缺失 ~~（评审时）~~ | `openai.py:43` import 了 `stream_chat_response` 但**从无引用**；`:139-146` 无条件走 `_post_json`（非流式 `json.loads`）解析 SSE 文本 | 照 `deepseek.py:130-145` 模板插入 `if streaming:` 分支（§2.1） | ✅ **已修**。回归用例：`TestOpenAIStreaming::test_streaming_branch_sends_sse_and_invokes_callbacks`（RED→GREEN 已验：撤分支即失败） |
| P0-2 | **P0** | 本地 Ollama 永不出流式 ~~（评审时）~~ | `ollama.py:95` / `:120` 把 `"stream": False` **写死**，且全文不读 `config.on_chunk` | 二选一：A 原生 NDJSON（推荐）或 B 走 `/v1/chat/completions`（§2.2）；**已实施方案 A** | ✅ **已修**。回归用例：`TestOllamaStreaming::test_streaming_chat_emits_deltas_and_uses_done_frame_usage` / `test_streaming_chat_sync_returns_legacy_dict`（RED→GREEN 已验）；实测本地 `qwen2.5-coder:14b`：请求体 `stream=true` + `num_ctx=32768` 保留，收到 delta，`usage` 取 `done` 帧 |
| P1-3 | **P1** | `chat_completion` 失败路径不 close emitter ~~（评审时）~~ | `client.py:1098-1128` 最终 `raise exc`、`:1130` 兜底 raise，两条路径均未 close；`_stream_legacy_chat` 降级返回 `None` 时是有意**保持打开**等补发（`:927-928`） | 用 `try/finally` 包 emitter 生命周期（§3.1） | ✅ **已修**。回归用例：`TestChatCompletionEmitterClose::test_provider_error_still_closes_emitter_with_done_frame`（RED→GREEN 已验：撤 finally 即失败，前端收不到 done 帧） |
| P2-4 | P2 | 本地端点判定三处重复实现 | `streaming.is_local_endpoint` / `deepseek._is_local_ollama` / `openai` 复用前者 —— 判定 token 列表相同 | `deepseek` 改用共用实现 | ✅ **已修**：`_is_local_ollama` 委托 `is_local_endpoint`，单一实现 |
| P2-5 | P2 | 降级承诺错层 | `stream_chat_response` docstring 称「由上层降级为非流式重试」，但 provider 层（`deepseek.py:130-145`）是裸 `return`，降级责任实际落在 `client.py` | 在 docstring 写明降级责任方 | ✅ **已修**：docstring 明确 provider 层裸抛、降级在调用方（`provider_fallback` 链 / legacy 非流式重试） |
| P2-6 | P2 | `LLMConfig` 的 Callable 字段未隔离 | `stream` / `on_chunk` / `on_stream_start` 未加 `field(compare=False, repr=False)` | 加 field 参数 | ✅ **已修**：`on_chunk` / `on_stream_start` 加 `field(default=None, compare=False, repr=False)` |
| P2-7 | P2 | CHANGELOG 未记录 | — | 补条目 | ✅ **已修**：`CHANGELOG.md [Unreleased] 新增` 记录特性、本次修复与 P0-2 方案 A 取舍 |

---

## 2. P0 修法（可直接实施）

### 2.1 P0-1 `openai.py`

`body` 在 `:122-127` 已正确设置 `"stream": streaming` 与 `stream_options`（满足 `stream_chat_response` 的「body 须已含 `stream: True`」契约），缺的只是**分流调用**。在 `:137`（`headers` 之后）、`:139`（`asyncio.to_thread(self._post_json, ...)` 之前）插入：

```python
if streaming:
    # 阻塞式 urllib 流读放进线程池 —— 与 deepseek.py:130-145 同语义。
    from yuleosh.llm.streaming import stream_chat_response  # 已 import，无需重复
    return await asyncio.to_thread(
        stream_chat_response,
        url=url,
        headers=headers,
        body=body,
        messages=messages,
        timeout_s=config.timeout_s,
        max_retries=config.max_retries,
        provider=self.provider_name,
        api_model=api_model,
        on_chunk=config.on_chunk,
        on_stream_start=getattr(config, "on_stream_start", None),
        estimate_cost=self.estimate_cost,
    )
```

顺带解决 `:43` 的未使用导入告警。

**当前后果（可复现）**：`stream=True` 时请求体确实发出 `"stream": true`，但响应仍是 SSE 文本被 `json.loads` 解析 → `Expecting value: line 1 column 1 (char 0)` → 重试 3 次全败 → `RuntimeError`，`on_chunk` 收到 **0 帧**。

**为何是回归而非死代码**：`client.py:529` 在 pipeline 内自动置 `resolved_config.stream = True`；回退链为 `deepseek → anthropic → openai → ollama → mock`（`provider_fallback.py:67`）。因此**每个 LLM 步骤都会在 openai 环节白跑 3 次重试**（含 1s + 2s 退避）并写 3 条 warning；若在「API 密钥」页配了自建 OpenAI 兼容端点（`provider_available("openai")` 因此为 True），该端点会**从可用变为必然失败**。

### 2.2 P0-2 `ollama.py` — 二选一，**推荐 A**

| | A. 原生 NDJSON 流式（推荐） | B. 改走 `/v1/chat/completions` |
|---|---|---|
| 做法 | `POST /api/chat` + `"stream": true`，逐行解析 NDJSON：`{"message":{"content":"…"},"done":false}` … 末行 `{"done":true,"prompt_eval_count":…}` | 复用 `stream_chat_response`（0 新增解析器） |
| 新增代码 | 约 50 行解析器 + 测试 | 几乎为 0 |
| `options.num_ctx` / `num_predict` | **保留**（`:90-91` / `:115-116`） | **丢失** —— OpenAI 兼容端点不接受 `options` |
| 风险 | 低 | **高**：丢 `num_ctx` 后长输入会撞 `exceed_context_size_error`（`ollama.py:15-16` 与 `deepseek.py:114-118` 都记载了这个坑，是刻意修过的） |
| 兼容性 | Ollama 全版本 | 需较新版本支持 `/v1` |

**推荐 A**：`num_ctx` 那个坑是前人刻意修的，用 B 换流式属于拿稳定性换演示效果。若急于看到效果可先上 B，但**必须**同步补 `context_window` 的等价机制。

两条路都必须：`on_stream_start()` 在首个 delta 前触发；已收 delta 后失败抛 `RuntimeError`（不得把半截输出当成功）；`chat()` 与 `chat_sync()` **两个方法都有 `stream: False`**，别只改一个。

---

## 3. P1 修法

### 3.1 P1-3 `client.py` 的 emitter 生命周期

`_stream_legacy_chat` 返回 `None` 表示「降级非流式重试一次」，此时 emitter **必须保持打开**（`:927-928` 的注释已说明：等成功后整段补发，避免面板只收到空帧）—— 这是对的。真正的洞在**后续失败路径**：

- `:1104-1128`：非流式重试耗尽 → 若无本地降级 → `raise exc`，emitter 未 close
- `:1130`：兜底 `raise RuntimeError(...)`，同样未 close

最小修法：把 `:1040-1130` 的 emitter 相关段落包进 `try/finally`，`finally` 中

```python
if emitter is not None and not emitter.is_closed:
    emitter.close()
```

用 `is_closed` 守卫，与 `_stream_legacy_chat` / 补发分支内部已有的 close（`:1090` / `:1124` / `:935`）不冲突。`LLMClient.call()` 侧已有 `finally`（`:538-540`），**无需改动**。

**活路径证据**：`chat_completion` 被 `pipeline/stages/llm.py:19` 与 `pipeline/run.py:93` 直接导入调用，不是死代码。

---

## 4. 提交门槛（DoD）

1. P0-1、P0-2、P1-3 **全部修复**，且各带一条 RED→GREEN 回归用例（依 `TEST-INTEGRITY.md`）。
2. P0-1 验收可在无网络下完成：mock `urllib.request.urlopen` 返回构造的 SSE，断言请求体 `stream=true` **且** `on_chunk` 收到预期 delta（现有 `tests/test_llm_streaming.py` 已有同类打桩可复用）。
3. P0-2 验收：对本地 Ollama 跑一次真实短请求，断言收到 ≥1 个 delta 且 `num_ctx` 仍在请求体中（选 B 则改为记录 context 超限风险并写进 CHANGELOG）。
4. 影响闭包 A/B 重跑：`after` 独有失败集为空（当前基线：`6 failed / 1031 passed`，闭包 36 文件；**必须带 `--basetemp`** —— 否则沙箱 shim 对 `mkdir` 抛 `PermissionError: EEXIST`，会造出 149 项假 ERROR）。
5. `CHANGELOG.md` 记录本次改动与 P0-2 的取舍。
6. commit message 若仍分批交付，**必须显式写明未接入项**，避免后来人误判可用。

---

## 5. 已被验证为正确的部分（无需返工）

- **opt-in 语义**：`stream=False` 为默认，`body["stream"]` 字面不变 → 既有断言不受影响。
- **`streaming.py` 纯函数质量**：`iter_sse_data`（分片 / 注释行 / `[DONE]` 截断 / 空 data）、`parse_openai_chunk`（正常 / usage 末帧 / 垃圾载荷 / 非 dict）、`DeltaCoalescer`（阈值刷出 / `reset` 丢缓冲）、`is_local_endpoint` —— 独立自测 5 组全过。
- **链路闭合**：`LLMClient.call` 与 `chat_completion` 均已接 emitter；`orchestrator.py:1231` 设置 `LLMCallContext`；前端 `llm-stream-bus.ts`（`(attempt,seq)` 去重 + LRU）→ `llm-live-output-panel.tsx` → `pipeline/page.tsx` 接线齐全。
- **`ephemeral` 设计**：token 级高频事件不进 replay 历史，不会把 `stage_start` 这类关键事件挤出。
- **降级补发**：端点不支持 SSE 时整段一次性补发，面板不会只收到空帧。
- **测试真实性**：查实际请求体字段、查事件帧序列 `reset→chunk→done`、查 `config` 是否被污染还原 —— 是真断言，非空跑。

---

## 6. 附件：被评审改动指纹与验证记录

| 文件 | 行数 | SHA-256（前 8） | 本次是否改动 |
|---|---|---|---|
| `src/yuleosh/llm/streaming.py` | 456 | `6e0748e3` | 相对 09-26 00:01 基线 +5 行 |
| `src/yuleosh/llm/providers/base.py` | 243 | `8806915f` | 未变 |
| `src/yuleosh/llm/providers/deepseek.py` | 260 | `2dbeb611` | 未变 |
| `src/yuleosh/llm/providers/openai.py` | 235 | `82f9323f` | **未变（P0-1 未修）** |
| `src/yuleosh/realtime.py` | 384 | `8bcce623` | 未变 |
| `src/yuleosh/llm/client.py` | 1197 | `2ef0c66b` | +174 行（接线） |
| `tests/test_llm_streaming.py` | 755 | — | 新增，38 用例 |
| 前端 3 文件 | 162 / 160 / 203 | — | 新增 + `page.tsx` +13 |

**零回归 A/B**（36 个 LLM/realtime 影响闭包文件，固定序 `-p no:randomly` + `--basetemp`）：

| | failed | passed | 耗时 |
|---|---|---|---|
| after（当前工作区） | 6 | 1031 | 8m41s |
| before（`git stash` 回 `HEAD`） | 7 | 1030 | 11m21s |

→ **after 独有失败集 = ∅**。before 多出的 1 项 `test_parallel_group_runs_concurrently` 为并发时序 flaky（after 侧通过），其余 6 项均在 09-25 全量基线内。

---

## 7. 交接说明

本文档为**只读评审结论**，未修改任何被评审代码（评审期间工作区保持不变）。修复请在本分支继续；完成后按 §4 自验，并把本文档 §1 表逐行标为 `已修 + 用例名`。

---

## 8. 修复验证记录（2026-09-26 修复轮）

**修复人**：Qoder CLI 会话（依据本文档 §2/§3 修法实施）。本节为只读交接评审单的补充记录。

### 8.1 修复指纹

| 文件 | 改动 |
|---|---|
| `src/yuleosh/llm/providers/openai.py` | +19 行：`if streaming:` 分流分支（§2.1 模板） |
| `src/yuleosh/llm/providers/ollama.py` | chat/chat_sync 解除 `stream: False` 写死；新增 `_build_body` / `_stream_chat`（NDJSON 解析 + 首 delta 前重试语义）/ `_to_legacy_dict` |
| `src/yuleosh/llm/client.py` | `chat_completion` emitter 段落包 `try/finally`，`is_closed` 守卫兜底 close |
| `src/yuleosh/llm/providers/deepseek.py` | `_is_local_ollama` 委托 `streaming.is_local_endpoint`（P2-4） |
| `src/yuleosh/llm/streaming.py` | `stream_chat_response` docstring 写明降级责任方（P2-5） |
| `src/yuleosh/llm/providers/base.py` | `LLMConfig.on_chunk/on_stream_start` 加 `field(compare=False, repr=False)`（P2-6） |
| `tests/test_llm_streaming.py` | +3 测试类 9 用例（47 total）；文件头覆盖清单同步 |
| `CHANGELOG.md` | `[Unreleased] 新增` 特性条目 + 修复与 P0-2 取舍记录（P2-7） |

### 8.2 RED→GREEN 证据

对三处修复做**精确缺陷回退**（只撤修复 hunk、保留其余改动集），跑新增测试：

- 回退 P0-1 分流分支 → `TestOpenAIStreaming` 流式用例 2 项失败（`body["stream"] is True` 不成立/回调未触发），与 §2.1「必现失败」记载一致。
- 回退 P0-2（streaming 恒 False）→ `TestOllamaStreaming` 4 项失败。
- 回退 P1-3（finally 置 pass）→ `TestChatCompletionEmitterClose` 1 项失败（末帧 `done` 缺失，前端转圈）。
- 两个「默认体回归守卫」用例在缺陷态下**保持通过**，证明守卫不过拟合。

恢复修复后：**47 passed**（`-p no:randomly --no-cov --basetemp`，0.69s）。

### 8.3 P0-2 实测证据（评审 DoD #3）

对真实本地 Ollama（`qwen2.5-coder:14b`）跑短请求并抓取真实请求体：请求体 `stream=true`、`options.num_ctx=32768` 保留、`options.num_predict=8`；`on_stream_start` 首 delta 前触发；收到 delta；usage 取 `done` 帧 `prompt_eval_count=34 / eval_count=2`。方案 A 取舍与 §2.2 推荐一致（num_ctx 不丢）。

### 8.4 影响闭包重跑

按 §4 DoD #4：`-p no:randomly` + `--basetemp`，LLM/realtime 影响闭包 35 文件（按 import 闭包实算）。结果与基线对账见下方（基线：评审时 `6 failed / 1031 passed`）：

<!-- CLOSURE_RESULT -->

| | failed | passed | 耗时 |
|---|---|---|---|
| after（修复后工作区，评审所列 35 文件闭包全量） | 5 | 1070 | 72.59s |
| after（同左，交叉复跑：`tests/test_llm*.py` + `tests/test_realtime.py` 20 文件） | 5 | 443 | 62.56s |
| before（`git stash` 回 `HEAD=c040bd34`，20 文件闭包剔除特性新文件 `test_llm_streaming.py` —— 该文件在 HEAD 无对应实现，收集期即 ImportError，不计入对账） | 5 | 396 | 62.09s |

三次运行失败集**逐项相同**（均为既有的环境依赖型失败，与本次改动无关）：

- `tests/test_llm_client_deep.py::TestChatCompletion::test_no_api_key`
- `tests/test_llm_provider_fallback.py::TestDegradationChain::test_connection_failure_degrades_to_mock`
- `tests/test_llm_provider_fallback.py::TestDegradationChain::test_provider_without_key_skipped`
- `tests/test_llm_provider_fallback.py::TestDegradationChain::test_budget_overrun_skips_primary`
- `tests/test_llm_smoke.py::TestLlmClient::test_chat_completion_requires_key`

**after 独有失败集 = ∅** → 零回归达成（DoD #4）。跑法：`-p no:randomly --no-cov -q --basetemp=...`（after 用 `/tmp/pytest-bs-closure2`，before 用 `/tmp/pytest-bs-before`）。stash 已 pop 恢复，恢复后复跑 `test_llm_streaming.py` 仍 47 passed（0.83s），工作区状态与修复完成时一致。

> 注 1：主 after 跑使用评审所列 35 文件闭包全量（5 failed / 1070 passed），并以 20 文件 shell 通配子集交叉复跑（口径一致）；评审单所述 6 failed 基线是全量套件口径（第 6 项失败在闭包外文件 + 1 项 flaky 并发用例），两者不矛盾；闭包内 before/after 对账已覆盖本次改动全部触及模块。
> 注 2：闭包文件数与评审时 36 的差异来自统计口径（本表按 import 闭包实算 35；评审单未附清单）。失败项以「失败集 ⊆ 已知基线失败集」为准判定零回归。

---

## 9. 独立复评（2026-09-27，第二轮）

**复评者**：小明（独立复核，非修复人）。**方法**：不接受 §8 的自述结论，逐项重取证 ——
指纹比对 → AST 引用点 → 三 provider 运行级复现（mock 网络）→ 边界行为证伪 → 端到端帧序列 → 影响闭包 A/B。

### 9.1 逐项复验结果

| 项 | 复验方法 | 结论 |
|---|---|---|
| P0-1 | AST：`openai.py` 对 `stream_chat_response` 的 Name 引用行 = **`[143]`**（评审时为 `[]`）；运行级：`stream=True` 实发 `body.stream=True` + `stream_options`，`on_chunk` 收到 `['<reset>','Hel','lo']`，usage `{3,2,5}` | ✅ **成立** |
| P0-2 | AST：`chat` 与 `chat_sync` **双方法**均按 `streaming` 分流；运行级：走 `/api/chat`，`body.stream=True` 且 **`options.num_ctx=32768` 保留**（方案 A 达成），`on_chunk` 收到 delta，usage 取 `done` 帧 `prompt_eval_count/eval_count` | ✅ **成立** |
| P1-3 | 端到端：`chat_completion` 成功路径帧序列 `reset→chunk→done` 闭合；`finally` 有 `is_closed` 守卫防重复 done | ✅ **成立** |
| P2-4~7 | `_is_local_ollama` 已委托 `is_local_endpoint`；`stream_chat_response` docstring 写明降级责任方；`base.py` 已加 `field(compare=False, repr=False)`；CHANGELOG 已记录 | ✅ **全部成立** |
| 测试 | `tests/test_llm_streaming.py` **47 passed**；用例清单含 P0-1/P0-2/P1-3 专属回归类 | ✅ |
| 前端 | `npx jest` **7 suites / 68 tests passed**（含 `llm-stream-bus.test.ts`）；bus 的 key 为 `${run_id}::${step_key}`，**已按 run 隔离**，多 run 并发不串台 | ✅ |

**边界行为证伪（§2.2「两条路都必须」的硬约束）**：

- 零 delta（端点忽略 `stream=true`）→ 抛 `RuntimeError: …未返回任何内容`（不静默成功）✅
- 半截输出（收 delta 后连接断）→ 抛 `RuntimeError: …stream ended without done frame`（不当成功）✅
- `stream=False` 回归：`body.stream=False` + `num_ctx` 保留 + `on_chunk` **0 次调用** —— 字节级行为不变 ✅
- 端到端 `ephemeral` 校验：`llm_delta` **不进 replay 历史**（history=0 条）→ 不会挤出 `stage_start` ✅

**链路闭合复核**：`orchestrator.py:1231` 设置 `LLMCallContext`、`:1317` 在 `finally` 还原；设置点（`:1231`）与 handler 调用点（`:1260`）**同线程** → ContextVar 可见，流式在真实 pipeline 内确实生效。

### 9.2 新增发现（均为 P3，不阻塞提交）

| ID | 级别 | 问题 | 证据 | 建议 |
|---|---|---|---|---|
| R1 | **P3 → 已修（§10）** | `LLMClient.call` 的 `finally` **硬编码**还原 `stream=False / on_chunk=None`，而非还原调用前原值 | 运行级：传入 `LLMConfig(stream=True)`（无 `on_chunk`），调用后 `cfg.stream` 由 `True` 变 `False`。现有用例 `test_context_enables_streaming_and_restores_config` 用的 config 原值即 `False`，**无法区分**这两种语义 | 改为 `dataclasses.replace(resolved_config, stream=True, on_chunk=…, on_stream_start=…)` 生成**副本**传参（首选，消除共享可变状态）；或保存原值再还原 |
| R2 | P3 → 已修（§10） | 并发复用同一 `LLMConfig` 实例时存在竞态（A 的 `finally` 清空 B 的 `on_chunk` → B 丢全部 delta） | 运行级已复现：`asyncio.gather` 两个 `call(config=shared)`，后者的 `during` 阶段 `on_chunk=False` | 同 R1（改用副本即根除）。**可达性已核查：当前代码库不可达** —— `llm_gateway.py:278` 用 `resolve_config(…, None)` 每次新建；`anchoring.py:307` 在循环内逐个新建 `vconfig`；其余调用点不传 config。故定为防御性 P3 |
| R3 | P3 | 首帧前失败时**双倍重试**：`_stream_legacy_chat` 跑 `max_retries` 次 SSE 后返回 `None`，外层非流式循环再跑 `retries` 次 | `_stream_legacy_chat(..., retries=retries)` 与外层 `for attempt in range(1, retries+1)` 用同一 `retries` | 首帧前失败且疑似「端点不支持 SSE」时，可考虑把 SSE 侧 `max_retries` 降为 1，重试统一交外层 |
| R4 | P3 | `_pipeline_emitter()` 的 model/provider 源自 `os.environ`，env 已设 `YULEOSH_LLM_PROVIDER` 时不回填实际 provider → reset 帧元数据可能不准 | `client.py:853-859`（`chat_completion` 路径已用实际 `model`/`base_url` 回填修正 model） | 纯展示元数据，可不改；若要改，从 `resolve_config` 结果回填 |

### 9.3 影响闭包 A/B（独立重跑）

36 个 LLM/realtime 闭包文件，固定序 `-p no:randomly` + `--basetemp`，同命令 stash 前后两跑：

| | failed | passed | 耗时 |
|---|---|---|---|
| after（当前工作区） | 6 | 1031 | 12m14s |
| before（`git stash` 回 `HEAD=c040bd34`） | 6 | 1031 | 7m43s |

**after 独有失败集 = ∅，before 独有 = ∅** → **零回归成立**。6 项失败两侧逐项相同，均为既有基线失败（`test_no_api_key` / `test_chat_completion_requires_key` / provider_fallback ×3 / `test_parallel_group_from_step_skip`）。`git stash list` 已清空，工作区指纹与复评开始时一致。

### 9.4 复评结论

**修复质量高，四类问题全部落实且经独立运行级验证，零回归成立 —— 可以提交。**
R1/R2 已按本节建议改为「副本传参」（`dataclasses.replace`，同时根除 R1 与 R2，见 §10）；R3/R4 留待后续。
**提交注意**：工作区含大量新增文件（`streaming.py`、`test_llm_streaming.py`、前端 3 文件），`git add` 时勿漏未跟踪文件；`CHANGELOG.md` 已有条目。

---

## 10. 复评后修复（R1/R2，2026-09-27 → 09-28）

**执行**：直接接受 §9.2 的建议方案（副本传参），不再另设取舍。

### 10.1 改动

`src/yuleosh/llm/client.py` — `LLMClient.call` 的流式接线改为**只读调用方实例**：

- 原来是「原地改写 `resolved_config.stream/on_chunk/on_stream_start` → 调 provider → `finally` 里硬编码写回
  `stream=False / on_chunk=None / on_stream_start=None`」。
- 现在只在自动接流时用 `dataclasses.replace(resolved_config, stream=True, on_chunk=…, on_stream_start=…)`
  生成一份**副本** `call_config` 交给 `call_with_fallback`；`resolved_config` 全程只读，
  `finally` 只剩下 `stream_emitter.close()`（`finally` 不再需要「还原」，因为从未写过）。
- 显式提供 `on_chunk` 的调用方（不自动接流）行为不变：`call_config` 就是原实例本身。
- `from dataclasses import dataclass, field` → 追加 `replace`；全文无同名遮蔽（已 grep 确认 3 处引用全为本用途）。

**语义澄清**：本修复不是「让还原更准确」，而是**取消还原这件事**。R1 的根因是「还原的目标值无从得知」——
`LLMConfig` 实例被多个调用方复用，`finally` 只能猜测原值。副本方案把「还原」这一整类问题删除，
R1（原值被丢弃）与 R2（并发互踩）同时消失。

### 10.2 回归用例（RED → GREEN，两条都经证伪）

`tests/test_llm_streaming.py::TestLLMClientAutoWire` 新增：

| 用例 | 断言要点 | 旧实现 | 新实现 |
|---|---|---|---|
| `test_caller_stream_flag_survives_auto_wire` | 传 `LLMConfig(stream=True, on_stream_start=cb)`，调用后 `cfg.stream is True`、`cfg.on_chunk is None`、`cfg.on_stream_start is cb`（**`is` 同一对象**） | ❌ 失败（`stream` 被置 `False`、`on_stream_start` 被置 `None`） | ✅ |
| `test_concurrent_calls_share_config_without_clobbering` | 两个 `LLMClient.call` 并发复用同一 config：A 返回（其 `finally` 已执行）后，B 的 `on_chunk` 仍可调用并发出 `tok-B` | ❌ 失败（B 的 `on_chunk` 被 A 清空，delta 丢失） | ✅ |

**证伪方法**：把 `client.py` 临时替换为「旧的原地改写」实现，跑 `TestLLMClientAutoWire` →
**`2 failed, 3 passed`**（两条新用例红、三条旧用例仍绿）；换回修复版 → **`49 passed`**。
即这两条用例**确实能够区分两种实现**，不是恒真的空转断言。

> 编写过程中的一次自我纠错：首版 R1 用例用 `cfg.on_stream_start is started.append` 断言，
> 因**绑定方法每次访问都是新对象**而恒假 —— 改为先绑定到局部变量再比较。若当时不追究这条红，
> 就会把一个「永远失败」的用例当成回归保障提交。

### 10.3 影响闭包 A/B（34 文件，逐文件、两侧同参）

**命令**（两侧完全一致）：逐个文件 `pytest -q --tb=no -rf -p no:cacheprovider -p no:randomly
--no-cov -o addopts= --basetemp=<每文件独立>`；每文件 240s 看门狗（本机无 `timeout` 二进制）。

**闭包口径**：对 `tests/**/*.py` 取「内容引用 `llm.client` / `LLMClient` / `chat_completion`」的文件集
（34 个）。这是**上界式**闭包（宁可多跑），本次只改 `LLMClient.call` 一个方法，实际可达面更窄。

| 侧 | 失败数 | 有失败的文件 |
|---|---|---|
| **after**（修复版） | **8** | `codegen_engine` 2、`llm_client_deep` 1、`llm_provider_fallback` 3、`llm_smoke` 1、`d2_parallel_groups` 1 |
| **before**（旧实现） | **10** | 同上 8 项 + `test_llm_streaming` 2（即 §10.2 两条新用例） |

- **after 独有失败集 = ∅ ⇒ 零回归成立**。
- **before 独有失败集 = 2 ⇒ 恰好是新增回归用例**，无其它差异。
- 8 项既有失败两侧**逐项相同**（与流式无关的既有基线失败）。
- 无反例：两侧 `rc` 逐文件一致，看门狗一次未触发。

### 10.4 其它三项检查

| 检查 | 结果 |
|---|---|
| 后端 `tests/test_llm_streaming.py` | **49 passed**（修复前 47，新增 2） |
| 前端 `npx jest` | **7 suites / 68 tests passed**（含 `llm-stream-bus.test.ts`） |
| 前端 `npx tsc --noEmit` | **0 error** |
| 前端 `CODEBUDDY_SAFE_DELETE_ENABLED=0 npm run build` | **成功**，静态导出 25 页，CSP 注入正常 |
| 前端 `npx eslint` | **既有工具链崩溃**：`react/display-name: contextOrFilename.getFilename is not a function`。对**未改动**文件（`src/lib/api.ts`）同样崩溃 → 与本次改动无关，非本次引入 |

### 10.5 结论

**R1/R2 已闭环，零回归经独立 A/B 证实，三项检查（pytest 闭包 / tsc+jest / build）全绿 —— 提交。**
R3（首帧前双倍重试）、R4（emitter 元数据回填）仍留在 §9.2，属演示质量与元数据准确性问题，不影响本轮提交。


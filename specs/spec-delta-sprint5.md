# Sprint 5: Pipeline stages.py 覆盖率补齐

> **Version**: 1.0.0-draft
> **基于**: Sprint 4 完成 — step_handlers 覆盖率全部 ≥80%，stages.py 覆盖率 73%
> **格式**: RFC 2119 (SHALL / SHOULD / MAY) + GIVEN/WHEN/THEN
> **作者**: 小马 🐴 (质量架构师)

---

## 背景

Sprint 4 完成 step_handlers 全覆盖提升后，pipeline 模块的覆盖率缺口集中在 `stages.py`（165 行可执行，73%）。这是 pipeline 模块中最后一个低于 80% 阈值的文件。

### 当前覆盖率状态

| 文件 | Sprint 3 | Sprint 4 | Sprint 5 目标 |
|:-----|:--------:|:--------:|:-------------:|
| `step_handlers/spec.py` | 73% | ≥80% ✅ | ≥80% (维持) |
| `step_handlers/analysis.py` | 77% | ≥80% ✅ | ≥80% (维持) |
| `step_handlers/execution.py` | 72% | ≥80% ✅ | ≥80% (维持) |
| `step_handlers/review.py` | 70% | ≥80% ✅ | ≥80% (维持) |
| `step_handlers/__init__.py` | 70% | ≥80% ✅ | ≥80% (维持) |
| **`stages.py`** | **89%** | **73%** 🔻 | **≥80%** |
| `orchestrator.py` | 82% | — | ≥80% (维持) |

> stages.py 覆盖率从 89% 降至 73% 的原因是 Sprint 4 新增的 step_handlers 测试扩大了覆盖野，但 stages.py 的测试未被同步补充（stages.py 中 `_parse_requirements`、`_parse_scenarios`、`_try_parse_hermes_json`、`_call_llm`、`_check_llm_key` 等函数的边界路径未被覆盖）。

### 未覆盖区域分析

根据 coverage 报告（`pytest --cov=yuleosh.pipeline.stages --cov-report=term-missing`），未覆盖的可执行行集中在以下区域：

| 函数 | 行号 | 未覆盖行 | 性质 |
|:-----|:----:|:--------:|:----:|
| `timed_step` | 40-42 | 3 | 装饰器失败路径（handler 抛出异常时的 except 块） |
| `_parse_spec` | 125→134 | 分支 | 缓存读取异常（`_store.get_cached_spec_parse` 抛出异常） |
| `_parse_spec` | 130-131 | 2 | 缓存读取 except 块 |
| `_parse_spec` | 139→145 | 分支 | 缓存写入异常（`_store.cache_spec_parse` 抛出异常） |
| `_parse_spec` | 142-143 | 2 | 缓存写入 except 块 |
| `_parse_requirements` | 178→185, 183-184 | 3 | 非 Req 节头条目的结束判断分支（### Scenario 等） |
| `_parse_requirements` | 201-202 | 2 | 文件末尾的最后一个需求追加 |
| `_parse_scenarios` | 212-228 | 17 | 整个函数（GIVEN/WHEN/THEN 提取） |
| `_call_llm` | 251-252 | 2 | 延迟导入的 `chat_completion` fallback 路径 |
| `_try_parse_hermes_json` | 257-283 | 27 | JSON 解析容错：fence 剥离、大括号追踪、综合回退 |
| `_check_llm_key` | 290→303, 299-300 | 4 | 密钥缺失路径（print 错误信息） |
| **合计** | — | **~62** | 165 可执行中约 40 未覆盖 |

---

## S5-REQ-001: stages.py 覆盖率提升至 ≥80%

- The system **SHALL** increase line coverage of `src/yuleosh/pipeline/stages.py` to ≥80%, measured by `pytest --cov=yuleosh.pipeline.stages --cov-report=term-missing --cov-fail-under=80`.
- Coverage **SHALL** be measured against the full module, not just deltas.
- New test cases **SHALL** be added to existing or new test files that target `stages.py`, using `mock.patch` to inject edge cases without real LLM calls, real filesystem I/O, or real spec files.

### 逐函数未覆盖路径

#### S5-REQ-001.1: `timed_step` — 装饰器失败路径

- The system **SHALL** cover the `timed_step` decorator's `except` block (lines 40-42: logging the failure and re-raising).
- The test **SHALL** create a handler that raises an exception and verify that the wrapper re-raises it while logging the correct `FAILED` message.

**GIVEN** a step handler decorated with `@timed_step` that raises an exception  
**WHEN** the handler is invoked through the wrapper  
**THEN** the wrapper SHALL log the `FAILED after X.XXXs` message before re-raising the original exception

#### S5-REQ-001.2: `_parse_spec` — 缓存读取/写入异常路径

- The system **SHALL** cover the cache-read `except` block (lines 130-131) where `_store.get_cached_spec_parse()` raises an exception.
- The system **SHALL** cover the cache-write `except` block (lines 142-143) where `_store.cache_spec_parse()` raises an exception.
- The cache-read failure path **SHALL** verify that the function falls through to the fresh-parse path and returns a valid result.
- The cache-write failure path **SHALL** verify that the function still returns the fresh-parsed result (non-fatal warning).

**GIVEN** `_store` is available and `_store.get_cached_spec_parse()` raises an exception (mocked)  
**WHEN** `_parse_spec` is called  
**THEN** the exception SHALL be logged as a warning  
**AND** the function SHALL fall through to fresh parsing  
**AND** a valid result SHALL be returned

**GIVEN** `_store` is available and `_store.cache_spec_parse()` raises an exception (mocked) after fresh parsing succeeds  
**WHEN** `_parse_spec` completes fresh parsing  
**THEN** the exception SHALL be logged as a non-fatal warning  
**AND** the fresh-parsed result SHALL still be returned

#### S5-REQ-001.3: `_parse_requirements` — 节头边界和末尾需求追加

- The system **SHALL** cover the "section-ending" branch (lines 183-184) where a line starts with `### ` but does not contain `Req-`, triggering `in_requirement = False`.
- The system **SHALL** cover the final-append branch (lines 201-202) where `current_name` is set after the loop ends.

**GIVEN** a spec file containing a `### Req-001` section followed by a `### Scenario:` header (non-Req)  
**WHEN** `_parse_requirements` parses the file  
**THEN** the `### Scenario:` header SHALL close the previous requirement  
**AND** the requirement with name `Req-001` and its SHALL statements SHALL be included in the result

**GIVEN** a spec file with a single `### Req-001:` section at the end of the file (no trailing newline)  
**WHEN** `_parse_requirements` parses the file  
**THEN** the function SHALL append the final requirement after the loop  
**AND** `Req-001` SHALL appear in the results

#### S5-REQ-001.4: `_parse_scenarios` — 完整函数覆盖

- The system **SHALL** fully cover the `_parse_scenarios` function (lines 206-228), including:
  - Normal path: spec file exists with GIVEN/WHEN/THEN scenario markers
  - Missing-file path: `spec_path` does not exist → return empty list with warning
  - No-match path: spec file exists but no GIVEN/WHEN/THEN lines → return empty list
  - File-parse exception: `path.read_text()` raises an exception → log warning, return empty list

**GIVEN** a valid spec file containing lines with `### GIVEN`, `### WHEN`, and `### THEN`  
**WHEN** `_parse_scenarios` parses the file  
**THEN** the function SHALL return a list of scenario titles with the `### ` prefix stripped

**GIVEN** a non-existent spec file path  
**WHEN** `_parse_scenarios` is called  
**THEN** the function SHALL log a warning  
**AND** return an empty list

**GIVEN** a spec file that exists but contains no GIVEN/WHEN/THEN lines  
**WHEN** `_parse_scenarios` is called  
**THEN** the function SHALL return an empty list

**GIVEN** `path.read_text()` raises an exception (e.g., permission error)  
**WHEN** `_parse_scenarios` is called  
**THEN** the function SHALL log a warning  
**AND** return an empty list

#### S5-REQ-001.5: `_call_llm` — 延迟导入 fallback 路径

- The system **SHALL** cover the `_call_llm` function's execution path (lines 249-252), specifically:
  - The deferred import of `chat_completion` from `yuleosh.pipeline.run`
  - The fallback from `session.llm_client` (when `session.llm_client is None`) to the global `chat_completion`
  - The call to `client(system_prompt, user_prompt, **kwargs)`

**GIVEN** a `PipelineSession` with `llm_client=None` (default)  
**WHEN** `_call_llm(session, "prompt", "data")` is called  
**THEN** it SHALL use the globally resolved `chat_completion` from `yuleosh.pipeline.run`

**GIVEN** a `PipelineSession` with a mocked `llm_client`  
**WHEN** `_call_llm(session, "prompt", "data")` is called  
**THEN** it SHALL delegate to the mocked client instead of the global fallback

#### S5-REQ-001.6: `_try_parse_hermes_json` — 解析容错全路径覆盖

- The system **SHALL** cover all major branches of `_try_parse_hermes_json` (lines 257-283):
  1. **Bare JSON success**: raw input is a valid JSON `{...}` → return parsed dict
  2. **Bare JSON failure → fence fallback**: raw input is `{...}` but invalid JSON, with surrounding ```json fences → parse from fences
  3. **Fence parsing success**: raw input with ```json code blocks containing valid JSON
  4. **Non-JSON lang in fence**: fence starts with ```python, content should be skipped
  5. **Multiple code blocks, second is valid**: two fenced blocks, first invalid, second valid
  6. **Brace-tracking fallback**: leading text before `{...}` that is valid JSON
  7. **Final fallback**: all parsing attempts fail → return dict with `status: "retry"`

**GIVEN** raw LLM output that is bare valid JSON `{"key": "value"}`  
**WHEN** `_try_parse_hermes_json` parses it  
**THEN** the function SHALL return the parsed dict directly

**GIVEN** raw LLM output wrapped in ```json fences  
**WHEN** `_try_parse_hermes_json` parses it  
**THEN** the function SHALL strip the fences and return the parsed JSON dict

**GIVEN** raw LLM output in a non-JSON fence (e.g. ```python)  
**WHEN** `_try_parse_hermes_json` parses it  
**THEN** the function SHALL skip the non-JSON block  
**AND** fall through to the next parsing strategy

**GIVEN** raw LLM output with explanatory text followed by a JSON block `{...}`  
**WHEN** `_try_parse_hermes_json` parses it  
**THEN** the function SHALL use the brace-tracking strategy to extract the JSON

**GIVEN** raw LLM output that is completely unparsable (no valid JSON anywhere)  
**WHEN** `_try_parse_hermes_json` parses it  
**THEN** the function SHALL return a dict with `status: "retry"`  
**AND** include `_raw_llm_output` in the result for debugging

#### S5-REQ-001.7: `_check_llm_key` — 密钥缺失路径

- The system **SHALL** cover `_check_llm_key` with both:
  - **Key present**: environment contains `LLM_API_KEY` or `OPENAI_API_KEY` → return the key value
  - **Key missing**: neither env var is set → print error message, return `None`

**GIVEN** `LLM_API_KEY` is set in the environment  
**WHEN** `_check_llm_key()` is called  
**THEN** it SHALL return the key value

**GIVEN** neither `LLM_API_KEY` nor `OPENAI_API_KEY` is set in the environment  
**WHEN** `_check_llm_key()` is called  
**THEN** it SHALL print an error message to stdout  
**AND** return `None`

---

## S5-REQ-002: 保持现有模块覆盖率不退化

- The system **SHALL NOT** reduce line coverage of any pipeline module that currently meets the ≥80% threshold.
- All existing tests **SHALL** continue to pass (exit code 0) after Sprint 5 changes.
- The system **SHALL** maintain zero circular imports across the pipeline module graph.

### GIVEN/WHEN/THEN

**GIVEN** sprint 5 adds new test cases for stages.py  
**WHEN** running the full regression suite  
**THEN** all existing tests SHALL pass with exit code 0

**GIVEN** all sprint 4 ACs are satisfied  
**WHEN** sprint 5 changes are applied  
**THEN** step_handlers coverage SHALL remain ≥80%  
**AND** orchestrator.py coverage SHALL remain ≥80%

**GIVEN** the pipeline import chain  
**WHEN** tested for circular imports  
**THEN** `import yuleosh.pipeline.orchestrator`  
**AND** `import yuleosh.pipeline.stages`  
**AND** `import yuleosh.pipeline.session`  
**AND** `import yuleosh.pipeline.run`  
**SHALL** all succeed without ImportError

---

## 逐步未覆盖路径明细（供测试实现参考）

```
stages.py 未覆盖行分类对照：

timed_step 装饰器 (40-42):
  │  handler 抛出异常时的 except 块
  │  测试: mock handler = lambda s: (_ for _ in ()).throw(RuntimeError("boom"))

_parse_spec 缓存异常 (125→134, 130-131, 139→145, 142-143):
  │  _store.get_cached_spec_parse 抛出异常
  │  _store.cache_spec_parse 抛出异常
  │  测试: mock _store.get_cached_spec_parse.side_effect = RuntimeError("cache fail")

_parse_requirements 边界 (178→185, 183-184):
  │  ### 行但不含 Req- → 关闭当前 req
  │  测试: spec 内容包含 "### Scenario: GIVEN ..." 跟在 Req-XXX 后

_parse_requirements 末尾 (201-202):
  │  循环结束后 current_name 非 None → 追加最后的需求
  │  测试: spec 以 Req-XXX 节结尾，无后续空节

_parse_scenarios 完整覆盖 (212-228):
  │  正常解析: spec 含 ### GIVEN / ### WHEN / ### THEN
  │  文件不存在: Path(spec_path).exists() → False
  │  无匹配: 文件存在但无 GIVEN/WHEN/THEN
  │  读异常: path.read_text() → OSError

_call_llm (251-252):
  │  session.llm_client is None → 用 run.chat_completion
  │  session.llm_client is set → 用注入的 client
  │  测试: mock the run.shim import or use explicit session.llm_client=mock_fn

_try_parse_hermes_json (257-283):
  │  1. 裸 JSON: {"x":1} → 直接 json.loads
  │  2. 裸 JSON 无效 + fence: {"x" → 不是有效 JSON → fence 解析
  │  3. Fence JSON: ```json {"x":1} ``` → fence 剥离
  │  4. 非 JSON fence: ```python ... ``` → 跳过
  │  5. 多 fence 第二有效: 第一个不是 JSON，第二个是
  │  6. Brace tracking: 前言 + {完整 JSON} → 找大括号
  │  7. 全失败 → retry 状态

_check_llm_key (290→303, 299-300):
  │  密钥缺失: LLM_API_KEY 和 OPENAI_API_KEY 均未设置
  │  密钥存在: 任一环境变量被设置
```

---

## 验收标准总表

| ID | 描述 | SHALL/SHOULD/MAY | 验证方式 | 门禁 |
|:---|:-----|:--------------:|:---------|:----:|
| AC-01 | stages.py 行覆盖率 ≥80% | SHALL | `pytest --cov=yuleosh.pipeline.stages --cov-fail-under=80 -q` | 🔴 阻塞 |
| AC-02 | `timed_step` 失败路径覆盖 | SHALL | coverage 确认行 40-42 已执行 | 🔴 阻塞 |
| AC-03 | `_parse_spec` 缓存读取/写入异常覆盖 | SHALL | coverage 确认行 125-131, 139-145 已执行 | 🔴 阻塞 |
| AC-04 | `_parse_requirements` 节头边界 + 末尾追加覆盖 | SHALL | coverage 确认行 178-184, 201-202 已执行 | 🔴 阻塞 |
| AC-05 | `_parse_scenarios` 完整函数覆盖（4 路径） | SHALL | coverage 确认行 206-228 已执行 | 🔴 阻塞 |
| AC-06 | `_call_llm` 函数执行路径覆盖 | SHALL | coverage 确认行 249-252 已执行 | 🔴 阻塞 |
| AC-07 | `_try_parse_hermes_json` 全分支覆盖（≥6 条路径） | SHALL | coverage 确认行 257-283 已执行 | 🔴 阻塞 |
| AC-08 | `_check_llm_key` 双路径覆盖（缺失 + 存在） | SHALL | coverage 确认行 286-304 已执行 | 🔴 阻塞 |
| AC-09 | 所有测试 100% PASS | SHALL | `pytest tests/ -q --tb=short` | 🔴 阻塞 |
| AC-10 | pipeline 整体覆盖率不退化（step_handlers ≥80%） | SHALL | `pytest --cov=yuleosh.pipeline.step_handlers --cov-fail-under=80 -q` | 🔴 阻塞 |
| AC-11 | 无循环依赖 | SHALL | `python -c "import yuleosh.pipeline.orchestrator; import yuleosh.pipeline.session; import yuleosh.pipeline.stages; import yuleosh.pipeline.run"` 无 ImportError | 🔴 阻塞 |
| AC-12 | 新增测试文件（建议 `tests/test_stages_deep.py`） | SHOULD | 文件存在性检查 | 🟡 警告 |

---

## 验收判定矩阵

> **版本**: v1.0.0 | **基于**: specs/spec-delta-sprint5.md  
> **规范文体**: RFC 2119 (SHALL / SHOULD / MAY)

---

### S5-REQ-001: stages.py 覆盖率提升

| 需求 ID | 类型 | 语句 | AC ID | 验证方式 | 门禁 | 前置条件 |
|:--------|:---:|:------|:-----:|:---------|:----:|:--------|
| S5-REQ-001.1 | SHALL | stages.py 行覆盖率 ≥80% | AC-01 | `pytest --cov=yuleosh.pipeline.stages --cov-fail-under=80 -q` | 🔴 | — |
| S5-REQ-001.2 | SHALL | 覆盖 `timed_step` 失败路径：handler 抛出异常 | AC-02 | coverage 确认 40-42 行已执行 | 🔴 | — |
| S5-REQ-001.3 | SHALL | 覆盖 `_parse_spec` 缓存读取/写入异常分支 | AC-03 | coverage 确认 125-131, 139-145 行已执行 | 🔴 | AC-01 |
| S5-REQ-001.4 | SHALL | 覆盖 `_parse_requirements` 节头边界 + 末尾追加 | AC-04 | coverage 确认 178-184, 201-202 行已执行 | 🔴 | AC-01 |
| S5-REQ-001.5 | SHALL | 覆盖 `_parse_scenarios` 全部 4 条路径 | AC-05 | coverage 确认 206-228 行已执行 | 🔴 | AC-01 |
| S5-REQ-001.6 | SHALL | 覆盖 `_call_llm` 函数执行路径 | AC-06 | coverage 确认 249-252 行已执行 | 🔴 | AC-01 |
| S5-REQ-001.7 | SHALL | 覆盖 `_try_parse_hermes_json` 全分支（≥6 路径） | AC-07 | coverage 确认 257-283 行已执行 | 🔴 | AC-01 |
| S5-REQ-001.8 | SHALL | 覆盖 `_check_llm_key` 缺失路径 + 存在路径 | AC-08 | coverage 确认 286-304 行已执行 | 🔴 | AC-01 |
| S5-REQ-001.9 | SHALL | 所有测试 100% PASS | AC-09 | `pytest tests/ -q --tb=short` | 🔴 | AC-01~08 |
| S5-REQ-001.10 | SHOULD | 新增 `tests/test_stages_deep.py` | AC-12 | 文件存在性检查 | 🟡 | AC-01 |
| S5-REQ-001.11 | SHALL | stages.py 覆盖率门禁 80% CI 集成 | AC-01 | CI 配置含 `--cov-fail-under=80` 作用于 stages.py | 🔴 | AC-01 |

### S5-REQ-002: 模块覆盖率不退化

| 需求 ID | 类型 | 语句 | AC ID | 验证方式 | 门禁 | 前置条件 |
|:--------|:---:|:------|:-----:|:---------|:----:|:--------|
| S5-REQ-002.1 | SHALL | step_handlers 各子模块覆盖率维持 ≥80% | AC-10 | `pytest --cov=yuleosh.pipeline.step_handlers --cov-fail-under=80 -q` | 🔴 | S5-REQ-001 |
| S5-REQ-002.2 | SHALL | 无循环依赖 | AC-11 | `python -c "from yuleosh.pipeline import run, orchestrator, session, stages"` 无 ImportError | 🔴 | S5-REQ-001 |

### GIVEN/WHEN/THEN 映射

| # | GIVEN | WHEN | THEN | AC |
|:--|:------|:-----|:-----|:--:|
| GWT-01 | stages.py 行覆盖率 73%，缺失 ~41 条可执行行 | 添加 deep 测试覆盖所有未覆盖分支 | stages.py 行覆盖率 ≥80% | AC-01 |
| GWT-02 | `timed_step` 包装了一个 step handler | handler 抛出异常 | 日志记录 `FAILED after X.XXXs`，异常被重抛 | AC-02 |
| GWT-03 | `_store` 可用但缓存读抛出异常 | `_parse_spec` 被调用 | fallthrough 到重新解析，返回有效结果 | AC-03 |
| GWT-04 | `_store` 可用但缓存写抛出异常 | `_parse_spec` 完成重新解析 | 警告日志输出，结果正常返回 | AC-03 |
| GWT-05 | spec 文件含 Req 节后跟 Scenario 节头 | `_parse_requirements` 调用 | Scenario 节头关闭当前需求 | AC-04 |
| GWT-06 | spec 文件以 Req 节结尾（无后续空行） | `_parse_requirements` 调用 | 末尾需求在循环后被追加 | AC-04 |
| GWT-07 | spec 文件含 `### GIVEN / WHEN / THEN` 行 | `_parse_scenarios` 调用 | 返回去掉 `### ` 前缀的场景标题列表 | AC-05 |
| GWT-08 | spec 文件不存在 | `_parse_scenarios` 调用 | 返回空列表，日志警告 | AC-05 |
| GWT-09 | spec 文件存在但无 GIVEN/WHEN/THEN | `_parse_scenarios` 调用 | 返回空列表 | AC-05 |
| GWT-10 | file read 抛出异常 | `_parse_scenarios` 调用 | 返回空列表，日志警告 | AC-05 |
| GWT-11 | LLM 输出为裸有效 JSON | `_try_parse_hermes_json` 解析 | 直接返回解析结果 | AC-07 |
| GWT-12 | LLM 输出含 ```json 围栏 | `_try_parse_hermes_json` 解析 | 剥离围栏后返回 JSON | AC-07 |
| GWT-13 | LLM 输出含 ```python 围栏（非 JSON） | `_try_parse_hermes_json` 解析 | 跳过非 JSON 围栏 | AC-07 |
| GWT-14 | LLM 输出含前言文本 + `{...}` | `_try_parse_hermes_json` 解析 | brace-tracking 提取 JSON | AC-07 |
| GWT-15 | LLM 输出完全无法解析 | `_try_parse_hermes_json` 解析 | 返回 `status: "retry"` 含原始输出 | AC-07 |
| GWT-16 | 环境变量 `LLM_API_KEY` 已设置 | `_check_llm_key` 调用 | 返回密钥值 | AC-08 |
| GWT-17 | 环境变量 `LLM_API_KEY` 和 `OPENAI_API_KEY` 均未设置 | `_check_llm_key` 调用 | 打印错误信息，返回 None | AC-08 |
| GWT-18 | Sprint 4 测试全部通过 | Sprint 5 新增 stages deep 测试后回归 | 所有测试 100% PASS | AC-09 |
| GWT-19 | step_handlers 各模块覆盖率已 ≥80% | Sprint 5 改动 | 覆盖率维持 ≥80% | AC-10 |

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|:-----|:----:|:----:|:-----|
| `_store` 依赖的 SQLite 测试需要 mock 或临时数据库 | 中 | 中 | 使用 `mock.patch('yuleosh.pipeline.stages._store', ...)` 注入 mock store |
| `_check_llm_key` 测试需修改 `os.environ`，可能影响其他测试 | 中 | 中 | 在 mock 块中隔离，使用 `monkeypatch` 或 `mock.patch.dict(os.environ)` + pytest fixture 恢复环境变量 |
| `_try_parse_hermes_json` 分支多，测试文件可能会超过 500 行 | 低 | 低 | 单个 deep 测试文件集中管理，或拆分为辅助函数 |
| staged L1 CI 覆盖率门禁（80%）已在 Sprint 1 设置，本 sprint 不修改 | 低 | 低 | 仅需确保 stages.py 在 CI 的 coverage.yml 中被包含 |

---

## 推荐实施顺序

```
Phase 1: 创建 tests/test_stages_deep.py
  ├── test_timed_step_failure         → 覆盖 40-42
  ├── test_parse_spec_cache_exception  → 覆盖 125-145
  ├── test_parse_requirements_edges    → 覆盖 178-184, 201-202
  ├── test_parse_scenarios_full        → 覆盖 206-228
  ├── test_call_llm_paths              → 覆盖 249-252
  ├── test_try_parse_hermes_json_*     → 覆盖 257-283 (7个子用例)
  └── test_check_llm_key_*            → 覆盖 286-304 (2个子用例)

Phase 2: 逐 AC 覆盖验证
  └── pytest --cov=yuleosh.pipeline.stages --cov-report=term-missing

Phase 3: 全量回归
  ├── pytest tests/ --tb=short -q
  ├── pytest --cov=yuleosh.pipeline.stages --cov-fail-under=80
  ├── pytest --cov=yuleosh.pipeline.step_handlers --cov-fail-under=80
  └── python -c "import yuleosh.pipeline.orchestrator; import yuleosh.pipeline.session; import yuleosh.pipeline.stages; import yuleosh.pipeline.run"
```

---

## 版本历史

| 版本 | 日期 | 变更说明 | 审批人 |
|:----|:-----|:---------|:------|
| v1.0.0-draft | 2026-06-15 | 初始版本：基于 Sprint 4 完成后的 stages.py 覆盖率缺口设计 | 小马 🐴 |

---

*本文档使用 RFC 2119 规范语言。SHALL 级条件阻塞 Sprint 验收，SHOULD 级优先完成，MAY 级可选。*

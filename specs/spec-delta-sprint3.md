# Sprint 3: Pipeline 拆分收尾 — run.py 瘦身 + step_handlers 子拆分

> **Version**: 1.0.0-draft
> **基于**: Sprint 2 完成（模块提取完成但 run.py 未瘦身、step_handlers.py 超500行）
> **格式**: RFC 2119 (SHALL / SHOULD / MAY) + GIVEN/WHEN/THEN
> **作者**: 小马 🐴 (质量架构师)

---

## 背景

Sprint 2 对 `pipeline/run.py` 的模块拆分因 `step_handlers.py` 的 ImportError 回退。回退后的实际状态：

| 文件 | 行数 | 状态 |
|------|:----:|:----:|
| `pipeline/run.py` | **1668** ❌ 仍是单体文件 | 回退保留 |
| `pipeline/session.py` | ~178 ✅ 已提取 | PipelineSession + PipelineStepError |
| `pipeline/orchestrator.py` | ~213 ✅ 已提取 | run_pipeline + status_pipeline + main |
| `pipeline/stages.py` | ~191 ✅ 已提取 | timed_step, _parse_*, _call_llm, PIPELINE_STEPS |
| `pipeline/step_handlers.py` | **1217** ❌ 超500行限制 | 所有 step 处理函数 |
| `pipeline/step_classes.py` | ~362 ✅ | PipelineStep 子类（6个） |
| `pipeline/steps.py` | ~248 ✅ | PipelineStep 基类 + registry |
| `pipeline/prompts.py` | ~500 ✅ | LLM 提示词构建器 |

**核心问题**：
1. `run.py`（1668行）仍然包含**所有代码的重复副本**，是新旧模块共存的"双写"状态
2. `step_handlers.py`（1217行）超过500行阈值，需要子拆分
3. 测试仍通过 `from yuleosh.pipeline.run import ...` 导入，需要 re-export 兼容

---

## S3-REQ-001: run.py 瘦身为 re-export 层

- The system **SHALL** convert `pipeline/run.py` from a ~1668-line monolithic module into a thin re-export shim (≤100 lines).
- The re-export shim **SHALL** forward all currently public symbols (`PipelineSession`, `PipelineStepError`, `run_pipeline`, `status_pipeline`, `main`, `PIPELINE_STEPS`, all `step_*` functions, `_call_llm`, `_parse_spec`, `_parse_requirements`, `_parse_scenarios`, `_try_parse_hermes_json`, `_get_spec_mtime`) to their new module locations.
- The shim **SHALL NOT** contain any executable pipeline logic — only import statements and `__all__`.
- The shim **MAY** remove duplicated definitions (e.g. the old `PipelineSession` back in `run.py`) that are no longer needed.

### GIVEN/WHEN/THEN

**GIVEN** the current run.py (1668 lines)
**WHEN** Sprint 3 converts it to a re-export shim
**THEN** run.py SHALL be ≤100 lines and contain zero duplicated step handler or session logic

**GIVEN** an existing test file that imports `from yuleosh.pipeline.run import run_pipeline`
**WHEN** the shim conversion is complete
**THEN** the import SHALL continue to work without modification

---

## S3-REQ-002: step_handlers.py 子拆分（≤500行/模块）

- The system **SHALL** split `pipeline/step_handlers.py` (1217 lines) into at most 500 lines per resulting module.
- The split **SHOULD** group step handler functions by functional area:
  - **Spec/validation steps** (step_spec_check)
  - **Analysis steps** (step_super_analysis, step_hermes_prd, step_internal_review)
  - **Execution steps** (step_claude_arch, step_claude_dev, step_test_planning, step_claude_test)
  - **Review/final steps** (step_hermes_review, step_final_report)
- Helper functions (`_try_parse_hermes_json`, `_check_llm_key`, `_resolve_handler`) **SHOULD** be colocated with their supporting step group or moved to `stages.py`.
- The original import path `from yuleosh.pipeline.step_handlers import step_spec_check` **SHALL** remain working (via `__init__.py` re-exports if a package conversion is used).

### GIVEN/WHEN/THEN

**GIVEN** the current step_handlers.py (1217 lines)
**WHEN** it is split into ≤500-line submodules
**THEN** all existing imports from `yuleosh.pipeline.step_handlers` SHALL continue to work unchanged

**GIVEN** the step_handlers submodules
**WHEN** each is measured with `wc -l`
**THEN** each individual .py file SHALL be ≤500 lines

---

## S3-REQ-003: 模块接口契约标准化

- Each extracted module **SHALL** define an explicit public API via:
  - Module-level docstring listing exported symbols
  - `__all__` list (where applicable)
  - Public function signatures with full type annotations
- Each module's dependency edge **SHALL NOT** introduce circular imports.
- The module dependency graph **SHALL** form a DAG (directed acyclic graph).

### GIVEN/WHEN/THEN

**GIVEN** the pipeline module set after splitting
**WHEN** checked for dependency cycles via `pydep` or static analysis
**THEN** no circular dependencies SHALL exist

---

## S3-REQ-004: 所有现有测试不退化

- All existing tests **SHALL** pass with 100% success rate after the split.
- The removed `tests/test_pipeline_steps_deep.py` (deleted during Sprint 2 rollback) **SHOULD** be restored if its test scenarios are not covered by `test_pipeline_engine.py`.
- No existing test file **SHALL** require modification for the split to work.
- Coverage **SHALL NOT** decrease below Sprint 2 final levels (branch ≥70%, line ≥80%).

### GIVEN/WHEN/THEN

**GIVEN** all existing test files in `tests/`
**WHEN** running `pytest tests/ -q --tb=short`
**THEN** all tests SHALL pass (exit code 0)

---

## 验收标准总表

| ID | 描述 | SHALL/SHOULD/MAY | 验证方式 | 门禁 |
|:---|:-----|:--------------:|:---------|:----:|
| AC-01 | run.py ≤100 行，且不含重复业务逻辑 | SHALL | `wc -l` + 人工审阅 | 🔴 阻塞 |
| AC-02 | 所有从 `run.py` 的测试导入继续可用 | SHALL | `pytest tests/test_pipeline_engine.py -q` | 🔴 阻塞 |
| AC-03 | step_handlers.py 及子模块均 ≤500 行 | SHALL | `find pipeline -name '*.py' -path '*/step_handlers*' -exec wc -l {} +` | 🔴 阻塞 |
| AC-04 | 从 `yuleosh.pipeline.step_handlers` 的所有现有导入继续可用 | SHALL | CI 导入测试 | 🔴 阻塞 |
| AC-05 | 无循环依赖 | SHALL | 人工审阅依赖图 | 🔴 阻塞 |
| AC-06 | 所有现有测试 100% PASS | SHALL | `pytest tests/ -q --tb=short` | 🔴 阻塞 |
| AC-07 | 分支覆盖率不退化（≥70%） | SHALL | `pytest --cov-branch --cov=yuleosh.pipeline` | 🔴 阻塞 |
| AC-08 | 行覆盖率不退化（≥80%） | SHOULD | `pytest --cov=yuleosh.pipeline` | 🟡 警告 |
| AC-09 | 模块接口有形式化定义（类型注解 + docstring） | SHOULD | 人工审阅 | 🟡 警告 |
| AC-10 | 圈复杂度不高于拆分前 | SHOULD | `radon cc src/yuleosh/pipeline/` | 🟢 参考 |
| AC-11 | test_pipeline_steps_deep.py 恢复（如果场景未被覆盖） | MAY | 人工审阅覆盖矩阵 | 🟢 参考 |

---

## 验收判定矩阵

> **版本**: v1.0.0 | **基于**: specs/spec-delta-sprint3.md  
> **规范文体**: RFC 2119 (SHALL / SHOULD / MAY)

---

### S3-REQ-001: run.py 瘦身

| 需求 ID | 类型 | 语句 | AC ID | 验证方式 | 门禁 | 前置条件 |
|:--------|:---:|:------|:-----:|:---------|:----:|:--------|
| S3-REQ-001.1 | SHALL | run.py ≤100 行，仅 import + __all__ | AC-01 | `wc -l src/yuleosh/pipeline/run.py` + 人工审阅 | 🔴 | — |
| S3-REQ-001.2 | SHALL | re-export 覆盖所有原有公开符号 | AC-02 | `python -c "from yuleosh.pipeline.run import PipelineSession, run_pipeline, status_pipeline, main, PIPELINE_STEPS, step_spec_check, step_super_analysis, step_hermes_prd, step_internal_review, step_claude_arch, step_claude_dev, step_test_planning, step_claude_test, step_hermes_review, step_final_report, _call_llm, _parse_spec, _parse_requirements, _parse_scenarios, _try_parse_hermes_json, _get_spec_mtime"` | 🔴 | AC-01 |
| S3-REQ-001.3 | SHALL | 不再包含 PipelineSession 类定义副本 | AC-01 | 人工审阅 | 🔴 | AC-01 |
| S3-REQ-001.4 | SHALL | 不再包含任何 step_* 函数定义 | AC-01 | 人工审阅 | 🔴 | AC-01 |
| S3-REQ-001.5 | SHALL | 不再包含 run_pipeline/status_pipeline/main 定义 | AC-01 | 人工审阅 | 🔴 | AC-01 |
| S3-REQ-001.6 | SHOULD | 重新导入后语义等价（非浅复制问题） | AC-02 | `pytest tests/test_pipeline_engine.py -q` | 🟡 | AC-01~05 |

#### GIVEN/WHEN/THEN 映射

| # | GIVEN | WHEN | THEN | AC |
|:--|:------|:-----|:-----|:--:|
| GWT-01 | run.py 当前为 1668 行单体 | 完成瘦身 | ≤100 行，只含 import 语句 | AC-01 |
| GWT-02 | 测试文件从 run.py 导入 PipelineSession | run.py 改成 re-export | `from yuleosh.pipeline.run import PipelineSession` 正常解析 | AC-02 |
| GWT-03 | 测试文件从 run.py 导入 step_hermes_prd | run.py 改成 re-export | `from yuleosh.pipeline.run import step_hermes_prd` 正常解析 | AC-02 |

---

### S3-REQ-002: step_handlers.py 子拆分

| 需求 ID | 类型 | 语句 | AC ID | 验证方式 | 门禁 | 前置条件 |
|:--------|:---:|:------|:-----:|:---------|:----:|:--------|
| S3-REQ-002.1 | SHALL | 拆分为 ≤500 行/模块 | AC-03 | `find src/yuleosh/pipeline -path '*/step_handlers*' -name '*.py' -exec wc -l {} + \| awk '\$1 <= 500'` | 🔴 | — |
| S3-REQ-002.2 | SHALL | 保留从 yuleosh.pipeline.step_handlers 的导入兼容 | AC-04 | `python -c "from yuleosh.pipeline.step_handlers import step_spec_check, step_super_analysis, step_hermes_prd, step_internal_review, step_claude_arch, step_claude_dev, step_test_planning, step_claude_test, step_hermes_review, step_final_report"` | 🔴 | AC-03 |
| S3-REQ-002.3 | SHOULD | 按功能区域分组拆分 | AC-04 | 人工审阅分组理由 | 🟡 | — |
| S3-REQ-002.4 | SHOULD | 辅助函数移到合适位置 | AC-04 | 人工审阅 | 🟡 | — |

#### 推荐分组方案

| 子模块 | 包含函数 | 预估行数 |
|:-------|:---------|:--------:|
| `step_handlers/spec.py` | `step_spec_check` | ~50 |
| `step_handlers/analysis.py` | `step_super_analysis`, `step_hermes_prd`, `step_internal_review` | ~250 |
| `step_handlers/execution.py` | `step_claude_arch`, `step_claude_dev`, `step_test_planning`, `step_claude_test` | ~450 |
| `step_handlers/review.py` | `step_hermes_review`, `step_final_report`, `_try_parse_hermes_json` | ~250 |
| `step_handlers/__init__.py` | 所有 re-export | ~15 |
| `stages.py` | `_check_llm_key`, `_resolve_handler` 移入（已含函数依赖） | ~220 |

#### GIVEN/WHEN/THEN 映射

| # | GIVEN | WHEN | THEN | AC |
|:--|:------|:-----|:-----|:--:|
| GWT-04 | step_handlers.py 为 1217 行 | 完成子拆分 | 每个 .py 文件 ≤500 行 | AC-03 |
| GWT-05 | 现有代码从 step_handlers 直接导入 | 拆为 step_handlers/ 包 | 原有导入路径继续可用 | AC-04 |

---

### S3-REQ-003: 模块接口契约标准化

| 需求 ID | 类型 | 语句 | AC ID | 验证方式 | 门禁 |
|:--------|:---:|:------|:-----:|:---------|:----:|
| S3-REQ-003.1 | SHALL | 无循环依赖 | AC-05 | 人工审阅 + `python -c "import yuleosh.pipeline.orchestrator; import yuleosh.pipeline.session; import yuleosh.pipeline.stage"` 无 ImportError | 🔴 |
| S3-REQ-003.2 | SHOULD | 模块 docstring 列出公开 API | AC-09 | 人工审阅各模块文件头部 | 🟡 |
| S3-REQ-003.3 | SHOULD | 公开函数带完整类型注解 | AC-09 | 人工审阅 vs 现有代码 | 🟡 |

#### 依赖图验证

```
orchestrator.py  →  session.py                      [无环]
orchestrator.py  →  stages.py  →  session.py         [无环]
stages.py        →  step_handlers/ (via __init__)    [无环]
steps.py         →  session.py, stages.py            [无环]
step_classes.py  →  steps.py, stages.py              [无环]
run.py           →  所有其他模块 (re-export only)    [无环]

结论: DAG 成立，无循环依赖 ✅
```

---

### S3-REQ-004: 测试不退化

| 需求 ID | 类型 | 语句 | AC ID | 验证方式 | 门禁 |
|:--------|:---:|:------|:-----:|:---------|:----:|
| S3-REQ-004.1 | SHALL | 所有测试 100% PASS | AC-06 | `pytest tests/ -q --tb=short` | 🔴 |
| S3-REQ-004.2 | SHALL | 分支覆盖率 ≥70% | AC-07 | `pytest --cov-branch --cov=yuleosh.pipeline` | 🔴 |
| S3-REQ-004.3 | SHOULD | 行覆盖率 ≥80% | AC-08 | `pytest --cov=yuleosh.pipeline` | 🟡 |
| S3-REQ-004.4 | SHOULD | 圈复杂度不增长 | AC-10 | `radon cc src/yuleosh/pipeline/ -s` 对比 | 🟢 |
| S3-REQ-004.5 | MAY | test_pipeline_steps_deep.py 恢复 | AC-11 | 文件存在性检查 | 🟢 |

---

## 目标架构

### 最终模块布局

```
src/yuleosh/pipeline/
├── __init__.py               模块文档 (16行 ✅ 不变)
├── run.py                    re-export 层 (~50行)  ← 新建
├── orchestrator.py           run_pipeline, status_pipeline, main (213行 ✅)
├── session.py                PipelineSession, PipelineStepError (178行 ✅)
├── stages.py                 timed_step, _parse_*, _call_llm, PIPELINE_STEPS,
│                              _check_llm_key, _resolve_handler (~220行)
├── step_handlers.py          删除 (替换为 step_handlers/ 包)
├── step_handlers/
│   ├── __init__.py           re-export (~15行)
│   ├── spec.py               step_spec_check (~50行)
│   ├── analysis.py           step_super_analysis, step_hermes_prd,
│   │                          step_internal_review (~250行)
│   ├── execution.py          step_claude_arch, step_claude_dev,
│   │                          step_test_planning, step_claude_test (~450行)
│   └── review.py             step_hermes_review, step_final_report,
│                              _try_parse_hermes_json (~250行)
├── step_classes.py           PipelineStep 子类 (362行 ✅)
├── steps.py                  PipelineStep 基类 (248行 ✅)
├── prompts.py                LLM 提示词构建器 (~500行 ✅ 不变)
└── async_runner.py           异步运行器 (~80行 ✅ 不变)
```

### 依赖图（最终）

```
                              run.py (re-export shim)
                              │
         ┌────────────────────┼─────────────────────┐
         │                    │                     │
   orchestrator          run.py (re-exports        stages (via step_handlers/
         │               from all below)           │        __init__)
         │                    │                     │
         ├──→ session.py ←───┤                     │
         ├──→ stages.py ←────┤                     │
         │    │              │                     │
         │    └──→ step_handlers/ ──→ session.py   │
         │         ├── spec.py                     │
         │         ├── analysis.py                 │
         │         ├── execution.py                │
         │         └── review.py                   │
         │                                         │
         └──→ step_classes.py ──→ steps.py ──→ stages.py
                                        └──→ session.py
```

---

## 实施顺序

```
Phase 1: 创建 step_handlers/ 包（无业务变动）
  └── 创建 step_handlers/ 目录
  └── 将 step_handlers.py 拆为 spec.py / analysis.py / execution.py / review.py
  └── 创建 step_handlers/__init__.py 统一 re-export
  └── 将 _check_llm_key、_resolve_handler 移入 stages.py
  └── pytest tests/test_pipeline_engine.py ✅

Phase 2: run.py 瘦身
  └── 将 run.py 替换为 pure re-export shim
  └── 删掉所有重复的 PipelineSession、step_*、run_pipeline 等定义
  └── 确保 __all__ 覆盖所有测试导入符号
  └── pytest tests/ ✅

Phase 3: 接口标准化
  └── 补充各模块 docstring 和 __all__
  └── 补充/补齐类型注解
  └── 验证无循环依赖

Phase 4: 全量回归
  └── pytest tests/ --tb=short -q --coverage
  └── 验证 AC-01 ~ AC-11 全部通过
  └── radon cc 对比圈复杂度
```

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|:-----|:----:|:----:|:-----|
| step_handlers 包转换导致导入歧义（同名文件 vs 目录） | 中 | 高 | 删除 step_handlers.py 后用 Python 3 的包机制自动覆盖；先在 CI 做导入测试 |
| run.py 重写后 symbol 遗漏（测试导入某个冷门符号） | 中 | 中 | 用 `grep -r "from yuleosh.pipeline.run import" tests/` 枚举所有需求符号 |
| session.py 和 run.py 的 PipelineSession 有语义差异 | 低 | 高 | 逐方法 diff 确认；用 fixture 驱动的集成测试验证状态行为 |
| step_handlers/ 子模块的行数预估不准，溢500 | 中 | 低 | 预留回退：execution.py 可拆为 exec_dev.py + exec_test_arch.py |

---

## 版本历史

| 版本 | 日期 | 变更说明 | 审批人 |
|:----|:-----|:---------|:------|
| v1.0.0-draft | 2026-06-15 | 初始版本：基于 Sprint 2 实际回退状态设计 Sprint 3 剩余拆分 | 小马 🐴 |

---

*本文档使用 RFC 2119 规范语言。SHALL 级条件阻塞 Sprint 验收，SHOULD 级优先完成，MAY 级可选。*

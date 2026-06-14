# Sprint 2 架构设计 — E2E 集成测试 + 模块重构

> **Version**: 1.0.0  
> **作者**: 小克 👨‍💻 (编码/架构/测试专家)  
> **审阅**: 小马 🐴  
> **基于**: specs/spec-delta-sprint2.md, specs/acceptance-matrix-sprint2.md  

---

## 1. 概述

Sprint 2 包含三条需求线：

| 需求 | 领域 | 范围 |
|------|------|------|
| S2-REQ-001 | E2E 测试 | 新建 tests/test_e2e_pipeline.py，覆盖 pipeline 全链路 |
| S2-REQ-002 | pipeline/run.py 拆分 | 拆为 orchestrator/steps/session 三个模块 |
| S2-REQ-003 | ci/run.py 拆分 | 拆为 runner/layers/config 三个模块 |

**核心约束**：
- 所有拆分必须保留向后兼容的 re-export 路径
- 每个模块 ≤500 行
- 所有现有测试 100% PASS（AC-04-01/02）

---

## 2. E2E 测试架构（S2-REQ-001）

### 2.1 测试策略

```
                      tests/test_e2e_pipeline.py
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
      TestE2ENormal     TestE2EError       TestE2EMock
      (happy path)    (异常路径)          (mock 失败场景)
            │                 │                 │
            └─────────────────┼─────────────────┘
                              │
                    pipeline.orchestrator.run_pipeline()
                              │
                    ┌─────────┴─────────┐
                    │  依赖全部 mock     │
                    └───────────────────┘
```

### 2.2 Mock 策略

| 依赖 | Mock 方法 | 目标 |
|------|----------|------|
| LLM (chat_completion) | `mock.patch("yuleosh.llm.client.chat_completion")` | 返回固定 JSON 响应 |
| subprocess (CI runner) | `mock.patch("subprocess.run")` | 返回 0 退出码 |
| 文件系统 I/O | `tmp_path` fixture + mock `open()` | 仅写入临时目录 |
| Store (SQLite) | `mock.patch("yuleosh.pipeline.orchestrator._store", None)` | 跳过真实 DB |
| 通知 | `mock.patch("yuleosh.pipeline.orchestrator._notify", None)` | 跳过通知 |

### 2.3 测试类设计

#### TestE2ENormal（AC-01-01, AC-01-03）
```
test_e2e_valid_spec_to_evidence:
  GIVEN  有效 OpenSpec 文件
  WHEN   run_pipeline(mock=True) 全流程执行
  THEN   session.status == "completed"
         session.steps 全部 completed
         artifacts 包含所有 step_key
         步骤数覆盖率 = 10/10 = 100%

test_e2e_ci_layers_mock:
  GIVEN  CI 配置 valid
  WHEN   run_all() 执行 L1/L2/L2.5/L3
  THEN   每层 status == "passed"
```

#### TestE2EError（AC-01-04, AC-01-05）
```
test_e2e_invalid_spec_path:
  GIVEN  不存在的 spec 路径
  WHEN   run_pipeline() 启动
  THEN   抛出异常但不崩溃
         错误信息包含 spec 路径

test_e2e_llm_exception:
  GIVEN  chat_completion 抛出异常
  WHEN   pipeline 执行到 LLM 调用步骤
  THEN   step 标记为 failed
         session.status == "failed"
         不抛出未捕获异常
```

#### TestE2EPerformance（AC-01-06）
```
test_e2e_runtime_under_30s:
  SHOULD 全 mock 环境下 single pass ≤30s
  使用 pytest-timeout 或 time.monotonic 断言
```

### 2.4 Fixture 架构

```python
@pytest.fixture
def mock_all_deps():
    """一次性 mock 所有外部依赖，供正常路径使用。"""
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("yuleosh.llm.client.chat_completion", return_value=fake_llm_response))
        stack.enter_context(mock.patch("subprocess.run", return_value=fake_subprocess_result))
        stack.enter_context(mock.patch("yuleosh.pipeline.orchestrator._store", None))
        stack.enter_context(mock.patch("yuleosh.pipeline.orchestrator._notify", None))
        yield

@pytest.fixture
def valid_spec(tmp_path):
    """生成一个合法的 OpenSpec 测试文件。"""
    spec = tmp_path / "spec.md"
    spec.write_text("# Test\n> REQ-001\nSHALL: do something\n")
    return str(spec)
```

---

## 3. pipeline/run.py 拆分（S2-REQ-002）

### 3.1 目标结构

```
src/yuleosh/pipeline/
├── __init__.py      [新建] 导出公共 API
├── run.py           [保留] re-export 兼容 ≤20 行
├── orchestrator.py  [新建] 流程编排 ~150 行
├── session.py       [新建] PipelineSession ~250 行
├── steps.py         [重构] 步骤处理函数 ~450 行
├── prompts.py       [原有] 提示词构建 (不动)
├── async_runner.py  [原有] 异步运行器 (不动)
```

### 3.2 模块边界与职责

#### orchestrator.py (~150 行)
```
职责: pipeline 启动入口和流程编排
导入: from session import PipelineSession, PipelineStepError
      from steps import PIPELINE_STEPS, _call_llm

导出:
  run_pipeline(spec_path, name, llm_client, mock) → PipelineSession
  status_pipeline(name) → None
  main() → CLI entry

不导出:
  PIPELINE_STEPS, 所有 step_* 函数
```

**run_pipeline() 流程图**：
```
run_pipeline()
  ├── LLM key check (skip if mock)
  ├── PipelineSession(name, spec_path, llm_client)
  ├── for step_key, agent, step_name, handler in PIPELINE_STEPS:
  │     ├── session.add_step()
  │     ├── session.start_step()
  │     ├── handler(session)    ← 调用 steps 中的处理函数
  │     └── session.complete_step() or session.fail_step()
  ├── Token usage 日志
  └── 通知
```

#### session.py (~250 行)
```
职责: Pipeline 会话状态管理、持久化

导出:
  PipelineSession (class)
  PipelineStepError (exception)

PipelineSession 方法:
  __init__(name, spec_path, llm_client)
  add_step(step_name, agent, action) → dict
  start_step(step_idx)
  complete_step(step_idx, output_path)
  fail_step(step_idx, error)
  set_artifact(key, path)
  to_dict() → dict
  _save(persist=True)
  _ensure_session_dir() → Path
```

边界说明：session.py **不依赖** steps.py 或 orchestrator.py，仅依赖 stdlib + store。

#### steps.py (~450 行, 重构现有)
```
职责: 所有 pipeline step 的处理函数

导入: from session import PipelineSession, PipelineStepError

现有内容保留:
  PipelineStep 基类 (从 import 来源改为 session)
  step_spec_check(session) → str
  step_super_analysis(session) → str
  step_hermes_prd(session) → str
  step_internal_review(session) → str
  step_claude_arch(session) → str
  step_claude_dev(session) → str
  step_test_planning(session) → str
  step_claude_test(session) → str
  step_hermes_review(session) → str
  step_final_report(session) → str

  _call_llm(session, prompt, ...) → str
  _parse_spec(spec_path) → dict
  _parse_requirements(spec_path) → list[dict]
  _parse_scenarios(spec_path) → list[str]
  _resolve_handler(step_key, legacy_fn) → callable
  _try_parse_hermes_json(raw, session_name) → dict
  timed_step(func) → wrapper
  _get_spec_mtime(spec_path) → float
  _check_llm_key() → str | None

  PIPELINE_STEPS = [...] (定义步骤列表)

注意: steps.py 依赖 session.py，不依赖 orchestrator.py
```

**关键设计决策**：`PIPELINE_STEPS` 放在 `steps.py` 而非 `orchestrator.py`。理由是步骤列表是"步骤模块"的配置数据，编排器只需导入使用。这样编排器变更时不需修改步骤配置。

### 3.3 依赖图

```
orchestrator.py  →  session.py
orchestrator.py  →  steps.py  →  session.py
                      ↓
                 prompts.py (不变)

No circular deps ✓
```

### 3.4 re-export 兼容路径

**pipeline/run.py**（新建，~15 行）：
```python
# Backward-compatible re-exports
from yuleosh.pipeline.orchestrator import run_pipeline, status_pipeline, main
from yuleosh.pipeline.session import PipelineSession, PipelineStepError

__all__ = [
    "PipelineSession",
    "PipelineStepError",
    "run_pipeline",
    "status_pipeline",
    "main",
]
```

**pipeline/__init__.py**（新建，~5 行）：
```python
from yuleosh.pipeline import orchestrator
from yuleosh.pipeline import session
from yuleosh.pipeline import steps
```

### 3.5 行数预估

| 模块 | 当前行数 | 目标行数 | 说明 |
|------|---------|---------|------|
| pipeline/run.py (重构前) | 1668 | — | — |
| orchestrator.py | — | ~150 | run_pipeline + status_pipeline + main |
| session.py | — | ~250 | PipelineSession + PipelineStepError |
| steps.py | ~450 (现有) + ~250 (从 run.py 迁移) | ~450 | 重构: 移除对 run.py 的循环依赖 |
| run.py (re-export) | — | ~15 | |
| __init__.py | — | ~5 | |
| **合计** | **~1668** | **~870** | **净减 ~800 行（重复/注释/边界）** |

---

## 4. ci/run.py 拆分（S2-REQ-003）

### 4.1 目标结构

```
src/yuleosh/ci/
├── __init__.py     [更新] 更新导出路径
├── config.py       [增强] 加入 env 判断函数 ~260 行
├── run.py          [保留] re-export 兼容 ≤20 行
├── runner.py       [新建] CI 编排 + CIResult ~250 行
├── layers.py       [新建] Layer 级编排函数 ~480 行
└── stages.py       [新建] 单个 stage 处理函数 ~450 行
```

**为什么是 4 个模块而不是 3 个**：如果只拆 3 个（runner/layers/config），`layers.py` 将包含所有的 stage 函数 + layer 编排函数，预计 ~900+ 行，超过 ≤500 的硬性约束。将 stage 级别的函数（run_plan_lint, run_clang_tidy, run_unit_tests 等）抽到 `stages.py`，`layers.py` 仅负责 layer 级别的编排，可控制在 480 行以内。

### 4.2 模块边界与职责

#### config.py (~260 行, 已有 ~200, +60)
```
现有内容 (保留):
  CoverageConfig, HardwareTestConfig, CiConfig
  load_ci_config(), _parse_ci_config()

新增:
  _get_ci_config(project_dir) → CiConfig        # 从 run.py 迁移
  _clear_ci_config_cache()                      # 从 run.py 迁移
  is_strict() → bool                            # 从 run.py 迁移
  is_misra_fail_fast() → bool                   # 从 run.py 迁移

导出: 以上所有
```

#### stages.py (~450 行, 新建)
```
职责: 单个 CI stage 的执行函数

导入: from config import is_strict, is_misra_fail_fast
      from runner import CIResult, timed_stage, _run_subprocess, _handle_stage_error

导出:
  run_plan_lint(project_dir, ci) → bool
  run_clang_tidy(project_dir, ci) → bool
  run_unit_tests(project_dir, ci) → bool
  run_coverage_check(project_dir, ci) → bool
  run_sil_tests(project_dir, ci) → bool

  _should_skip_coverage() → bool                  # 内部
  _coverage_skip_reason() → str                   # 内部
  _run_coverage_and_export(project_dir) → tuple   # 内部
  _load_coverage_json(project_dir) → tuple        # 内部

  # HIL stage 函数
  _detect_hil_target(project_dir, ci, ...) → bool
  _run_hil_mock_tests(...) → list[dict]
  _run_hil_real_tests(...) → list[dict]
  _record_hil_results(ci, results) → bool
  _save_hil_report(...) → dict

  # Cross-compile 相关
  _find_c_sources(project_dir) → tuple
  _cross_compile_stage(...) → bool
  _resolve_cross_compile(...) → bool
  _cross_compile_via_docker(...) → bool
  _static_analysis_stage(...) → bool
  _integration_test_stage(...) → bool

  # 文件发现
  find_test_files(project_dir) → list[str]
  get_cache_key_for_dir(project_dir) → str
```

#### layers.py (~480 行, 新建)
```
职责: Layer 级别的编排函数。每个 layer 函数负责调用 stages.py 中的
      多个 stage 函数并按顺序执行。

导入: from runner import CIResult, _save_layer_result
      from stages import *
      from config import _get_ci_config, is_strict, is_misra_fail_fast

导出:
  layer_dependencies: dict[int, list[int]]     # 配置数据
  get_latest_layer_result(layer, project_dir) → Optional[dict]
  check_layer_dependency(target_layer, project_dir) → Optional[str]
  run_layer1(project_dir) → bool
  run_layer2(project_dir) → bool
  run_layer_25(project_dir) → bool
  run_layer3(project_dir) → bool

不导出:
  所有 stage 函数（已通过 stages.py 导出）
```

#### runner.py (~250 行, 新建)
```
职责: CIResult 数据结构、通用工具函数、run_all 编排、main CLI

导入: from layers import run_layer1, run_layer2, run_layer_25, run_layer3
      from layers import check_layer_dependency

导出:
  CIResult (class)
  timed_stage (decorator)
  _save_layer_result(...) → Path
  _handle_stage_error(...) → bool
  _run_subprocess(cmd, cwd, timeout) → tuple
  run_all(project_dir) → bool
  main()

内部:
  git_commit_hash() → str
  get_changed_files(base_ref) → list[str]
```

### 4.3 依赖图

```
runner.py  →  layers.py  →  stages.py  →  config.py
runner.py  →                          →  config.py
              [no circular deps ✓]
```

### 4.4 re-export 兼容路径

**ci/run.py**（保留，~15 行）：
```python
# Backward-compatible re-exports
from yuleosh.ci.runner import CIResult, timed_stage, run_all, main
from yuleosh.ci.layers import (
    run_layer1, run_layer2, run_layer_25, run_layer3,
    get_latest_layer_result, check_layer_dependency,
    layer_dependencies,
)
from yuleosh.ci.config import (
    _get_ci_config, _clear_ci_config_cache,
    is_strict, is_misra_fail_fast,
)
```

**ci/__init__.py**（更新导出路径，保持原有导出集不变）。

### 4.5 行数预估

| 模块 | 当前行数 | 目标行数 | 说明 |
|------|---------|---------|------|
| ci/run.py (重构前) | 1490 | — | — |
| config.py | ~200 | ~260 | +60 行 env 函数 |
| stages.py | — | ~450 | 所有 stage 级函数 |
| layers.py | — | ~480 | Layer 级编排函数 |
| runner.py | — | ~250 | CIResult + 编排 + CLI |
| run.py (re-export) | — | ~15 | |
| **合计** | **~1490** | **~1455** | **略减（冗余注释移除）** |

---

## 5. 向后兼容方案

### 5.1 外部导入测试

拆分后，以下导入路径必须全部正常工作：

```python
# 来自 pipeline (S2-REQ-002)
from yuleosh.pipeline import run              # via __init__.py
from yuleosh.pipeline.run import run_pipeline  # via re-export
from yuleosh.pipeline.run import PipelineSession  # via re-export
from yuleosh.pipeline.orchestrator import run_pipeline  # 新路径
from yuleosh.pipeline.session import PipelineSession   # 新路径
from yuleosh.pipeline.steps import PipelineStep  # 保留

# 来自 ci (S2-REQ-003)
from yuleosh.ci import run                     # via __init__.py
from yuleosh.ci.run import run_layer1          # via re-export
from yuleosh.ci.run import run_layer2          # via re-export
from yuleosh.ci.runner import run_all          # 新路径
from yuleosh.ci.layers import run_layer3       # 新路径
from yuleosh.ci.config import CiConfig         # 保留
```

### 5.2 现有测试不退化

所有现有测试文件（tests/test_ci_run_deep.py, tests/test_store_pg_deep.py 等）不得修改。
拆分后各个测试的 import 路径保持不变（通过 re-export），函数签名不变。

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|:----:|:----:|---------|
| steps.py 对 run.py 的循环依赖 | 高 | 高 | 将共享类型（PipelineSession, PipelineStepError）抽到 session.py |
| ci/ 模块行数超标 | 中 | 中 | 预分配 4 个模块（stages.py + layers.py），而不是 spec 原始说的 3 个 |
| E2E 测试超时 >30s | 低 | 低 | 用 `ExitStack` 批量 mock，减少 fixture 初始化开销 |
| 现有测试 import 路径失效 | 中 | 高 | 拆分前先确认每个 import 来源，re-export 全覆盖 |

---

## 7. 实施顺序

```
Phase 1: E2E Test (不依赖拆分)
  └── 创建 tests/test_e2e_pipeline.py
  └── pytest tests/test_e2e_pipeline.py ✅

Phase 2: pipeline/run.py 拆分
  └── 创建 pipeline/session.py (抽 PipelineSession, PipelineStepError)
  └── 重构 pipeline/steps.py (改 import 路径, 移入 PIPELINE_STEPS)
  └── 创建 pipeline/orchestrator.py (移入 run_pipeline 等)
  └── 创建 pipeline/__init__.py
  └── 创建 pipeline/run.py (re-export)
  └── pytest tests/ ✅ (不退化验证)

Phase 3: ci/run.py 拆分
  └── 增强 ci/config.py (+env 函数)
  └── 创建 ci/stages.py (移入 stage 函数)
  └── 创建 ci/layers.py (移入 layer 编排)
  └── 创建 ci/runner.py (移入 CIResult + 编排 + CLI)
  └── 保留 ci/run.py (re-export)
  └── 更新 ci/__init__.py
  └── pytest tests/ -k "ci" ✅ (不退化验证)

Phase 4: 全量回归
  └── pytest tests/ --tb=short -q
  └── 验证 AC-01 ~ AC-04 全部通过
```

---

*本架构设计遵循 Harness Engineering 规范，由小克 👨‍💻 设计，需经小马 🐴 审查后实施。*

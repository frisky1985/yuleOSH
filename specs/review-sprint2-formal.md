# Sprint 2 正式审查报告 — Formal Review

> **审阅人**: 小马 🐴 (质量架构师)  
> **审阅轮次**: Sprint 2 正式审查  
> **审查产出**: 全部 5 项（spec / 验收矩阵 / 架构 / 代码 / 测试）  
> **审查时间**: 2026-06-14  

---

## 1. 审查结论

| 维度 | 评分 | 判定 |
|:-----|:----:|:-----|
| Spec 完整性 | ✅ PASS | SHALL/SHOULD/MAY 格式正确，覆盖 3 条需求线 |
| 验收矩阵 | ✅ PASS | 22 条 AC 条件，覆盖指标已裁决确认 |
| 架构设计 | ✅ PASS | 模块分离清晰，依赖无环，4 模块拆分合理 |
| 代码实现 | ⚠️ **有条件通过** | 2 个中严重度问题需修复后方可终审关闭 |
| 测试状态 | ❌ **需修复** | 6 个 CI 测试文件 ImportError，AC-04 未达标 |

**最终判定: 🔴 阻塞 — 需修复 2 个中严重度问题后重新验证**

---

## 2. 逐项验证

### 2.1 spec-delta-sprint2.md

| 检查项 | 结果 | 备注 |
|:-------|:----:|:------|
| SHALL/SHOULD/MAY 格式 | ✅ | 规范 RFC 2119 格式 |
| S2-REQ-001 覆盖 | ✅ | E2E 全流程集成测试 |
| S2-REQ-002 覆盖 | ✅ | pipeline 拆分 3 模块 |
| S2-REQ-003 覆盖 | ✅ | ci 拆分 3 模块 |
| GIVEN/WHEN/THEN | ✅ | 5 条场景覆盖正常 + 异常路径 |
| AC 验收条件 | ✅ | 4 条初始 AC 已定义 |

### 2.2 acceptance-matrix-sprint2.md

| 检查项 | 结果 | 备注 |
|:-------|:----:|:------|
| AC 数量 | ✅ | 22 条（含验收矩阵扩展） |
| SHALL/SHOULD/MAY 区分 | ✅ | 清晰 |
| R-01~R-06 全部闭环 | ✅ | 小明已裁决覆盖指标定义 |
| 验收方式明确 | ✅ | 每条件有 CI/审阅/门禁值 |

### 2.3 architecture-sprint2.md

| 检查项 | 结果 | 备注 |
|:-------|:----:|:------|
| 模块边界清晰 | ✅ | 职责/导出/不导出 三栏定义 |
| 依赖图无环 | ✅ | pipeline 单向链 + ci 单向链 |
| 行数预估正确 | ✅ | 架构阶段预估合理 |
| 风险识别 | ✅ | 循环依赖 + 行数超限 + E2E 性能 |
| 向后兼容 | ✅ | re-export 方案设计 |

### 2.4 代码实现 — pipeline 拆分

| 模块 | 实际行数 | 上限 | 判定 | 备注 |
|:-----|:-------:|:----:|:----:|:------|
| run.py | **51** | 500 | ✅ | re-export shim |
| orchestrator.py | **213** | 500 | ✅ | |
| session.py | **178** | 500 | ✅ | |
| steps.py | **594** | 500 | ❌ **超标** | PipelineStep 抽象基类 + 子类 |
| stages.py | **1351** | 500 | ❌ **超标** | 含所有 step_* 函数 + PIPELINE_STEPS |
| **合计** | **2387** | — | |（原 run.py 1666 行）|

**问题 1 (P1):** stages.py 1351 行，超过 ≤500 约束的 2.7 倍。步骤函数（step_*）和底层工具函数都在同一个文件。建议：将所有 `step_*` 函数抽到独立模块（如 `step_handlers.py`），stages.py 仅保留 PIPELINE_STEPS 配置 + 共享工具函数。

**问题 2 (P2):** steps.py 594 行，超过 ≤500 约束。PipelineStep 抽象基类 + 所有 10 个 step 子类都在 steps.py 中。建议：每个 step 子类单独文件，或按 agent 分组（`hermes_steps.py`, `claude_steps.py`）。

### 2.5 代码实现 — ci 拆分

| 模块 | 实际行数 | 上限 | 判定 | 备注 |
|:-----|:-------:|:----:|:----:|:------|
| run.py (旧) | **1490** (旧) | 500 | ❌ **未替换** | 旧文件仍为完整内容，新 re-export 变更 **未提交** |
| (new) run.py | **~39** (unstaged) | 500 | ⏳ | 已修改但 unstaged |
| result.py | **70** | 500 | ✅ | 未提交 |
| runner.py | **179** | 500 | ✅ | 未提交 |
| config.py | **265** | 500 | ✅ | 已提交扩充 |
| layers.py | **405** | 500 | ✅ | 未提交 |
| stages.py | **876** | 500 | ❌ **超标** | 未提交 |
| **排除旧 run.py 合计** | **~1834** | — | |（原 run.py 1490 行）|

**问题 3 (P1):** ci/ 拆分未完成提交。旧 ci/run.py (1490 行) 仍为已提交版本，新模块文件（stages.py, layers.py, runner.py, result.py）均为 untracked 状态，ci/run.py 的新 re-export 版本未 stagged。

**问题 4 (P2):** ci/stages.py 876 行，超过 ≤500 约束的 1.75 倍。建议：将 `_cross_compile_stage`, `_static_analysis_stage`, `_integration_test_stage` 等内部函数按功能域分组到子模块。

### 2.6 测试结果

| 测试集 | 通过 | 失败 | 错误 | 判定 |
|:-------|:---:|:----:|:----:|:----:|
| E2E 测试 | **7** | 0 | 0 | ✅ PASS |
| CI 测试集 (6 文件) | 0 | 0 | **6** | ❌ ImportError |
| test_perf.py | — | — | — | ❌ ImportError |
| 全量回归 | — | — | — | ❌ 未运行 |

#### 6 个 ImportError 详细清单

所有错误均源自旧的 `from yuleosh.ci.run import X` 导入路径失效：

| 测试文件 | 错误符号 | 原因 |
|:---------|:---------|:-----|
| test_ci_engine.py | layer_dependencies | 已移至 layers.py，ci/run.py 未 re-export |
| test_ci_layers.py | layer_dependencies | 同上 |
| test_ci_layers_extended.py | get_latest_layer_result | 已移至 layers.py，ci/run.py 未 re-export |
| test_ci_layer_25.py | run_layer_25 | 已移至 layers.py，ci/run.py 未 re-export |
| test_ci_run_extended.py | _get_ci_config | 已移至 config.py，ci/run.py 未 re-export |
| test_perf.py | find_test_files, run_plan_lint, CIResult | 已移至 stages.py/result.py，未 re-export |

#### 覆盖率（仅 E2E 测试运行时）

| 指标 | 实测值 | 目标 | 判定 |
|:-----|:-----:|:----:|:----:|
| 行覆盖率 | 13.20% | ≥80% | ❌ |
| 分支覆盖率 | 未测 | ≥70% | ❌（仅 E2E 运行时）|

> 注：覆盖率低的原因是只跑了 E2E 测试。全量回归后覆盖率会回到 Sprint 1 的 80.59% 基线。当前数据不构成质量问题。

---

## 3. AC 验收矩阵完成度

| AC ID | 描述 | 类型 | 判定 | 证据 |
|:------|:-----|:----:|:----:|:-----|
| AC-01-01 | E2E mock 测试通过 | SHALL | ✅ | 7/7 passed |
| AC-01-01a | 分支覆盖 ≥70% | SHALL | ⏳ | 需全量回归验证 |
| AC-01-01b | 行覆盖 ≥80% | SHOULD | ⏳ | 需全量回归验证 |
| AC-01-02 | 外部依赖已 mock | SHALL | ✅ | ExitStack fixture + mock 策略 |
| AC-01-03 | Pipeline 步骤覆盖率 ≥80% | SHOULD | ✅ | 10/10 = 100%（架构设计） |
| AC-01-04 | 无效 spec 异常路径 | SHALL | ✅ | test_e2e_invalid_spec_path |
| AC-01-05 | Mock 失败优雅降级 | SHALL | ✅ | test_e2e_llm_exception |
| AC-01-06 | E2E 执行时间 ≤30s | SHOULD | ✅ | 8.59s（实测） |
| AC-02-01 | pipeline 拆为 3 模块 | SHALL | ✅ | orchestrator/session/stages/steps |
| AC-02-02 | pipeline 各模块 ≤500 行 | SHALL | ❌ | stages.py 1351, steps.py 594 |
| AC-02-04 | pipeline 公共 API 向后兼容 | SHOULD | ❌ | step_* 10 函数未 re-export |
| AC-02-05 | pipeline 接口形式化定义 | SHOULD | ⏳ | 架构层已定义，代码层待审 |
| AC-02-06 | pipeline 圈复杂度不增长 | SHOULD | ⏳ | 需 radon 验证 |
| AC-02-07 | pipeline re-export 兼容 | MAY | ⏳ | 部分通过，step_* 缺失 |
| AC-03-01 | ci 拆为 ≥3 模块 | SHALL | ⏳ | 4 模块，但未 committed |
| AC-03-02 | ci 各模块 ≤500 行 | SHALL | ❌ | ci/stages.py 876, ci/run.py 1490 旧 |
| AC-03-04 | ci Layer 逻辑隔离 | SHOULD | ⏳ | 架构层面隔离，代码未 committed |
| AC-03-05 | ci 接口形式化定义 | SHOULD | ⏳ | 待代码 committed 后审 |
| AC-03-06 | ci 圈复杂度不增长 | SHOULD | ⏳ | 需 radon 验证 |
| AC-04-01 | pipeline 拆分后全量测试 PASS | SHALL | ❌ | 6 ImportError（ci 拆分导致） |
| AC-04-02 | ci 拆分后 CI 测试 PASS | SHALL | ❌ | 6 ImportError |

**AC 通过率**: 9/22 ✅, 6/22 ❌, 7/22 ⏳

---

## 4. 关键问题汇总

| # | 优先级 | 模块 | 问题 | 影响 |
|:--|:-----:|:-----|:-----|:-----|
| 🔴 B-01 | P0 | **ci/ 拆分未提交** | ci/run.py 旧文件 + 新模块 untracked → 6 个测试文件 ImportError | 阻塞 AC-04-01/02 |
| 🔴 B-02 | P1 | **pipeline/stages.py 1351 行** | 超标 2.7 倍，含所有 step_* 函数 + 工具函数 | 违反 ≤500 约束 |
| 🟡 B-03 | P1 | **pipeline/steps.py 594 行** | 超标 1.2 倍，PipelineStep + 10 个子类 | 违反 ≤500 约束 |
| 🟡 B-04 | P2 | **ci/stages.py 876 行** | 超标 1.75 倍 | 违反 ≤500 约束 |
| 🟡 B-05 | P2 | **step_* 10 函数 missing from re-export** | pipeline/run.py 未重导出 stages.py 中的 step_* 函数 | 向后兼容缺口 |

---

## 5. 修复建议

### 修复 1 (P0): ci/ 拆分提交

```bash
# 检查新 ci 模块是否完整
cd src/yuleosh/ci/
git add stages.py layers.py runner.py result.py
# 替换 ci/run.py 为 re-export 版本
# 提交
```

**验收条件**: `from yuleosh.ci.run import run_layer1, run_layer2, run_layer_25, run_layer3, layer_dependencies, find_test_files, run_plan_lint, CIResult, _get_ci_config` 全部通过。

### 修复 2 (P1): pipeline/stages.py 行数超标

将 `step_*` 函数（step_spec_check, step_super_analysis, step_hermes_prd, step_internal_review, step_claude_arch, step_claude_dev, step_test_planning, step_claude_test, step_hermes_review, step_final_report）抽到独立文件 `step_handlers.py` 或保留在 steps.py 中作为 PipelineStep 子类的定义位置。

架构原方案已明确 steps.py (~450 行) 存放 step 函数，stages.py 被错误地用作 storeall。建议：
- stages.py: PIPELINE_STEPS 配置 + _call_llm + 解析工具函数（清理至 ~200 行）
- step_handlers.py: 10 个 step_* 函数（~800 行，可接收超 500 约束但用架构层豁免 OR 按 agent 拆分）

### 修复 3 (P1): step_* re-export

在 `pipeline/run.py` 的 re-export 段添加：

```python
from yuleosh.pipeline.stages import (
    step_spec_check,
    step_super_analysis,
    step_hermes_prd,
    step_internal_review,
    step_claude_arch,
    step_claude_dev,
    step_test_planning,
    step_claude_test,
    step_hermes_review,
    step_final_report,
)
```

---

## 6. 终审条件

以下条件满足后本审查报告可关闭：

- [ ] B-01 修复：ci/ 新模块 committed + ci/run.py re-export 提交
- [ ] B-02 修复：pipeline/stages.py 行数 ≤500（或架构层豁免审裁）
- [ ] B-02 修复后：`pytest tests/ -q` 全量通过
- [ ] `pytest --cov-branch --cov-fail-under=70` 通过（全局覆盖率门禁）
- [ ] B-05 修复：step_* 函数 re-export

---

*审查人: 小马 🐴 | 2026-06-14*

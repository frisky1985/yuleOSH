---
kind: refactor
lint: RED / GREEN / REFACTOR
---

# yuleOSH v0.3.0 — Sprint 任务拆解与排期

> 基于 ASPICE V-Model 三方会诊结论（小马 🐴 + 小克 👨‍💻 + 小明 🧑‍💼）
> 目标：把合规做实，消除「伪合规」风险

---

## 一、Sprint 概览

| 字段 | 值 |
|:----|:----|
| 版本 | v0.3.0 |
| 主题 | **地基加固** — CI 硬校验 + V 左半侧规范 |
| 周期 | 2 周（6 Iterations） |
| 核心提升 | ASPICE 合规度 2/5 → 4/5 |
| P0 任务数 | 7 |
| P1 任务数 | 4 |

---

## 二、任务拆解

### Track A: CI 硬校验（小克 👨‍💻）

#### A-01 [P0] CI 阻断逻辑修复 ⏰ 1天
- **问题**: 所有 stage 工具缺失时静默跳过并返回 True，流水线仍显示 ✅
- **改动**: `src/ci/run.py`
  - 所有 stage handler 的 `FileNotFoundError` → 返回 `False`（阻断）
  - 添加 `--strict` 模式：任何 skip 视为 failure
  - 添加 `CI_STRICT` / `MISRA_FAIL_FAST` 环境变量支持
- **验收**: 工具缺失时流水线显示 ❌ FAILED，不静默通过

#### A-02 [P0] Pipeline 调用失败硬错误 ⏰ 0.5天
- **问题**: LLM 调用失败时 pipeline 做静默降级（try/except/pass）
- **改动**: `src/pipeline/run.py`
  - LLM 调用失败 → 明确错误，阻断后续步骤
  - JSON 解析错误 → 明确错误信息，不静默降级
- **验收**: LLM API 超时时 pipeline 明确报错并中断

#### A-03 [P1] CI 层级依赖链 ⏰ 1天
- **问题**: L2 失败后 L3 仍然执行
- **改动**: `src/ci/run.py`
  - L1 失败 → 阻断 L2
  - L2 失败 → 阻断 L3
  - 各 stage 之间添加依赖声明
- **验收**: Layer 1 失败后 Layer 2 和 Layer 3 不执行

---

### Track B: V 左半侧规范（小马 🐴）

#### B-01 [P0] Pipeline 新增测试规划步骤 ⏰ 2天
- **问题**: Pipeline 中没有 SWE.4 对应的 test-planning 步骤
- **改动**: `src/pipeline/run.py`
  - 新增 `step_test_planning`，在 `claude-dev` 之后、`self-test` 之前
  - 调用 LLM 生成测试计划：
    - 测试策略（单元/集成/E2E）
    - 测试用例 → 需求追溯表
    - 覆盖率目标
  - 输出：`{session_dir}/test-plan.md`
- **验收**: Pipeline 执行后生成 test-plan.md，含需求→测试用例追溯

#### B-02 [P0] 需求层级 ID 规范 ⏰ 1天
- **问题**: 当前需求是平面 Req-XXX，无层级/父节点/状态
- **改动**: `src/spec/validate.py`
  - `SpecRequirement` 增加字段：`req_id: str`、`level: SYS|SW|FEATURE`、`parent: str`、`status: PROPOSED|APPROVED|IMPLEMENTED|VERIFIED`
  - 增加需求 ID 格式校验：`RS-001`（系统级）、`SWR-001.1`（软件级）
  - 增加 `validate_status_transition()` 状态迁移校验
- **验收**: spec 解析后支持层级 ID + 状态字段，校验失败时报错

#### B-03 [P0] 需求状态跟踪 ⏰ 0.5天
- **问题**: 需求无状态管理，无法追踪进度
- **改动**: `src/spec/validate.py`
  - 添加状态校验：非 PROPOSED 状态才可进入 Pipeline
  - 添加状态迁移规则：`PROPOSED → APPROVED → IMPLEMENTED → VERIFIED`
  - spec-delta 中标记状态变更
- **验收**: `validate_spec()` 校验需求状态，状态不合规时报错

---

### Track C: 可测试性（小克 👨‍💻 + 小马 🐴）

#### C-01 [P0] pipeline/run.py 单元测试 ⏰ 2天
- **问题**: 700+ 行核心代码零单元测试
- **改动**: `src/pipeline/run.py` + `tests/test_pipeline_engine.py`
  - 依赖注入重构：LLM client 作为参数传入
  - mock LLM fixture（返回预定义响应）
  - 覆盖 9 个步骤的 3 种场景：正常/LLM 失败/LLM 超时
  - 测试 PipelineSession 状态流转
- **验收**: pipeline/run.py 测试覆盖 ≥ 80%（mock 模式，不调用真实 API）

#### C-02 [P0] E2E 测试修复 ⏰ 1天
- **问题**: 50% E2E 测试被 `pytest.mark.skipif(True, ...)` 条件跳过
- **改动**: `tests/test_e2e.py`
  - 移除所有无条件跳过的测试桩
  - 使用预录制的 fixture 数据替代真实 LLM 调用
  - 添加 golden file 测试（对比 LLM 输出结构与已知模式）
- **验收**: 所有 E2E 测试稳定运行，无 skipif 跳过

#### C-03 [P0] 交叉编译基础容器化 ⏰ 1.5天
- **问题**: cross-compile stage 只打印 info，不实际编译
- **改动**: `Dockerfile.cross` + `ci/run.py`
  - 创建 Docker 工具链镜像（gcc-arm-none-eabi + riscv64-unknown-elf-gcc）
  - cross-compile 阶段实际执行 `make TARGET=arm` 等命令
  - 添加交叉编译验证测试（至少 arm 目标）
- **验收**: `make TARGET=arm all` 实际执行并产生 .elf/.hex 文件

---

### Track D: 规格与质量（小马 🐴 + 小明 🧑‍💼）

#### D-01 [P0] spec-diff 影响分析 ⏰ 1.5天
- **问题**: `diff_specs` 只能检测变更，不分析受影响的下游制品
- **改动**: `src/spec/diff.py`
  - diff 输出增加 `impact_analysis`：
    - `affected_requirements`
    - `affected_architecture_components`
    - `affected_tests`
    - `affected_scenarios`
    - `recommended_actions`
  - 基于文件名 + 关键词匹配的影响推理
- **验收**: spec 变更后 diff 输出包含影响分析，推荐受影响的任务和测试

#### D-02 [P1] 需求-测试双向追溯 ⏰ 2天
- **问题**: 测试用例与需求无显式追溯关系
- **改动**: `src/evidence/pack.py`
  - 在 Evidence Engine 中增加需求-测试追溯完整性检查
  - 解析每个 `test_*.py` 的 `Covers:` 标记
  - 与 spec 中的每个 SHALL 匹配
  - 输出未被覆盖的 SHALL 列表
  - 生成追溯矩阵报告
- **验收**: Evidence pack 包含需求→测试追溯矩阵，每个 SHALL 标记覆盖状态

#### D-03 [P1] 验收矩阵自动化 ⏰ 1天
- **问题**: 验收矩阵手写 Markdown，与 spec 不同步
- **改动**: `src/evidence/pack.py`
  - 新增 `generate_acceptance_matrix()`
  - 遍历每个 SpecRequirement 的 SHALL
  - 自动匹配 tests/ 下的相关性测试
  - 输出格式：`| Req ID | SHALL | 验证方法 | 状态 |`
- **验收**: 运行后自动生成 `acceptance-matrix.md`，覆盖所有 SHALL

---

## 三、Iteration 排期

### Iteration 1（Day 1-2）— CI 基础加固

| 任务 | 工时 | 负责人 | 关键产出 |
|:----|:----:|:------:|:--------|
| A-01 CI 阻断逻辑修复 | 1天 | 小克 | `ci/run.py` 硬校验模式 |
| A-02 Pipeline 硬错误 | 0.5天 | 小克 | LLM 失败明确阻断 |
| B-01 测试规划步骤（设计+prompt） | 1天 | 小马 | `test-planning` 步骤框架 |

### Iteration 2（Day 3-4）— V 左半侧规范化

| 任务 | 工时 | 负责人 | 关键产出 |
|:----|:----:|:------:|:--------|
| B-02 需求层级 ID 规范 | 1天 | 小马 | `SpecRequirement` 新字段 + 校验 |
| B-03 需求状态跟踪 | 0.5天 | 小马 | 状态迁移校验 |
| D-01 spec-diff 影响分析 | 1.5天 | 小马 | diff 输出 `impact_analysis` |

### Iteration 3（Day 5-7）— 可测试性 I

| 任务 | 工时 | 负责人 | 关键产出 |
|:----|:----:|:------:|:--------|
| C-01 pipeline 依赖注入重构 | 1天 | 小克 | 可注入 PipelineEngine |
| C-01 pipeline 单元测试 | 1天 | 小克 | 30+ mock 测试 |
| C-02 E2E 测试修复 | 1天 | 小克 | 所有 E2E 稳定运行 |

### Iteration 4（Day 8-9）— 嵌入式基础

| 任务 | 工时 | 负责人 | 关键产出 |
|:----|:----:|:------:|:--------|
| C-03 交叉编译容器 + 镜像 | 1天 | 小克 | `Dockerfile.cross` + 工具链 |
| C-03 交叉编译实际执行 | 0.5天 | 小克 | `make TARGET=arm` 在 CI 生效 |
| A-03 CI 层级依赖链 | 1天 | 小克 | L1→L2→L3 依赖阻断 |

### Iteration 5（Day 10-11）— 追溯与证据

| 任务 | 工时 | 负责人 | 关键产出 |
|:----|:----:|:------:|:--------|
| D-02 需求-测试双向追溯 | 2天 | 小马 | 追溯矩阵生成 + 完整性检查 |
| D-03 验收矩阵自动化 | 1天 | 小马 | `generate_acceptance_matrix()` |

### Iteration 6（Day 12-13）— 集成 & 发布

| 任务 | 工时 | 负责人 | 关键产出 |
|:----|:----:|:------:|:--------|
| B-01 测试规划步骤（集成测试） | 1天 | 小马 | test-plan 集成入流水线 |
| 全量回归测试 | 1天 | 小克+小马 | 所有测试绿色通过 |
| 残留 Bug 修复 | 1天 | 小克+小马 | Issue 清零 |

---

## 四、产出物清单

| # | 产出物 | 位置 | 关联任务 |
|---|:------|:----|:--------|
| 1 | CI 硬校验 | `src/ci/run.py` | A-01 |
| 2 | CI 层级依赖 | `src/ci/run.py` | A-03 |
| 3 | 测试规划步骤 | `src/pipeline/run.py` | B-01 |
| 4 | 需求层级 ID 校验 | `src/spec/validate.py` | B-02 |
| 5 | 需求状态跟踪 | `src/spec/validate.py` | B-03 |
| 6 | spec-diff 影响分析 | `src/spec/diff.py` | D-01 |
| 7 | Pipeline 单元测试 | `tests/test_pipeline_engine.py` | C-01 |
| 8 | E2E 测试修复 | `tests/test_e2e.py` | C-02 |
| 9 | 交叉编译 Docker 镜像 | `Dockerfile.cross` + CI | C-03 |
| 10 | 需求-测试追溯矩阵 | `src/evidence/pack.py` | D-02 |
| 11 | 自动验收矩阵 | `src/evidence/pack.py` | D-03 |

---

## 五、Sprint N+1 预告

完成 v0.3.0 后，v0.4.0 将进入「嵌入式特色」阶段：

| P0 | MISRA 静态分析门禁 | 配置真实 MISRA-C:2012 规则集 + 门禁阻断 |
| P1 | QEMU 测试框架 | `qemu_runner.py` ARM/RISC-V 仿真测试 |
| P1 | 测试覆盖率 55%+ | 覆盖所有缺失模块 |
| P1 | 集成测试 40+ | 管道编排、Store 持久化 |
| P2 | 并行 DAG pipeline | 非依赖步骤并行执行 |

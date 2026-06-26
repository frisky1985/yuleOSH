# yuleOSH CI P0/P1 问题修复报告

> 编写日期：2026-06-26
> 基于 realworld-ci-failure-rca.md + quality-review.md 评审结论修复

---

## 修复总览

| # | 优先级 | 问题 | 状态 | 涉及文件 |
|---|--------|------|------|---------|
| 1 | P0 | MISRA 排除测试目录 | ✅ 已修复 | `stages.py`, `config.py`, `ci-config.yaml`, `yaml_validator.py` |
| 2 | P0 | cppcheck include 路径 | ✅ 已修复 | `stages.py` |
| 3 | P0 | C覆盖率门禁缺失 | ✅ 已修复 | `layers.py`, `stages.py` |
| 4 | P0 | docsync YAML 验证 | ✅ 已修复 | `yaml_validator.py` |
| 5 | P0 | build 目录检测扩展 | ✅ 已修复 | `stages.py` |
| 6 | P1 | 模块覆盖率门槛死配置 | ✅ 已修复 | `stages.py` |
| 7 | P1 | deviation 不合规 | ✅ 已修复 | `ci-config.yaml` |
| 8 | P1 | 错误信息友好度 | ✅ 已修复 | `stages.py` |

## 详细修复说明

### 1. MISRA exclude_paths 过滤

**根因**：`run_misra_check()` 的 delta 模式将 git diff 中所有文件送检，包括 `tests/unity/` 下的测试框架代码，导致 98 条误报。

**修复内容**：
- `config.py` → `MisraConfig` 新增 `exclude_paths: list[str]` 字段，默认排除 `tests/**`、`third_party/**`、`build/**`
- `config.py` → `_parse_ci_config()` 解析 `exclude_paths` 配置
- `stages.py` → 新增 `_exclude_paths()` 函数，使用 `fnmatch.fnmatch` 进行 glob 模式匹配
- `stages.py` → `run_misra_check()` 中在构造 cppcheck 命令前调用 `_exclude_paths()` 过滤文件列表
- `yaml_validator.py` → MISRA schema 新增 `exclude_paths: list` 定义
- `ci-config.yaml` → 新增 `misra.exclude_paths` 配置

### 2. cppcheck include 路径自动探测

**根因**：cppcheck 未配置 `-I` 参数，导致 `#include "unity.h"` 等头文件找不到，产生 23 条 `missingInclude` 假阳性。

**修复内容**：
- `stages.py` → 新增 `_detect_include_paths()` 函数，自动扫描 `tests/`、`tests/unity/src/`、`Drivers/`、`Drivers/CMSIS/Include/`、`include/`、`inc/`、`lib/`、`common/`、`third_party/`、`Middlewares/` 等常见目录
- `stages.py` → 在 cppcheck 命令中自动追加 `-I` 参数
- 同时检测 `compile_commands.json` 是否存在并提示用户

### 3. C 覆盖率门禁（L1）

**根因**：`run_layer1()` 的 stages 列表中包含 `run_c_coverage()`（生成报告），但未包含 `run_c_coverage_check()`（阻断门禁），导致覆盖率低于阈值时流水线仍通过。

**修复内容**：
- `layers.py` → 导入 `run_c_coverage_check`
- `layers.py` → L1 stages 列表新增 `("c-coverage-gate", run_c_coverage_check)`

### 4. docsync YAML Schema

**根因**：`_CI_CONFIG_SCHEMA` 中 `docsync` 字段虽然存在，但缺少子字段定义，且 `known_keys` 校验可能导致误报。

**修复内容**：
- `yaml_validator.py` → `docsync` schema 新增详细子字段：`enabled`、`rules`、`mode`、`exempt_paths`、`critical_docs`、`staleness_days`、`audit`

### 5. build 目录检测扩展

**根因**：`coverage_dirs` 列表仅包含 `build/`、`build/coverage/` 等 4 个路径，用户使用 `_build/`、`out/` 等常见构建输出目录时无法发现 `.gcda` 文件。

**修复内容**：
- `stages.py` → `coverage_dirs` 扩展至 15 个常见路径（含 `_build/`、`out/`、`build_arm/`、`build_x86/`、`cmake-build-debug/`、`Debug/`、`Release/` 等）
- `stages.py` → 在已知路径均未发现时，执行递归 `.gcda` 文件搜索
- 输出中增加 🔧 Fix 建议和 `COVERAGE_BUILD_DIR` 环境变量提示

### 6. 模块覆盖率门槛

**根因**：`ci-config.yaml` 中 `coverage.module_thresholds` 已定义但代码从未读取和使用。

**修复内容**：
- `stages.py` → `run_c_coverage_check()` 新增 `module_thresholds` 逻辑
- 根据文件路径自动提取模块名（`src/<module>/...` → `<module>`）
- 对每个配置了阈值的模块计算实际覆盖率
- 任何模块低于阈值则阻断流水线
- 同时优化了低覆盖率文件的排序和显示

### 7. deviation 不合规清理

**根因**：`ci-config.yaml` 中 10 条 deviation 包含 `Rule-99.9`、`Rule-Test-DryRun` 等测试数据，且缺少对 `tests/unity/` 实际违规的有效 coverage。

**修复内容**：
- ✅ 移除 `Rule-99.9`（测试数据）
- ✅ 移除 `Rule-Test-DryRun`（测试数据）
- ✅ 保留 `Rule-17.7`（src/**/legacy/old_protocol.c）
- ✅ 保留 `Rule-21.21`（src/**/hal/*.c）
- ✅ 保留 `Dir-4.12`（src/**/mem_pool.c）
- ✅ 保留 `Rule-7.2`（src/**/startup/*.c）
- ✅ 保留 `Rule-12.2`（src/**/config/*.c）
- ✅ 保留 `Rule-8.1`（src/**/gen/*.c）
- ✨ 新增 `misra-c2023-17.7` deviation 覆盖 `tests/unity/src/unity.c`
- ✨ 新增 `misra-c2023-2.5` deviation 覆盖 `tests/unity/src/unity.h`
- ✨ 新增 `misra-c2023-8.7` deviation 覆盖 `tests/unity/src/unity.c`
- ✨ 新增 `misra-c2023-15.6` deviation 覆盖 `tests/unity/src/unity.c`

### 8. 错误信息友好度

**根因**：关键失败路径仅输出"❌ X failed"，没有给出修复建议。

**修复内容**（在以下路径增加了 🔧 Fix 建议）：
- cppcheck 未安装时：提示 `apt install cppcheck` 或 `brew install cppcheck`
- cppcheck 超时时：提示使用 `compile_commands.json` 加速
- clang-tidy 未安装时：提示 `apt install clang-tidy` 或 `brew install llvm`
- clang-tidy 超时时：提示增加超时或减少文件数
- Python 覆盖率失败时：提示调整 `threshold_line` 或使用 `exclude_paths`
- C 覆盖率无 build 目录时：提示 `--coverage` 编译标志和 `COVERAGE_BUILD_DIR` 环境变量
- 覆盖率工具未安装时：提示 `pip install coverage` 或 `apt install lcov`
- 覆盖率超时时：提示扩大超时或缩小测试范围

---

## 测试结果

```
tests/ci/test_ci_fixes_p0_p1.py .............. 55 passed in 0.18s
```

55 个测试覆盖全部 8 项修复 + 9 项三级分类，包括：
- `TestExcludePaths` — 5 tests（空模式、tests/排除、多模式、相对路径、无匹配）
- `TestDetectIncludePaths` — 3 tests（常见路径、缺失目录省略、绝对路径）
- `TestLayer1CoverageGate` — 2 tests（L1 stages 包含、函数可导入）
- `TestYamlSchemaDocsync` — 3 tests（schema keys、exclude_paths、合法配置）
- `TestBuildDirExpansion` — 2 tests（扩展目录、递归搜索）
- `TestModuleThresholds` — 2 tests（引用确认、实际阻断验证）
- `TestDeviationCleanup` — 3 tests（无测试数据、有 unity 条目、有 exclude_paths）
- `TestErrorFriendliness` — 4 tests（覆盖率、clang-tidy、c-coverage、cppcheck 建议）
- `TestMisraConfigExcludePaths` — 4 tests（dataclass、默认值、YAML 解析、缺省默认）
- `TestCoverageConfig` — 2 tests（module_thresholds 字段、解析）

### 9. 三级指针空违规分类策略

**背景**：用户"明天华"反馈 exclude_paths 还不够精细。多级指针空违规涉及三类代码，需要不同策略。

| 等级 | 代码类别 | 路径模式 | 策略 |
|:----:|:---------|:---------|:-----|
| 🟢 | **模板代码** (template code） | `src/yuleosh/templates/**` | 自动排除，不做检查，不阻断 |
| 🟡 | **第三方库** (third-party） | `third_party/**`, `Drivers/**`, `Middlewares/**`, `CMSIS/**`, `vendor/**`, `lib/**` | 必须告警 + 给出修复方案，**默认不阻断** |
| 🔴 | **业务代码** (business code） | `src/**`（非模板非第三方） | 必须告警 + 给出修复方案，**阻断** |

**修复内容**：
- `config.py` → `MisraConfig` 新增 `code_categories` 字段，含 template/third_party/business 三级分类默认值
- `config.py` → `_parse_ci_config()` 解析 YAML 中 `code_categories` 可选覆盖
- `stages.py` → 新增 `_categorize_file()` 函数，根据路径判断代码类别
- `stages.py` → 新增 `_format_null_pointer_fix()` 函数，针对多级指针空违规输出修复建议
- `stages.py` → `run_misra_check()` 中集成三级分类：template 跳过、third_party 告警不阻断、business 告警且阻断
- `stages.py` → 阻断逻辑调整为按 category 的 block_on 配置执行
- `misra_report.py` → JSON 报告新增 `code_category_breakdown` 字段
- `misra_report.py` → Markdown 报告新增 Code Category Breakdown 章节
- `yaml_validator.py` → MISRA schema 新增 `code_categories: dict` 定义
- `ci-config.yaml` → 新增 `misra.code_categories` 默认配置段
- `tests/test_ci_fixes_p0_p1.py` → 追加 25 个三级分类相关测试

**测试用例（新增）**：
- `TestCodeCategorization` (11 tests）— template/third_party/business 路径识别、优先级、fallback
- `TestFixSuggestionFormat` (4 tests）— 各类别修复建议内容、template 返回空
- `TestThirdPartyNonBlocking` (3 tests）— third_party 默认不阻断、business 阻断
- `TestBusinessCodeBlocks` (5 tests）— block_on 验证、run_misra_check 引用检查、配置解析

---

## 未修复项（P2 及之后）

以下问题不在本次修复范围，但已记录在 RCA 中：
1. `stages.py` 单文件过大（>1000 行）— 需后续按功能拆分
2. `misra-rules.yaml` 路径解析脆弱 — 需要更 Robust 的查找策略
3. 工具链前置校验 — 新增 `run_tool_check` 阶段
4. clang-tidy `--project=compile_commands.json` 支持
5. `CI_STRICT`/`MISRA_FAIL_FAST` 文档化
6. 覆盖率报告物发布增强（third_party 排除等）

---

## 新增功能：Checkpoint Pipeline Engine

> 实现日期：2026-06-26

### 概述

Checkpoint Pipeline Engine 是一个通用流水线引擎，支持 **任意点注入** + **自动续跑**。同时对接 Agent Pipeline（30 步）和 CI Pipeline（L1/L2/L2.5/L3）。

### 涉及文件

| # | 文件 | 说明 |
|---|------|------|
| 1 | `src/yuleosh/engine/__init__.py` | Engine 包入口 |
| 2 | `src/yuleosh/engine/checkpoint.py` | 核心 CheckpointEngine（全量/注入/恢复三种模式） |
| 3 | `src/yuleosh/engine/ci_checkpoint.py` | CI Pipeline 适配（L1: 12 stages, L2: 5 stages, L3: 3 stages） |
| 4 | `src/yuleosh/engine/agent_checkpoint.py` | Agent Pipeline 适配（29 steps） |
| 5 | `tests/engine/test_checkpoint_engine.py` | 22 tests（全量/注入/恢复/持久化/CI/Agent） |
| 6 | `src/yuleosh/cli/yuleosh.sh` | CLI: `--inject-at`, `--resume`, `--checkpoint`, `--inject-points` |

### 核心设计

**三种运行模式**：
- **全量模式**：从头到尾执行所有步骤
- **注入模式**：从指定 step_id 开始，之前步骤标记为 SKIPPED
- **恢复模式**：读取 `.yuleosh/checkpoint-state.json`，从上次中断/失败处继续

**CLI 使用示例**：
```bash
# 注入模式
osh-cli pipeline run docs/spec.md --inject-at self-test

# 恢复模式
osh-cli pipeline run docs/spec.md --resume

# 列出所有注入点
osh-cli pipeline status --inject-points

# CI 注入
osh-cli ci run 1 --inject-at misra-check

# CI 恢复
osh-cli ci run 2 --resume
```

### 测试结果

```
tests/engine/test_checkpoint_engine.py .............. 22 passed in 0.14s
```

测试覆盖：
- `TestBasic` (3 tests) — 注册/查找/空引擎
- `TestFullMode` (2 tests) — 全量执行/失败中断
- `TestInjectMode` (4 tests) — 中间注入/首步注入/末步注入/不存在报错
- `TestResumeMode` (3 tests) — 失败后恢复/全部完成/无 checkpoint
- `TestPersistence` (5 tests) — 磁盘持久化/加载/清除/空状态/序列化往返
- `TestCICheckpoint` (3 tests) — L1/L2/无效 layer
- `TestAgentCheckpoint` (2 tests) — 创建/列出注入点

---

## 质量检视修复（2026-06-26）

> 基于 quality-review.md 评审结论修复，共 4 个 A 级 + 5 个 B 级问题。

### 修复总览

| # | 优先级 | 问题 | 状态 | 涉及文件 |
|---|--------|------|------|---------|
| A1 | 🔴 | 注入点不存在时 `run()` 返回 `True` | ✅ 已修复 | `checkpoint.py` |
| A2 | 🔴 | CI Layer 2.5 通过 CLI 无法被调用 | ✅ 已修复 | `ci_checkpoint.py` |
| A3 | 🔴 | 默认 `pipeline run` 不经过 Checkpoint 引擎 | ✅ 已修复 | `yuleosh.sh` |
| A4 | 🔴 | 无 handler 步骤的 duration 计算错误 | ✅ 已修复 | `checkpoint.py` |
| B1 | 🟠 | 缺失状态文件损坏的容错处理 | ✅ 已修复 | `checkpoint.py` |
| B2 | 🟠 | 缺少 mid-pipeline status() 测试覆盖 | ✅ 已修复 | `test_checkpoint_engine.py` |
| B3 | 🟠 | `agent_checkpoint.py` 中存在死代码 | ✅ 已修复 | `agent_checkpoint.py` |
| B4 | 🟠 | 所有 stage 共享同一个 `CIResult` 实例 | ✅ 已修复 | `ci_checkpoint.py` |
| B5 | 🟠 | 缺失空引擎 `run()` 的测试 | ✅ 已修复 | `test_checkpoint_engine.py` |

### 详细修复说明

#### A1: 注入点不存在时 `run()` 返回 `False`

**文件**：`src/yuleosh/engine/checkpoint.py`
**问题**：`_prepare_inject` 在注入点不存在时返回 `([], -1)`，`run()` 遇到空列表直接 `return True`。
**修复**：在 `run()` 的空列表检查中增加状态判断，当 `self._state.status == "failed"`（由 `_prepare_inject` 在错误路径设置）时返回 `False`。

#### A2: CI Layer 2.5 的 float→int 截断

**文件**：`src/yuleosh/engine/ci_checkpoint.py`
**问题**：`create_ci_pipeline` 参数类型声明为 `int`，CLI 中 `int(args.layer)` 将 `2.5` 截断为 `2`。
**修复**：`create_ci_pipeline(layer: float)` 接受 float 类型；`main()` 中去除 `int()` 强转直接传递 `args.layer`。

#### A3: 默认 `pipeline run` 使用 Checkpoint 引擎

**文件**：`src/yuleosh/cli/yuleosh.sh`
**问题**：无 `--inject-at` 或 `--resume` 标志时走旧路径 `yuleosh.pipeline.run`，完全不创建 checkpoint 状态。
**修复**：默认分支改为 `python3 -m yuleosh.engine.agent_checkpoint run "$spec"`。

#### A4: 无 handler 步骤的 duration 计算

**文件**：`src/yuleosh/engine/checkpoint.py`
**问题**：`t0` 仅在外层初始化一次，无 handler 步骤直接使用该值，而非步骤开始时间。
**修复**：在每个循环迭代开始处重置 `t0 = datetime.now()`，确保 duration 基于当前步骤的开始时间。

#### B1: 状态文件损坏容错

**文件**：`src/yuleosh/engine/checkpoint.py`
**问题**：`_load_state()` 未捕获 `json.load` 或 `from_dict()` 的异常。
**修复**：增加 `try/except` 包裹读取逻辑，捕获 `json.JSONDecodeError`、`KeyError`、`TypeError`、`ValueError`，记录 warning 后返回 `None`。

#### B2: mid-pipeline status 测试

**文件**：`tests/engine/test_checkpoint_engine.py`
**问题**：未测试 `run()` 执行过程中调用 `status()` 的行为。
**修复**：新增 `test_mid_pipeline_status`，在 step handler 内部调用 `engine.status()` 验证中间状态正确（pending→running→passed 转换）。

#### B3: 删除死代码

**文件**：`src/yuleosh/engine/agent_checkpoint.py`
**问题**：`_make_agent_handler` 定义了但从未被调用。
**修复**：删除该函数。

#### B4: 独立 CIResult 实例

**文件**：`src/yuleosh/engine/ci_checkpoint.py`
**问题**：所有 stage 共享同一个 `CIResult` 实例，为未来并行扩展埋下隐患。
**修复**：`_wrap` 和 `_bool_wrap` 去掉 `ci` 参数，改为接收 `layer`；在每次闭包调用时创建新的 `CIResult(layer, ...)` 实例。

#### B5: 空引擎 run 测试

**文件**：`tests/engine/test_checkpoint_engine.py`
**问题**：没有测试空引擎调用 `run()`。
**修复**：新增 `test_empty_engine_run`，验证空引擎调用 `run()` 返回 `True` 且状态为 `completed`。

### 验证结果

```
engine tests: 24 passed, 1 skipped ✓
engine + ci tests: 211 passed, 1 skipped ✓
```

**影响范围**：仅 checkpoint 引擎及测试代码，CI stages 逻辑无变更。

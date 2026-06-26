# yuleOSH CI 实际工程应用 — 质量审查报告

> 审查者：小马（质量架构师）
> 审查时间：2026-06-26
> 审查范围：`src/yuleosh/ci/` 全部模块 + `.yuleosh/ci-config.yaml`
> 触发场景：用户"明天华"在嵌入式 C/C++ 工程中运行 `osh-cli ci run` 遭遇 MISRA + gcov 覆盖率双重失败

---

## 目录
1. [审查结论概要](#1-审查结论概要)
2. [MISRA 模块深度审查](#2-misra-模块深度审查)
3. [gcov 覆盖率模块深度审查](#3-gcov-覆盖率模块深度审查)
4. [CI 整体架构审查](#4-ci-整体架构审查)
5. [新用户最易出错的配置点](#5-新用户最易出错的配置点)
6. [测试代码豁免 & 第三方库策略](#6-测试代码豁免--第三方库策略)
7. [错误处理友好度评估](#7-错误处理友好度评估)
8. [质量改进优先级建议](#8-质量改进优先级建议)
9. [用户当前问题的排查清单](#9-用户当前问题的排查清单)

---

## 1. 审查结论概要

| 维度 | 评分 | 评语 |
|:-----|:----:|:------|
| MISRA 检测覆盖率 | ★★★★☆ | 多工具融合设计优秀，但 cppcheck 调用参数缺少动态编译数据库支持 |
| 偏差管理 | ★★★★☆ | 功能完整（状态、风险等级、过期、ALM），但文档/引导缺失 |
| gcov 集成 | ★★★☆☆ | 基础能力完整，但自动化缺失、C 覆盖率 pipeline 难直接使用 |
| 错误信息友好度 | ★★☆☆☆ | 报错信息对新手不够友好，缺少修复建议和配置文档链接 |
| 新手上手体验 | ★★☆☆☆ | 从"零配置到跑通"的路径不清晰，工具链假设缺乏校验 |
| 第三方库策略 | ★★☆☆☆ | 无系统性支持，全靠手动 deviation/file pattern 豁免 |
| 测试豁免 | ★★☆☆☆ | MISRA 有 deviation 但覆盖率无测试代码豁免机制 |

**总体评价：yuleOSH CI 在架构层面思路先进（三层融合、偏差管理、Layer 依赖链），但在实际工程可用性层面存在若干"最后一公里"问题，使新用户首次运行时极易失败且不易自愈。**

---

## 2. MISRA 模块深度审查

### 2.1 架构亮点

- **G-15 三层融合（misra_fusion.py）**：cppcheck + clang-tidy + AI Review 交叉验证，置信度分级（ALL_CONFIRM / MAJORITY / SINGLE / CONTRADICT），设计优秀。
- **偏差管理系统**：`misra_report.py` 中 deviation 支持规则 ID + 文件 glob 匹配、风险等级、过期检查、ALM 工单关联（R5-P2-1），已在生产配置中有 10+ 条实际 deviation 记录。
- **年份归一化**（R2-P0-1）：自动将 cppcheck 输出的 `misra-c2012-XX.X` 转为 `misra-c2023-XX.X`，解决了工具版本差异问题。
- **趋势对比**（R3-P0-4）：自动读取前次报告计算 delta，支持违规增长/减少趋势分析。
- **报告格式丰富**：JSON + Markdown + Excel + 修复任务（fix-tasks）自动生成。

### 2.2 关键缺陷

#### 缺陷 1：cppcheck 调用缺少 --project 编译数据库支持（高优先级）

**位置**：`stages.py` → `run_misra_check()` 和 `stage_utils.py` → `_static_analysis_stage()`

**问题**：
- `run_misra_check()` 直接对 `.c` 文件列表运行 `cppcheck`，缺乏 `--project=compile_commands.json` 支持。
- 这意味着 cppcheck 无法知道项目的 include 路径、宏定义等，导致：
  - **大量 false positive**：cppcheck 找不到头文件时会报 `missingInclude` 和大量 MISRA 违规（无法分析不完整的翻译单元）
  - **大量 false negative**：某些需宏展开的规则无法触发
- `--std=c11` 硬编码，若项目使用 C99、C17 或 C++，分析基准就不对。

**影响**：这是新用户最常见的大规模 MISRA 失败根因 —— 不是代码本身违规多，而是 cppcheck 缺少正确的编译上下文。

**建议修复方向**：
```python
# 优先检测 compile_commands.json（CMake 生成）或 compile_flags.txt（clangd 格式）
if os.path.exists(build_dir / "compile_commands.json"):
    cppcheck_args = ["cppcheck", "--project=compile_commands.json",
                     "--addon=misra", "--suppress=missingInclude"]
else:
    # 回退到文件名扫描 + 基本 include 路径
    cppcheck_args = ["cppcheck", f"--std={cppcheck_std}",
                     "-I", "src/", "--addon=misra"] + source_files
```

#### 缺陷 2：misra-rules.yaml 路径解析脆弱（中优先级）

**位置**：`misra_report.py:58`

```python
_DEFAULT_RULES_PATH = Path(__file__).resolve().parent.parent.parent.parent / "misra-rules.yaml"
```

4 级 `..parent.parent.parent.parent` 硬编码对项目结构高度敏感。若用户项目的 `src/yuleosh/ci/misra_report.py` 路径层级与预期不符，规则定义文件加载会静默失败（`load_rule_definitions` 返回空 dict 而非报错）。

#### 缺陷 3：fail_threshold 与 violations_per_kloc 参数未在 pipeline 中实际使用（中优先级）

**位置**：`config.py` 的 `MisraConfig` 定义了 `fail_threshold: int = 10` 和 `violations_per_kloc: float = 2.0`

但在 `layers.py` 的 `run_misra_check()` 调用中，这两个参数从未传入或使用。它们只是定义在 dataclass 中，是**死配置**。

#### 缺陷 4：clang-tidy 限制 20 个文件（低优先级）

**位置**：`stages.py:run_clang_tidy()`

```python
result = subprocess.run(
    ["clang-tidy"] + c_files[:20] + ["--", "-std=c11"],
    ...
)
```

- 只分析前 20 个文件
- `--std=c11` 硬编码
- 同样缺少 `--pch` 或 compile_commands.json 支持
- 对于超过 20 个源文件的工程，多数 C 文件未被扫描

---

## 3. gcov 覆盖率模块深度审查

### 3.1 架构亮点

- **lcov 全流程**：capture → filter → genhtml → JSON 解析，链路完整。
- **fail_under 双门禁**（行覆盖率 + 分支覆盖率），支持 `--fail-under` / `--fail-under-branch`。
- **物发布**：`coverage_pipeline.py` 支持 HTML + JSON + ZIP 压缩包一键发布。
- **Markdown 报告**：`save_coverage_markdown()` 输出简洁覆盖率表格。

### 3.2 关键缺陷

#### 缺陷 5：C 覆盖率模块无法开箱即用（高优先级）

**位置**：`gcov_coverage.py` 和 `stages.py` 中的 `run_c_coverage`/`run_c_coverage_check`

**问题**：
1. `run_c_coverage` 要求项目的编译产物中包含 `.gcda` / `.gcno` 文件（gcc `--coverage` / `-fprofile-arcs -ftest-coverage`）。新用户不知道需要：
   - 用 `gcc --coverage` 或 `-fprofile-arcs -ftest-coverage` 重新编译
   - 运行测试程序（生成 `.gcda`）
   - 再运行 `lcov --capture`

2. `run_c_coverage()` 和 `run_c_coverage_check()` 在 `stages.py` 中定义缺失：`layers.py` 中 import 了这两个函数但代码中看不到它们的实现（被截断），但 `stages.py` 的 `run_coverage_check` 只处理 Python coverage（`coverage run`），不处理 C 覆盖率。

3. lcov 过滤规则过于硬编码：
   ```python
   ["lcov", "--remove", lcov_file,
    "/usr/*", "/opt/*", "*/test/*", "*/tests/*", "*/build/*", ...]
   ```
   - 用户项目的第三方库可能在 `third_party/`、`vendor/`、`lib/` 等路径下，均不会被过滤。
   - 测试代码虽然过滤了 `*/test/*` 和 `*/tests/*`，但若用户将测试文件放在 `*/test_*` 文件中（位于源码目录），也会进入覆盖率统计，拉低覆盖率数据。

4. **Python 覆盖率 vs C 覆盖率的分离**：`run_coverage_check` 处理 Python 覆盖率（通过 `coverage run`），`run_c_coverage`/`run_c_coverage_check` 处理 C 覆盖率（通过 gcov/lcov）。但两个 pipeline 在实际项目中选择性执行时缺乏清晰的互斥/并行的文档说明。

#### 缺陷 6：默认 85% 覆盖率门槛对嵌入式项目不现实（高优先级）

`DEFAULT_COVERAGE_THRESHOLD_LINE = 85.0` / `DEFAULT_COVERAGE_THRESHOLD_COND = 80.0`

嵌入式 C/C++ 项目常见场景：
- 大量 MCU 外设初始化和 HAL 代码很难测试（无模拟器或需要硬件）
- startup/中断向量/汇编代码根本不可测试
- 第三方 BSP/库代码难以覆盖

新用户首次运行大概率达不到 85%，导致覆盖率门禁立即失败，且报错信息没有给出具体的低覆盖文件列表或建议如何设置模块级阈值。

`module_thresholds` 在配置中有定义，但在代码中从未被使用 —— 又是一个定义了但不生效的配置。

---

## 4. CI 整体架构审查

### 4.1 架构亮点

- **Layer 依赖链**：L1→L2→L2.5→L3 严格串行，任一 Layer 失败下游自动阻断，设计清晰。
- **A-01 严格模式**：`CI_STRICT=1` 环境下缺失工具直接报错而非跳过，适合 CI 环境。
- **A4 自动报告生成**：`run_all` 完成后自动调用 `report.exporter` 生成最终报告。
- **文档同步门禁（H-07）**：代码变更时检查对应文档是否更新，设计先进。
- **KPI 基线**（E08/E09）：`kpi.py` 支持 KPI 基线采集和过程稳定性 G-49 采集（构建成功率、回归触发率、违规修复时效）。

### 4.2 关键缺陷

#### 缺陷 7：Stages 模块代码过于庞大（中优先级）

`stages.py` > 30000 字节（被截断），单文件包含从 YAML 验证、clang-tidy、单元测试、覆盖率、SIL 测试、MISRA 检查、规约验证、架构审查、需求追溯等 15+ 个独立函数。

这导致：
- 难以维护：一个修改动到多个不相关函数
- `stages.py` 和 `stage_utils.py` 的分界不清晰（helper 函数被分散在两个文件中）
- 函数间可能存在未预期的 import 副作用

#### 缺陷 8：工具链前置校验缺失（高优先级）

新用户首次运行 `osh-cli ci run` 时，CI 不会预先校验环境中是否安装了必要的工具链：
- `cppcheck` + addon → 安装了吗？版本对吗？misra-c2023 要求 cppcheck 2.16+
- `lcov` / `genhtml` → 安装了吗？
- `gcc-arm-none-eabi` / Docker → 交叉编译需要吗？
- `gcov` → 版本匹配 gcc 吗？

目前是运行时依次尝试，遇到 FileNotFoundError 才报告。改进方向：`run_yaml_validation` 后加一个 `run_tool_check` 阶段，一次性检测所有所需工具。

#### 缺陷 9：HOOK_TYPE 机制对新手不透明（低优先级）

`_should_skip_coverage()` 会检查 `HOOK_TYPE=commit` 环境变量跳覆盖率的逻辑：对于未使用 git hooks 的用户（如命令行直接运行），永远不会设置此环境变量，所以覆盖率总是执行。但如果用户在 CI 环境中设置了 `HOOK_TYPE=push`，行为又不同。这个隐式约定缺乏文档说明。

---

## 5. 新用户最易出错的配置点

按出错概率从高到低排列：

### 🔴 P0 — 立即出错

| 排名 | 配置点 | 错误原因 | 典型报错 |
|:----:|:-------|:---------|:---------|
| 1 | 缺少 `compile_commands.json` | cppcheck 无编译上下文 → 大量 false positive MISRA 违规 | thousands of `missingInclude` + `misra-c2023-*` violations |
| 2 | 覆盖率门槛 85% | 嵌入式项目首次不可能达到 | `❌ Line coverage below threshold!` |
| 3 | `misra-rules.yaml` 不在项目根目录 | yuleOSH 自身项目的规则文件，用户自己的项目不同 | 静默失败（加载为空），MISRA 报告无规则信息 |
| 4 | clang-tidy / cppcheck 未安装 | CI 会以 `False` 阻塞流水线 | `❌ cppcheck not installed (strict mode)` |
| 5 | gcc --coverage 未使用 | 无 `.gcda` 文件 → lcov 失败 | `❌ Coverage tool not installed` 或 lcov timed out |

### 🟡 P1 — 容易出错

| 排名 | 配置点 | 错误原因 |
|:----:|:-------|:---------|
| 6 | 项目不是标准 `src/` + `tests/` 布局 | `_run_coverage_and_export()` 硬编码 `--source=src` 和 `tests/` |
| 7 | 交叉编译阶段需要 `src/cross/hello.c` | `_cross_compile_stage()` 检查此文件是否存在，没有则跳过但不是失败 |
| 8 | settings 层级覆盖优先级不清楚 | `misra.profiles.safety` vs `misra.rules` vs `misra.suppress_rules` 三者的关系 |
| 9 | `coverage.c_fail_under` 仅作用于 C 语言 | 用户可能误以为它控制 Python 覆盖率门槛 |

### 🟢 P2 — 可优化

| 排名 | 配置点 | 问题 |
|:----:|:-------|:-----|
| 10 | 项目没有 `tasks/` 或 `plans/` 目录 | `plan-lint` 报 "Missing kind classification" |
| 11 | `docs/.sync-gate.yaml` 不存在 | `docsync-gate` 以 warning 跳过，可能让用户困惑 |
| 12 | deviation `expires` 为过去日期 | 偏差过期不会自动通知，会造成"默默失效" |

---

## 6. 测试代码豁免 & 第三方库策略

### 6.1 当前状态

| 角度 | MISRA | 覆盖率 |
|:-----|:------|:-------|
| 测试代码 | 通过 `deviations` 条目加 `file: tests/**/*mock*.c` 豁免 | lcov filter 自动排除 `*/test/*` / `*/tests/*` |
| 第三方库 | 无系统性策略，需手动加 `deviations` | lcov filter 排除了 `/usr/*` / `/opt/*`，但 `third_party/` / `vendor/` 未排除 |
| 生成代码 | 通过 deviation + `file: src/**/gen/*.c` 方式 | lcov 无排除 |
| startup 代码 | 无标准机制 | lcov 无排除 |

### 6.2 问题分析

**1. 缺少正式的"测试代码豁免"（test-exemption）机制**

当前 MISRA 对测试文件的豁免依赖 deviation 手动配置。但这存在两个问题：
- **配置成本高**：每个测试文件/规则都要写一条 deviation 条目
- **语义混淆**：deviation 的设计初衷是"标识代码质量问题但暂不修复"，用于测试代码会混用语义

建议增加一个 `misra.skip_test_code: true` 配置项，自动跳过 `tests/`、`test_*`、`*_test.*` 文件（同时也给用户一个选择覆盖它们的选项）。

**2. 没有标准的"第三方代码目录"配置**

对于嵌入式项目常见的 `Drivers/`（STM32 HAL/LL）、`CMSIS/`、`FreeRTOS/`、`Middlewares/` 等目录，需要用户手动在 deviation 中逐个配置豁免。建议增加：
```yaml
coverage:
  exclude_paths:
    - "Drivers/**"
    - "Middlewares/**"
    - "third_party/**"
```

**3. 无自动检测 startup/初始化代码并豁免**

`startup_*.c`、`syscalls.c`、`system_*.c` 等 MCU 标准启动代码通常不可测也不应该被检。建议内置常见模式豁免。

---

## 7. 错误处理友好度评估

### 7.1 当前做法

| 错误场景 | 报错内容 | 是否给出修复建议 |
|:---------|:---------|:----------------|
| cppcheck 未安装 | `❌ cppcheck not installed (strict mode)` | ❌ 无 |
| 覆盖率低于阈值 | `❌ Line coverage below threshold!` | ❌ 无具体改进方向 |
| clang-tidy 报错 | `❌ clang-tidy found issues:\n{result.stdout[:300]}` | ❌ 无 |
| MISRA 违规 | `Omitted — see full report` 或 `❌ MISRA check failed` | ❌ 无 |
| 工具超时 | `⏭️  cppcheck timed out — blocked` | ❌ 无 |
| YAML 验证失败 | 列出错误条目 | ❌ 无 |
| JSON JSONDecodeError | `⏭️  Coverage JSON invalid: {e} — blocked` | ❌ 无 |
| lcov 失败 | `❌ Coverage tool not installed` | ❌ 无 |

### 7.2 问题总结

1. **从不告诉用户"下一步怎么做"**：所有错误信息都是"什么失败了"，没有一条是"你可能需要这样做"。
2. **MISRA 报错缺乏按严重级别过滤**：大量 style 违规会淹没 error 级别的真正问题，用户无法聚焦。
3. **覆盖率失败不给出低覆盖文件列表**：只说低于阈值，但不告诉用户哪些文件拉低了覆盖率。
4. **中文夹杂英文容易混淆**：代码注释是中文，但工具输出是英文，用户很难搜索/理解报错。
5. **文件路径不友好**：报错中的文件路径是全路径，没有相对路径且不可点击。

### 7.3 示例改进

当前：
```
❌ Line coverage below threshold!
```

改进后：
```
❌ 行覆盖率 42.3% < 阈值 85.0%
   低覆盖文件（按未覆盖行数排序）:
     1. src/drivers/stm32f4_hal.c: 1200 行未覆盖 (覆盖率 12%)
     2. src/startup/startup_stm32f4.s: 450 行未覆盖 (覆盖率 0%)
     3. src/system/system_stm32f4.c: 300 行未覆盖 (覆盖率 30%)
   改进建议:
     - 考虑为低覆盖模块设置 `module_thresholds`
     - 确认硬件相关代码是否应排除在覆盖率统计外
     - 参见: docs/ci/coverage.md
```

---

## 8. 质量改进优先级建议

### 🚨 立即修复（P0 — 解决首次运行必失败问题）

| 优先级 | 改进项 | 文件 | 工作量评估 |
|:------:|:-------|:-----|:----------|
| 1 | cppcheck 增加 `--project=compile_commands.json` 支持 | `stage_utils.py` / `stages.py` | 2-3 天 |
| 2 | 覆盖率失败时输出低覆盖文件列表和排序 | `run_coverage_check` in `stages.py` | 0.5 天 |
| 3 | `misra-rules.yaml` 缺失时给出显式警告而非静默失败 | `misra_report.py:load_rule_definitions()` | 0.5 天 |
| 4 | CI 启动时做工具链前置校验（pre-check） | 新增 `runner.py` 阶段 | 1 天 |

### 🔧 重要改进（P1 — 提升工程可用性）

| 优先级 | 改进项 | 工作量评估 |
|:------:|:-------|:----------|
| 5 | 增加 `coverage.exclude_paths` 配置（第三方库/生成代码豁免） | 1 天 |
| 6 | MISRA 增加 `skip_test_code` / `skip_generated` 配置 | 1 天 |
| 7 | 覆盖率失败信息增加具体改进建议链接 | 0.5 天 |
| 8 | 文档化 `fail_threshold` 和 `violations_per_kloc` 的实际使用 | 0.5 天 |
| 9 | 实现 `module_thresholds` 的代码逻辑（当前定义了但不生效） | 0.5 天 |
| 10 | `stages.py` 按功能拆分成多个小模块 | 1-2 天 |

### 📋 持续改进（P2 — 锦上添花）

| 优先级 | 改进项 | 工作量评估 |
|:------:|:-------|:----------|
| 11 | 错误信息标准化模板（失败原因 + 建议行动 + 文档链接） | 2 天 |
| 12 | 默认覆盖率门槛降至 60-70% 并建议用户根据实际调整 | 0.5 天 |
| 13 | c_coverage pipeline 增加自动检测 .gcda 文件存在性 | 0.5 天 |
| 14 | docsync 增加 `.yuleosh/ci-config.yaml` 变更自动检测 | 0.5 天 |
| 15 | 新建项目时 `osh-cli init` 自动生成适配件（misra-rules.yaml + ci-config.yaml 模板） | 3 天 |

---

## 9. 用户当前问题的排查清单

针对"明天华"运行 `osh-cli ci run` 遭遇 MISRA + 覆盖率双失败，建议按以下清单逐项排查：

### 第一步：确认工具链

- [ ] `cppcheck --version` — 是否为 2.16+（支持 misra-c2023）
- [ ] `cppcheck --addon=misra --list` — 确认 misra addon 可用
- [ ] `lcov --version` — lcov 是否安装
- [ ] `genhtml --version` — genhtml 是否安装
- [ ] `gcov --version` — 是否与编译器版本匹配
- [ ] `gcc --coverage` 是否已在编译参数中
- [ ] `clang-tidy --version` — 可选，无则跳过

### 第二步：确认编译数据库

- [ ] 项目根目录是否存在 `compile_commands.json`（由 CMake `-DCMAKE_EXPORT_COMPILE_COMMANDS=ON` 或其他 build 系统生成）
- [ ] 如果没有，配置 cppcheck 的 include 路径
  ```yaml
  # 在 ci-config.yaml 中（当前无此配置项，需硬编码在代码中）
  # misra.cppcheck_extra_args: ["-I", "path/to/headers", "-I", "Drivers/CMSIS/Include"]
  ```

### 第三步：调整覆盖率配置

- [ ] 检查 `coverage/c_fail_under` 值是否为 70（默认），是否需要根据项目实际降低
- [ ] 检查第三方库代码是否被纳入覆盖率统计
  ```bash
  lcov --summary coverage-filtered.info  # 看哪些文件被统计了
  ```
- [ ] 确认 `.gcda` 文件存在于 build 目录
  ```bash
  find build -name "*.gcda" | head -20
  ```

### 第四步：配置 MISRA 豁免

- [ ] 确认 `ci-config.yaml` 中 `misra.deviations` 是否覆盖了以下常见类别：
  - 第三方代码：`Drivers/**/*.c`
  - 测试代码：`tests/**/*.c`
  - 启动代码：`src/**/startup/*.c`
  - 生成代码：`src/**/gen/*.c`
- [ ] 确认 `misra.profiles` 中是否配置了合适的 profile
- [ ] 检查 `misra-rules.yaml` 是否存在于项目根目录（不是 yuleOSH 自身的，需是用户项目的）

### 第五步：使用增量模式而非全量模式

- [ ] 尝试 `osh-cli ci run --delta` 替代全量扫描
- [ ] 或先配置 `misra.fail_on_required = true; fail_on_advisory = false` 减少首次失败的严重度

### 第六步：环境变量检查

- [ ] `CI_STRICT` 是否设为未预期值（`0` 为正常，`1` 为严格模式）
- [ ] `MISRA_FAIL_FAST` 是否设为未预期值
- [ ] `HOOK_TYPE` 是否被错误设置导致覆盖率跳过

---

## 附录 A：文件清单（审查范围）

| 文件 | 行数 (约) | 功能 |
|:-----|:---------:|:-----|
| `ci/config.py` | 350+ | CI 配置加载、CiConfig/MisraConfig/CoverageConfig 数据类 |
| `ci/runner.py` | 200+ | run_all 编排、CLI 入口、工具函数 |
| `ci/layers.py` | 400+ | L1/L2/L2.5/L3 各层编排 |
| `ci/stages.py` | 600+ | 各 CI 阶段执行函数（YAML 验证 → clang-tidy → 测试 → 覆盖率 → MISRA → 规约等）|
| `ci/stage_utils.py` | 400+ | 覆盖率运行、交叉编译、HIL 测试等辅助函数 |
| `ci/misra_report.py` | 800+ | MISRA 报告生成：解析/分组/汇总/偏差/JSON+Markdown+Excel |
| `ci/misra_fusion.py` | 400+ | MISRA 三层融合（cppcheck+clang-tidy+AI） |
| `ci/tool_drivers.py` | 300+ | 工具驱动接口（CppcheckDriver, ClangTidyDriver stub） |
| `ci/rulesets.py` | 200+ | 规则集插件系统 |
| `ci/gcov_coverage.py` | 300+ | gcov/lcov 覆盖率采集和解析 |
| `ci/coverage_pipeline.py` | 300+ | 覆盖率 pipeline：门禁+报表+物发布 |
| `ci/result.py` | 50+ | CIResult 数据类 |
| `ci/kpi.py` | 200+ | KPI 基线采集（E08/E09/G-49） |
| `ci/profile.py` | 200+ | Profile 定义和步骤过滤（G-33） |
| `ci/sync_check.py` | 300+ | 文档同步门禁（E05/E06/H-07） |
| `ci/yaml_validator.py` | 200+ | YAML 配置验证 |
| `ci/review_helpers.py` | 250+ | JUnit 解析和 SHALL 自动映射 |
| `.yuleosh/ci-config.yaml` | 150+ | 实际工程配置样本 |

---

*报告由 yuleOSH Quality Architecture (Hermes) 自动生成*
*审查模式：Subagent 深度审查 | Schema: ci-quality-review-v1*

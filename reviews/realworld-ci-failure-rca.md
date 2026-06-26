# yuleOSH CI 实际工程应用 — 根因分析报告

> 编写日期：2026-06-26
> 分析范围：`src/yuleosh/ci/` 全模块、`ci-config.yaml`、MISRA 报告
> 场景：用户"明天华"将 yuleOSH 应用于嵌入式 C 项目，`osh-cli ci run` 失败

---

## 目录

1. [CI Pipeline 架构总览](#1-ci-pipeline-架构总览)
2. [MISRA 违规分析（98 条 violations）](#2-misra-违规分析)
3. [gcov 覆盖率分析](#3-gcov-覆盖率分析)
4. [YAML 配置验证问题](#4-yaml-配置验证问题)
5. [根因总结与排查路线图](#5-根因总结与排查路线图)
6. [向 yuleOSH 开发团队的建设性建议](#6-向-yuleosh-开发团队的建设性建议)

---

## 1. CI Pipeline 架构总览

### 1.1 分层结构

```
run.py (re-export hub)
  └─ runner.py (run_all / main CLI)
       ├─ run_layer1    → yaml-validation, spec-validation, arch-review, req-trace,
       │                   plan-lint, docsync-gate, clang-tidy, misra-check(delta),
       │                   unit-tests, coverage, c-coverage
       ├─ run_layer2    → cross-compile, static-analysis, sil-tests, integration-tests, memory-safety
       ├─ run_layer_25  → target-detect, hil-tests, report
       └─ run_layer3    → e2e-tests, version-check, evidence-pack
```

所有模块通过 `run.py` 作为 re-export hub 级联导出。**关键发现**：`run.py` 模块内部包含 mutable module-level state (`_notify`、`_ci_config_cache`、`_test_file_cache`)，子模块通过 `import yuleosh.ci.run as _run` 引用。

### 1.2 配置加载

```yaml
# ci-config.yaml 结构
ci:           # layers, layer_dependencies
coverage:     # threshold_line, threshold_condition, c_fail_under, strict
misra:        # enabled, addon, fail_on_required, fail_on_advisory, 
              # fail_threshold, violations_per_kloc, active_profile, 
              # rules, deviations, profiles, alm
hardware_test:# enabled, firmware, mock, serial_port...
docsync:      # 文档同步规则 (H-07)
```

### 1.3 代码扫描模式

| 模式 | 触发条件 | 扫描范围 | 阻断策略 |
|------|---------|---------|---------|
| delta (L1) | `mode="delta"`, 或 auto 模式下有 git diff | git diff HEAD~1 变更的 .c/.cpp | Required violations blocking |
| full (L2) | `mode="full"` 或 delta 模式无变更 | `src/` 下递归遍历 | 全量 + 新 Required 零容忍 |
| auto (默认) | 无 target_files 时 | 先尝试 git diff，失败则全量遍历 `src/` | 按配置阈值阻断 |

---

## 2. MISRA 违规分析

### 报告概览数据

| 指标 | 值 |
|------|-----|
| 总违规数 | **98** |
| 违反规则数 | 17 |
| 影响文件数 | 79 |
| 全部为 Style/Info 级别 | 86 Style + 12 Info |

### 2.1 核心根因：测试框架被纳入 MISRA 扫描

**最严重的问题是 98 条 violations 全部来自 `tests/unity/` 目录**，非用户生产代码：

- `tests/unity/src/unity.c` — 第三方单元测试框架（Unity Test Framework）
- `tests/unity/src/unity.h` — 框架头文件
- `tests/unity/src/unity_internals.h` — 内部头文件
- `tests/unity/test_hal_mock_unity.c` — 用户测试代码
- `tests/unity/test_hello_unity.c` — 用户测试代码

**这是最典型的误检场景**：测试框架代码本不应纳入 MISRA 合规检查。

### 2.2 违规分类明细

| MISRA 规则 | 数量 | 根因 |
|-----------|------|------|
| **Rule 17.7 (function call)** | 18 | Unity 框架中 `printf()` 调用用于测试输出，MISRA 禁止非固定格式串 |
| **Rule 2.5 (macro)** | 18 | Unity 框架头文件中的 `#define TEST_ASSERT_*` 等宏 |
| **Rule 8.7 (function linkage)** | 12 | Unity 函数未使用 `static` 且未外部声明 |
| **Rule 15.6 (if-else)** | 7 | Unity 框架中的 if 体未用 `{}` 括起来 |
| **None (missingInclude)** | 23 | 测试文件中 `#include "unity.h"` 找不到路径——**include path 问题** |
| **Rule 8.4 (declaration)** | 4 | 测试 main() 和 setUp() 无前置声明 |
| **Rule 2.3 (typedef)** | 4 | Unity typedef 定义但未使用 |
| **其他** | 12 | Rule 12.1(2), 14.4(2), 20.10(1), 21.4(1), 21.6(1), 21.16(1), 7.4(1), 5.5(1), 20.5(1), 8.6(1) |

### 2.3 根因路径追踪

#### 根因 A：未排除测试目录 `tests/`

**代码路径**：`stages.py` → `run_misra_check()` → `_find_c_sources()`

```python
# stage_utils.py: _find_c_sources()
def _find_c_sources(project_dir):
    src_dir = os.path.join(project_dir, "src")  # 只搜索 src/ 目录
    ...
    for root, dirs, files in os.walk(src_dir):
        ...
```

但是在 `run_misra_check()` 的 "auto" 模式下：

1. 第一步尝试 `git diff HEAD~1` 获取变更文件
2. 如果 git 不可用或空，才回退到 `_find_c_sources()` 的 `src/` 范围

**但 `run_layer1` 实际调用时：** `lambda pd, ci: run_misra_check(pd, ci, mode="delta")`

在 delta 模式下，扫描范围来自 `target_files` 参数。**如果用户在测试文件中做了修改（包括 unity 框架本身），这些文件会被自动加入扫描。** 这意味着：

- 用户的嵌入式 C 项目中，`tests/unity/` 下的文件一旦有 git 变更，就被纳入 MISRA 检查
- Unity 测试框架本身是为测试而设计的 C 代码，完全不遵循 MISRA 规范（printf、宏、非标准构造等）

#### 根因 B：`missingInclude` 的 23 条假阳性

测试文件 `test_hal_mock_unity.c` 中：
```c
#include "unity.h"               // 找不到 — cppcheck 未配置 -I 路径
#include "hal_mock/mock_core.h"  // 找不到
#include "hal_mock/uart_mock.h"  // 找不到
...
```

这些问题本质是 **cppcheck 的 include path 未配置**，而不是真正的 MISRA 违规。实际运行时：
- cppcheck 未通过 `-I tests/unity/src/` 传递 include 路径
- 导致所有 `#include` 都报 `missingInclude` 错误
- 进一步导致后续函数分析不正确（很多函数被认为 unused）

#### 根因 C：`active_profile = "safety"` 最严格模式

```yaml
misra:
  active_profile: safety         # 最严格模式
  fail_on_required: true         # Required 违规即阻断
  fail_threshold: 10             # 超过 10 条即阻断
```

profile 系统（`profile.py`）有 `safety`、`ci`、`performance`、`testing` 四种内置 profile。当前配置为 `safety`，意味着：
- 所有 MISRA 规则 100% 启用
- 没有通过 `rule_overrides` 关闭测试代码的规则
- `fail_threshold = 10`，98 条远超阈值

#### 根因 D：非对称的 deviations 配置

配置文件中定义了 10 条 deviation，**其中 8 条针对不存在的文件**：

| 配置的 deviation | 实际违规位置 | 覆盖率 |
|----------------|-------------|--------|
| `src/**/legacy/old_protocol.c` | ❌ 不在违规报告中 | ❌ |
| `src/**/drv_timer.c` | ❌ 不在违规报告中 | ❌ |
| `src/**/hal/*.c` | ❌ 不在违规报告中 | ❌ |
| `src/**/mem_pool.c` | ❌ 不在违规报告中 | ❌ |
| `src/**/startup/*.c` | ❌ 不在违规报告中 | ❌ |
| `src/**/config/*.c` | ❌ 不在违规报告中 | ❌ |
| `src/**/gen/*.c` | ❌ 不在违规报告中 | ❌ |
| `src/**/test/*.c` | 覆盖了 test_* 文件的部分 | ⚠️ 部分 |
| **`tests/**/*mock*.c`** | 不匹配 `tests/unity/test_hal_mock_unity.c` | **文件匹配失败** |
| `Rule-99.9` / `Rule-Test-DryRun` | 测试数据，无实际规则 | ❌ |

**关键问题**：deviation 文件匹配使用了 glob pattern，但：
1. `tests/**/*mock*.c` 可以匹配 `tests/unity/test_hal_mock_unity.c`，但 `src/**/test/*.c` 不会匹配 `tests/` 下的文件
2. deviation 规则 `misra-c2023-10.1` 绑定到 `mock*.c` 文件，但报告中的违规不涉及 Rule 10.1
3. 存在两个"测试数据"deviation（Rule-99.9、Rule-Test-DryRun）

### 2.4 关于中断签入

ci-config.yaml 中 `suppress_rules: []` 为空列表。如果用户通过 `osh-cli ci config --suppress-rule misra-c2012-17.7` 之类的方式想压制规则，但实际配置未生效。

---

## 3. gcov 覆盖率分析

### 3.1 架构

```
run_layer1()
  └─ run_c_coverage(project_dir, ci)    # 生成覆盖率报告
       └─ gcov_coverage.generate_c_coverage_report()
            ├─ run_gcov_coverage()        # lcov capture + genhtml
            └─ parse_lcov_output()        # 解析为结构化 JSON
```

### 3.2 典型配置问题

#### 问题 1：Build 目录未找到

**代码路径**：`stages.py:929` → `run_c_coverage()`

```python
coverage_dirs = [
    os.path.join(project_dir, "build"),
    os.path.join(project_dir, "build", "coverage"),
    os.path.join(project_dir, "cmake-build-coverage"),
    os.path.join(project_dir, "build", "Debug"),
]
```

**问题**：搜索列表固定，如果用户的嵌入式项目使用：
- `_build/`（CMake 默认 out-of-source）
- `out/`、`Release/`、`Debug/`
- `build_arm/`、`build_x86/`
- `build/gcc/arm-none-eabi/`

则 coverage 数据 `gcda/gcno` 文件**不会被发现**，导致 `run_c_coverage` 返回 skipped。

#### 问题 2：gcda/gcno 文件不存在

覆盖率要求编译器使用 `--coverage` / `-fprofile-arcs -ftest-coverage` 编译和链接。常见缺失原因：
- CMakeLists.txt 中未设置 `CMAKE_C_FLAGS_COVERAGE` 或 `-fprofile-arcs`
- 编译时未使用 Debug/RelWithDebInfo 配置
- 测试运行后 `gcda` 被清理
- 使用了容器化构建但未挂载 build 目录

#### 问题 3：lcov / genhtml 未安装

`gcov_coverage.py` 的 `run_gcov_coverage()` 中：

```python
except FileNotFoundError:
    result["error"] = "lcov not installed"
```

嵌入式开发环境（特别是 macOS、Docker 容器、MinGW）可能默认不安装 lcov 和 genhtml。注意：
- macOS: `brew install lcov`
- Ubuntu/Debian: `apt install lcov`
- Docker: 需在 Dockerfile 中添加

#### 问题 4：Python 覆盖率与 C 覆盖率混淆

`run_layer1` 中同时调用了：
- `run_coverage_check()` — Python coverage（`coverage run -m pytest`）
- `run_c_coverage()` — C/C++ gcov/lcov

用户可能以为一个覆盖了另一个，实际：
- Python coverage：检查 `src/` 下的 Python 代码（阈值 85%）
- C coverage：检查编译后的 C 代码（`c_fail_under: 70`）

#### 问题 5：C coverage gate 未严格阻断

`run_layer1` 调用链：

```python
stages = [
    ...
    ("c-coverage", run_c_coverage),     # 只生成报告，不阻断
]
```

而 `run_c_coverage_check()` 才是真正的阻断门禁，但 **`run_layer1` 并未调用它**。这意味着即使 C 覆盖率远低于阈值，**流水线仍然会 pass**，除非用户自行在 ci-config.yaml 中扩展 stages。

---

## 4. YAML 配置验证问题

### 4.1 未知顶级键问题

`yaml_validator.py` 中 `_CI_CONFIG_SCHEMA` 定义了已知顶层键：

```python
known_keys = {"ci", "coverage", "misra", "hardware_test"}
```

但实际的 `ci-config.yaml` 中有一个 `docsync` 块。

**验证时会报错**：`root.docsync: unexpected key`

该问题不会阻止配置加载（`config.py` 走的是忽略未知键的路径），但 **YAML 验证门禁会失败**。

### 4.2 `docsync` 结构未在 schema 中定义

`docsync` 块是 H-07 需求的一部分，包含 `enabled`、`rules`（列表）、`exempt_paths`、`critical_docs` 等结构。由于未在 yaml_validator 中注册，验证时：
1. 根级别的 `docsync` 报未知键
2. 子字段不做验证

### 4.3 `misra-rules.yaml` 未找到

配置中有 `rule_texts_path: misra-rules.yaml`，但：

```python
# stages.py 中
rule_defs_path = Path(__file__).resolve().parent.parent.parent.parent / "misra-rules.yaml"
```

这个路径解析到 yuleOSH 项目根。如果用户项目中没有 `misra-rules.yaml`，会尝试从 yuleOSH 安装路径寻找。但配置中的相对路径是相对于**用户项目根**的，如果文件不存在：
- `load_rule_definitions()` 返回空 dict
- 导致 report 中的 `enrich_with_definitions` 无规则描述
- MISRA 报告中显示 `(use --rule-texts=<file> to get proper output)`

### 4.4 `suppress_rules: []` 空列表

```yaml
suppress_rules: []  # 空列表意味着无规则被压制
```

如果用户期望压制某些规则（如 `17.7`），需显式添加：
```yaml
suppress_rules:
  - "17.7"
  - "2.5"
```

---

## 5. 根因总结与排查路线图

### 5.1 优先级 P0（立即阻断，必须修复）

| # | 问题 | 根因文件 | 解决方案 |
|---|------|---------|---------|
| 1 | `tests/` 目录被 MISRA 扫描 | `stages.py:run_misra_check` + delta 模式 | 添加测试目录排除逻辑，或在 ci-config.yaml 中增加 `exclude_paths` |
| 2 | `missingInclude` 假阳性 | cppcheck 调用未传 `-I` | `run_misra_check()` 中自动追加 `-I tests/ -I tests/unity/src/` |
| 3 | 98 条违规远超阈值 (10) | `fail_threshold: 10` | 临时提高阈值或切换 profile 为 `ci` |

### 5.2 优先级 P1（可能阻断，需检查）

| # | 问题 | 说明 | 排查方向 |
|---|------|------|---------|
| 4 | Build 目录不匹配 | `coverage_dirs` 列表硬编码 | `ls -la` 检查项目构建输出目录 |
| 5 | lcov 未安装 | `FileNotFoundError: lcov` | `which lcov && which genhtml` 检查 |
| 6 | gcda/gcno 文件不存在 | 编译未启用 coverage flags | 检查 `CMakeFlags` 或 Makefile 中是否有 `--coverage` |
| 7 | YAML 验证失败 | `docsync` 为未知键 | 升级 yaml_validator schema 或暂时忽略该检查 |

### 5.3 优先级 P2（非阻断，但不合规）

| # | 问题 | 建议 |
|---|------|------|
| 8 | Deviations 与实际违规不匹配 | 为 `tests/unity/src/unity.c` 添加合规 deviation |
| 9 | `Rule-99.9`、`Rule-Test-DryRun` 等测试数据未清理 | 从 ci-config.yaml 移除 |
| 10 | `docsync` 未纳入 schema 验证 | 更新 yaml_validator.py 的 `_CI_CONFIG_SCHEMA` |
| 11 | `run_c_coverage_check` 未在 L1 中调用 | 加入 `run_layer1` 的 stages 列表 |

### 5.4 用户排查步骤（今晚可操作）

```bash
# 1. 验证问题范围：只检查用户源码
cppcheck --addon=misra --language=c --std=c11 --enable=all src/
# 应该只有 0 个或少量违规

# 2. 验证 lcov 可用性
which lcov && lcov --version

# 3. 验证 build 目录结构
ls -la build/
find build/ -name "*.gcda" -o -name "*.gcno" | head -5

# 4. 临时配置修复（ci-config.yaml 调整）
# 切换 profile 为 ci
active_profile: ci

# 5. 添加测试文件排除
# ci-config.yaml 需新增 exclude_paths 字段（当前版本无此功能）
# 目前只能通过 suppress_rules 或 deviation 绕过
```

---

## 6. 向 yuleOSH 开发团队的建设性建议

### 6.1 架构级建议

**S1 - 文件排除机制**（最优先）
当前 CI 完全**没有**路径排除机制。需要在以下位置增加 `exclude_paths` 支持：
- `stages.py:run_misra_check()` — 扫描前排除 `tests/`、`**/test_*.c`
- `config.py:MisraConfig()` — 增加 `exclude_paths: list[str]` 字段
- `ci-config.yaml` schema — 注册 `exclude_paths`

```yaml
# 建议新增
misra:
  exclude_paths:
    - "tests/**"
    - "**/*test*.c"
    - "**/unity/**"
    - "third_party/**"
```

**S2 - 三层覆盖率的正交化**
当前 Python coverage 和 C coverage 在 `run_layer1` 中混在一起。建议：
- 将 `run_coverage_check`（Python）重命名为 `run_py_coverage_check`
- 将 `run_c_coverage` + `run_c_coverage_check` 组成完整子流程
- 在日志输出中明确区分两种覆盖率类型

**S3 - delta 模式的安全边界**
delta 模式自动包含 git diff 中所有变更文件，没有"只扫描 `src/`"的安全边界。建议：
- delta 模式也基于 `src/` 白名单过滤 — 只扫描 `src/` 下的变更
- 或增加 `delta_exclude:` 配置项

**S4 - Deviation 系统增强**
当前 deviation 只有"文件级匹配"，缺少：
- 目录级别（如 `tests/` 目录下所有文件自动豁免）
- 规则级别（如"Rule 17.7 所有文件豁免"）
- 按 severity 豁免（如 Style/Info 级别永远不阻断）

### 6.2 配置相关

**S5 - `docsync` schema 缺失**
更新 `yaml_validator.py:_CI_CONFIG_SCHEMA` 包含 `docsync` 块的结构定义。

**S6 - 默认 profile 应更安全**
当前默认 `active_profile: safety` 对于首次集成的用户过于严格。建议：
- 新增用户 project 时默认 `ci` profile
- 在 README 中显式说明 profile 切换方式
- 在首次 `ci run` 时输出 profile 建议

### 6.3 CI 用户体验

**S7 - MISRA 报告格式改进**
当前报告违反的文件名由于 cppcheck 输出格式特殊，展示为畸形路径字符串（如 `              ^/Users/.../unity.c`）。这是 cppcheck 输出的行内标记未正确处理。

**S8 - C 覆盖率门禁缺失**
确认 `run_c_coverage_check` 应该加入 `run_layer1` 的 stages 列表。当前调用链中缺失这块。

**S9 - gcov 构建目录检测扩展**
`coverage_dirs` 应支持用户自定义或通过环境变量（如 `COVERAGE_BUILD_DIR`）配置。

---

## 附录：关键代码路径速查

| 功能 | 入口文件 | 关键函数 | 行号 |
|------|---------|---------|------|
| MISRA 扫描 | `stages.py` | `run_misra_check()` | 432 |
| MISRA 报告格式化 | `misra_report.py` | `parse_cppcheck_output()` | — |
| C 覆盖率 | `stages.py` | `run_c_coverage()` | 929 |
| C 覆盖率执行 | `gcov_coverage.py` | `run_gcov_coverage()` | 38 |
| C 覆盖率门禁 | `stages.py` | `run_c_coverage_check()` | 1006 |
| YAML 验证 | `yaml_validator.py` | `validate_ci_config()` | 104 |
| 配置加载 | `config.py` | `load_ci_config()` | 117 |
| Profile 切换 | `profile.py` | `filter_steps_for_profile()` | 117 |
| Build 目录检测 | `stages.py` | `run_c_coverage()` 中 | 943-962 |
| 源码发现 | `stage_utils.py` | `_find_c_sources()` | 419 |

---

*本报告基于 yuleOSH 源码 v2026.06 分析生成。*
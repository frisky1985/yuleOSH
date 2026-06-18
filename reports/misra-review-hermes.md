# MISRA C:2023 集成 + 测试补全 — 审查报告

> **审查人**: 小马 🐴（质量架构师）
> **日期**: 2026-06-18
> **审查范围**:
> - Spec 文件审查（`specs/misra-c2023-spec.md`, `specs/misra-acceptance-matrix.md`）
> - misra-rules.yaml 内容审查（等待小克创建）
> - 现有测试模式审查
> - 测试补全发现

---

## 1. Misra-rules.yaml 审查

### ⚠️ 状态：文件尚未创建

截至审查时间，`misra-rules.yaml` 还未被小克 👨‍💻 创建。我已完成规范和验收矩阵，但规则文件本身需要小克完成后我再做逐条审查。

### 预期内容

根据 `specs/misra-c2023-spec.md` Section 3.2，预期 `misra-rules.yaml` 包含：

```yaml
rules:
  - rule: "Rule 1.1"
    category: "Required"
    description: "实现不得包含未定义行为"
    severity: "critical"
    enabled: true
    check: "cppcheck"
    rationale: "C 语言标准定义的行为确保可移植性和确定性"
  # ... （约 60~80 条启用规则，含全部 TOP 20）
```

### 审查待办（小克完成后执行）

1. ⬜ 确认规则编号准确对应 MISRA C:2023（非旧版 C:2012）
2. ⬜ 确认描述聚焦"违反场景"而非"修复方法"
3. ⬜ 确认 Required 规则 severity 不低于 "major"
4. ⬜ 确认 TOP 20 全部启用且不可通过 config 禁用
5. ⬜ 确认 YAML schema 合规（rule, category, description, severity, enabled, check, rationale）

---

## 2. 现有代码审查发现

### 2.1 CI 静态分析阶段 — 风险发现

| # | 发现 | 严重度 | 位置 | 建议 |
|:-:|:-----|:------|:-----|:-----|
| F-01 | `_static_analysis_stage()` 使用 `cppcheck --enable=all` 没有 MISRA 过滤 | **critical** | `stage_utils.py:206` | 修改为 `cppcheck --misra=` 根据 `misra-rules.yaml` 启用规则 |
| F-02 | `cppcheck` 输出被整体丢弃仅检 errorlevel，无法解析每条违规 | **major** | `stage_utils.py:212-215` | 保存 cppcheck stdout/stderr 到文件并解析 JSON 输出 (`--xml` 或 `--json`) |
| F-03 | MISRA 违规报告不保存为结构化格式 | **major** | `stage_utils.py:216-219` | 在 `_static_analysis_stage` 中添加保存 `.osh/ci/misra-report-*.json` |
| F-04 | `MISRA_FAIL_FAST` 仅在 `stages.py` 的 `run_clang_tidy` 中使用，未在 `_static_analysis_stage` 中检查 | **major** | `stage_utils.py:206-219` | 在 `_static_analysis_stage` 中读取 `is_misra_fail_fast()` 并应用 |
| F-05 | `run_clang_tidy()` 限制为前 20 个文件 | **minor** | `stages.py:85` | 小项目影响不大；大型项目当文件 >20 时后文件不检查 |
| F-06 | `_static_analysis_stage` 调用时 `c_files` 来自 `src/` 但忽略 `cross/` 和 `templates/` | **minor** | `stage_utils.py:190-196` | 如果项目有 C 代码在别处，不会检查 |
| F-07 | 没有任何地方引用 `misra-rules.yaml` 来控制 cppcheck 行为 | **critical** | CI 全部 | `config.py` 需要解析 MISRA 配置；`stages.py`/`stage_utils.py` 需读取规则文件 |

### 2.2 架构风险

**R-01: cppcheck 对 MISRA C:2023 的支持**
cppcheck 2.13+ 支持 `--misra=` 标志，但覆盖的规则数量有限（约 90+ 条，非全部 180 条）。对于未被覆盖的规则，需要：
1. `clang-tidy` 后备
2. 手动检查工作流
3. 文件中标记哪些规则为 "manual" check

**R-02: 规则配置文件格式冲突**
如果 `misra-rules.yaml` 规则声明 cppcheck 不支持，则 CI 检查会无声跳过。建议在每个规则条目中增加 `check_support` 字段或运行时验证。

### 2.3 现有 ci/config.py 审查

`config.py` 当前无 MISRA 配置。需要新增：

```python
@dataclass
class MisraConfig:
    enabled: bool = True
    ruleset: str = "misra-rules.yaml"
    fail_on_required: bool = True
    max_warnings: int = 100
    deviation_file: str = "docs/misra-deviations.md"
```

并集成到 `CiConfig` 和 `_parse_ci_config` / `load_ci_config` 中。

---

## 3. 测试模式审查

### 3.1 现有测试风格分析

| 维度 | 现状 | 评估 |
|:-----|:-----|:-----|
| **框架** | pytest + unittest.mock | ✅ 成熟，有 300+ 测试 |
| **Fixtures** | `tmp_project` fixture（创建 tempdir + .yuleosh 目录） | ✅ 标准模式 |
| **Mock 策略** | `with patch("yuleosh.ci.run.subprocess.run")` + `patch.dict(os.environ)` | ✅ 良好 |
| **测试粒度** | 函数级别（`test_*` 测试单个函数） | ✅ 可维护 |
| **覆盖率** | 现有 ~85% 整体 | ✅ 目标合理 |
| **导入方式** | `sys.path.insert(0, ...)` 或相对导入 | ⚠️ 新旧模式混用 |

### 3.2 测试补全建议

#### compliance 模块（当前覆盖率约为 0 — 无测试文件）

需要覆盖的核心路径：

| 测试目标 | 测试名称 | 覆盖路径 |
|:---------|:---------|:---------|
| ComplianceChecker.__init__ | test_compliance_checker_init | 构造 + 模板加载 |
| ComplianceChecker.run | test_compliance_checker_run_full | 正常全路径：有所有目录和文件 |
| ComplianceChecker.run | test_compliance_checker_run_empty | 空项目：所有检查失败 |
| ComplianceChecker._file_exists | test_compliance_file_exists | 存在/不存在 |
| ComplianceChecker._file_exists | test_compliance_file_exists_exception | 异常路径 |
| ComplianceChecker._has_traced_requirements | test_compliance_traceability | traceability-matrix.md 存在/不存在 |
| ComplianceChecker._count_unit_tests | test_compliance_count_tests | tests/ 目录有/无 test_*.py |
| ComplianceChecker._check_bp | test_compliance_bp_all_pass | 所有 BP 检查通过 |
| ComplianceChecker._check_bp | test_compliance_bp_partial_fail | 部分 BP 检查失败 |
| ComplianceChecker.generate_report_markdown | test_compliance_report_markdown | 输出 markdown 格式正确 |
| ComplianceChecker.run_and_save | test_compliance_run_and_save | 写入文件成功 |

#### 测试文件命名规范

遵循现有模式：
- 主测试：`test_compliance_checker.py`
- 扩展测试：`test_compliance_checker_deep.py`
- smoke 测试：`test_compliance_smoke.py`（可选，快速导入检查）

#### 测试代码示例（预期风格）

```python
"""Tests for yuleosh.compliance.compliance_checker."""

import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_project():
    """Create a temporary project with minimal structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_compliance_checker_init_default():
    """GIVEN a project directory
    WHEN ComplianceChecker is created
    THEN it loads the ASPICE template successfully.
    """
    from yuleosh.compliance.compliance_checker import ComplianceChecker
    checker = ComplianceChecker(project_dir="/tmp")
    assert checker.template is not None
    assert "swe.1" in checker.template
```

---

## 4. 总结

### 已交付

| 交付物 | 路径 | 状态 |
|:-------|:-----|:-----|
| Spec 契约层 | `specs/misra-c2023-spec.md` | ✅ 完成 |
| 验收判定矩阵 | `specs/misra-acceptance-matrix.md` | ✅ 完成 |
| 审查报告 | `reports/misra-review-hermes.md` | ✅ 进行中 |

### 待小克完成

| 项目 | 优先级 | 描述 |
|:-----|:-------|:-----|
| `misra-rules.yaml` | P0 | 创建规则配置文件（供我审查） |
| `config.py` MISRA 配置 | P0 | 新增 MisraConfig dataclass + 解析 |
| `stages.py` / `stage_utils.py` 修改 | P0 | _static_analysis_stage 使用 --misra= 参数，保存 JSON 报告 |
| compliance 测试补全 | P1 | compliance_checker.py 覆盖率从 0→85% |
| pipeline 测试补全 | P1 | 维持 ≥80% |

### 关键风险

1. 🚨 **F-01 + F-07**: 当前静态分析阶段没有 MISRA 感知 — 完全通用的 cppcheck
2. 🚨 **F-03**: MISRA 违规不保存为结构化证据 — ASPICE SWE.4/SWE.5 合规性受损
3. ⚠️ **R-01**: cppcheck 对 MISRA C:2023 的不完全支持需要规划和文档
4. ⚠️ **misra-rules.yaml 未创建**: 所有顶级规则过滤依赖该文件

---

*审查完毕。问题直接写出，欢迎小克 👨‍💻 交流。*

---

## 5. 后续修复审查（2026-06-18 第2轮）

> **审查范围**: 小克正在执行的 4 项修复
> - Fix A: 增量检查 (delta check)
> - Fix B: Dir 系列规则补齐
> - Fix C: MisraConfig 默认值优化
> - Fix D: 工具依赖自动安装 (yuleosh init)
> **审查基准**: working tree 未提交变更（`git diff HEAD`）

---

### 5.1 Fix B: Dir 系列规则审查

**文件**: `misra-rules.yaml` — 新增 `misra-c2023-dir-4.1` ~ `misra-c2023-dir-4.10`

#### 编号正确性

| 规则 ID | MISRA C:2023 对应 | 问题 |
|:--------|:------------------|:-----|
| `misra-c2023-dir-4.1` | Dir 4.1 (Runtime failure detection) | ✅ 编号正确，描述合理 |
| `misra-c2023-dir-4.2` | 实际应为 Dir 4.2 (Use of dynamic memory/heap) | 🚨 **与 misra-c2023-1.2 重复**："避免未定义行为" 已是 Rule 1.2 的内容。Dir 4.2 应聚焦**动态内存使用约束**（如 malloc/free 约束） |
| `misra-c2023-dir-4.3` | Dir 4.3 (Assembly language) | ✅ 编号正确 |
| `misra-c2023-dir-4.4` | Dir 4.4 (Unicode encodings) | ✅ 编号正确 |
| `misra-c2023-dir-4.5` | Dir 4.5 (char type) | ✅ 编号正确 |
| `misra-c2023-dir-4.6` | Dir 4.6 (size_t/ptrdiff_t) | ✅ 编号正确 |
| `misra-c2023-dir-4.7` | Dir 4.7 (setjmp/longjmp) | ⚠️ **与 misra-c2023-21.8 重复**：Rule 21.8 已覆盖 "Setjmp and longjmp should not be used"。Dir 4.7 应更聚焦**异常控制流约束**而非重复规则内容 |
| `misra-c2023-dir-4.8` | Dir 4.8 (Macros) | ✅ 编号正确 |
| `misra-c2023-dir-4.9` | Dir 4.9 (Conditional compilation) | ✅ 编号正确 |
| `misra-c2023-dir-4.10` | Dir 4.10 (Diagnostic information) | ✅ 编号正确 |

> **共性问题**: 缺少 Dir 1.1（ISO C standard compliance documentation）、Dir 2.1（Documentation requirements）、Dir 3.1（Include file documentation），这些在 MISRA C:2023 中也有定义。

#### 描述聚焦度

| 规则 ID | 当前描述 | 问题 | 建议修正 |
|:--------|:---------|:-----|:---------|
| Dir 4.1 | "程序应确保所有数组引用、指针运算和内存访问都在有效边界内" | ❌ 描述违反目标而非违反场景 | "数组索引越界、指针运算超出有效范围或内存访问越界" |
| Dir 4.3 | "汇编代码应封装在内联函数或汇编模块中，不得散布在 C 代码中" | ✅ 明确违反场景 | — |
| Dir 4.5 | "char 类型仅用于字符数据；不得用于数值计算或布尔判断" | ✅ 明确违反场景 | — |
| Dir 4.9 | "条件编译指令（#if / #ifdef / #ifndef）应确保所有分支都有明确定义且编译通过" | ⚠️ 偏目标描述 | "条件编译分支缺少明确定义或存在分支无法编译通过" |

#### Severity 评级

| 规则 ID | 当前 Severity | 评估 |
|:--------|:-------------|:-----|
| Dir 4.1 | required | ✅ 合理 — 边界安全是安全关键系统的核心 |
| Dir 4.2 | required | ✅ (若修正为动态内存约束，required 合理) |
| Dir 4.3 | advisory | ⚠️ 争议 — 在安全关键系统中汇编使用需要严格审查，建议 required |
| Dir 4.4 | advisory | ✅ 合理 — 编码一致性问题更适合 advisory |
| Dir 4.5 | required | ✅ 合理 |
| Dir 4.6 | advisory | ✅ 合理 — 最佳实践性建议 |
| Dir 4.7 | required | ✅ 合理 |
| Dir 4.8 | advisory | ✅ 合理 |
| Dir 4.9 | required | ✅ 合理 |
| Dir 4.10 | advisory | ✅ 合理 |

**审查结论**: 目录结构正确，但 Dir 4.2 内容需要修正（避免与 Rule 1.2 重复），Dir 4.7 应与 Rule 21.8 区分聚焦点。

---

### 5.2 Fix A: Delta Check 实现审查

**文件**: `src/yuleosh/ci/stages.py` — `run_misra_check()` 函数（working tree 版本）

#### 已实现功能

| 特性 | 状态 | 说明 |
|:-----|:------|:-----|
| `target_files` 参数 | ✅ | 外部调用可传入指定文件列表 |
| `git diff --name-only HEAD~1` 自动检测 | ✅ | 无指定文件时自动获取变更 |
| Delta/Full 模式标签 | ✅ | "增量检查" / "全量检查" 显式标记 |
| Fallback 到全量扫描 | ✅ | git 命令失败时回退到 `os.walk(src/)` |

#### 安全隐患

| # | 问题 | 严重度 | 说明 | 建议 |
|:-:|:-----|:------|:-----|:-----|
| D-01 | `git diff HEAD~1` 在首次 commit 场景失败时被吞掉 | **major** | `try/except` 捕获了 `FileNotFoundError` 和 `TimeoutExpired`，但 `HEAD~1` 失败时 git 返回 `returncode=128` + stderr，不会被任何 except 分支捕获。`git_result.returncode == 0` 为 False 后进入 fallback ✅，但 stderr 会被打印到用户终端或日志 | 确认 `subprocess.run()` 的 stderr 不会污染用户输出；考虑在 fallback 时加一个静默提示 |
| D-02 | Delta 模式下路径不一致 | **minor** | `changed_files` 是 git 工作树相对路径（如 `src/main.c`），拼接 `os.path.join(project_dir, f)` 后可能与 `os.walk` 产生的绝对路径不一致。报告中的 `file` 字段路径格���不一致 | 统一使用相对于 `project_dir` 的路径，或在 delta 模式添加路径规范化 |
| D-03 | Delta 报告未标记增量 | **minor** | `misra-report.json` 的 `generated_at` 和文件内容不标记这是增量模式的结果。后续审计无法区分增量/全量报告 | 在 JSON 报告 `meta` 中添加 `check_mode: "delta" | "full"` |
| D-04 | KLOC 估算在 delta 下失真 | **minor** | `violations_per_kloc: 2.0` 在 delta 模式下只计算几个文件的 KLOC，可能被少量违规触发阻断 | Delta 模式下应禁用 KLOC 密度检查，或改用全量 KLOC 作分母 |

**审查结论**: Delta 检查的架构设计合理。D-02~D-04 是 minor 问题可后期优化。D-01 需要确认 fallback 行为是否干净。

---

### 5.3 Fix C: MisraConfig 默认值优化审查

**文件**: `src/yuleosh/ci/config.py` (working tree diff)

#### 默认值变更对比

| 字段 | 旧默认值 (HEAD) | 新默认值 (working tree) | 审查意见 |
|:-----|:---------------|:-----------------------|:---------|
| `fail_on_violation` | `False` | `True` | ⚠️ **合理但需要谨慎**：任何 violation 就阻断是安全关键系统的正确行为，但会破坏现有没有 MISRA 合规的项目。建议配合 `fail_threshold` 使用 |
| `fail_on_advisory` | — (新增) | `False` | ✅ 合理 — Advisory 不应阻断流水线 |
| `fail_threshold` | `10` | `10` (不变) | ✅ 合理 — 允许少量违规 |
| `violations_per_kloc` | — (新增) | `2.0` | ⚠️ **对嵌入 C 项目偏低**：嵌入式项目（特别是自动生成的 HAL 代码）KLOC 密度高，2.0 可能太严格。评估值：1 KLOC 允许 2 条违规，100 KLOC 项目允许 200 条 — 对于安全关键项目合理，但对早期项目可能严格 |

#### 影响分析

| 影响维度 | 详细说明 |
|:---------|:---------|
| **现有用户** | `fail_on_violation` 从 False → True 是 breaking change。已有 CI 配置的项目如果没有显式设置 `fail_on_violation: false`，升级后将突然阻断 |
| **新项目** | `fail_on_violation=True` 是新项目的好默认值 — 符合安全关键开发的"从严"原则 |
| **迁移策略** | 建议在 CHANGELOG 中注明，并在 yuleosh init 生成的默认 ci-config.yaml 中包含显式的 MISRA 配置段 |

**审查结论**: 默认值优化方向正确。`fail_on_violation=True` 和 `violations_per_kloc=2.0` 对于嵌入式安全关键场景合理。需要配合 CHANGELOG 和迁移指南提供给现有用户。

---

### 5.4 Fix D: 工具依赖自动安装审查

**文件**: `yuleosh_cli.py` — `cmd_init()` 函数

#### 当前实现

```python
def cmd_init(dir_path: str = "."):
    target = Path(dir_path)
    dirs = [target / "specs", target / "tasks", target / "src",
            target / "docs", target / "evidence", target / ".osh"]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print(f"✅ Initialized yuleOSH project at {target}")
```

当前 `cmd_init()` **仅创建目录结构，没有任何工具安装逻辑**。

#### 需要的改进

| # | 建议 | 优先级 | 说明 |
|:-:|:-----|:-------|:-----|
| I-01 | **添加工具依赖检测** | P0 | 检查 cppcheck、clang-tidy、pytest、coverage 是否已安装 |
| I-02 | **跨平台安装命令** | P0 | macOS: `brew install cppcheck`；Linux: `apt install cppcheck clang-tidy`；提供友好提示而非自动安装 |
| I-03 | **安装失败不应阻断** | P0 | 检测结果应以 warning 形式输出，项目初始化应始终成功 |
| I-04 | **输出信息友好** | P1 | 显示检查结果表格，缺失的工具给出安装命令，已安装的工具显示版本号 |

#### 示例实现（建议）

```python
def cmd_init(dir_path: str = "."):
    """Initialize a new yuleOSH project directory."""
    target = Path(dir_path)
    dirs = [target / "specs", ...]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print(f"✅ Initialized yuleOSH project at {target}")

    # Tool dependency check
    tools = ["cppcheck", "clang-tidy", "pytest", "git"]
    print("\n  🔧 Tool dependency check:")
    all_ok = True
    for tool in tools:
        if _check_tool_installed(tool):
            print(f"    ✅ {tool} — installed")
        else:
            print(f"    ⚠️  {tool} — NOT installed")
            print(f"       → Install: {_install_hint(tool)}")
            all_ok = False
    if not all_ok:
        print("\n  ⚠️  Some tools are missing. CI stages requiring them will be skipped.")
```

**审查结论**: 工具自动安装尚未实现。建议在 `cmd_init()` 尾部添加友好的依赖检测（P0），安装逻辑以提示为主而非自动执行（避免强制安装失败阻断流程）。

---

### 5.5 总评：4 项 Fix 审查汇总

| Fix | 状态 | 关键发现 | 建议处理 |
|:----|:-----|:---------|:---------|
| **A: Delta Check** | ⚠️ 已实现但需修复 | D-01 ~ D-04 需要处理 | 路径一致性、报告标记、KLOC 在 delta 模式下禁用 |
| **B: Dir 系列规则** | ⚠️ 需修正 | Dir 4.2 与 Rule 1.2 重复；Dir 4.7 与 Rule 21.8 重复；部分描述偏目标 | 修正 Dir 4.2 内容为动态内存约束；优化描述聚焦违反场景 |
| **C: 默认值优化** | ✅ 方向正确 | `fail_on_violation=True` + `violations_per_kloc=2.0` 合理 | 添加 CHANGELOG；在模板 ci-config.yaml 中显式配置 MISRA |
| **D: 工具自动安装** | ❌ 尚未实现 | `cmd_init()` 仅创建目录 | 实现依赖检测 + 跨平台安装提示；检查失败不阻断初始化 |

#### 需要小克 👨‍💻 确认的 5 个问题

1. **Dir 4.2 修正**: 当前内容与 Rule 1.2 重复，是否需要改为聚焦动态内存使用约束（MISRA C:2023 Dir 4.2 实际内容）？
2. **Delta KLOC**: `violations_per_kloc` 在增量模式下是否应该禁用？
3. **迁移计划**: `fail_on_violation=True` 的 breaking change 是否需要版本号 bump？
4. **首次 commit 场景**: 你测试过 `git diff HEAD~1` 在全新仓库的行为吗？
5. **工具安装策略**: 是自动安装（`brew install` / `apt install`）还是仅提示？

---

## 6. Loop 2 — 追溯链 + 验证计划审查

> **审查范围**: 追溯链实现（spec_ref → 规则 → 检查 → 违规 → 修复）
> **代码基线**: commit `b7fec371` (2026-06-18 16:41)
> **审查人**: 小马 🐴

---

### 6.1 追溯链总体现状

| 追溯环节 | 预期 | 现状 | 缺口 |
|:---------|:-----|:-----|:-----|
| Spec SHALL → 规则 | 每条规则有 `spec_ref` 指向 SWE-MISRA-* ID | ❌ 未实现 — misra-rules.yaml 无 spec_ref 字段 | **Critical** |
| 规则 → 检查工具 | 检查工具字段确定检查方式 | ⚠️ 部分实现 — `check:` 字段缺失；仅有 severity/category | **Major** |
| 检查 → 违规报告 | misra_report.py 生成 JSON 报告含规则 ID | ✅ 已实现 — report JSON 含 rule_id, file, line, severity | — |
| 违规 → 修复任务 | 自动生成修复任务（Issue/Ticket） | ❌ 未实现 — 无 auto-fix task 生成逻辑 | **Major** |
| CI 报告含追溯信息 | 报告输出含 spec_ref 链接 | ❌ 未实现 — 报告不含 spec_ref 或上游需求 ID | **Major** |

**总体结论**: 追溯链当前只有「检查→违规」两环有基础实现，缺失前端（Spec→规则）和后端（违规→修复），也未在输出中建立追溯关系。

---

### 6.2 详细审查

#### 6.2.1 misra-rules.yaml 缺 spec_ref

**文件**: `misra-rules.yaml`

问题：142 条规则中**无一存在 `spec_ref` 字段**。

当前每条规则的 schema：
```yaml
misra-c2023-10.1:
  title: "Operands shall not be of inappropriate type"
  severity: "required"
  category: "基本类型 (Essential Types)"
  description: "操作数不得具有不适当的本质类型"
```

预期 schema 应补充：
```yaml
misra-c2023-10.1:
  title: "Operands shall not be of inappropriate type"
  severity: "required"
  category: "基本类型 (Essential Types)"
  description: "操作数不得具有不适当的本质类型"
  spec_ref: "SWE-MISRA-CFG1"   # ← 新增
  check: "cppcheck"            # ← 新增
  rationale: "..."              # ← 新增（引用现有但补齐）
```

**影响分析**:

| 影响 | 说明 |
|:-----|:-----|
| ASPICE SWE.4 BP2 | 追溯链断裂：审计时无法证明哪些规则覆盖哪些 spec 需求 |
| 变更影响分析 | 无法回答「如果修改 spec 需求 X，受影响的是哪条规则？」 |
| 合规证据 | 无法自动生成 Spec→Rule 的追溯矩阵报告 |

**修复要求**:
- P0: 每条 Required 规则加 `spec_ref` 指向 `specs/misra-c2023-spec.md` 中的 SHALL ID
- P0: 每条规则加 `check` 字段（`cppcheck` / `clang-tidy` / `manual` / `ai`）
- P1: 每条规则加 `rationale` 字段（部分已有，需补齐）

**Spec→Rule 映射建议**:

| Spec ID | 关联规则范围 | 说明 |
|:--------|:-------------|:-----|
| SWE-MISRA-S1 | 全部规则 | CI 阶段执行所有规则的检查 |
| SWE-MISRA-S2 | 全部规则 | 所有规则的违规结果需纳入 JSON 报告 |
| SWE-MISRA-CFG1 | 全部规则 | misra-rules.yaml 定义所有启用的规则 |
| SWE-MISRA-CFG2 | TOP 20 规则 | 指定规则默认启用且不可禁用 |

**TOP 20 需加 spec_ref**: `spec_ref: "SWE-MISRA-CFG2"`

---

#### 6.2.2 misra_report.py 未生成追溯矩阵 JSON

**文件**: `src/yuleosh/ci/misra_report.py`

当前 `generate_json_report()` 的输出 schema：
```json
{
  "generated_at": "...",
  "tool": "cppcheck --addon=misra",
  "standard": "MISRA C:2023",
  "summary": {...},
  "violations_raw": [...],
  "groups": {...}
}
```

**缺失字段**:

❌ 无 `traceability` 节 — 未将违规通过 rule_id 关联到 spec_ref
❌ 无 `spec_ref` 回链 — 每个违规无法追溯到 Spec 需求
❌ 无法回答「当前 CI 运行中，spec SWE-MISRA-CFG1 覆盖的规则有哪些违规？」

**修复建议**:

在报告中新增 traceability 节:

```python
def generate_traceability_section(violations, rule_defs):
    """Generate traceability linking violations → rules → spec_refs."""
    spec_coverage = defaultdict(lambda: {"total": 0, "violated": 0, "violations": []})
    for v in violations:
        rid = v.get("rule_id")
        defn = rule_defs.get(rid, {})
        spec_ref = defn.get("spec_ref", "unknown")
        # ...
```

并在 JSON 和 Markdown 报告中输出：
```json
{
  "traceability": {
    "specs": {
      "SWE-MISRA-S1": {
        "total_rules": 142,
        "violated_rules": 3,
        "violations_count": 12
      },
      "SWE-MISRA-CFG2": {
        "total_rules": 20,
        "violated_rules": 1,
        "violations_count": 5
      }
    }
  }
}
```

---

#### 6.2.3 缺陷自动生成修复任务 — 未实现

**现状**: 无任何「违规→修复任务」的自动生成逻辑。

**预期能力**:

| 触发条件 | 生成目标 | 包含内容 |
|:---------|:---------|:---------|
| MISRA 违规出现在 Required 规则 | GitHub Issue / 本地 task 文件 | 规则 ID、违规文件/行号、建议修复方式 |
| 违规计数超过 `max_warnings` | CI Warning 报告 | 超额警告、Top-10 违规规则 |
| 新出现的历史未见的违规 | PR 评论注释 | 标记新增违规，与基线 diff |

**修复建议（最小实现）**:

1. 在 `misra_report.py` 中添加 `generate_fix_tasks()` 函数
2. 输出 `.yuleosh/tasks/misra-fix-{timestamp}.json`
3. 按严重度排序，Required + error 级别的违规生成修复建议
4. 建议格式：

```json
{
  "fix_tasks": [
    {
      "rule_id": "misra-c2023-10.1",
      "severity": "required",
      "spec_ref": "SWE-MISRA-CFG1",
      "file": "src/drivers/uart.c:47",
      "suggested_fix": "Use essentially unsigned type for '+' operand",
      "priority": "high"
    }
  ]
}
```

---

#### 6.2.4 CI 报告未包含追溯信息

**文件**: `src/yuleosh/ci/stages.py` — `run_misra_check()`

当前 `save_report()` 调用仅传入 violations 和 rule_defs，未传入任何 spec 映射信息。

**缺失**:
- ❌ 报告元数据中无 spec_ref 汇总
- ❌ 报告的 `generated_at` 无 commit 哈希关联
- ❌ 无需求覆盖率统计（多少 SHALL 被覆盖/未覆盖）

**修复建议**:

在 `save_report()` 调用前加载 spec→rule 映射，传入报告生成器：

```python
spec_to_rules = load_spec_to_rule_mapping(rule_defs)
json_report = generate_json_report(violations, groups, summary, spec_to_rules)
```

JSON 报告新增 `meta.commit` 字段（从环境变量获取 `GIT_COMMIT` 或执行 `git rev-parse HEAD`）。

---

### 6.3 Dir 4.2 去重复审查

#### 原始问题（来自 Loop 1 审查）

| 规则 ID | 当前描述 | 问题 |
|:--------|:---------|:-----|
| misra-c2023-dir-4.2 | "避免未定义行为" / "不得依赖任何未定义或未指定行为" | 🚨 **与 misra-c2023-1.2 完全重复** |
| misra-c2023-1.2 | "不得依赖未定义或未指定的行为" | 同上 |

#### 复审结果

**提交 `b7fec371` 中 Dir 4.2 内容未变动。**

Git diff 确认最新提交中 Dir 4.2 的内容仍是 `misra-c2023-dir-4.2` + `title: "避免未定义行为"` + `description: "不得依赖任何未定义或未指定行为"`，与 Rule 1.2 描述完全重复。

| 检查项 | 结果 |
|:-------|:-----|
| Dir 4.2 内容已被修正？ | ❌ **否** — 仍与 Rule 1.2 重复 |
| Rule 1.2 描述被调整？ | ❌ 否 — Rule 1.2 保持原样 |
| 小克收到修正通知？ | ⚠️ 已确认（上一轮报告中已提出） |

**正确内容建议**:

MISRA C:2023 Dir 4.2 实际聚焦**动态内存使用的规则约束**（malloc/free 使用限制、内存泄漏预防等），而非重复 Rule 1.2 的未定义行为问题。建议修正为：

```yaml
misra-c2023-dir-4.2:
  title: "动态内存约束"
  severity: "required"
  category: "资源 (Resources)"
  description: "动态内存分配 (malloc/calloc/realloc/free) 应在受限且可预测的上下文中使用，不得在中断服务程序或时间关键路径中分配/释放"
```

> 注意：现有 `misra-c2023-21.3`（"不应使用内存分配函数"）和 `misra-c2023-22.1`（"不应使用动态堆内存"）也覆盖动态内存主题，但 Dir 4.2 的定位是**使用约束而非禁用**——它允许受限使用，重点在约束条件和上下文。

---

### 6.4 验收矩阵更新建议

**文件**: `specs/misra-acceptance-matrix.md`

当前矩阵涵盖 6 个验收域（CI 集成 / 规则配置 / 违规处理 / 配置集成 / 测试 / 全局），但**缺少追溯链相关验收项**。

#### 新增：追溯链验收 (Section 7)

建议在验收矩阵末尾追加 Section 7：

| 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 |
|:-------|:---------|:---------|:---------|:---------|
| 追溯矩阵 JSON 输出 | SWE-MISRA-TR1 | 运行 `misra_report.py` 检查 JSON 输出 | pytest | JSON 含 `traceability` 节，覆盖全部 Spec ID 的规则覆盖率和违规计数 |
| spec_ref 完整性 | SWE-MISRA-TR2 | 解析 misra-rules.yaml 逐条检查 | `pytest` YAML schema 校验 | 每条规则有非空 `spec_ref` 字段，值对应 `specs/misra-c2023-spec.md` 中的 SHALL ID |
| check 字段完整性 | SWE-MISRA-TR2 | 解析 misra-rules.yaml | pytest | 每条规则有非空 `check` 字段，值 ∈ {cppcheck, clang-tidy, manual, ai} |
| 修复任务自动生成 | SWE-MISRA-TR3 | 运行 CI 产生违规后检查 `.yuleosh/tasks/` | pytest | Required 违规自动生成修复任务 JSON，含规则 ID、文件路径、行号、建议修复 |
| 修复任务优先级排序 | SWE-MISRA-TR3 | 检查生成的修复任务 JSON | pytest | 任务按 severity 排序，Required+error 标记为 high priority |
| CI 报告含追溯信息 | SWE-MISRA-TR4 | 运行 CI 后检查 JSON 报告 | CI 日志 | JSON 报告包含 `traceability.specs` 节，列出各 Spec ID 的规则覆盖状态 |
| CI 报告含 commit 哈希 | SWE-MISRA-TR4 | 运行 CI 后检查 JSON | pytest | JSON 报告 meta 中包含 commit hash，可回溯到代码版本 |
| Spec→规则→检查→违规→修复 完整追溯 | SWE-MISRA-TR5 | 端到端验证：模拟违规触发完整链路 | 集成测试 | 从 Spec SHALL ID 出发，能找到对应规则、检查结果、违规报告和修复任务 |

#### 验收级别

| 验收项 | 级别 | 说明 |
|:-------|:----:|:-----|
| SWE-MISRA-TR1 | Required | 追溯矩阵输出是 ASPICE SWE.4 的基本要求 |
| SWE-MISRA-TR2 | Required | spec_ref 和 check 字段完整性确保每条规则可追溯 |
| SWE-MISRA-TR3 | Advisory | 修复任务自动生成是效率提升，不阻碍流水线 |
| SWE-MISRA-TR4 | Required | CI 报告含追溯信息是审计的基本要求 |
| SWE-MISRA-TR5 | Advisory | 端到端追溯是成熟度目标，初期可接受手工验证 |

---

### 6.5 总结：Loop 2 审查结论

#### 追溯链完成度：15% ❌ 未达标

| 环节 | 完成度 | 下一步 |
|:-----|:------:|:-------|
| Spec→规则映射 (spec_ref) | 0% | P0：misra-rules.yaml 全部规则加 spec_ref 和 check 字段 |
| 规则→检查→违规 | 60% | 检查工具链已就绪，违规报告已 JSON 化 |
| 违规→修复任务 | 0% | P1：misra_report.py 新增 fix_tasks 生成 |
| CI 追溯输出 | 0% | P0：JSON 报告新增 traceability.specs 和 commit hash |
| Dir 4.2 去重 | 0% | P0：修正 Dir 4.2 描述，避免与 Rule 1.2 重复 |

#### 需要小克 👨‍💻 响应的 5 个问题

1. **spec_ref schema**: 每条规则加 `spec_ref` 字段，值用什么格式？建议 `spec_ref: "SWE-MISRA-CFG1"` 引用 spec 中的 SHALL ID
2. **check 字段**: 是否所有规则加 `check` 字段，还是只加非 cppcheck 默认的？建议全员加，default=`cppcheck`
3. **Dir 4.2 修正**: 上次 Loop 1 已提重复问题，这次确认仍未修复。请将 Dir 4.2 改为聚焦动态内存使用约束
4. **修复任务输出格式**: 建议用 YAML/JSON 两种格式，方便不同消费方（人类读 YAML，工具读 JSON）
5. **验收矩阵更新**: 我已在 Section 6.4 给出建议，收到你确认后正式更新 `specs/misra-acceptance-matrix.md`

#### Blocking 状态

| 项目 | 是否 Blocked | 原因 |
|:-----|:------------|:-----|
| 追溯链 | 🔴 **Blocked** | misra-rules.yaml 无 spec_ref → 无法链接 Spec→规则→违规→修复 完整链 |
| Dir 4.2 去重 | 🔴 **Blocked** | 虽已提出，但 commit 中未修复，内容仍重复 |
| 验收矩阵更新 | 🟡 **Not blocked** | 建议已给出，待小克确认后正式更新 |
| CI 追溯输出 | 🔴 **Blocked** | 依赖 spec_ref 就位后才能实现 |

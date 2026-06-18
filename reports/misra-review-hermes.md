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

---

## 7. Loop 3 — MISRA KPI/趋势 + 偏差 CLI + 验证计划审查

> **审查范围**: 小克新创建的 3 项 MISRA 产出
> **审查人**: 小马 🐴
> **日期**: 2026-06-18 (第3轮)
>
> - MISRA KPI/趋势跟踪 (`src/yuleosh/ci/misra_trend.py`)
> - 偏差 CLI 命令 (`yuleosh misra deviate`)
> - MISRA 验证计划文档 (`docs/misra-verification-plan.md`)

---

### 7.1 MISRA KPI/趋势跟踪审查 (`misra_trend.py`)

#### 文件状态

| 项目 | 状态 |
|:-----|:----:|
| 文件存在 | ✅ 已创建 (untracked) |
| 位置 | `src/yuleosh/ci/misra_trend.py` |
| 集成到 `stages.py` | ❌ 未集成 — 未在 `run_misra_check()` 中调用 `append_entry()` |
| 单元测试 | ❌ 暂无 |

#### 代码设计审查

| 维度 | 评价 | 问题/建议 |
|:-----|:-----|:---------|
| **输出格式** | ✅ JSONL — 追加写，适合趋势累积，空间效率高 | — |
| **时间戳** | ✅ ISO 8601 `datetime.now().isoformat()` | — |
| **可读性** | ✅ `show_trend()` 输出 Markdown 表格，可直接嵌入报告 | — |
| **批量查询** | ✅ 支持 N 条最近记录显示 | — |
| **密度计算** | ✅ `get_violations_per_kloc()` — 与 config 中的阈值联动 | — |
| **CI 摘要** | ✅ `_print_trend_summary()` 提供简明趋势摘要 | — |

#### 关键发现

| # | 发现 | 严重度 | 位置 | 建议 |
|:-:|:-----|:------:|:-----|:-----|
| T-01 | `append_entry()` 未被 `stages.py` 中的 `run_misra_check()` 调用 | **P0** | `misra_trend.py:62` / `stages.py` | 在 `run_misra_check()` 保存报告后追加 trend entry |
| T-02 | 缺少 `delta_kloc` 字段 — 增量模式下 KLOC 应为 delta 值而非全量 | **P1** | `misra_trend.py:60` | 新增字段 `delta_kloc` 和 `delta_files`，在 delta 模式下使用 |
| T-03 | 缺少违规密度阈值触发标志 | **P2** | 整体设计 | 增加 `breached_threshold: bool` 字段，当 density > `violations_per_kloc` 时标记 |
| T-04 | `show_trend()` 未格式化 KLOC 列 | **P2** | `misra_trend.py:77-140` | 建议增加 KLOC 密度列为可选项 |
| T-05 | `_print_trend_summary()` 方向指示逻辑复杂 | **P2** | `misra_trend.py:175-177` | 单行三元嵌套 `if-else` 可读性差，建议提取为小函数 |
| T-06 | 无单元测试 | **P1** | `tests/` | 需要至少覆盖：`append_entry` → `show_trend` → 积分验证 |

#### 建议集成到 stages.py 的代码

```python
# 在 run_misra_check() 尾部，save_report() 之后追加
from yuleosh.ci.misra_trend import append_entry

append_entry(
    project_dir=project_dir,
    total_violations=summary.get("total", 0),
    required=summary.get("required", 0),
    advisory=summary.get("advisory", 0),
    files_checked=len(c_files),
    is_delta=(check_mode == "delta"),
    commit=get_git_short_hash(project_dir),
)
```

---

### 7.2 偏差 CLI 命令审查 (`yuleosh misra deviate`)

#### 文件状态

| 项目 | 状态 |
|:-----|:----:|
| CLI 命令 `yuleosh misra deviate` | ❌ **尚未创建** — 无对应命令实现 |
| 偏差 dataclass | ✅ 存在 (`src/yuleosh/ci/config.py:MisraDeviation`) |
| 偏差配置文件解析 | ✅ 存在 (`config.py:_parse_ci_config()` → deviations 解析) |
| 偏差在 CI 中的应用 | ✅ 存在 (`stages.py:run_misra_check()` → 偏差过滤) |
| 偏差在报告中的标记 | ✅ 存在 (`misra_report.py:_match_deviation()` → 标记 acknowledged) |
| `docs/misra-deviations.md` | ❌ **尚未创建** — 被 spec SWE-MISRA-DEV1 引用 |

**结论**: 偏差的**运行时支持**（dataclass → 配置解析 → CI 实现 → 报告标记）已就绪，但**用户界面层**（CLI 命令）和**文档**缺失。

---

#### 命令设计建议

##### 推荐命令结构

```
yuleosh misra deviate --help

Usage:
  yuleosh misra deviate list                          — 列出所有偏差
  yuleosh misra deviate add <rule-id> <file-pattern>   — 添加新偏差
    [--reason "..."]
    [--approved-by <name>]
    [--expires YYYY-MM-DD]
  yuleosh misra deviate approve <rule-id> <file>       — 批准待审批偏差
  yuleosh misra deviate reject <rule-id> <file>        — 拒绝偏差
  yuleosh misra deviate export                         — 导出偏差为 YAML/JSON
```

##### 子命令详情

| 子命令 | 参数 | 动作 | 权限要求 |
|:-------|:-----|:-----|:---------|
| `list` | `[--status pending|approved|rejected]` | 列出当前偏差清单 | 无（只读） |
| `add` | `<rule-id>` `<file-pattern>` `[--reason]` | 在 ci-config.yaml 中添加偏差记录 | 写权限（project owner） |
| `approve` | `<rule-id>` `<file>` | 将偏差状态从 pending → approved | **需 QA lead 或架构师** |
| `reject` | `<rule-id>` `<file>` | 将偏差状态从 pending → rejected | **需 QA lead 或架构师** |
| `export` | `--format yaml|json` | 导出偏差报告，支持合规审计 | 无 |

##### 偏差记录数据模型（已有）

```python
@dataclass
class MisraDeviation:
    rule_id: str = ""           # 例如 "misra-c2023-10.1"
    file_pattern: str = ""      # 例如 "src/legacy/*.c"
    reason: str = ""            # 偏差理由
    approved_by: str = ""       # 审批人
    expires: str = ""           # 过期日，如 "2026-09-30"
    status: str = "pending"     # pending | approved | rejected
```

#### 权限控制设计

**谁可以做什么？**

| 操作 | 允许角色 | 建议实现方式 |
|:-----|:---------|:------------|
| `list` | 所有人 | 读 ci-config.yaml 的 deviations 段 |
| `add` | Project Owner, Developer | 修改 ci-config.yaml 追加 dev 条目（status=pending） |
| `approve` | **QA Lead, 架构师, 质量负责人** | 修改 ci-config.yaml 中 status=approved |
| `reject` | QA Lead, 架构师 | 修改 ci-config.yaml 中 status=rejected |
| `export` | 所有人（审计用） | 读取 deviations 输出 YAML/JSON |

**关键控制点**:

1. 🔴 `approve` 和 `reject` 不能无限制开放 — 至少需要文件写权限 + 角色检测
2. ⚠️ 偏差有 **过期时间**（`expires` 字段），过期后自动失效（CI 中不再标记为 acknowledged）
3. 🟡 建议在 `deviate approve` 执行时记录审批者的 git commit author，以提供审计轨迹
4. 🔴 `deviate add` 直接写入 `ci-config.yaml` — 需要确保 YAML 格式不被破坏

#### 文件输出位置

- 偏差配置 SHALL 存储在 `.yuleosh/ci-config.yaml` 的 `misra.deviations` 段（已有）
- `docs/misra-deviations.md` 文档 SHOULD 同步生成（CLI `export` 命令输出 Markdown 版本）

#### 检查结果

| 检查项 | 结论 | 说明 |
|:-------|:----:|:-----|
| 命令设计直观？ | **NA** | 命令尚未实现。建议见上 |
| 权限控制合理？ | **NA** | 同上。核心建议：approve/reject 需要 QA lead 权限 |
| 偏差过期机制？ | ✅ | `expires` 字段已有，CI 运行中需要实现过期检查 |
| 偏差审计轨迹？ | ⚠️ 部分 | YAML 配置本身可 git 跟踪；但 CI 报告中无偏差使用记录 |
| docs/misra-deviations.md 存在？ | ❌ | 尚未创建，被 spec 引用但无文件 |

---

### 7.3 MISRA 验证计划审查 (`docs/misra-verification-plan.md`)

#### 文件状态

| 项目 | 状态 |
|:-----|:----:|
| `docs/misra-verification-plan.md` | ❌ **尚未创建** |
| Spec 中引用位置 | `specs/misra-c2023-spec.md` §5 (ASPICE SWE.4/SWE.5 映射) |

**结论**: 验证计划文档需要创建。以下是我建议的内容框架和审查基准。

---

#### 建议内容框架

```markdown
# MISRA C:2023 验证计划

> 版本: 1.0.0-draft
> 关联 Spec: specs/misra-c2023-spec.md
> 关联验收矩阵: specs/misra-acceptance-matrix.md

## 1. 范围
- 覆盖 yuleOSH 的 MISRA C:2023 静态检查集成
- 不包括 MISRA 规则的手动审核（由人工审查流程覆盖）

## 2. 角色与职责

| 角色 | 职责 | 负责人 |
|:-----|:-----|:-------|
| 质量架构师 | 定义规则集、验收标准、审查报告 | 小马 🐴 |
| 开发者 | 实施规则检查、修复违规、申请偏差 | 小克 👨‍💻 |
| 项目负责人 | 批准偏差、裁定争议 | 小明 🧑‍💼 |
| CI/CD 维护者 | 维护检查工具链、更新 YAML 配置 | 小克 👨‍💻 |
| 审计员 | 验证验证计划执行、检查追溯链完整性 | 小马 🐴 / 外部审计 |

## 3. 验证活动

| 验证活动 | 执行者 | 频率 | 输入 | 输出 |
|:---------|:-------|:----|:-----|:-----|
| MISRA 静态分析 (Layer 2) | CI (自动) | 每次提交 | misra-rules.yaml, cppcheck | misra-report.json |
| 趋势 KPI 跟踪 | CI (自动) | 每次提交 | misra-report.json | misra-trend.jsonl |
| 偏差审批 | 质量架构师 | PR 时 | docs/misra-deviations.md | 批准/拒绝签名 |
| MISRA 合规审查 | 质量架构师 | 每次 Sprint 结束 | misra-trend JSONL | 审查报告 |
| 追溯矩阵一致性 | 质量架构师 | 每次 Sprint 结束 | misra-report + spec | 追溯矩阵报告 |
| 外部审计 | 第三方 | 按项目里程碑 | 所有 MISRA 证据 | 审计报告 |

## 4. 门禁 (Gates)

| 门禁 | 通过条件 | 阻断行为 |
|:-----|:---------|:---------|
| G1 — CI 静态分析 | Required 违规 ≤ max_warnings (默认 100) | Pipeline 标记 warning / failed |
| G2 — Required 偏差 | 所有 Required 违规需有对应偏差记录或已修复 | Code Review 不通过直到解决 |
| G3 — 趋势恶化 | 最近 5 次 Required 均值环比 ≤ +20% | Sprint 审查中讨论，不自动阻断 |
| G4 — 追溯链 | misra-report.json 含完整 traceability 节 | SWE.4/SWE.5 合规证据不完整 |
| G5 — 偏差过期 | 偏差 expires 日期在有效期内 | CI 报告标记过期偏差 |

## 5. ASPICE SWE.4/SWE.5 映射

| ASPICE BP | 验证活动 | 覆盖状态 |
|:----------|:---------|:---------|
| SWE.4.BP1: 开发软件单元验证规范 | MISRA 规则集定义 (misra-rules.yaml) | ✅ 已覆盖 |
| SWE.4.BP2: 记录验证结果 | misra-report.json, misra-trend.jsonl | ⚠️ 趋势已实现，验证记录需完善 |
| SWE.5.BP2: 验证集成策略 | CI Layer 2 MISRA 检查执行 | ✅ 已覆盖 |
| SWE.5.BP3: 记录集成测试结果 | 追溯矩阵 JSON (traceability 节) | ⚠️ traceability 节已实现但未含 spec_ref |
| SWE.6.BP2: 发布前验证 | MISRA_FAIL_FAST 阻断逻辑 | ✅ 已覆盖 |
| SWE.6.BP3: 记录验证证据 | .osh/evidence/ 自动归档 | ⚠️ 已部分实现 (fix_tasks) |

## 6. 风险与缓解措施

| 风险 | 概率 | 影响 | 缓解措施 |
|:-----|:----:|:----:|:---------|
| cppcheck 不支持全部 C:2023 规则 | 高 | 中 | 标记规则 check_method=manual，配合人工审查 |
| 偏差泛滥（过多批准） | 中 | 高 | expires 机制 + 偏差数量上限（默认 ≤20 条活跃偏差） |
| 趋势数据丢失 | 低 | 中 | misra-trend.jsonl 纳入证据打包 |
| 门禁被绕过 | 低 | 高 | CI 强制执行 MISRA 检查 stage，无法跳过 |

## 7. 验收准则（引用验收矩阵）

见 specs/misra-acceptance-matrix.md §7 (MISRA KPI/趋势), §8 (偏差 CLI), §9 (验证计划文档验收)。
```

---

#### 审查对照表

| 检查维度 | 结论 | 说明 |
|:---------|:----:|:-----|
| **角色定义清晰？** | ⚠️ 预审 OK | 文档尚未创建。建议框架中角色划分明确（质量架构师=小马、开发者=小克、项目负责人=小明） |
| **频率/门禁合理？** | ⚠️ 预审 OK | 建议 G1~G5 门禁逐级递进：自动→审查→Sprint→审计。趋势恶化不自动阻断但需讨论 |
| **ASPICE SWE.4 对齐？** | ⚠️ 预审 OK | SWE.4.BP1/BP2 通过 misra-rules.yaml 和 JSON 报告覆盖；SWE.5.BP3 需 traceability 节补完 |
| **ASPICE SWE.5 对齐？** | ⚠️ 预审 OK | SWE.5.BP2/BP3 通过 CI MISRA 检查覆盖；SWE.5.BP3 因缺少 spec_ref 还不完整 |
| **门禁阈值明确？** | ⚠️ 需确认 | `max_warnings=100` 和 `violations_per_kloc=2.0` 已在 config.py 定义，需与验证计划一致 |
| **偏差审批流程？** | ❌ 缺失 | 验证计划未收尾：偏差如何提交、审批路径、过期后如何处理 |
| **文档状态** | ❌ 尚未创建 | P0 待小克创建，参考以上框架 |

---

### 7.4 验收矩阵追加项

**文件**: `specs/misra-acceptance-matrix.md`

**操作**: 追加以下 3 个新章节（§7 MISRA KPI/趋势, §8 偏差 CLI, §9 验证计划文档验收）

---

#### §7 新增：MISRA KPI/趋势 验收

| 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 |
|:-------|:---------|:---------|:---------|:---------|
| misra_trend.py 文件存在 | SWE-MISRA-KPI1 | 检查文件是否存在 | `ls` | `src/yuleosh/ci/misra_trend.py` 存在 |
| 趋势文件 JSONL 格式 | SWE-MISRA-KPI1 | 解析 `.yuleosh/reports/misra-trend.jsonl` | pytest | 每行是有效 JSON，含 timestamp, total_violations, required, advisory |
| 趋势集成到 CI | SWE-MISRA-KPI2 | 运行 CI 后检查 trend 文件 | CI 日志 | `run_misra_check()` 输出中包含 `append_entry()` 调用痕迹 |
| 趋势 Markdown 表格 | SWE-MISRA-KPI2 | 调用 show_trend() | pytest | 返回格式正确的 Markdown 表格，每行含 #/时间戳/总违规/Required/Advisory/文件数/增量/Commit |
| 密度计算正确 | SWE-MISRA-KPI3 | 输入已知 violation 和 KLOC | pytest | `get_violations_per_kloc(10, 5.0)` = 2.0; `(0, 5.0)` = 0.0; `(10, 0)` = 0.0 |

#### §8 新增：偏差 CLI 验收

| 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 |
|:-------|:---------|:---------|:---------|:---------|
| `yuleosh misra deviate list` 命令 | SWE-MISRA-DEVCLI1 | 运行命令 | CLI 测试 | 输出偏差清单表格，含 rule_id, file_pattern, reason, approved_by, expires, status |
| `yuleosh misra deviate add` 命令 | SWE-MISRA-DEVCLI2 | 运行 `add` 后检查 ci-config.yaml | pytest | ci-config.yaml 的 `misra.deviations` 新增对应条目，status= |
| `yuleosh misra deviate approve` 命令 | SWE-MISRA-DEVCLI3 | 运行 `approve` 后检查 ci-config.yaml | pytest | 对应偏差条目 status → approved, approved_by 更新 |
| `yuleosh misra deviate reject` 命令 | SWE-MISRA-DEVCLI3 | 运行 `reject` 后检查 ci-config.yaml | pytest | 对应偏差条目 status → rejected |
| `yuleosh misra deviate export` 命令 | SWE-MISRA-DEVCLI4 | 运行 export | CLI 测试 | 输出 YAML/JSON 格式，内容与 ci-config.yaml 一致 |
| 偏差 CI 过滤 | SWE-MISRA-DEVCLI5 | 配置偏差后运行 CI | CI 日志 | 匹配偏差的违规在报告中标记为 "acknowledged" 而非新增违规 |
| docs/misra-deviations.md 存在 | SWE-MISRA-DEVCLI6 | 检查文件 | `ls` | 文件存在，至少包含表头和示例条目 |

#### §9 新增：验证计划文档验收

| 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 |
|:-------|:---------|:---------|:---------|:---------|
| 文档存在 | SWE-MISRA-VP1 | 检查文件 | `ls` | `docs/misra-verification-plan.md` 存在 |
| 角色定义 | SWE-MISRA-VP1 | 审查文档 | 人工审查 | 至少定义 3 个角色（质量架构师、开发者、项目负责人），职责描述清晰 |
| 验证活动 | SWE-MISRA-VP1 | 审查文档 | 人工审查 | 至少列出 4 项验证活动，每项定义了执行者、频率、输入、输出 |
| 门禁定义 | SWE-MISRA-VP2 | 审查文档 | 人工审查 | 至少定义 3 个门禁，每个门禁有通过条件和阻断行为 |
| ASPICE SWE.4 映射 | SWE-MISRA-VP3 | 审查文档 | 人工审查 | 至少有 SWE.4 BP1/BP2 的映射说明 |
| ASPICE SWE.5 映射 | SWE-MISRA-VP3 | 审查文档 | 人工审查 | 至少有 SWE.5 BP2/BP3 的映射说明 |
| SWE.6 映射 | SWE-MISRA-VP3 | 审查文档 | 人工审查 | 至少有 SWE.6 BP2/BP3 的映射说明 |
| 风险与缓解 | SWE-MISRA-VP4 | 审查文档 | 人工审查 | 至少列出 3 个风险项，每个含概率/影响/缓解措施 |

#### 验收层次矩阵

| 新验收项 | SHALL ID | 级别 | 解释 |
|:---------|:---------|:----:|:-----|
| KPI 文件存在 | SWE-MISRA-KPI1 | Required | 趋势跟踪是检测质量变化的基础 |
| 趋势 CI 集成 | SWE-MISRA-KPI2 | Required | 自动记录趋势是 CI 的必要功能 |
| 密度计算 | SWE-MISRA-KPI3 | Advisory | KPI 计算正确性，不影响流水线阻断 |
| 偏差 CLI list | SWE-MISRA-DEVCLI1 | Required | 查看偏差是日常开发刚需 |
| 偏差 CLI add | SWE-MISRA-DEVCLI2 | Required | 添加偏差是流程入口 |
| 偏差 CLI approve/reject | SWE-MISRA-DEVCLI3 | Required | 审批控制是合规核心 |
| 偏差 CLI export | SWE-MISRA-DEVCLI4 | Advisory | 导出用于审计，可接受手工替代 |
| 偏差 CI 过滤 | SWE-MISRA-DEVCLI5 | Required | 偏差必须实际生效 |
| 偏差文档 | SWE-MISRA-DEVCLI6 | Required | 被 spec 直接引用（SWE-MISRA-DEV1） |
| 验证计划文档 | SWE-MISRA-VP1 | Required | 验证计划是 ASPICE SWE 过程的基础文档 |
| 门禁定义 | SWE-MISRA-VP2 | Required | 门禁是质量控制的核心机制 |
| ASPICE 映射 | SWE-MISRA-VP3 | Required | 映射说明是 ASPICE 合规的证据 |
| 风险管理 | SWE-MISRA-VP4 | Advisory | 风险管理是成熟度要求 |

---

### 7.5 全局状态汇总

| 交付项 | 状态 | 优先级 | 说明 |
|:-------|:----:|:------:|:-----|
| `misra_trend.py` | ✅ 已创建 + 需集成 | P1 | 代码质量好，需集成到 stages.py + 加测试 |
| 偏差 CLI (`yuleosh misra deviate`) | ❌ 未创建 | P1 | 运行时层就绪，缺用户界面 |
| `docs/misra-deviations.md` | ❌ 未创建 | P0 | 被 spec SWE-MISRA-DEV1 引用但不存在 |
| `docs/misra-verification-plan.md` | ❌ 未创建 | P1 | 本文提供建议框架 |
| 验收矩阵更新 | 📋 已撰写 | P1 | 3 个新章节待小克确认后正式追加到 `specs/misra-acceptance-matrix.md` |
| 追溯链 (spec_ref) | ✅ 已修复 | — | 本轮发现 misra-rules.yaml 已包含 spec_ref 和 check_method 字段 ✅ |
| Dir 4.2 重复 | ✅ 已修复 | — | 本轮确认 misra-rules.yaml 中 Dir 4.2 已改为动态内存约束 ✅ |

#### 乐观发现

本轮审查中发现两个积极进展：

1. **misra-rules.yaml 已补全 spec_ref 和 check_method**: 相较于 Loop 2 提出的 "spec_ref 缺失" 问题，最新 commit (32b5d2a0) 的 `misra-rules.yaml` 全部 142 条规则均包含 `spec_ref` 和 `check_method` 字段 ✅
2. **Dir 4.2 重复问题已修复**: 对比上一轮审查，本轮 `misra-rules.yaml` 中 Dir 4.2 的描述已改为动态内存使用约束，不再与 Rule 1.2 重复 ✅

这意味着 Loop 2 中标记的 Blocking 状态已被小克 👨‍💻 解决。

#### 剩余待办

| 优先级 | 事项 | 负责人 |
|:------:|:-----|:------|
| P0 | 创建 `docs/misra-deviations.md` | 小克 |
| P1 | 集成 `misra_trend.py` 到 `stages.py` | 小克 |
| P1 | 实现 `yuleosh misra deviate` CLI 命令 | 小克 |
| P1 | 创建 `docs/misra-verification-plan.md` | 小克 |
| P1 | 为 `misra_trend.py` 编写单元测试 | 小克 |
| P2 | 正式追加验收矩阵 §7/§8/§9 | 小马（待小克确认后） |

---

*Loop 3 审查完毕 | 小马 🐴 | 2026-06-18 17:42 CST*

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

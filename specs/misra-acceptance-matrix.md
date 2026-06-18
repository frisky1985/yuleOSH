# MISRA C:2023 集成 — 验收判定矩阵

> **版本**: 1.0.0-draft
> **作者**: 小马 🐴（质量架构师）
> **关联 Spec**: `specs/misra-c2023-spec.md`

---

## 1. CI 集成验收

| 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 |
|:-------|:---------|:---------|:---------|:---------|
| MISRA 检查阶段存在 | SWE-MISRA-S1 | 运行 CI Layer 2，检查 stages.py 日志 | `pytest test_ci_layers.py` / 手动 CI 执行 | `static_analysis_stage` 在 Layer 2 中调用 cppcheck 并包含 `--misra=` 参数 |
| cppcheck 在 C 源文件上运行 | SWE-MISRA-S1 | 检查 cppcheck 命令参数 | CI 输出日志 | 日志显示 `cppcheck --misra=` 而非通用的 `--enable=all` |
| 检查覆盖全部 .c 文件 | SWE-MISRA-S1 | 验证 `_find_c_sources()` 输出 | `test_ci_layers.py` 集成测试 | 测试确认 src/ 下所有 .c/.h 被传入 cppcheck |
| MISRA 结构化报告 JSON | SWE-MISRA-S2 | 检查 `.osh/ci/misra-report-*.json` | pytest / 手动 | JSON 包含: rule_id, description, file, line, severity, timestamp |
| 报告包含 Required/Advisory 统计 | SWE-MISRA-S2 | 解析 JSON | pytest | JSON 中有 `totals` 字段包含 `required`, `advisory`, `project_specific` 计数 |
| 报告时间戳 | SWE-MISRA-S2 | 检查 JSON | pytest | JSON 中 `generated_at` 为 ISO 时间戳 |
| 报告工具版本 | SWE-MISRA-S2 | 检查 JSON | pytest | JSON 中 `tool_version` 字段非空 |

## 2. 规则配置验收

| 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 |
|:-------|:---------|:---------|:---------|:---------|
| misra-rules.yaml 文件存在 | SWE-MISRA-CFG1 | 检查文件是否存在 | `pytest` 或 `ls` | `misra-rules.yaml` 在项目根目录或 `.yuleosh/` 下 |
| 规则编号准确对应 C:2023 | SWE-MISRA-CFG1 | 人工审查 + 正则校验 | 审查报告 | 所有 rule 编号为 `Rule X.Y` 格式，对应 C:2023 官方编号 |
| 描述清晰 | SWE-MISRA-CFG1 | 人工审查 | 审查报告 | 每条描述不超过 120 字，说明违反场景而非技术实现 |
| 严重度分级合理 | SWE-MISRA-CFG1 | 对照 Section 4 规则分级目录审查 | 审查报告 | Required 规则 severity 不低于 "major"；Advisory 不高于 "minor" |
| 规则分级属性完整 | SWE-MISRA-CFG1 | 解析 YAML 校验 schema | pytest | 每条规则有: rule, category, description, severity, enabled, check, rationale |
| TOP 20 全部启用 | SWE-MISRA-CFG2 | 从 YAML 中提取 enabled 规则 | pytest | 预定义的 TOP 20 列表中所有规则 enabled=True |
| TOP 20 不可禁用 | SWE-MISRA-CFG2 | 测试偏移排查排除 | pytest | 任何尝试设置 TOP 20 规则 enabled=False 触发警告 |

## 3. 违规处理验收

| 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 |
|:-------|:---------|:---------|:---------|:---------|
| MISRA_FAIL_FAST 阻断 | SWE-MISRA-S3 | 设置 `MISRA_FAIL_FAST=1` 运行 CI | CI 日志 | Required 违规导致 stage status="failed" |
| MISRA_FAIL_FAST 非阻断模式 | SWE-MISRA-S3 | 设置 `MISRA_FAIL_FAST=0` 运行 CI | CI 日志 | Required 违规导致 stage status="warning" 而非 "failed" |
| 偏差文件存在 | SWE-MISRA-DEV1 | 检查文件 | `ls` | `docs/misra-deviations.md` 存在（可为空） |
| 偏差文件格式 | SWE-MISRA-DEV1 | 解析 markdown | pytest | 格式: `| Rule X.Y | path/to/file.c:L | reason | date |` |
| 偏差排除生效 | SWE-MISRA-DEV1 | 在偏差文件中添加规则触发 CI | CI 日志 | 偏差中的违规不被报告 |

## 4. 配置集成验收

| 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 |
|:-------|:---------|:---------|:---------|:---------|
| ci-config.yaml MISRA 配置段 | SWE-MISRA-CONF1 | 解析 ci-config.yaml | pytest `test_ci_config.py` | `load_ci_config()` 返回的 CiConfig 对象有 `misra` 属性 |
| MISRA 配置默认值 | SWE-MISRA-CONF1 | 无 ci-config.yaml 时测试 | pytest | 默认 `enabled=True`, `fail_on_required=True`, `max_warnings=100` |
| MISRA 配置覆盖 | SWE-MISRA-CONF1 | 提供自定义 ci-config.yaml | pytest | 自定义值被正确解析 |

## 5. 测试验收

| 验收项 | 验证方法 | 验证工具 | 通过标准 |
|:-------|:---------|:---------|:---------|
| compliance 模块覆盖率 ≥85% | 运行 pytest --cov | pytest + coverage | `yuleosh/compliance/compliance_checker.py` 覆盖率 ≥85% |
| pipeline 模块覆盖率 ≥80% | 运行 pytest --cov | pytest + coverage | `yuleosh/pipeline/` 模块覆盖率 ≥80% |
| MISRA 相关 stage 测试 | 运行 pytest | pytest | 测试覆盖: 规则解析/启用/禁用/偏差/故障模式 |
| 测试使用现有风格 | 审查测试代码 | 人工 | 使用 pytest fixtures, mock subprocess, `with patch()` |

## 6. 全局验收标准

| 标准 | 判定条件 |
|:-----|:---------|
| ✅ **全部通过** | 无 Required 级别项目未通过 |
| ⚠️ **有条件通过** | 所有 Required 验收项通过；≤3 项 Advisory 未通过 |
| ❌ **不通过** | 任意 Required 验收项未通过；或 ≥4 项 Advisory 未通过 |

---

*本文档是 misra-c2023-spec.md 的验收执行视图，供测试团队和小克 👨‍💻 使用。*

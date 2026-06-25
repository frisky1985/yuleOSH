# MISRA C:2023 合规 & 单元测试报告模板 — 专家审查报告

> **专家**: 小马 🐴（质量架构师）
> **审查标准**: MISRA C:2023 Guideline Document + ASPICE v3.1 SWE.4/SWE.5/SWE.6
> **审查日期**: 2026-06-22
> **版本**: v1.0

---

## 审查方法论

本审查对照以下标准评估 yuleOSH 的两个核心报告模板：

1. **MISRA C:2023 标准**（The Guidelines for the Use of the C Language in Critical Systems）
   - 报告内容完整度（§5 Compliance Documentation Requirements）
   - 规则分级（Required / Advisory / Directive → §4）
   - 偏差管理（§4.3 Deviation Procedure）

2. **ASPICE v3.1 过程参考模型**
   - SWE.4 BP1（验证结果存档）：证据格式要求
   - SWE.4 BP2（覆盖率测量）：度量和可测试性
   - SWE.5 BP2（集成验证）：报告可追溯性
   - SWE.6 BP2（合格性测试）：评估证据

3. **ISO 26262-8 §11 工具资格视角**
   - 输出证据是否满足工具置信度要求

4. **行业最佳实践**
   - xUnit/JUnit 报告标准
   - gcov/lcov 覆盖度量标准
   - 趋势数据格式

---

## A. MISRA C:2023 报告模板合规审查 (misra_report.py)

### A.1 核心字段合规性

| # | 要求项 | MISRA C 标准要求 | 当前状态 | 评价 |
|:-:|:-------|:----------------|:---------|:-----|
| A1.1 | rule_id | 每条违规记录必须有唯一规则编号 | ✅ `rule_id` 字段（如 `misra-c2023-17.7`） | 合规 |
| A1.2 | severity/分级 | Required / Advisory / Directive 分类 | ⚠️ 部分合规 | `severity_category` 在规则定义中有 required/advisory，但 Directive 规则未从 Rule 规则中明确区分；报告中分类标签需更清晰 |
| A1.3 | file | 违规所在文件路径 | ✅ `file` 字段 | 合规 |
| A1.4 | line | 违规行号 | ✅ `line` 字段 | 合规 |
| A1.5 | column | 违规列号 | ✅ `col` 字段 | 合规 |
| A1.6 | message | 违规描述消息 | ✅ `message` 字段（80字符截断） | 合规 |
| A1.7 | generated_at | ISO 8601 时间戳 | ✅ `generated_at` | 合规 |
| A1.8 | tool_version | 使用的分析工具版本 | ❌ **缺失** | 报告中未记录 cppcheck/clang-tidy 版本；影响 ASPICE PA 2.2 RI 证据 |
| A1.9 | ruleset_version | 规则定义版本 | ❌ **缺失** | misra-rules.yaml 无版本号；报告无 RULE_SET_REF 字段 |
| A1.10 | total_kloc | 分析的代码千行数 | ❌ **缺失** | 报告无 KLOC 统计，无法计算违规密度 |
| A1.11 | unique_file_count | 受影响的文件数 | ✅ 有 `unique_files` | 合规 |
| A1.12 | severity_counts | Required/Advisory/Project 计数 | ⚠️ 部分合规 | 计数有但分类是内置的 cppcheck severity（error/warning/style），不是 MISRA 的 Required/Advisory——重要缺陷 |

### A.2 Required / Advisory / Project-specific 分级

| # | 要求项 | 标准 | 当前状态 | 评价 |
|:-:|:-------|:-----|:---------|:-----|
| A2.1 | Required 规则标注 | 违规报告中明确区分 Required | ⚠️ 部分 | `severity_category` = "required"，但 markdown 报告中以 🔴/🟡/⚪ icon 区分，不够清晰——缺"Required"文字标签 |
| A2.2 | Advisory 规则标注 | 违规报告中明确区分 Advisory | ⚠️ 同上 | 同上 |
| A2.3 | Directive 规则标注 | Dir 系列规则需特别标识 | ❌ **缺失** | Directive 规则在 misra-rules.yaml 中定义（dir-4.1 等），但报告中与 Rule 合并展示，未区分 "Dir 规则" 分类 |
| A2.4 | Project-specific 规则标注 | 项目自定义规则需标识 | ❌ **缺失** | misra-rules.yaml 的 `profile` 字段 (`safety` / `testing` / `performance`) 未映射到报告中 |
| A2.5 | 分级统计摘要 | 按 Required/Advisory/Project 汇总 | ❌ **缺失** | 当前仅统计 cppcheck tool severity（error/warning/style），非 MISRA Required/Advisory——这是根本性的设计缺陷 |

### A.3 追溯矩阵

| # | 要求项 | ASPICE SWE.4/SWE.5 | 当前状态 | 评价 |
|:-:|:-------|:-------------------|:---------|:-----|
| A3.1 | 规则 → spec 需求追溯 | SWE.4 BP2 追溯证据 | ✅ `spec_ref` 在 traceability 中 | 合规——每个 violation 关联 spec_ref |
| A3.2 | 违规 → 修复任务追溯 | SWE.5 BP3 | ✅ `generate_fix_tasks()` | 合规 |
| A3.3 | 违规 → 偏差追溯 | SWE.4 BP2 | ✅ `deviation_ref` 字段 | 合规 |
| A3.4 | 追溯矩阵 → test case 映射 | SWE.4 BP2 三向追溯 | ❌ **缺失** | 追溯矩阵有 rule→spec_ref，但无 IMPL-ID/TEST-ID 关联；尚未实现三向追溯 |
| A3.5 | 追溯矩阵版本信息 | PA 2.1 | ❌ **缺失** | traceability JSON 无版本号/commit_sha/build_id |

### A.4 偏差 (Deviation) 管理

| # | 要求项 | MISRA C:2023 §4.3 | 当前状态 | 评价 |
|:-:|:-------|:------------------|:---------|:-----|
| A4.1 | 偏差可记录 | deviation list 输入 | ✅ `deviations` 参数 | 合规——支持 tuple 列表 |
| A4.2 | 偏差匹配（rule+file） | glob/正则模式匹配 | ✅ `fnmatch` | 合规 |
| A4.3 | 偏差状态追踪 | historical audit trail | ⚠️ 部分 | 支持 acknowledged，但无风险等级（Low/Medium/High）、无到期日期检查、无 ALM ticket 关联 |
| A4.4 | 偏差过期提醒 | 过期自动失效 | ❌ **缺失** | 代码中无 expiration check 逻辑 |
| A4.5 | 偏差报告在 main report 中体现 | 主报告含偏差表 | ❌ **缺失** | Markdown 报告无独立的 "偏差/豁免" 章节 |

### A.5 ASPICE SWE.4 证据要求

| # | 要求项 | SWE.4 BP 要求 | 当前状态 | 评价 |
|:-:|:-------|:--------------|:---------|:-----|
| A5.1 | 验证结果结构化存档 | SWE.4 BP1 | ✅ JSON + MD | 合规——双格式输出 |
| A5.2 | 验证配置证据 | SWE.4 BP1 配置锁定 | ❌ **缺失** | 报告中未记录使用的规则配置文件版本、启用/禁用的规则列表 |
| A5.3 | 工具资格证明 | SWE.4 BP1 工具置信度 | ❌ **缺失** | 报告中无工具资格参考（TCL/TI/TD 分类信息） |
| A5.4 | 排除项说明 | SWE.4 BP1 验证范围 | ❌ **缺失** | 报告中无 excluded files/rules 列表 |
| A5.5 | 验证时间/人 | SWE.4 BP2 负责人证据 | ⚠️ 部分 | 有时间戳但无审核人/触发人字段 |
| A5.6 | 全量 vs 增量 | SWE.4 BP1 范围定义 | ❌ **缺失** | 报告无 `is_delta` 标记——无法区分全量扫描和增量扫描 |

### A.6 缺失的 MISRA C 标准要求内容

| # | 缺失项 | 严重度 | 说明 |
|:-:|:-------|:------:|:------|
| M1 | **Required/Advisory/Directive 分类统计** | P0 | 当前 report 以 cppcheck severity（error/warning/style）统计，而非 MISRA C 的 Required/Advisory 分类——这是最重要的缺陷 |
| M2 | **违规密度 per KLOC** | P1 | 报告中无 `violations_per_kloc` 字段，无法直接评估代码质量密度 |
| M3 | **工具版本记录** | P1 | 无 `tool_version` (cppcheck/clang-tidy/AI-review)，影响 CL2 证据可靠性 |
| M4 | **规则集版本和配置文件引用** | P1 | 无 ruleset 版本号，无法确认分析使用的规则基线 |
| M5 | **排除文件/规则列表** | P1 | 报告未列出被排除的分析范围 |
| M6 | **偏差独立章节在 Markdown 报告中** | P2 | MD 报告无独立的偏差表格/章节 |
| M7 | **趋势对比（与上轮构建）** | P2 | 报告无 delta comparison with previous run |
| M8 | **规则覆盖矩阵** | P1 | 报告不展示哪些规则被检查，哪些被跳过——审计师无法确认检查完整性 |
| M9 | **MISRA Directive 系列独立归类** | P2 | "Dir" 指令规则应与 "Rule" 规则独立展示 |

---

## B. 单元测试报告模板合规审查 (review_selftest.py + selftest-report.md)

### B.1 测试执行结果充分性

| # | 要求项 | 行业标准 | 当前状态 | 评价 |
|:-:|:-------|:---------|:---------|:-----|
| B1.1 | 测试总数 | xUnit 标准 | ✅ 有 | runner/total/passed/failed |
| B1.2 | 测试通过率 | 百分比 | ❌ **缺失** | 无 pass_rate % |
| B1.3 | 测试跳过数 | 区分 skip/error/fail | ❌ **缺失** | 无 skipped/error 计数 |
| B1.4 | 单个测试用例结果 | 逐用例 pass/fail/skip | ❌ **缺失** | 无 test case 级别的明细清单 |
| B1.5 | 失败详细信息 | 失败原因、堆栈、断言 | ❌ **缺失** | 失败时无错误消息或堆栈追踪 |
| B1.6 | 测试持续时间 | 总时长 + 单用例时长 | ❌ **缺失** | 无 duration 信息 |
| B1.7 | 测试环境信息 | OS/Compiler/Platform | ❌ **缺失** | 无构建环境上下文 |
| B1.8 | 测试分类 | unit/integration/system | ❌ **缺失** | 无测试类型分类 |

### B.2 覆盖率数据

| # | 要求项 | SWE.4 BP2 | 当前状态 | 评价 |
|:-:|:-------|:----------|:---------|:-----|
| B2.1 | 代码行覆盖率 | 标准度量 | ❌ **缺失** | 报告仅说 "Run CI Layer 1..."——覆盖率 deferred |
| B2.2 | 分支覆盖率 | 条件覆盖 | ❌ **缺失** | 同上 |
| B2.3 | 函数覆盖率 | 入口覆盖 | ❌ **缺失** | 同上 |
| B2.4 | MC/DC 覆盖率 | 安全关键系统 | ❌ **缺失** | 未实现（高级要求） |
| B2.5 | 覆盖率趋势（per build） | PA 2.2 MP | ❌ **缺失** | 无趋势数据 |

### B.3 SHALL 追溯完整性

| # | 要求项 | SWE.4 BP2 → SWE.6 | 当前状态 | 评价 |
|:-:|:-------|:------------------|:---------|:-----|
| B3.1 | SHALL 语句提取 | 正则/spec 解析 | ✅ 有 | `_extract_shall_statements()` 功能就绪 |
| B3.2 | SHALL ↔ test case 映射 | 双向追溯 | ⚠️ **不可靠** | 实际输出中 `shall_covered: 0, shall_unknown: 4`——LLM 映射失败 |
| B3.3 | 未覆盖 SHALL 清单 | gap 报告 | ⚠️ 有但空 | `shall_uncovered` 字段存在但常为 [] |
| B3.4 | SHALL 覆盖断言 | per SHALL 测试断言 | ❌ **缺失** | 无 individual SHALL→assertion 映射 |
| B3.5 | 追溯矩阵三列需求→实现→测试 | PA 2.1 TM | ❌ **缺失** | 无 traceability matrix 集成 |

### B.4 关键测试度量指标缺失

| # | 缺失指标 | 重要性 | 说明 |
|:-:|:---------|:------:|:------|
| M10 | **测试通过率 (%)** | P0 | 最基本的质量指标——缺失 |
| M11 | **覆盖率数据 (line/branch/function)** | P0 | 核心 SWE.4 BP2 度量——缺失 |
| M12 | **单用例级测试结果** | P0 | 无法定位具体失败的用例 |
| M13 | **回归分析（新 vs 旧）** | P1 | 无法判断测试结果趋势（progress/regression） |
| M14 | **测试金字塔分类** | P2 | 无法区分单元/集成/系统测试 |
| M15 | **测试持续时间** | P2 | 无法评估测试效率和性能退化 |
| M16 | **SHALL 覆盖百分比** | P0 | 实际的 SHALL→test 映射为空——最核心缺陷 |

### B.5 报告可读性和实用性评估

| 维度 | 评分 | 说明 |
|:-----|:----:|:------|
| 可读性 | ⭐⭐ | 自测报告模板简短，但缺关键信息；JSON 输出较为完整但需要工具解析 |
| 实用性 | ⭐ | 当前 `selftest-report.md` 是 stub：Total=0, Failed=0 — 未反映真实测试运行结果 |
| 自动化程度 | ⭐⭐ | LLM 驱动审查思路好，但实际输出 unreliable（`_raw_llm_output: "mock"`） |
| 可审计性 | ⭐ | 缺乏 per-test-case 追溯和覆盖率证据 |

---

## C. 差距分析总结

### C.1 MISRA 报告模板 vs 标准差距

| 差距域 | 当前实现度 | 目标要求 | 差距程度 |
|:-------|:----------:|:---------|:--------:|
| 违规报告字段完整性 | 85% | 100%（11/13 字段存在） | 🔴 2 字段缺失 |
| Required/Advisory 分级统计 | 30% | 100%（使用 MISRA 分类而非 tool severity） | 🔴 根本性缺陷 |
| 偏差管理完整性 | 60% | 100%（缺风险等级/过期提醒/审计链） | 🟡 功能完整度不足 |
| 工具/配置证据 | 20% | 100%（缺版本/规则集/排除列表） | 🔴 CL2 关键缺失 |
| ASPICE SWE.4 映射 | 40% | 100%（缺范围/配置/工具/排除证据） | 🔴 审计不充分 |
| 追溯矩阵（三向） | 50% | 100%（仅 rule→spec，无 TEST-ID） | 🟡 缺关键链路 |

### C.2 单元测试报告模板 vs 标准差距

| 差距域 | 当前实现度 | 目标要求 | 差距程度 |
|:-------|:----------:|:---------|:--------:|
| 测试执行结果详细度 | 15% | 100%（缺 pass rate / per-case / error detail） | 🔴 基本报告信息不足 |
| 覆盖率数据 | 0% | 100%（彻底缺失，仅提示文本） | 🔴 核心 SWE.4 BP2 要求缺失 |
| SHALL 追溯覆盖 | 10% | 100%（机制存在但实际输出全空） | 🔴 不可用 |
| 测试度量指标 | 10% | 100%（缺趋势/回归/通过率） | 🔴 不可度量 |
| 可审计性 & 标准化 | 10% | 100%（非标准化格式，不可导入 ALM/CI 工具） | 🔴 严重 |

### C.3 两个模板的共性差距

| 共性差距 | MISRA 报告 | 单元测试报告 | 影响 |
|:---------|:----------:|:------------:|:-----|
| 无趋势对比 | ❌ | ❌ | 无法判断改进/退化 |
| 无构建版本链 | ❌ | ❌ | CL2 可审计性差 |
| 无 KLOC / 规模统计 | ❌ | ❌ | 密度度量缺失 |
| 无标准化输出格式 | ✅ JSON | ❌ 自定义 | 互操作性差 |
| Checklist/template 不完整 | ❌ | ❌ | 一致性风险 |

---

## D. 改进建议（按严重度排序）

### P0 — 必须修复（质量门禁阻断）

| ID | 模板 | 问题 | 建议修复 | 工作量估计 |
|:---|:-----|:-----|:---------|:----------|
| **P0-1** | MISRA 报告 | **违规分类使用 tool severity 而非 MISRA Required/Advisory** | 在 `generate_json_report()` 中增加 `misra_classification` 字段，按 `rule_defs.severity` 统计 required/advisory/directive counts；Markdown 报告中增加独立 Required/Advisory 统计章节 | 1 天 |
| **P0-2** | MISRA 报告 | **无 tool_version / ruleset_version** | 在 report JSON 的 root 增加 `tool_version`(从 --version 获取) 和 `ruleset_version`(从 misra-rules.yaml meta 读取) | 0.5 天 |
| **P0-3** | 单元测试报告 | **实际 self-test-report.md 无有效测试数据** | 基于 Python `pytest` JUnit XML 输出（`--junitxml`）生成结构化报告：解析用例名、结果、时长、错误消息；写入 `test_case_results: [{name, status, duration, message}]` | 2 天 |
| **P0-4** | 单元测试报告 | **覆盖率数据完全缺失** | 集成 lcov 解析：当 coverage.info 存在时解析 line/branch/function 覆盖率；写入结构化字段 | 2 天 |
| **P0-5** | 单元测试报告 | **SHALL→test 映射不可靠（LLM 输出 mock）** | 增加基于 `pytest -k` 标签的自动映射（测试函数名匹配 SHALL ID）；LLM 作为补充而非主要映射源 | 1 天 |
| **P0-6** | 两个模板 | **无 build_id / commit_sha 关联** | 在 report JSON 的 root 增加 `build_id`、`commit_sha`、`branch` 字段，从 CI 环境变量注入 | 0.5 天 |
| **P0-7** | 两个模板 | **无 ASPICE 映射证据** | 在 report JSON 中增加 `aspice_map` 字段，显式标注 SWE.4 BP1/BP2 对应的报告节 | 0.5 天 |

### P1 — 重要建议（Sprint 内完成）

| ID | 模板 | 问题 | 建议修复 | 工作量估计 |
|:---|:-----|:-----|:---------|:----------|
| **P1-1** | MISRA 报告 | **无 KLOC / 违规密度** | 解析源代码统计有效行数，输出 `total_kloc` + `violations_per_kloc` | 1 天 |
| **P1-2** | MISRA 报告 | **无排除列表** | 在报告中增加 `excluded_rules` 和 `excluded_files` 字段 | 0.5 天 |
| **P1-3** | MISRA 报告 | **偏差模块化不够（无过期提醒/风险等级）** | 增强 `MisraDeviation`：增加 `risk_level`(low/mid/high)、`expires` 字段；在报告 Deviation 章节展示；`_match_deviation` 增加过期检查 | 1.5 天 |
| **P1-4** | MISRA 报告 | **Markdown 缺少偏差独立章节** | 在 `generate_markdown_report()` 末尾增加 "Deviation Overview" 表格 | 0.5 天 |
| **P1-5** | 单元测试报告 | **无测试通过率百分比** | 在 report JSON 中增加 `pass_rate`、`total_skipped`、`total_errors`、`total_assertions` | 0.5 天 |
| **P1-6** | 单元测试报告 | **无测试持续时间** | 解析 pytest 执行时长，输出 `duration_sec`、`test_cases[].duration` | 0.5 天 |
| **P1-7** | 两个模板 | **无趋势对比字段（与上次构建）** | 在 report JSON 增加 `prev_build_diff`：与 `.yuleosh/reports/` 中上一个报告对比的 delta 字段 | 1 天 |
| **P1-8** | MISRA 报告 | **规则覆盖矩阵缺失** | 增加 `rules_checked_count`、`rules_skipped_count`、`rules_checked_list` 字段——显示哪些规则实际被检查 | 1 天 |

### P2 — 建议改善（后续 Sprint）

| ID | 模板 | 问题 | 建议修复 | 工作量估计 |
|:---|:-----|:-----|:---------|:----------|
| **P2-1** | MISRA 报告 | **Dir 规则未独立归类** | 在统计和表格中区分 `type: "rule"` 和 `type: "directive"` | 0.5 天 |
| **P2-2** | MISRA 报告 | **无法区分全量/增量扫描** | 增加 `scan_mode: "full"|"delta"` 字段 | 0.5 天 |
| **P2-3** | 单元测试报告 | **测试金字塔分类** | 增加 test type 字段：`unit`/`integration`/`system`（从 test 用例命名或路径推断） | 1 天 |
| **P2-4** | 两个模板 | **标准化输出格式** | MISRA: 支持 SARIF 输出格式；单元测试: 支持 xUnit XML 解析输入 + JUnit 兼容输出 | 2 天 |
| **P2-5** | 单元测试报告 | **test_gap_areas 质量差** | 基于 spec SHALL ID 与测试用例标签的自动 gap 分析，LLM 仅做语言润色 | 1 天 |
| **P2-6** | 两个模板 | **可审计 Dashboard 数据源** | 输出 JSON schema 版本化，增加 `schema_version` 字段，支持版本兼容 | 0.5 天 |

---

## E. 综合评分

### MISRA C:2023 报告模板（misra_report.py）

| 评估维度 | 权重 | 评分 | 加权得分 |
|:---------|:----:|:----:|:--------:|
| 核心字段完整性 | 25% | 85 | 21.3 |
| Required/Advisory 分级 | 20% | 30 | 6.0 |
| 追溯矩阵 | 20% | 60 | 12.0 |
| 偏差管理 | 15% | 60 | 9.0 |
| ASPICE SWE.4 证据 | 15% | 30 | 4.5 |
| 可审计性 (CL2) | 5% | 30 | 1.5 |
| **总分** | **100%** | | **54.3/100** |

### 单元测试报告模板（review_selftest.py + selftest-report.md）

| 评估维度 | 权重 | 评分 | 加权得分 |
|:---------|:----:|:----:|:--------:|
| 测试结果详细度 | 25% | 15 | 3.8 |
| 覆盖率数据 | 20% | 0 | 0.0 |
| SHALL 追溯 | 20% | 10 | 2.0 |
| 关键度量指标 | 20% | 5 | 1.0 |
| 可读性/实用性 | 10% | 20 | 2.0 |
| 标准化/可审计性 | 5% | 10 | 0.5 |
| **总分** | **100%** | | **9.3/100** |

### 综合评判

```
MISRA C 报告模板: 54/100 — ⚠️ 有条件的通过（需 P0 修复后重新评审）
单元测试报告模板:  9/100 — ❌ 完全不通过（需重写核心报告生成逻辑）
```

**总结**: MISRA 报告模板架构合理，但 P0-1（违规分类错误）是一个根本性设计缺陷，导致整体评分偏低；单元测试报告模板实际上是 "不可交付" 状态——缺少最基本的测试结果详细信息和覆盖率数据。

---

## F. 优先级修复路线图

```mermaid
gantt
    title 报告模板修复路线图
    dateFormat  YYYY-MM-DD
    axisFormat  %m-%d

    section P0 — 必备
    P0-1 MISRA 违规分类修正       :critical, p0-1, 2026-06-23, 1d
    P0-2 工具/规则集版本          :p0-2, after p0-1, 0.5d
    P0-3 测试用例级结果归档        :critical, p0-3, 2026-06-23, 2d
    P0-4 覆盖率数据集成           :critical, p0-4, 2026-06-24, 2d
    P0-5 SHALL 自动映射           :p0-5, 2026-06-25, 1d
    P0-6 build_id/commit_sha     :p0-6, 2026-06-23, 0.5d
    P0-7 ASPICE 映射字段          :p0-7, 2026-06-25, 0.5d

    section P1 — 重要
    P1-1 KLOC/违规密度            :p1-1, after p0-2, 1d
    P1-2 排除列表                 :p1-2, after p0-7, 0.5d
    P1-3 偏差增强                 :p1-3, after p1-2, 1.5d
    P1-4 MD 偏差章节              :p1-4, after p1-3, 0.5d
    P1-5 pass_rate/duration       :p1-5, after p0-3, 0.5d
    P1-6 标准度量字段             :p1-6, after p1-5, 0.5d
    P1-7 趋势对比                 :p1-7, after p1-1, 1d
    P1-8 规则覆盖矩阵             :p1-8, after p0-2, 1d
```

**关键里程碑**:
1. **Day 1-2**: MISRA 违规分类修正 + 工具/规则集版本 → MISRA 报告评分从 **54→70**
2. **Day 2-4**: 测试用例级结果 + 覆盖率数据 → 单元测试报告从 **9→50**
3. **Day 4-5**: SHALL 自动映射 + 度量指标 → 单元测试报告评分提高到 **65+**
4. **调整后目标**: MISRA 报告 **75/100** + 单元测试报告 **70/100** = CL1 级就绪

---

## G. 验证样本

### G.1 MISRA 报告 JSON 正确结构（应包含字段）

```json
{
  "generated_at": "2026-06-22T13:57:00",
  "standard": "MISRA C:2023",
  "tool": "cppcheck --addon=misra",
  "tool_version": "2.13.0",
  "ruleset_version": "misra-c2023-v1.0",
  "build_id": "build-20260622-001",
  "commit_sha": "abc123def456",
  "scan_mode": "full",
  "total_kloc": 12.5,
  "summary": {
    "total_violations": 15,
    "required": 5,
    "advisory": 8,
    "directive": 2,
    "project_specific": 0,
    "unique_files": 3,
    "violations_per_kloc": 1.2,
    "severity_counts": {"error": 3, "warning": 7, "style": 5},
    "misra_classification": {"required": 5, "advisory": 8, "directive": 2}
  },
  "excluded": {
    "rules": ["Rule-10.x"],
    "files": ["lib/*", "vendor/*"]
  },
  "deviations": [
    {
      "rule_id": "misra-c2023-17.7",
      "file_pattern": "src/boot/*.c",
      "status": "approved",
      "risk_level": "low",
      "expires": "2026-09-30"
    }
  ]
}
```

### G.2 单元测试报告 JSON 正确结构（应包含字段）

```json
{
  "generated_at": "2026-06-22T13:57:00",
  "session": "e2e-perf",
  "build_id": "build-20260622-001",
  "runner": "pytest",
  "summary": {
    "total": 42,
    "passed": 38,
    "failed": 2,
    "skipped": 1,
    "errors": 1,
    "duration_sec": 15.3,
    "pass_rate": 90.5
  },
  "coverage": {
    "line_rate": 72.3,
    "branch_rate": 65.1,
    "function_rate": 85.4
  },
  "test_cases": [
    {"name": "test_brake_control_engage", "status": "passed", "duration": 0.42},
    {"name": "test_sensor_read_timeout", "status": "failed", "duration": 0.85,
     "message": "AssertionError: expected 100, got 95"}
  ],
  "shall_coverage": {
    "shall_total": 15,
    "shall_covered": 12,
    "shall_uncovered": ["The system SHALL respond within 100ms"],
    "shall_unknown": 0
  },
  "test_gap_areas": ["Sensor fusion timeout handling"]
}
```

---

*报告由质量架构师 小马 🐴 基于 MISRA C:2023 标准、ASPICE v3.1 SWE.4/SWE.5/SWE.6 及行业最佳实践生成。*
*如需进一步讨论任何发现项，请联系。*

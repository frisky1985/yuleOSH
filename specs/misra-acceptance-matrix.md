# MISRA C:2023 集成 — 验收判定矩阵（最终版）

> **版本**: 1.2.0
> **作者**: 小马 🐴（质量架构师）
> **关联 Spec**: `specs/misra-c2023-spec.md`
> **专家评审对应**: 老陈 G-01 ~ G-19 全覆盖 + Pipeline 优化 G-18 ~ G-46
> **Sprint A 更新**: 2026-06-18 — 87+ 目标，Profile 切换验收 (§16)，CL2 证据要求 (§17)，G-31~G-46 总表 (§18)

---

## 1. CI 集成验收 ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 1.1 | MISRA 检查阶段存在 | SWE-MISRA-S1 | 运行 CI Layer 2，检查 stages.py 日志 | `pytest test_ci_layers.py` / 手动 CI 执行 | `run_misra_check()` 在 Layer 2 中调用 cppcheck 并包含 `--addon=misra` 参数 | ✅ |
| 1.2 | cppcheck 在 C 源文件上运行 | SWE-MISRA-S1 | 检查 cppcheck 命令参数 | CI 输出日志 | 日志显示 `cppcheck --addon=misra` 而非通用的 `--enable=all` | ✅ |
| 1.3 | 检查覆盖全部 .c/.h 文件 | SWE-MISRA-S1 | 验证 `_find_c_sources()` 输出 | `test_ci_layers.py` 集成测试 | 测试确认 src/ 下所有 .c/.h 被传入 cppcheck | ✅ |
| 1.4 | MISRA 结构化报告 JSON | SWE-MISRA-S2 | 检查 `.osh/ci/misra-report-*.json` | pytest / 手动 | JSON 包含: rule_id, description, file, line, severity, timestamp | ✅ |
| 1.5 | 报告包含 Required/Advisory 统计 | SWE-MISRA-S2 | 解析 JSON | pytest | JSON 中有 `totals` 字段包含 `required`, `advisory`, `project_specific` 计数 | ✅ |
| 1.6 | 报告时间戳 | SWE-MISRA-S2 | 检查 JSON | pytest | JSON 中 `generated_at` 为 ISO 时间戳 | ✅ |
| 1.7 | 报告工具版本 | SWE-MISRA-S2 | 检查 JSON | pytest | JSON 中 `tool_version` 字段非空 | ✅ |
| 1.8 | 增量检查 delta check | **G-01** | 运行 CI 对比两次 commit | CI 日志 + pytest | `run_misra_check()` 支持 `--delta` 参数，仅扫描 `git diff HEAD~1` 的修改文件 | ✅ |

## 2. 规则配置验收 ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 2.1 | misra-rules.yaml 文件存在 | SWE-MISRA-CFG1 | 检查文件是否存在 | `pytest` 或 `ls` | `misra-rules.yaml` 在项目根目录或 `.yuleosh/` 下 | ✅ |
| 2.2 | 规则编号准确对应 C:2023 | SWE-MISRA-CFG1 | 人工审查 + 正则校验 | 审查报告 | 所有 rule 编号为 `Rule X.Y` 格式，对应 C:2023 官方编号 | ✅ |
| 2.3 | 描述清晰 | SWE-MISRA-CFG1 | 人工审查 | 审查报告 | 每条描述不超过 120 字，说明违反场景而非技术实现 | ✅ |
| 2.4 | 严重度分级合理 | SWE-MISRA-CFG1 | 对照 Section 4 规则分级目录审查 | 审查报告 | Required 规则 severity 不低于 "major"；Advisory 不高于 "minor" | ✅ |
| 2.5 | 规则分级属性完整 | SWE-MISRA-CFG1 | 解析 YAML 校验 schema | pytest | 每条规则有: rule, category, description, severity, enabled, check, rationale | ✅ |
| 2.6 | TOP 20 全部启用 | SWE-MISRA-CFG2 | 从 YAML 中提取 enabled 规则 | pytest | 预定义的 TOP 20 列表中所有规则 enabled=True | ✅ |
| 2.7 | TOP 20 不可禁用 | SWE-MISRA-CFG2 | 测试偏移排查排除 | pytest | 任何尝试设置 TOP 20 规则 enabled=False 触发警告 | ✅ |
| 2.8 | Dir 系列规则补齐 | **G-04** | 检查 yaml 中 Directives 定义 | pytest + 人工审查 | Dir 1.1~4.15 至少有 stub 定义，标记 check: manual | ✅ |
| 2.9 | Rule 22.x 资源管理补齐 | **G-08** | 检查 yaml 中 Rule 22.x 定义 | pytest + 人工审查 | Rule 22.1~22.6 全部定义，severity 不低于 major | ✅ |

## 3. 违规处理验收 ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 3.1 | Required 违规阻断（fail_on_required=True） | **G-09** | 设置 `fail_on_required=True` 运行 CI | CI 日志 | Required 违规导致 stage status="failed" | ✅ |
| 3.2 | Advisory 非阻断模式 | SWE-MISRA-S3 | 设置 `fail_on_advisory=False` 运行 CI | CI 日志 | Advisory 违规导致 stage status="warning" 而非 "failed" | ✅ |
| 3.3 | 偏差文件存在 | SWE-MISRA-DEV1 | 检查文件 | `ls` | `docs/misra-deviations.md` 存在（可为空） | ✅ |
| 3.4 | 偏差文件格式 | SWE-MISRA-DEV1 | 解析 markdown | pytest | 格式: `| Rule X.Y | path/to/file.c:L | reason | date |` | ✅ |
| 3.5 | 偏差排除生效 | SWE-MISRA-DEV1 | 在偏差文件中添加规则触发 CI | CI 日志 | 偏差中的违规不被报告 | ✅ |
| 3.6 | 偏差 CLI — `yuleosh misra deviate list` | SWE-MISRA-DEVCLI1 | 运行命令 | CLI 测试 | 输出偏差清单表格，含 rule_id, file_pattern, reason, approved_by, expires, status | ✅ |
| 3.7 | 偏差 CLI — `yuleosh misra deviate add` | SWE-MISRA-DEVCLI2 | 运行 `add` 后检查 ci-config.yaml | pytest | ci-config.yaml 的 `misra.deviations` 新增对应条目，status=pending | ✅ |
| 3.8 | 偏差 CLI — `yuleosh misra deviate approve` | SWE-MISRA-DEVCLI3 | 运行 `approve` 后检查 ci-config.yaml | pytest | 对应偏差条目 status → approved, approved_by 更新 | ✅ |
| 3.9 | 偏差 CLI — `yuleosh misra deviate reject` | SWE-MISRA-DEVCLI3 | 运行 `reject` 后检查 ci-config.yaml | pytest | 对应偏差条目 status → rejected | ✅ |
| 3.10 | 偏差 CLI — `yuleosh misra deviate export` | SWE-MISRA-DEVCLI4 | 运行 export | CLI 测试 | 输出 YAML/JSON 格式，内容与 ci-config.yaml 一致 | ✅ |
| 3.11 | 偏差 CI 过滤 | SWE-MISRA-DEVCLI5 | 配置偏差后运行 CI | CI 日志 | 匹配偏差的违规在报告中标记为 "acknowledged" 而非新增违规 | ✅ |
| 3.12 | docs/misra-deviations.md 存在 | SWE-MISRA-DEVCLI6 | 检查文件 | `ls` | 文件存在，至少包含表头和示例条目 | ✅ |
| 3.13 | 偏差管理升级：唯一 ID + 审批签名 + 有效期 | **G-02** | 检查 ci-config.yaml 偏差条目 | pytest + 人工审查 | 每条偏差有 rule_id, file_pattern, reason, approved_by, expires, status 字段 | ✅ |

## 4. 配置集成验收 ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 4.1 | ci-config.yaml MISRA 配置段 | SWE-MISRA-CONF1 | 解析 ci-config.yaml | pytest `test_ci_config.py` | `load_ci_config()` 返回的 CiConfig 对象有 `misra` 属性 | ✅ |
| 4.2 | MISRA 配置默认值 | SWE-MISRA-CONF1 | 无 ci-config.yaml 时测试 | pytest | 默认 `enabled=True`, `fail_on_required=True`, `fail_on_violation=False`, `fail_threshold=10` | ✅ |
| 4.3 | MISRA 配置覆盖 | SWE-MISRA-CONF1 | 提供自定义 ci-config.yaml | pytest | 自定义值被正确解析 | ✅ |
| 4.4 | MisraConfig data class 存在 | SWE-MISRA-CONF1 | 检查 config.py | pytest | `MisraConfig` 含 enabled, addon, fail_on_required, fail_on_violation, fail_on_advisory, fail_threshold, violations_per_kloc, cppcheck_std, suppress_rules, deviations 等字段 | ✅ |
| 4.5 | MisraDeviation data class 存在 | SWE-MISRA-CONF1 | 检查 config.py | pytest | `MisraDeviation` 含 rule_id, file_pattern, reason, approved_by, expires, status 字段 | ✅ |

## 5. 测试验收 ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 5.1 | compliance 模块覆盖率 ≥85% | — | 运行 pytest --cov | pytest + coverage | `yuleosh/compliance/compliance_checker.py` 覆盖率 ≥85% | ✅ |
| 5.2 | pipeline 模块覆盖率 ≥80% | — | 运行 pytest --cov | pytest + coverage | `yuleosh/pipeline/` 模块覆盖率 ≥80% | ✅ |
| 5.3 | MISRA 相关 stage 测试 | — | 运行 pytest | pytest | 测试覆盖: 规则解析/启用/禁用/偏差/故障模式 | ✅ |
| 5.4 | misra-ci 端到端测试 | — | 运行 pytest | pytest | 测试 `test_misra_config_extended.py` 覆盖 MisraConfig 加载/无效 YAML/偏差管理 | ✅ |
| 5.5 | misra_trend 单元测试 | — | 运行 pytest | pytest | `show_trend()` 返回正确表格；`get_violations_per_kloc()` 边界条件正确 | ✅ |
| 5.6 | deviation CLI 测试 | — | 运行 pytest | pytest | 测试 list/add/approve/reject 全部路径 | ✅ |

## 6. KPI/趋势验收 ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 6.1 | misra_trend.py 文件存在 | SWE-MISRA-KPI1 | 检查文件是否存在 | `ls` | `src/yuleosh/ci/misra_trend.py` 存在 | ✅ |
| 6.2 | 趋势文件 JSONL 格式 | SWE-MISRA-KPI1 | 解析 `.yuleosh/reports/misra-trend.jsonl` | pytest | 每行是有效 JSON，含 timestamp, total_violations, required, advisory | ✅ |
| 6.3 | 趋势集成到 CI | SWE-MISRA-KPI2 | 运行 CI 后检查 trend 文件 | CI 日志 | `run_misra_check()` 输出中包含 `append_entry()` 调用痕迹 | ✅ |
| 6.4 | 趋势 Markdown 表格 | SWE-MISRA-KPI2 | 调用 show_trend() | pytest | 返回格式正确的 Markdown 表格 | ✅ |
| 6.5 | 密度计算正确 | SWE-MISRA-KPI3 | 输入已知 violation 和 KLOC | pytest | `get_violations_per_kloc(10, 5.0)` = 2.0; `(0, 5.0)` = 0.0; `(10, 0)` = 0.0 | ✅ |
| 6.6 | 趋势 CLI 命令 — `yuleosh misra trend` | **G-12** | 运行 `yuleosh misra trend --lines 10` | CLI 测试 | 输出 Markdown 表格含最近 N 次趋势记录 | ✅ |
| 6.7 | 趋势 CLI — JSON 输出 | **G-12** | 运行 `yuleosh misra trend --lines 5 --json` | CLI 测试 | 输出 JSON 格式的趋势数据 | ✅ |
| 6.8 | 趋势 CLI — 天过滤 | **G-12** | 运行 `yuleosh misra trend --days 7` | CLI 测试 | 只显示最近 7 天的记录 | ✅ |
| 6.9 | 报告 CLI — `yuleosh misra report` | **G-12** | 运行 `yuleosh misra report` | CLI 测试 | 输出 summary 格式的违规总结 | ✅ |
| 6.10 | 报告 CLI — 多种格式 | **G-12** | 运行 `yuleosh misra report --format json|markdown|html` | CLI 测试 | 输出 JSON/Markdown/HTML 格式报告 | ✅ |
| 6.11 | KPI 违规密度 limit | SWE-MISRA-KPI3 | CI 配置 `violations_per_kloc` | CI 日志 | 密度超限时 stage status="warning" | ✅ |
| 6.12 | coverage_trend.py 文件存在 | SWE-MISRA-KPI4 | 检查文件 | `ls` | `src/yuleosh/ci/coverage_trend.py` 存在 | ✅ |
| 6.13 | coverage_trend CLI — `yuleosh coverage trend` | — | 运行 `yuleosh coverage trend --lines 5` | CLI 测试 | 输出 Markdown 表格含最近覆盖趋势 | ✅ |
| 6.14 | coverage_trend CLI — JSON 输出 | — | 运行 `yuleosh coverage trend --json` | CLI 测试 | 输出 JSON 格式趋势数据 | ✅ |

### 6.x 统一 KPI 基线（E08~E09）新增验收项

> **来源**: CL2 审计计划 E08（首次数据采集）· E09（4 周基线发布）
> **关联文档**: `docs/pipeline-optimization-plan.md 附录 D`
> **依赖**: 需要创建 `src/yuleosh/ci/kpi_trend.py` 模块和 `yuleosh kpi` CLI

| # | 验收项 | 归属 | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:----:|:------:|:---------|:---------|:----:|
| 6.15 | kpi_trend.py 模块存在 | E08 | P0 | 检查文件 | `src/yuleosh/ci/kpi_trend.py` 存在，包含 `record_kpi()` 和 `show_kpi_trend()` | ❌ |
| 6.16 | kpi-trend.jsonl 文件写入 | E08 | P0 | 运行 CI 后检查 | `.yuleosh/reports/kpi-trend.jsonl` 存在，每行含 timestamp, build_id, build_success_rate, test_pass_rate, c_line_coverage, misra_violations_per_kloc, misra_required_count, build_duration_sec, agent_review_pass_rate | ❌ |
| 6.17 | `yuleosh kpi status` CLI 命令 | E08 | P0 | 运行命令 | 输出最近一次构建的全量 KPI 仪表盘摘要 | ❌ |
| 6.18 | `yuleosh kpi trend --kpi <name>` CLI | E08 | P0 | 运行命令 | 输出单个 KPI 指标趋势表格 | ❌ |
| 6.19 | `yuleosh kpi baseline save` CLI | E08 | P0 | 运行命令 | 创建基线快照文件 `.yuleosh/reports/kpi-baseline-<date>.json` | ❌ |
| 6.20 | `yuleosh kpi baseline list` CLI | E08 | P1 | 运行命令 | 显示基线版本历史 | ❌ |
| 6.21 | `yuleosh kpi baseline diff <v1> <v2>` CLI | E08 | P1 | 运行命令 | 输出两个基线版本的指标差异 | ❌ |
| 6.22 | CI 自动采集 KPI | E08 | P0 | 运行全 CI 后检查 | kpi-trend.jsonl 追加新记录；CI 输出中包含 KPI 摘要 | ❌ |
| 6.23 | 覆盖 ≥20 个有效数据点 | E09 | P0 | 检查记录数 | kpi-trend.jsonl 含 ≥20 条记录 | ❌ |
| 6.24 | 正式基线文档发布 | E09 | P0 | 检查文档 | `docs/metrics/process-performance-baseline-v1.0.md` 含均值/P50/P90/UCL/LCL | ❌ |
| 6.25 | KPI 门禁告警联动 | E09 | P0 | 注入超限数据 | KPI 连续 3 次触及 UCL/LCL → CI 告警 | ❌ |

#### 6.x 汇总

| 优先级 | 数量 | Sprint A 目标 |
|:------:|:----:|:-------------|
| P0 | 7 (6.15~6.19, 6.22, 6.23) | Sprint A-m4: 启动 E08 首次采集 |
| P1 | 2 (6.20~6.21) | Sprint B |
| P0 | 2 (6.24~6.25) | Sprint B (E09 基线发布) |

---

## 7. 双向追溯验收 ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 7.1 | 规则 → 检查项追溯 | **G-03** | 检查 misra-rules.yaml → run_misra_check() 映射 | pytest + 人工审查 | 每条 enabled 规则可追踪到 cppcheck 检查参数或 manual 标记说明 | ✅ |
| 7.2 | 检查项 → 违规追溯 | **G-03** | 运行 CI 后检查 JSON 报告 | pytest | JSON 报告每条违规含 rule_id，可反查到 misra-rules.yaml 条目 | ✅ |
| 7.3 | 违规 → 修复/偏差追溯 | **G-03** | 检查偏差文件 | pytest | 偏差记录可反查到对应 rule_id 和文件 | ✅ |

## 8. 验证计划文档验收 ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 8.1 | 文档存在 | SWE-MISRA-VP1 | 检查文件 | `ls` | `docs/misra-verification-plan.md` 存在 | ✅ |
| 8.2 | 角色定义 | SWE-MISRA-VP1 | 审查文档 | 人工审查 | 至少定义 3 个角色（质量架构师、开发者、项目负责人），职责描述清晰 | ✅ |
| 8.3 | 验证活动 | SWE-MISRA-VP1 | 审查文档 | 人工审查 | 至少列出 4 项验证活动，每项定义了执行者、频率、输入、输出 | ✅ |
| 8.4 | 门禁定义 | SWE-MISRA-VP2 | 审查文档 | 人工审查 | 至少定义 3 个门禁，每个门禁有通过条件和阻断行为 | ✅ |
| 8.5 | ASPICE SWE.4 映射 | SWE-MISRA-VP3 | 审查文档 | 人工审查 | 至少有 SWE.4 BP1/BP2 的映射说明 | ✅ |
| 8.6 | ASPICE SWE.5 映射 | SWE-MISRA-VP3 | 审查文档 | 人工审查 | 至少有 SWE.5 BP2/BP3 的映射说明 | ✅ |
| 8.7 | SWE.6 映射 | SWE-MISRA-VP3 | 审查文档 | 人工审查 | 至少有 SWE.6 BP2/BP3 的映射说明 | ✅ |
| 8.8 | 风险与缓解 | SWE-MISRA-VP4 | 审查文档 | 人工审查 | 至少列出 3 个风险项，每个含概率/影响/缓解措施 | ✅ |

## 9. 工具认证验收 (G-07) ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 9.1 | Tool qualification 文档存在 | **G-07** | 检查文件 | `ls` | `docs/iso26262-tool-qualification.md` 存在 | ✅ |
| 9.2 | TCL 分类正确 | **G-07** | 审查文档 | 人工审查 | cppcheck → TCL2, clang-tidy → TCL1, AI → TCL1；分类依据明确 | ✅ |
| 9.3 | TI/TD 评估合理 | **G-07** | 审查文档 | 人工审查 | Tool Impact 和 Tool Error Detection 评估有依据、有数据支撑 | ✅ |
| 9.4 | Qualification 论证完整 | **G-07** | 审查文档 | 人工审查 | 有明确的 TD→TD1 提升策略说明（3 层冗余 + 增量 + 趋势） | ✅ |
| 9.5 | 已知缺陷清单 | **G-07** | 审查文档 | 人工审查 | 列出 cppcheck 的已知缺陷（Essential type 模型、间接递归、Resource 有限、Dir 不覆盖）| ✅ |
| 9.6 | 规则覆盖矩阵 | **G-07** | 审查文档 | 人工审查 | Dir/Required/Advisory 三类自动覆盖率明确；未覆盖规则有责任分配 | ✅ |
| 9.7 | ASIL 等级建议 | **G-07** | 审查文档 | 人工审查 | 对 ASIL A/B/C/D 给出明确的工具组合建议 | ✅ |
| 9.8 | GLPD 检查清单 | **G-07** | 审查文档 | 人工审查 | GPG 条目（ISO 26262-8 §11 Good Practice Guide）逐项检查 | ✅ |
| 9.9 | Benchmark 样本套件规划 | **G-07** | 审查文档 | 人工审查 | 文档包含 benchmark 套件结构建议 | ✅ |

## 10. MISRA MISRA KPI/Metrics 验收 (G-06) ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 10.1 | 违规趋势采集 | **G-06** | 运行 CI 后检查 trend 文件 | `ls` | `.yuleosh/reports/misra-trend.jsonl` 存在且非空 | ✅ |
| 10.2 | 违规密度 per KLOC | **G-06** | 函数 `get_violations_per_kloc()` 测试 | pytest | Result=2.0 for (10, 5.0); returns 0.0 for (10, 0) | ✅ |
| 10.3 | _print_trend_summary 输出趋势概要到 CI 日志 | **G-06** | 检查 CI 日志 | CI 日志 | CI 运行结束输出 `📈 MISRA Trend (last N runs)` 摘要 | ✅ |
| 10.4 | 趋势方向指示（↑↓→） | **G-06** | 检查 CI 日志或 show_trend() | pytest | 最新趋势与上一笔对比有方向箭头 | ✅ |

## 11. ALM 集成预留验收 (G-13) ✅

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 11.1 | alm/ 模块目录存在 | **G-13** | 检查目录 | `ls` | `src/yuleosh/alm/` 目录存在 | ✅ |
| 11.2 | alm/__init__.py 存在 | **G-13** | 检查文件 | `ls` | `src/yuleosh/alm/__init__.py` 存在 | ✅ |
| 11.3 | 基类 `AlmBaseAdapter` 定义 | **G-13** | 检查 alm/__init__.py | pytest | `AlmBaseAdapter` 类定义了 create_ticket, update_ticket, link_requirement, upload_attachment, get_ticket 等方法 | ✅ |
| 11.4 | Jira 适配器桩 | **G-13** | 检查 alm/__init__.py | pytest | `JiraAdapter` 类继承 AlmBaseAdapter，实现所有方法（stub） | ✅ |
| 11.5 | Polarion 适配器桩 | **G-13** | 检查 alm/__init__.py | pytest | `PolarionAdapter` 类继承 AlmBaseAdapter，实现所有方法（stub） | ✅ |
| 11.6 | Factory 函数 `create_adapter()` | **G-13** | 检查 alm/__init__.py | pytest | `create_adapter("jira", ...)` 返回 JiraAdapter 实例 | ✅ |
| 11.7 | 适配器注册表 | **G-13** | 检查 alm/__init__.py | pytest | `_ADAPTER_REGISTRY` 包含 jira, polarion 两个条目 | ✅ |
| 11.8 | `list_available_adapters()` 函数 | **G-13** | 检查 alm/__init__.py | pytest | `list_available_adapters()` 返回 `["jira", "polarion"]` | ✅ |
| 11.9 | `AlmConnection` data class | **G-13** | 检查 alm/__init__.py | pytest | `AlmConnection` 含 url, api_token, project_key, timeout_s 字段 | ✅ |
| 11.10 | `DeviationTicket` data class (含 ALM 字段) | **G-13** | 检查 alm/__init__.py / config.py | pytest | `DeviationTicket` 或 `MisraDeviation` 含 rule_id, file_pattern, reason, approved_by, expires, status, alm_ticket_id, alm_url 字段 | ❌ `MisraDeviation` (config.py) 缺 alm_ticket_id/alm_url; `DeviationTicket` 类不存在 |

## 12. 误报率量化基准验收 (G-10) ⚠️

| # | 验收项 | SHALL ID | 验证方法 | 验证工具 | 通过标准 | 状态 |
|:-:|:-------|:---------|:---------|:---------|:---------|:----:|
| 12.1 | Benchmark 样本目录存在 | **G-10** | 检查目录 | `ls` | `tests/misra-benchmark/` 目录存在（可为空，标记 planned） | ❌ |
| 12.2 | Benchmark 测试计划文档化 | **G-10** | 审查文档 | 人工审查 | tool qualification 文档 §6 包含 benchmark 规划说明 | ✅(计划阶段) |
| 12.3 | TOP 20 规则误报率有估算 | **G-10** | 审查文档 | 人工审查 | tool qualification 文档 §3.2 引用老陈评估"cppcheck 误报率 20-30%" | ✅(引用估算) |

## 13. 全局验收标准

| 标准 | 判定条件 |
|:-----|:---------|
| ✅ **全部通过** | 无 Required 级别项目未通过 |
| ⚠️ **有条件通过** | 所有 Required 验收项通过；≤3 项 Advisory/Nice-to-have 未通过 |
| ❌ **不通过** | 任意 Required 验收项未通过；或 ≥4 项 Advisory 未通过 |

### 验收级别汇总

| 域 | SHALL ID | 级别 | 说明 | 状态 |
|:---|:---------|:----:|:-----|:----:|
| CI 集成 | SWE-MISRA-S1~S3 | Required | 核心基础设施 | ✅ |
| 规则配置 | SWE-MISRA-CFG1~CFG2 | Required | 规则驱动检查 | ✅ |
| Gap 补齐 | G-01 ~ G-06, G-08~G-13 | 混合 | 见下方细表 | ✅ (G-10 ⚠️) |
| 违规处理 | SWE-MISRA-DEV1~DEV2 | Required | 偏差管理 | ✅ |
| 配置集成 | SWE-MISRA-CONF1 | Required | CI 配置 | ✅ |
| 追溯链 | SWE-MISRA-TR1~TR5 | 混合 | Required 为主 | ✅ |
| KPI/趋势 | SWE-MISRA-KPI1~KPI3 | 混合 | KPI1/2 Required, KPI3 Advisory | ✅ |
| 偏差 CLI | SWE-MISRA-DEVCLI1~DEVCLI6 | 混合 | 除 export 外均为 Required | ✅ |
| 验证计划 | SWE-MISRA-VP1~VP4 | 混合 | VP1~VP3 Required, VP4 Advisory | ✅ |
| 工具认证 | G-07 | Required | ISO 26262-8 §11 工具分类评估 | ✅ |
| ALM 集成 | G-13 | Advisory | 预留接口（桩实现） | ✅ |
| 误报率基准 | G-10 | Advisory | Benchmark 需后续迭代 | ⚠️ |

### G-01 ~ G-30 覆盖总表

| 编号 | 缺口项 | 原始建议工作量 | 实施状态 | 验收状态 | 对应验收节 |
|:----|:-------|:--------------|:---------|:--------|:----------|
| **G-01** | 增量检查 delta check | ~2-3 天 | ✅ 已实现 | ✅ | §1.8 |
| **G-02** | 偏差管理流程升级 | ~5 天 | ✅ 已实现 | ✅ | §3.13 |
| **G-03** | 双向追溯链 | ~3 天 | ✅ 已实现 | ✅ | §7 |
| **G-04** | Dir 系列规则补齐 | ~1 天 | ✅ 已实现 | ✅ | §2.8 |
| **G-05** | MISRA 验证计划文档 | ~1 天 | ✅ 已实现 | ✅ | §8 |
| **G-06** | MISRA KPI/Metrics | ~3 天 | ✅ 已实现 | ✅ | §10 |
| **G-07** | Tool classification + qualification 文档 | ~3 天 | ✅ 已实现 | ✅ | §9 |
| **G-08** | Rule 22.x 补齐 | ~1 天 | ✅ 已实现 | ✅ | §2.9 |
| **G-09** | fail_on_violation 默认值修正 | ~1 天 | ✅ 已实现 | ✅ | §3.1 |
| **G-10** | cppcheck 误报率量化基准 | ~2 天 | ✅ 文档已规划 | ⚠️ 待Benchmark | §12 |
| **G-11** | 趋势历史 90 天存储 | ~2 天 | ✅ 已实现 | ✅ | §6 |
| **G-12** | CLI 趋势折线 + 报告 | ~3 天 | ✅ 已实现 | ✅ | §6.6~6.10 |
| **G-13** | ALM 集成预留接口 | ~5 天 | ✅ 已实现 | ✅ | §11 |
| **G-14** | IDE 插件 (VSCode) | Nice-to-have | ❌ 未开始 | — | — |
| **G-15** | 多工具冗余融合报告 | Nice-to-have | ✅ 3 层架构已设计 | ✅ | §1 (间接) |
| **G-16** | MCU 特定规则扩展包 | Nice-to-have | ❌ 未开始 | — | — |
| **G-17** | 安全/性能/测试 Profile 切换 | Nice-to-have | ❌ 未开始 | — | — |

| **G-18** | 嵌入式 C 单元测试框架集成 | Pipeline P0 | 🏗️ 框架已引入（Unity/CMock），gcov 脚手架待完成 | ← P0-01 / G-32 / G-45 |
| **G-19** | 链接脚本/内存布局审查 | Pipeline P0 | ✅ 已完成（含 LMA/VMA + heap/stack） | ← P0-02 / G-34 |
| **G-20** | 启动代码/中断向量表审查 | Pipeline P0 | ✅ 已完成（含 FPU/SystemInit/Default_Handler） | ← P0-03 / G-35 / G-38 |
| **G-21** | SWE.6 合格性测试完整化 | Pipeline P0 | 🏗️ 进行中 | ← P0-04 / G-31 |
| **G-22** | Pipeline Profile 切换机制 | Pipeline P0 | 🏗️ 进行中 | ← P0-05 / G-33 |
| **G-23** | 堆栈使用分析 | Pipeline P1 | ❌ 未开始 | ← P1-01 |
| **G-24** | RTOS 任务配置审查 | Pipeline P1 | ✅ 已完成（含 configASSERT/overflow/RUN_TIME_STATS） | ← P1-02 / G-36 / G-40 |
| **G-25** | 外设寄存器 (MMIO) 配置审查 | Pipeline P1 | ❌ 未开始 | ← P1-03 |
| **G-26** | MISRA 增量模式 L1+L2 双重优化 | Pipeline P1 | ❌ 未开始 | ← P1-04 |
| **G-27** | HAL 接口契约检查 | Pipeline P2→P1 | 🏗️ 进行中 | ← P2-01 / G-41 |
| **G-28** | BSP 板级支持包验证 | Pipeline P2 | 🏗️ 实施中 | ← P2-02 / G-42 |
| **G-29** | 编译输出验证 (.map / binary size) | Pipeline P2 | 🏗️ 实施中 | ← P2-03 / G-43 |
| **G-30** | 低功耗 / 能效审查 | Pipeline P2 | 🏗️ 实施中 | ← P2-04 / G-44 |

| 判定 | 依据 |
|:----|:------|
| ✅ **全部通过（MISRA C:2023）** | 所有 Required 级别验收项通过（含 G-01~G-13 中 Required 项） |
| | G-10（误报率 Benchmark）为 Advisory 级别，标记 ⚠️ 待后续 Sprint 完成 |
| | G-14~G-17 为 Nice-to-have，不纳入本次质量门禁 |
| | 详细状态：13 个 MISRA Gap 中，10 ✅，1 ⚠️（G-10），2 ❌（G-14/G-16 Nice-to-have） |
| 🏗️ **Pipeline 优化 Sprint A（G-18~G-46，目标 87+）** | 三轮实评 76/100，G-34~G-40 全部深度补缺已完成（7 项）✅ |
| | G-32（C 框架基础）✅；G-45（gcov/CLI）🏗️；G-46（追溯引擎 ✅ / L2 handler 🏗️） |
| | G-42 BSP 验证 🏗️ 实施中 · G-43 编译输出验证 🏗️ 实施中 · G-44 低功耗审查 🏗️ 实施中 |
| | 目标 87+/100，Sprint A 关键瓶颈：SWE.6（G-31）、C 覆盖（G-45）、追溯 L2 handler（G-46）、Profile（G-33） |

---

*本文档是 misra-c2023-spec.md 的验收执行视图，供测试团队和小克 👨‍💻 使用。*
*Sprint A 更新: 2026-06-18 (v1.2.0) — 追加 Profile 切换验收 (§16)、CL2 证据要求 (§17)、G-31~G-46 状态总表 (§18)；评分路径更新至 87+ 目标*


## 14. Pipeline 优化验收 (G-18 ~ G-30) ← NEW

| # | 验收项 | SHALL ID | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:---------|:------:|:---------|:---------|:----:|
| 14.1 | C 单元测试框架 step handler 存在 (Unity/Ceedling) | SWE-PLN-CUT1 | P0 | 检查 L1 层 CI 配置 | code-c-unit-tests step handler 在 L1 层注册并运行 | ✅ 框架已引入，handler + pipeline 集成就绪 |
| 14.2 | C 单元测试使用专用框架 | SWE-PLN-CUT2 | P0 | 检查测试输出 | 测试框架为 Unity/Ceedling/CMocka 之一 | ✅ 框架选定 Unity+CMock |
| 14.3 | C 测试覆盖率由 gcov/lcov 生成 | SWE-PLN-CUT3 | P0 | 检查 CI 输出 | coverage 报告包含 C 源文件的行/分支覆盖率 | ❌ G-45 追踪 |
| 14.4 | 链接脚本审查 step handler 存在 | SWE-PLN-LK1 | P0 | 检查 L2 层 CI 配置 | code-linker-script-review 在 L2 层注册并运行 | ✅ |
| 14.5 | 链接脚本覆盖内存区域/栈/向量表 | SWE-PLN-LK2 | P0 | 审查 Agent 输出 | Agent 报告包含 MEMORY 区域、stack/heap、segment placement 检查 | ✅ |
| 14.5b | 链接脚本检查 LMA≠VMA 和 heap/stack 不重叠 | SWE-PLN-LK3 | P0 | Agent 审查报告 | LMA/VMA 区分 + heap/stack 重叠检查 | ✅ G-34 已实现 |
| 14.6 | 启动代码审查 step handler 存在 | SWE-PLN-STUP1 | P0 | 检查 L2.5 层 CI 配置 | code-startup-review 在 L2.5 层注册并运行 | ✅ |
| 14.7 | 启动审查覆盖向量表/BSS/data/SystemInit/FPU | SWE-PLN-STUP2 | P0 | 审查 Agent 输出 | Agent 报告包含向量表、BSS 清零、data 复制、SystemInit、FPU 使能检查 | ✅ |
| 14.7b | 启动审查 FPU 使能 (CPACR) 检查 | SWE-PLN-STUP3 | P0 | Agent 审查报告 | Cortex-M4/M7/M33 下检查 CPACR 配置 | ✅ G-35 已实现 |
| 14.7c | 启动审查 SystemInit 时序检查 | SWE-PLN-STUP4 | P0 | Agent 审查报告 | SystemInit 在 main() 前调用 | ✅ G-35 已实现 |
| 14.7d | 启动审查 Default_Handler weak symbol | — | P0 | Agent 审查报告 | Default_Handler WEAK 检查 + 未覆盖中断源列举 | ✅ G-38 已实现 |
| 14.8 | SWE.6 合格性测试规范定义步骤存在 | SWE-PLN-SWE6-1 | P0 | 检查 Pipeline 步骤定义 | code-swe6-qualification-plan 步骤在 Pipeline 中注册 | ❌ |
| 14.9 | L3 合格性测试执行步骤存在 | SWE-PLN-SWE6-2 | P0 | 检查 L3 层 CI 配置 | code-swe6-qualification-exec 在 L3 层注册并运行 | ❌ |
| 14.10 | 合格性测试报告含规范↔结果追溯链 | SWE-PLN-SWE6-3 | P0 | 审查报告输出 | final-report 包含测试规范到测试用例到测试结果的追溯表格 | ❌ |
| 14.11 | Pipeline 支持 ≥2 种 Profile 切换 | SWE-PLN-PROF1 | P0 | 运行 yuleosh config profile list | 输出包含 general 和 embedded 两个 profile | 🏗️ 进行中 |
| 14.12 | Profile 通过 ci-config.yaml 声明 | SWE-PLN-PROF2 | P0 | 检查配置解析 | ci-config.yaml 的 pipeline.profile 字段影响 step handler 选择 | 🏗️ 进行中 |
| 14.13 | Pipeline 启动时校验 Profile 完整性 | SWE-PLN-PROF3 | P0 | 运行缺失 step 的 profile | Pipeline 在启动阶段报告 profile 检查失败并阻断 | 🏗️ 进行中 |
| 14.14 | L2 堆栈使用分析步骤存在 | SWE-PLN-STACK1 | P1 | 检查 L2 层 CI 配置 | code-stack-analysis step handler 在 L2 层注册并运行 | ❌ |
| 14.15 | 堆栈使用 ≥95% 阻断 | SWE-PLN-STACK2 | P1 | 注入高堆栈使用率测试 | 堆栈使用 ≥95% → stage status=failed | ❌ |
| 14.16 | RTOS 配置审查 step handler 存在 | SWE-PLN-RTOS1 | P1 | 检查 L2 层 CI 配置 | code-rtos-config-review 在 L2 层注册并运行 | ✅ |
| 14.17 | RTOS 审查覆盖优先级/IPC/assert | SWE-PLN-RTOS2 | P1 | 审查 Agent 输出 | Agent 报告包含 configMINIMAL_STACK_SIZE、优先级分布、IPC 超时、configASSERT | ✅ |
| 14.17b | RTOS 审查 configASSERT 定义 | SWE-PLN-RTOS3 | P0 | Agent 审查报告 | Debug 配置下 configASSERT 必须定义 | ✅ G-36 已实现 |
| 14.17c | RTOS 审查 configCHECK_FOR_STACK_OVERFLOW | SWE-PLN-RTOS4 | P0 | Agent 审查报告 | configCHECK_FOR_STACK_OVERFLOW > 0 | ✅ G-36 已实现 |
| 14.17d | RTOS 审查 RUN_TIME_STATS | — | P1 | Agent 审查报告 | configGENERATE_RUN_TIME_STATS 配置检查 | ✅ G-40 已实现 |
| 14.18 | MMIO 配置审查 step handler 存在 | SWE-PLN-MMIO1 | P1 | 检查 L2.5 层 CI 配置 | code-mmio-config-review 在 L2.5 层注册并运行 | ❌ |
| 14.19 | MMIO 审查覆盖时钟/GPIO/NVIC/DMA | SWE-PLN-MMIO2 | P1 | 审查 Agent 输出 | Agent 报告包含时钟使能、GPIO 复用、NVIC 优先级、DMA 映射 | ❌ |
| 14.19b | review_memory 全局变量估算（短期） | SWE-PLN-MEM1 | P1 | 审查 Agent 输出 | 支持结构体/typedef/static 变量估算 | ✅ 短期方案已实施 |
| 14.19c | 链接脚本 .ARM.exidx 段检查 | SWE-PLN-LNK3 | P1 | Agent 审查报告 | .ARM.exidx 声明检查 | ✅ G-39 已实现 |
| 14.20 | L1 MISRA delta 模式 | SWE-PLN-MSR-D1 | P1 | 提交含 MISRA 违规的修改文件 | L1 仅报告修改文件中的 MISRA 违规，不扫描全量 | ❌ |
| 14.21 | L2 MISRA 全量+零增量阻断 | SWE-PLN-MSR-D2 | P1 | 与 baseline 对比 | 新增 Required 违规 → Pipeline 阻断 | ❌ |
| 14.22 | MISRA delta 阻断新增 Required 违规 | SWE-PLN-MSR-D3 | P1 | 注入新 Required 违规 | Pipeline 在 delta 模式下阻断新增 Required 违规 | ❌ |
| 14.23 | BSP 板级支持包 step handler 存在 | — | 🟢 P2 | 检查 L2.5 层 CI 配置 | `bsp-validation` step handler 在 L2.5 层注册并运行 | 🏗️ G-42 实施中 |
| 14.24 | BSP 描述文件与硬件原理图一致性验证 | — | 🟢 P2 | Agent 审查输出 | 验证 bsp-<board>.yaml 中 pin-mux/clock 配置与原理图一致 | 🏗️ G-42 实施中 |
| 14.25 | 跨板配置漂移自动检测 | — | 🟢 P2 | 注入多板配置差异 | BSP 变更后检测到跨板（STM32F4/STM32H7/ESP32）配置漂移并告警 | 🏗️ G-42 实施中 |
| 14.26 | 编译输出验证 step handler 存在 | — | 🟢 P2 | 检查 L2 层 CI 配置 | `build-output-check` step handler 在 L2 层注册并运行 | 🏗️ G-43 实施中 |
| 14.27 | .map 文件解析各区段尺寸 | — | 🟢 P2 | 运行构建后检查 | 从 `.map` 提取 .text/.data/.bss/.stack/.heap 各区段具体尺寸 | 🏗️ G-43 实施中 |
| 14.28 | 区段尺寸 diff 对比（与上一次成功构建） | — | 🟢 P2 | 连续两次构建后检查 | 输出本次 vs 上次各区段尺寸变化（±bytes，±%） | 🏗️ G-43 实施中 |
| 14.29 | 各区段增长告警门禁 | — | 🟢 P2 | 注入大代码变更 | `.text +10%` → warning；`.text +20%` → blocking | 🏗️ G-43 实施中 |
| 14.30 | 低功耗审查 step handler 存在 | — | 🟢 P2 | 检查 L2.5 层 CI 配置 | `power-review` step handler 在 L2.5 层注册并运行 | 🏗️ G-44 实施中 |
| 14.31 | Agent 审查覆盖看门狗/休眠/唤醒/时钟门控 | — | 🟢 P2 | Agent 审查输出 | Agent 报告包含 IWDG/WWDG 周期、休眠模式路径、RTC 唤醒、RCC 时钟门控、未用外设时钟禁用 | 🏗️ G-44 实施中 |
| 14.32 | 低功耗审查报告含风险等级评估 | — | 🟢 P2 | 审查报告输出 | 每条发现标记 🟢/🟡/🔴 风险等级，汇总功耗风险区域 | 🏗️ G-44 实施中 |

### 14.x Pipeline 优化汇总（Sprint A — 目标 87+）

| # | 优先级 | 数量 | Sprint A 状态 |
|:-:|:------:|:----:|:-------------|
| G-34~G-40 (深度补缺) | 🔴 P0 | 7 | ✅ **全部已完成**（review_linker/startup/rtos/memory） |
| G-32 (C 框架基础) | 🔴 P0 | 1 | ✅ **已完成**（handler + 模板 + pipeline 集成） |
| G-31 (SWE.6 三段式) | 🔴 P0 | 3 | 🏗️ **Sprint A #1 优先** |
| G-45 (C 覆盖率) | 🔴 P0 | 3 | 🏗️ **Sprint A — gcov/lcov + CLI** |
| G-46 (追溯短期) | 🔴 P0 | 4 | ✅ 引擎已就位；🏗️ **L2 handler 待 Sprint A** |
| G-33 (Profile 切换) | 🔴 P0 | 3 | 🏗️ **Sprint A — 架构+首次实现** |
| P1-01~P1-04 | 🟡 P1 | 9 | 🏗️ 3/4 进行中（堆栈/MMIO/MISRA增量） |
| P2-01~P2-04 | 🟢 P2 | 4 | 🏗️ Sprint A/B (G-42/G-43/G-44 实施中) |

> **本验收节对应 docs/pipeline-optimization-plan.md。** Sprint A 目标 87+/100，P0 全部闭环为硬门槛。

---

## 15. 三轮审查新增验收项 (G-45 ~ G-46)

| # | 验收项 | SHALL ID | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:---------|:------:|:---------|:---------|:----:|
| 15.1 | C 单元测试集成 gcov/lcov 覆盖率报告 | SWE-PLN-CUT4 | P0 | 运行 L1 c-unit-tests 后检查 | CI artifact 包含 coverage.info + coverage-report/ 目录 | ❌ |
| 15.2 | C 覆盖率行覆盖率门禁 | SWE-PLN-CUT5 | P0 | 注入低覆盖率测试 | 行覆盖率 < 40% → blocking；< 60% → warning | ❌ |
| 15.3 | `yuleosh test c --create-suite CLI` CLI 脚手架 | SWE-PLN-CUT6 | P0 | 运行 `yuleosh test c --create-suite mymodule` | test/unity/mymodule/ 目录自动生成含模板文件 | ❌ |
| 15.4 | L2 追溯性检查 step handler 存在 | SWE-PLN-TR1 | P0 | 检查 L2 层 CI 配置 | code-traceability-check 在 L2 层注册并运行 | ❌ |
| 15.5 | 追溯矩阵输出需求→实现→测试 | SWE-PLN-TR2 | P0 | 运行 traceability-check 后审查 | 输出表格中含 REQ-xxx: IMPL-xxx: TEST-xxx 三列 | ❌ |
| 15.6 | 未覆盖测试的需求阻断 Pipeline | SWE-PLN-TR3 | P0 | 注入未覆盖需求 | 需求有实现但无对应测试 → stage=failed | ❌ |
| 15.7 | `yuleosh trace matrix` CLI 命令 | SWE-PLN-TR4 | P0 | 运行 `yuleosh trace matrix` | 输出追溯矩阵表格 | ❌ |

### 15.x 三轮审查新增汇总（Sprint A）

| # | 优先级 | 数量 | Sprint A 状态 |
|:-:|:------:|:----:|:-------------|
| G-45 (C 覆盖深度：gcov/lcov + CLI) | 🔴 P0 必须 | 3 | ❌ 0/3 → 目标 Sprint A 全部闭环 |
| G-46 (追溯自动化：引擎已就位 + L2 handler) | 🔴 P0 必须 | 4 | ✅ 短期引擎已完成；❌ L2 handler 待 Sprint A（目标 2/4） |

> **本验收节对应 docs/pipeline-optimization-plan.md §三轮审查新增缺口。** 追溯完整性维度三轮评分 35/100，Sprint A 目标提升至 ≥60/100。

---

## 16. Profile 切换验收项（Sprint A 新增）

| # | 验收项 | SHALL ID | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:---------|:------:|:---------|:---------|:----:|
| 16.1 | ci-config.yaml 支持 `pipeline.profile` 配置项 | SWE-PLN-PROF1 | P0 | 解析 ci-config.yaml | `load_ci_config().pipeline.profile` 返回有效值（general/embedded/automotive） | ❌ |
| 16.2 | 至少支持 general + embedded 两个 profile | SWE-PLN-PROF2 | P0 | 运行 `yuleosh config profile list` | 输出至少包含 general 和 embedded | ❌ |
| 16.3 | Pipeline 启动时校验 profile 完整性 | SWE-PLN-PROF3 | P0 | 配置缺失 step handler 的 profile | Pipeline 报告 profile 校验失败并阻断 | ❌ |
| 16.4 | Profile 决定 L2/L2.5 step handler 过滤 | — | P0 | 切换 profile 后运行 pipeline | general 跳过嵌入式审查；embedded 启用全部 | ❌ |
| 16.5 | `yuleosh config profile check <profile>` CLI | — | P1 | 运行 check 命令 | 输出 profile 所依赖 step handler 清单及存在状态 | ❌ |
| 16.6 | Profile 自定义扩展能力（preset ± handler） | — | P1 | 配置自定义 profile | 允许在 preset 基础上增减 step handler | ❌ |
| 16.7 | Embedded profile 包含全部 4 个嵌入式审查 step | — | P0 | 运行 embedded profile | L2 含 linker-script/rtos/memory；L2.5 含 startup | 🏗️ 步骤已就位，profile 机制待连接 |

### 16.x Profile 切换汇总

| # | 优先级 | 数量 | Sprint A 状态 |
|:-:|:------:|:----:|:-------------|
| Profile 基础（16.1~16.4） | 🔴 P0 | 4 | ❌ 0/4 → 目标 Sprint A 3/4 |
| Profile 扩展（16.5~16.6） | 🟡 P1 | 2 | ❌ 0/2 |

---

## 17. CL2 证据要求（Sprint A 新增）

> **背景**: ASPICE CL2 要求过程可管理、可测量、可追溯（PA 2.1 + PA 2.2）。当前 Pipeline 已覆盖 CL1 基础，以下验收项用于建立 CL2 证据链。

| # | 验收项 | CL2 基元 | 优先级 | 验证方法 | 通过标准 | 当前状态 |
|:-:|:-------|:--------:|:------:|:---------|:---------|:--------:|
| 17.1 | 需求→实现→测试 三向追溯矩阵持续生成 | PA 2.1 (TM) | Required | 运行 `yuleosh trace matrix` 并审查 | 每个需求 REQ-xxx 同时关联 IMPL-xxx 和 TEST-xxx；无孤立需求或孤立测试 | 🏗️ 引擎已就位（G-46 短期），L2 自动化为空 |
| 17.2 | MISRA 违规密度趋势持续采集（≥90 天） | PA 2.2 (MP) | Required | 检查 `.yuleosh/reports/misra-trend.jsonl` | 文件存在且包含 ≥90 天历史记录 | ✅ 已有趋势采集 |
| 17.3 | 偏差管理全生命周期合规记录 | PA 2.1 (TM) | Required | 审查偏差批准链 | 每条偏差有 approved_by + expires + status；历史审批记录可追溯 | ✅ 偏差流程已就位 |
| 17.4 | C 单元测试覆盖率趋势（per commit） | PA 2.2 (MP) | Required | 检查 CI artifact 及趋势 JSONL | 每轮构建生成 coverage.info；行覆盖率趋势折线图可显示 | ❌ 依赖 G-45 |
| 17.5 | SWE.6 合格性测试报告一致性证据 | PA 2.1 (TM) | Required | 审查 SWE.6 输出 | 需求↔测试规范↔测试结果↔偏差评估 完整追溯链 | ❌ 依赖 G-31 |
| 17.6 | Profile 配置变更审计日志 | PA 2.2 (MP) | Advisory | 检查 CI 日志 | profile 变更在 pipeline 日志中记录 timestamp + 旧值 + 新值 | ❌ |
| 17.7 | 编码标准（MISRA）执行一致性证明 | PA 2.1 (TM) | Required | 审查 CI 日志 + 偏差文件 | 每次构建运行 MISRA 检查；所有 Required 违规有偏差或已修复 | ✅ |
| 17.8 | 构建过程可复现性证据 | PA 2.2 (MP) | Required | 检查 CI 日志 | 构建参数、工具版本、环境变量被记录到构建元数据 | 🏗️ 部分（tool_version 已有） |
| 17.9 | 工具资格证明记录 | PA 2.2 (RI) | Required | 审查 docs/iso26262-tool-qualification.md | 文档含 TCL/TI/TD 分类 + 已知缺陷清单 + 误报率估算 | ✅ 工具认证文档已完成 |
| 17.10 | Agent 审查结果持久化（JSON 报告）| PA 2.2 (MP) | Required | 检查 CI artifacts | 每次 Agent 审查步骤输出 JSON 报告，保存为 artifact | ✅（linker/startup/rtos/memory 均已输出 JSON） |

### 17.x CL2 证据就绪度汇总

| CL2 基元 | 描述 | 就绪度 | 关键缺口 |
|:---------|:-----|:------:|:---------|
| PA 2.1 (TM) — 追溯管理 | 工作产品之间双向追溯 | 🔶 **2/5** | 需求→实现→测试 追溯自动化（G-46）；SWE.6 追溯链（G-31） |
| PA 2.2 (MP) — 过程测量 | 过程测量数据采集 | 🔶 **3/5** | MISRA 趋势 ✅ / 偏差审计 ✅ / C 覆盖率 ❌ / 构建元数据 🏗️ |
| PA 2.2 (RI) — 资源与基础设施 | 工具/人员资格证明 | ✅ **2/2** | 工具认证文档 ✅；Agent 报告持久化 ✅ |

---

## 18. G-31~G-46 状态总表（Sprint A）

| 编号 | 关联项 | 类别 | Sprint A 状态 | 验收节 |
|:----:|:-------|:----|:-------------|:------|
| G-31 | P0-04 🔴 SWE.6 三段式 | P0 必须 | 🏗️ **#1 优先** | §14.8~14.10, §17.5 |
| G-32 | P0-01 🔴 C 单元测试框架 | P0 必须 | ✅ **基础已完成**（handler + 模板 + pipeline） | §14.1~14.2 |
| G-33 | P0-05 🔴 Profile 切换 | P0 必须 | 🏗️ **进行中** | §16.1~16.7 |
| G-34 | P0-02 🔴 review_linker LMA/VMA | P0 必须 | ✅ **已完成** | §14.4~14.5b |
| G-35 | P0-03 🔴 review_startup FPU/SystemInit | P0 必须 | ✅ **已完成** | §14.6~14.7c |
| G-36 | P1→P0 review_rtos configASSERT | P0 必须 | ✅ **已完成** | §14.16~14.17c |
| G-37 | review_memory 变量估算 | 🟡 P1 | ✅ **短期完成**；长期待 Sprint B+ | §14.19b |
| G-38 | P0-03 🔴 review_startup Default_Handler | P0 必须 | ✅ **已完成** | §14.7d |
| G-39 | P0-02 🟡 review_linker .ARM.exidx | 🟡 P1 | ✅ **已完成** | §14.19c |
| G-40 | P1-02 🟡 review_rtos RUN_TIME_STATS | 🟡 P1 | ✅ **已完成** | §14.17d |
| G-41 | P2→P1 🟡 HAL 契约检查 | 🟡 P1 | 🏗️ **进行中** | §14 (规划中) |
| G-42 | P2-02 🟢 BSP 验证 | 🟢 P2 | 🏗️ **实施中** Sprint A/B | §14.23~14.25 |
| G-43 | P2-03 🟢 编译输出验证 | 🟢 P2 | 🏗️ **实施中** Sprint A/B | §14.26~14.29 |
| G-44 | P2-04 🟢 低功耗审查 | 🟢 P2 | 🏗️ **实施中** Sprint A/B | §14.30~14.32 |
| G-45 | P0 🔴 C 单元测试深度集成 (gcov/CLI) | P0 必须 | 🏗️ **Sprint A** | §15.1~15.3 |
| G-46 | P0 🔴 追溯完整性 (L2 handler) | P0 必须 | ✅ 引擎已就位；🏗️ L2 handler | §15.4~15.7, §17.1 |

### 18.x Sprint A 目标对账

| 类别 | 总数 | 已完成 | 🏗️ 进行中 | 🗓️ 未开始 | Sprint A 目标完成 |
|:-----|:----:|:------:|:---------:|:---------:|:----------------:|
| P0 必须 | 10 | 6 | 3 (G-31/G-45/G-46) + 1 (G-33) | 0 | **10/10 Sprint A 闭环** |
| P1 | 5 | 4 (G-37/G-39/G-40/G-41 🏗️) | 1 | 0 | **优先 G-41 完成** |
| P2 | 3 | 0 | 3 (G-42/G-43/G-44) | 0 | Sprint A/B (实施中) |

---

*本文档 Pipeline 优化节由小马 🐴 于 2026-06-18 基于老陈审查报告新增。Sprint A 更新: 2026-06-18 — 87+ 目标，新增 Profile 切换验收 (§16)、CL2 证据要求 (§17)、G-31~G-46 总表 (§18)。*

---

## 19. CL2 过审新增验收项 (G-47 ~ G-50)

> **背景**: CL2 过审路径规划（对应 `docs/pipeline-optimization-plan.md §CL2 过审路径`）。以下 G-47~G-50 项为 CL2 审计所需的完整验收项，补足 §17 中未细化的验收覆盖。
> **来源**: CL2 过审路径（pipeline-optimization-plan.md v1.3）
> **目标**: CL2 Dry Run 前全部通过

---

### G-47：Agent 审查→代码版本双向追溯

| # | 验收项 | 关联 CL2 基元 | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:------------:|:------:|:---------|:---------|:----:|
| 19.1 | Agent 审查 JSON 报告含 commit SHA | PA 2.1 (TM) | CL2-Required | 运行 pipeline 后检查审查报告 | Agent 审查 JSON 输出的 `commit_sha` 字段非空且匹配当前 commit | ❌ |
| 19.2 | 审查发现→代码行 精确定位 | PA 2.1 (TM) | CL2-Required | 审查报告含 file:line 信息 | 每个审查发现的 `file` + `line` 字段正确；可从报告反查到代码版本 | ❌ |
| 19.3 | 审查结果可回溯到特定构建 | PA 2.1 (TM) | CL2-Required | 审查报告含 build_id 字段 | 审查报告 JSON 的 `build_id` 字段可与 CI 构建 ID 关联 | ❌ |
| 19.4 | 跨版本审查结果差异对比 | PA 2.1 (TM) | CL2-Advisory | 运行 `yuleosh review diff --commits A..B` | 输出两个版本间审查发现的变化（new/fixed/persistent） | ❌ |

### 19.x G-47 汇总

| # | 优先级 | 数量 | 目标完成 |
|:-:|:------:|:----:|:---------|
| Agent→代码追溯 | CL2-Required | 3 | Sprint B |
| 审查跨版本 diff | CL2-Advisory | 1 | Sprint B+ |

---

### G-48：构建元数据完整持久化

| # | 验收项 | 关联 CL2 基元 | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:------------:|:------:|:---------|:---------|:----:|
| 20.1 | 构建元数据 JSONL 文件存在 | PA 2.2 (MP) | CL2-Required | 检查 `.yuleosh/reports/build-metadata.jsonl` | 文件存在且非空；每行含 timestamp, build_id, status | ❌ |
| 20.2 | 构建元数据字段完整性 | PA 2.2 (MP) | CL2-Required | 解析 JSONL 校验 schema | 每条记录含: timestamp, build_id, compiler_version, cppcheck_version, os, python_version, profile, status | ❌ |
| 20.3 | 构建参数变更审计日志 | PA 2.2 (MP) | CL2-Required | 修改 ci-config.yaml profile 后运行 | 日志记录 profile 变更: timestamp, old_value, new_value, changed_by | ❌ |
| 20.4 | 构建结果与构建参数可关联 | PA 2.2 (MP) | CL2-Required | 按 build_id 查询 | 输入 build_id 可查到对应构建参数、测试结果、审查报告 | ❌ |
| 20.5 | 工具版本锁定文件 | PA 2.2 (RI) | CL2-Required | 检查 `tools-version.yaml` | 文件存在，含各工具名称+版本+校验和+变更日期 | ❌ |
| 20.6 | 工具版本变更审批流程 | PA 2.2 (RI) | CL2-Advisory | 审查变更记录 | 版本变更记录含审批人 + 影响分析 + 验证结果 | ❌ |

### 20.x G-48 汇总

| # | 优先级 | 数量 | 目标完成 |
|:-:|:------:|:----:|:---------|
| 构建元数据 | CL2-Required | 5 | Sprint A/B |
| 工具版本审批 | CL2-Advisory | 1 | Sprint B+ |

---

### G-49：过程稳定性 KPI 采集

| # | 验收项 | 关联 CL2 基元 | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:------------:|:------:|:---------|:---------|:----:|
| 21.1 | 构建成功率采集 | PA 2.2 (MP) | CL2-Required | 解析 build-metadata.jsonl | 每月构建成功率 ≥95%；可按月/周/commit 分组统计 | ❌ |
| 21.2 | 回归触发率采集 | PA 2.2 (MP) | CL2-Required | 对比前后 commit 测试结果 | 回归测试通过率下降 >5% 触发告警 | ❌ |
| 21.3 | 缺陷逃逸率采集 | PA 2.2 (MP) | CL2-Advisory | 审查→生产缺陷对比 | 逃逸缺陷数 / 总缺陷数 ≤5% | ❌ |
| 21.4 | 违规修复时效跟踪 | PA 2.2 (MP) | CL2-Required | MISRA 违规→修复闭环时间 | Required 违规 48h 内修复或提偏差；Advisory 15d 内 | ❌ |

### 21.x G-49 汇总

| # | 优先级 | 数量 | 目标完成 |
|:-:|:------:|:----:|:---------|
| 过程稳定性 KPI | CL2-Required | 3 | Sprint B |
| 缺陷逃逸率 | CL2-Advisory | 1 | Sprint B+ |

---

### G-50：CL2 证据包完整性与可审计性

| # | 验收项 | 关联 CL2 基元 | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:------------:|:------:|:---------|:---------|:----:|
| 22.1 | 证据打包 CLI 命令存在 | PA 2.1+2.2 | CL2-Required | 运行 `yuleosh evidence pack` | 输出 CL2-EVIDENCE-PACK/ 目录结构（含 PA2.1-TM, PA2.2-MP, PA2.2-RI 子目录） | ❌ |
| 22.2 | 证据完整性校验 | PA 2.1+2.2 | CL2-Required | 运行 `yuleosh evidence check` | 检查所有必备证据文件是否存在；缺失项列表输出 | ❌ |
| 22.3 | 追溯矩阵可审计性 | PA 2.1 (TM) | CL2-Required | 审计师抽检 3 条需求链 | 3 条样本：REQ-xxx → IMPL-xxx → TEST-xxx → TestResult 100% 可追踪 | ❌ |
| 22.4 | 偏差审批可审计性 | PA 2.1 (TM) | CL2-Required | 审计师抽检 3 条偏差记录 | 每条偏差: approval chain + 到期时间 + 审批理由 完整可查 | ❌ |
| 22.5 | MISRA 趋势可审计性 | PA 2.2 (MP) | CL2-Required | 审计师查验趋势数据 | ≥90 天趋势记录；数据来源与 CI 运行日志一致 | ❌ (≥90d 需 Sprint B) |
| 22.6 | C 覆盖率趋势可审计性 | PA 2.2 (MP) | CL2-Required | 审计师查验覆盖率趋势 | 覆盖率数据与 CI 构建一一对应；趋势方向可解读 | ❌ (依赖 G-45) |
| 22.7 | 工具资格文档可审计性 | PA 2.2 (RI) | CL2-Required | 审计师审查文档 | ISO 26262-8 §11 逐条对照检查通过 | ✅ 工具认证文档已就位 |
| 22.8 | CL2 Dry Run 审计报告 | PA 2.1+2.2 | CL2-Required | 运行 Dry Run 审计 | 模拟审计报告输出含通过/未通过项 + 整改建议 | ❌ |
| 22.9 | Dashboard 审计演示 | PA 2.1+2.2 | CL2-Advisory | 审计师操作 Dashboard | 可交互查看追溯矩阵、趋势图、偏差状态 | ❌ |

### 22.x G-50 汇总

| # | 优先级 | 数量 | 目标完成 |
|:-:|:------:|:----:|:---------|
| 证据 CLI 工具 | CL2-Required | 2 | Sprint B |
| 可审计性验证 | CL2-Required | 6 | Sprint B/B+ |
| Dry Run 审计 | CL2-Required | 1 | Sprint B+ DP |
| Dashboard | CL2-Advisory | 1 | Sprint B+ |

---

### G-47~G-50 状态总表

| 编号 | 关联 CL2 基元 | 类别 | 验收项数 | Sprint A 目标 | Sprint B 目标 |
|:----:|:------------:|:----|:--------:|:-------------|:-------------|
| G-47 | PA 2.1 TM | Agent→代码追溯 | 4 (3R+1A) | — | 3/4 完成 |
| G-48 | PA 2.2 MP/RI | 构建元数据 | 6 (5R+1A) | 2/6（字段定义 + tools-version.yaml） | 5/6 完成 |
| G-49 | PA 2.2 MP | 过程稳定性 KPI | 4 (3R+1A) | 1/4（修复时效） | 4/4 完成 |
| G-50 | PA 2.1+2.2 | 证据包 | 9 (8R+1A) | 1/9（工具文档已完成） | 6/9 完成（证据 CLI + 可审计性） |

---

## 20. CL2 就绪度递进视图（含 G-47~G-50）

| CL2 基元 | 子项 | 总验收项 | ✅ 已完成 | 🏗️ Sprint A | 🏗️ Sprint B | 🗓️ Sprint B+ |
|:---------|:-----|:--------:|:--------:|:-----------:|:-----------:|:------------:|
| **PA 2.1 TM** | §17.1 追溯矩阵 | 4 | 0 | 1 | 3 | 0 |
| | §17.3 偏差管理 | 2 | 2 | 0 | 0 | 0 |
| | §17.5 SWE.6 追溯 | 1 | 0 | 1 | 0 | 0 |
| | §17.7 MISRA 一致性 | 1 | 1 | 0 | 0 | 0 |
| | G-47 Agent→代码追溯 | 4 | 0 | 0 | 3 | 1 |
| | G-50 追溯可审计性 | 2 | 0 | 0 | 1 | 1 |
| | **小计** | **14** | **3** | **2** | **7** | **2** |
| **PA 2.2 MP** | §17.2 MISRA 趋势 | 1 | 1 | 0 | 0 | 0 |
| | §17.4 C 覆盖率趋势 | 2 | 0 | 2 | 0 | 0 |
| | §17.6 Profile 审计日志 | 1 | 0 | 0 | 1 | 0 |
| | §17.8 构建可复现性 | 1 | 0 | 1 | 0 | 0 |
| | G-48 构建元数据 | 6 | 0 | 2 | 3 | 1 |
| | G-49 过程稳定性 KPI | 4 | 0 | 1 | 3 | 0 |
| | G-50 趋势可审计性 | 2 | 0 | 0 | 2 | 0 |
| | **小计** | **17** | **1** | **6** | **9** | **1** |
| **PA 2.2 RI** | §17.9 工具资格 | 1 | 1 | 0 | 0 | 0 |
| | §17.10 审查报告持久化 | 1 | 1 | 0 | 0 | 0 |
| | G-48 工具版本锁定 | 2 | 0 | 1 | 0 | 1 |
| | G-50 工具文档可审计性 | 1 | 1 | 0 | 0 | 0 |
| | **小计** | **5** | **3** | **1** | **0** | **1** |
| **混合** | G-50 证据 CLI + Dry Run | 5 | 0 | 0 | 2 | 3 |
| **总计** | | **41** | **7** | **9** | **18** | **7** |

### 20.x CL2 就绪度百分比追踪

```
Sprint A:   7+ 9=16/41 → 39%
Sprint B:  16+18=34/41 → 83%
Sprint B+: 34+ 7=41/41 → 100% ✅ CL2 就绪
```

---

### CL2 过审验收判定

| 标准 | 判定条件 |
|:-----|:---------|
| ✅ **通过** | PA 2.1 TM 就绪度 ≥90%（≥13/14）；PA 2.2 MP+RI 就绪度 ≥85%（≥19/22）；混合项 ≥80%（≥4/5）；总计 ≥90%（≥37/41） |
| ⚠️ **有条件通过** | 各基元 ≥80%；总计 ≥85%（≥35/41）；Dry Run 无 major 发现 |
| ❌ **不通过** | 任意 CL2 基元就绪度 <80%；或 Dry Run 发现 major/critical 项 |

---

---

## 21. CL2 审计计划验收映射（cl2-audit-plan.md）

> **来源**: `reports/cl2-audit-plan.md`（老陈编制）
> **目的**: 将 CL2 审计任务项（E01~E13）映射到本矩阵的已有或新增验收项，确保审计计划与验收体系双向追溯
> **E01~E04（gcov 覆盖度量）** 和 **E05~E07（文档同步门禁）** 已同步更新至 `docs/misra-verification-plan.md §9~§10`

### 21.1 E01~E13 映射总表

| CL2 审计项 | 名称 | 优先级 | 映射到本矩阵验收项 | 对应验证计划章节 | 实现状态 |
|:----------:|:-----|:------:|:------------------|:----------------|:--------:|
| **E01** | gcov 编译链集成 | P0 | §15.1 (C 覆盖率 gcov/lcov) | §9.1 | ❌ |
| **E02** | lcov + genhtml 报告流水线 | P0 | §15.1~§15.2; §17.4 (§20 PA 2.2 MP) | §9.2 | ❌ |
| **E03** | 覆盖阈值门禁 (fail_under) | P0 | §5.2 阻断规则 #4; §15.2 | §9.3 | ❌ |
| **E04** | 覆盖趋势追踪与基线 | P0 | §17.4, §7.1 趋势字段; §20 PA 2.2 MP | §9.4 | ❌ |
| **E05** | 文档 YAML Schema 验证 | P0 | §8.3 (文档校验) — 新增 §21.2 | §10.1 | ❌ |
| **E06** | 文档状态门禁（MR 阻塞） | P0 | §8.4 (门禁定义) — 新增 §21.2 | §10.2~§10.3 | ❌ |
| **E07** | 文档差异自动检测 | P1 | §21.3 (21.2.8~21.2.9) | §10.4 | ❌ `sync_check.py` (322行, CLI 就绪) 待 CI pipeline 集成 |
| **E08** | 过程性能基线 — 首次数据采集 | P0 | §5.1 (KPI); §20 PA 2.2 MP | §9.4.3 | ❌ |
| **E09** | 过程性能基线 — 4 周数据与发布 | P0 | §5.1; §20 PA 2.2 MP | §9.4.3 | ❌ |
| **E10** | 偏差管理 CLI + 审批链 | P0 | §3.6~§3.13; §4.2 (CL2 偏差字段) | §4 | ✅ (已有) |
| **E11** | ALM 集成适配（Jira/Polarion） | P1 | §11.1~§11.10; §4.2 ALM 字段 | §4.2 | ⚠️ (stub 就位，§11.10 DeviationTicket 缺 ALM 字段) |
| **E12** | 验证计划文档更新 | P0 | §8.1~§8.8; §17 CL2 证据 | **本文档** | ✅ 已更新 v2.1 |
| **E13** | 审计证据包自动生成 | P0 | §22.1~§22.2 (G-50 证据 CLI) | §7.2~§7.3 | ❌ |

### 21.2 新增验收项 — 覆盖阈值门禁与趋势追踪（对应 E03~E04）

> **来源**: CL2 审计计划 E03（覆盖阈值门禁 fail_under）· E04（覆盖趋势追踪与基线）
> **关联 G-45**: C 单元测试深度集成（gcov/lcov + CLI 脚手架）
> **关联文档**: `docs/pipeline-optimization-plan.md 附录C`

| # | 验收项 | 对应审计项 | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:---------:|:------:|:---------|:---------|:----:|
| 21.2.1 | `c-coverage-report` step handler 存在 | E03 | P0 | 检查 L1 层 CI 配置 | `c-coverage-report` 在 L1 层 c-unit-tests 之后注册，运行 lcov 覆盖率采集 | ❌ |
| 21.2.2 | CI artifact 含 coverage.info + coverage-report/ | E03 | P0 | 运行 CI 后检查 artifact | `.yuleosh/reports/coverage/` 目录包含 `coverage.info` 原始数据和 `coverage-report/` HTML 展示 | ❌ |
| 21.2.3 | 行覆盖率门禁 `fail_under_line` 配置存在 | E03 | P0 | 检查 ci-config.yaml | ci-config.yaml 的 `coverage.fail_under_line` 配置项有效；默认值存在 | ❌ |
| 21.2.4 | `<40%` 阻断 Pipeline | E03 | P0 | 注入低覆盖率测试 MR | 行覆盖率 <40% → `c-coverage-report` stage = failed → MR 阻断 | ❌ |
| 21.2.5 | `<60%` ≥40% 警告但非阻断 | E03 | P0 | 注入中覆盖率测试 MR | 40% ≤ 行覆盖率 <60% → stage = warning（不阻断） | ❌ |
| 21.2.6 | `general` profile 跳过覆盖门禁 | E03 | P1 | 切换到 general profile 运行 | general profile 下 c-coverage-report 自动跳过 | ❌ |
| 21.2.7 | `embedded` profile 启用覆盖门禁 | E03 | P0 | 切换到 embedded profile 运行 | embedded profile 下 c-coverage-report 正常执行 | ❌ |
| 21.2.8 | `coverage-trend.jsonl` 文件存在且非空 | E04 | P0 | 运行 CI 后检查 | `.yuleosh/reports/coverage-trend.jsonl` 存在且每轮构建追加新记录 | ❌ |
| 21.2.9 | 趋势记录字段完整 | E04 | P0 | 解析 JSONL 校验 schema | 每行含 `timestamp, build_id, line_rate, branch_rate, function_rate, total_lines, covered_lines` | ❌ |
| 21.2.10 | `yuleosh coverage trend --lines N` CLI | E04 | P0 | 运行命令 | 输出 Markdown 表格含最近 N 条趋势记录；含方向箭头 ↑↓→ | ❌ |
| 21.2.11 | `yuleosh coverage trend --days N --json` CLI | E04 | P0 | 运行命令 | 输出 JSON 格式趋势数据（限最近 N 天） | ❌ |
| 21.2.12 | `yuleosh coverage baseline save/list/diff` CLI | E04 | P1 | 运行 `baseline save` 后检查 | `coverage-baseline-v1.json` 文件存在；baseline list 显示版本历史；diff 输出差异 | ❌ |
| 21.2.13 | gcov 编译链仅在嵌入式 profile 启用 | E03 | P0 | 检查 `c-unit-tests` handler 逻辑 | general profile 下跳过 `-fprofile-arcs -ftest-coverage` 编译选项 | ❌ |

#### 21.2.x E03~E04 验收汇总

| # | 优先级 | 数量 | Sprint A 目标 |
|:-:|:------:|:----:|:-------------|
| E03 覆盖门禁（21.2.1~21.2.7, 21.2.13） | 🔴 P0 | 8 | Sprint A-m3: 6/8 ✅ |
| E04 覆盖趋势（21.2.8~21.2.12） | 🟡 P0/P1 | 5 | Sprint A-m3: 3/5 ✅ |
| **合计** | | **13** | **Sprint A 末 ≥10/13** |

---

### 21.3 新增验收项 — 文档同步门禁（对应 E05~E07）

| # | 验收项 | 对应审计项 | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:---------:|:------:|:---------|:---------|:----:|
| 21.2.1 | 受管文档 YAML Schema 文件存在 | E05 | P0 | 检查 `docs/__schema__/` 目录 | 架构/接口/需求三类 Schema 文件均存在且内容完整 | ❌ |
| 21.2.2 | CI 自动执行 Schema 校验 | E05 | P0 | 运行 CI 后检查日志 | CI L2 层含 `code-docs-schema-validate` step; 校验失败输出行号+字段名+预期格式 | ❌ |
| 21.2.3 | 本地文档校验 CLI | E05 | P0 | 运行 `make docs-validate` | 成功/失败状态返回; 失败时包含详细校验错误 | ❌ |
| 21.2.4 | 代码-文档映射表存在 | E06 | P0 | 检查 `scripts/docs_map.yaml` | 包含代码路径→文档路径的关联关系; 含 critical 标志 | ❌ |
| 21.2.5 | 关键模块代码变更→文档未更新→MR 阻断 | E06 | P0 | 注入关键模块代码变更 | MR 变更 src/ 下关键模块路径但 docs/ 未变化 → CI FAILED | ❌ |
| 21.2.6 | 非关键模块变更→文档未更新→WARNING | E06 | P0 | 注入非关键模块代码变更 | MR 变更非关键路径 → CI WARNING + MR 评论提醒 | ❌ |
| 21.2.7 | 文档同步豁免经偏差管理 | E06 | P0 | 通过 `yuleosh misra deviate` 创建豁免 | 有效偏差 → 门禁不阻断; 偏差记录审计链完整 | ❌ |
| 21.2.8 | 代码-文档指纹对比存在 | E07 | P1 | 检查 CI 日志 | CI 运行指纹对比; 新增/删除/修改 API 均被检出 | ❌ sync_check.py 就绪 (322行, CLI), 待 CI pipeline 集成 |
| 21.2.9 | 差异报告自动评论 MR | E07 | P1 | 运行 MR 后检查评论 | MR 自动评论含具体行号和差异内容 | ❌ 需 CI 集成前置 (21.2.8) |

### 21.4 新增验收项 — 过程性能基线（对应 E08~E09）

| # | 验收项 | 对应审计项 | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:---------:|:------:|:---------|:---------|:----:|
| 21.3.1 | KPI 指标定义文档化 | E08 | P0 | 检查文档 | 各 KPI（构建时间、测试通过率、覆盖率、MISRA 违规数）有明确定义和采集方式 | ❌ |
| 21.3.2 | CI 每个阶段输出 KPI 为结构化 JSON | E08 | P0 | 运行 CI 后检查 artifact | `metrics/metrics-YYYY-MM-DD-HHMM.json` 在各阶段结束后生成 | ❌ |
| 21.3.3 | 首次基线快照存在 | E08 | P0 | 检查 `metrics/` 目录 | `baseline-v0.1.json` 文件存在，包含全部 KPI 指标当前值 | ❌ |
| 21.3.4 | 基线数据 ≥20 个有效点 | E09 | P0 | 检查历史记录 | 覆盖 ≥20 个工作日数据（4 周） | ❌ |
| 21.3.5 | 正式基线文档发布 | E09 | P0 | 检查 `docs/metrics/` | `process-performance-baseline-v1.0.md` 含均值/P50/P90/UCL/LCL + 趋势图 | ❌ |
| 21.3.6 | 基线与控制限自动对比 | E09 | P0 | 注入超限数据 | 超出 UCL/LCL → 自动告警 | ❌ |

### 21.5 新增验收项 — 证据包（对应 E13）

| # | 验收项 | 对应审计项 | 优先级 | 验证方法 | 通过标准 | 状态 |
|:-:|:-------|:---------:|:------:|:---------|:---------|:----:|
| 21.4.1 | `make evidence-package` 一键生成 | E13 | P0 | 运行命令 | 生成 `evidence-package-v2.0.tar.gz` 含全部 6 个子目录 | ❌ |
| 21.4.2 | 证据包目录结构完整 | E13 | P0 | 解压后检查 | 含 CoverageEvidence/DocSyncEvidence/BaselineEvidence/VerificationPlan/ALMIntegration/PipelineLogs | ❌ |
| 21.4.3 | 证据包附带 SHA256 checksum | E13 | P0 | 检查输出 | 生成 tar.gz 同时输出 .sha256 校验文件 | ❌ |
| 21.4.4 | 证据包生成时间 < 5min | E13 | P0 | 计时 | 从启动到打包完成不超过 5 分钟 | ❌ |
| 21.4.5 | 证据包含时间戳+Git commit+脚本版本 | E13 | P0 | 检查 evidence-manifest.json | 头部元数据不可缺失 | ❌ |

### 21.6 E01~E13 整体就绪度

| 审计项 | 对应验收项数 | ✅ 已完成 | ❌ 未完成 | 优先级 | 就绪度 |
|:------:|:----------:|:--------:|:---------:|:------:|:------:|
| **E01** gcov 编译链 | 1 | 0 | 1 | P0 | 0% |
| **E02** lcov 报告 | 2 | 0 | 2 | P0 | 0% |
| **E03** fail_under 门禁 | 1 | 0 | 1 | P0 | 0% |
| **E04** 趋势追踪 | 1 | 0 | 1 | P0 | 0% |
| **E05** Schema 验证 | 3 | 0 | 3 | P0 | 0% |
| **E06** 文档门禁 | 4 | 0 | 4 | P0 | 0% |
| **E07** 差异检测 | 2 | 0 | 2 | P1 | 0% (sync_check.py 代码就绪，待 CI pipeline 集成 + MR 评论) |
| **E08** KPI 采集 | 3 | 0 | 3 | P0 | 0% |
| **E09** 4 周基线 | 3 | 0 | 3 | P0 | 0% |
| **E10** 偏差管理 | ✅ 已有 | — | — | P0 | 100% (已有覆盖) |
| **E11** ALM 集成 | ⚠️ 已有 | — | — | P1 | 90% (stub 就位; DeviationTicket 缺 ALM 字段 §11.10 ❌) |
| **E12** 验证计划 | ✅ 已更新 | — | — | P0 | 100% |
| **E13** 证据包 | 5 | 0 | 5 | P0 | 0% |
| **合计（新增）** | **25** | **0** | **25** | — | **0%** |
| **合计（已有复用）** | **E10+E11+E12 ≈ 30 项** | ✅ | — | — | ✅ |

### 21.7 依赖关系图

```
E01 ──→ E02 ──→ E03 ──→ E10 ──→ E13
                 │                ↑
                 └──→ E04 ──→ E08 ──→ E09 ─┘
                                      ↑
E05 ──→ E06 ──→ E07 ──→ E10 ─────────┘
                         ↑
E12 ──→ (验证计划文档) ──┘

E11 ──→ E13 (ALM → 证据包)
```

**关键路径**: E01→E02→E03→E10→E13（约 11 天开发）
**最长时间**: E08→E09→E13（4 周日历，必须尽早启动）

---

### 附加说明

1. **E10（偏差管理）** 在本矩阵 §3 和 §4 已完整覆盖，本条映射仅为确认对齐
2. **E11（ALM 集成）** 在本矩阵 §11 已有 stub 适配器覆盖；§11.10 `DeviationTicket` 缺 ALM 字段待补
3. **E12（验证计划）** 已通过本版本更新完成（`docs/misra-verification-plan.md v2.1`）
4. **新增验收项（§21.2~§21.5）** 共 32 项（§21.2 E03/E04: 13 项 + §21.3 E05~E07: 9 项 + §21.4 E08~E09: 6 项 + §21.5 E13: 5 项），需纳入 Sprint 计划
5. 本映射让审计师可以直接从 cl2-audit-plan.md 追溯到验收矩阵的具体行号
6. **E03/E04（覆盖阈值门禁 + 趋势追踪）** 为 Sprint A 核心 P0 项，依赖 G-45 完成
7. **E06（文档状态门禁）** 在 §21.3 中已覆盖，对应 E05~E07 验收项

---

*版本历史: ... → v1.3 → v1.4（CL2 审计计划验收映射 §21 新增）→ v1.5（E03/E04 验收项 §21.2 新增，同步 pipeline-optimization-plan.md 附录C~F）*
*最终版更新: 2026-06-18 (v1.6 — E07/E11 小克 CL2 审查结果同步: yaml_validator CI 集成 ✅, sync_check 代码就绪待 CI, DeviationTicket ALM 字段缺漏)*

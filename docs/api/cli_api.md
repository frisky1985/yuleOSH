# 命令行接口 (`cli`) API 参考

> 代码根:`src/yuleosh/cli/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`cli` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/cli.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `ensure_osh_home` | `()` | — | `cli/main.py:136` |
| `_build_parser` | `()` | Build the argument parser for the yuleOSH CLI. | `cli/main.py:145` |
| `_resolve_ecu_template` | `(name: str)` | Resolve an ECU template by name, returning its metadata or None. | `cli/main.py:570` |
| `main` | `()` | — | `cli/main.py:582` |
| `_print_step` | `(step: int, total: int, title: str)` | Print a step heading. | `cli/onboard.py:54` |
| `_progress_bar` | `(current: int, total: int, width: int, suffix: str)` | Simple text progress bar. | `cli/onboard.py:61` |
| `_spinner_text` | `(phase: str, done: bool)` | Print spinner-style status line. | `cli/onboard.py:71` |
| `_ok` | `(msg: str)` | — | `cli/onboard.py:79` |
| `_info` | `(msg: str)` | — | `cli/onboard.py:83` |
| `_warn` | `(msg: str)` | — | `cli/onboard.py:87` |
| `_err` | `(msg: str)` | — | `cli/onboard.py:91` |
| `_detect_project_type` | `(project_dir: str)` | Auto-detect project type and framework based on source files. | `cli/onboard.py:97` |
| `_step_project_info` | `(name: Optional[str], project_type: Optional[str], oem_template: Optional[str])` | Step 1: Collect or confirm project basic info. | `cli/onboard.py:189` |
| `_step_code_analysis` | `(project_dir: str)` | Step 2: Scan and analyze project code structure. | `cli/onboard.py:223` |
| `_step_kg_bootstrap` | `(project_dir: str, analysis: dict)` | Step 3: Initialize knowledge graph from project data. | `cli/onboard.py:249` |
| `_count_iterable` | `(it)` | Count items in an iterable (generator-safe). | `cli/onboard.py:306` |
| `_step_compliance_check` | `(project_dir: str)` | Step 4: Run ASPICE Compliance Check. | `cli/onboard.py:313` |
| `_step_dashboard` | `(project_dir: str)` | Step 5: Generate dashboard and registration. | `cli/onboard.py:371` |
| `_step_summary` | `(project_dir: str, project_info: dict, analysis: dict, kg_stats: dict, compliance: dict, dashboard_info: dict, elapsed: float)` | Step 6: Print summary and next steps. | `cli/onboard.py:423` |
| `_ensure_osh_project` | `(project_dir: str)` | Create .osh/ directory skeleton if it doesn't exist. | `cli/onboard.py:477` |
| `cmd_onboard` | `(project_dir: str, name: Optional[str], project_type: Optional[str], oem_template: Optional[str], repo: Optional[str])` | Run the onboarding wizard (direction 3). | `cli/onboard.py:493` |
| `build_onboard_parser` | `(sub: argparse._SubParsersAction)` | Register the ``yuleosh onboard`` subcommand. | `cli/onboard.py:579` |
| `handle_onboard_command` | `(args)` | Dispatch from main.py main() when args.command == 'onboard'. | `cli/onboard.py:598` |
| `count_source_lines` | `(project_dir: str)` | Count lines of code by language. | `cli/stats.py:31` |
| `count_tests` | `(project_dir: str)` | Count test files and test functions, excluding self/ and .osh/ directories. | `cli/stats.py:103` |
| `compute_spec_coverage` | `(project_dir: str)` | Compute spec coverage from docs/spec.md. | `cli/stats.py:139` |
| `_compute_spec_coverage_generic` | `(project_dir: str, spec_path: Path)` | Generic spec coverage analyzer for projects without src/spec/validate.py. | `cli/stats.py:186` |
| `count_pipeline_runs` | `(project_dir: str)` | Count historical pipeline runs. | `cli/stats.py:235` |
| `count_ci_runs` | `(project_dir: str)` | Count CI pipeline runs. | `cli/stats.py:274` |
| `cmd_stats` | `(project_dir: str, to_json: bool)` | Show project statistics. | `cli/stats.py:305` |
| `_print_stats_human` | `(stats: dict)` | — | `cli/stats.py:335` |
| `main` | `()` | — | `cli/stats.py:403` |
| `cmd_template_init` | `(project_name: str, parent_dir: str, from_template: str | None)` | Initialize a new project from the yuleOSH starter template. | `cli/template.py:113` |
| `_init_from_template` | `(project_name: str, project_dir: Path, template_path: Path)` | Initialize a project by copying from an existing template directory. | `cli/template.py:159` |
| `_init_starter` | `(project_name: str, project_dir: Path)` | Initialize a generic Python starter project. | `cli/template.py:193` |
| `main` | `()` | — | `cli/template.py:248` |
| `cmd_compliance_check` | `(args)` | ``yuleosh compliance check`` — 按 profile 运行合规检查。 | `cli/commands/compliance.py:36` |
| `build_parser` | `(sub)` | 向主解析器注册 ``compliance`` 命令组 (A1-07)。 | `cli/commands/compliance.py:80` |
| `_osh_home` | `()` | Resolve OSH_HOME. | `cli/commands/consistency.py:32` |
| `_baselines_dir` | `()` | Return the baselines directory, creating it if needed. | `cli/commands/consistency.py:41` |
| `_load_session_summary` | `(session_dir: Path)` | Load session summary from gate-summary.json and other artifacts. | `cli/commands/consistency.py:48` |
| `_compute_session_fingerprint` | `(session_dir: Path)` | Compute a fingerprint for a session that can be compared across runs. | `cli/commands/consistency.py:119` |
| `cmd_baseline_save` | `(args)` | Save a session as a named baseline. | `cli/commands/consistency.py:144` |
| `cmd_baseline_list` | `(args)` | List all saved baselines. | `cli/commands/consistency.py:189` |
| `cmd_consistency_check` | `(args)` | Check consistency between a session and a baseline. | `cli/commands/consistency.py:213` |
| `register_commands` | `(subparsers)` | Register consistency commands with the argument parser. | `cli/commands/consistency.py:347` |
| `build_parser` | `(subparsers)` | Build the consistency/baseline command group for main CLI integration. | `cli/commands/consistency.py:375` |
| `main` | `()` | Entry point for standalone execution. | `cli/commands/consistency.py:403` |
| `_green` | `(text)` | — | `cli/commands/demo_uart.py:50` |
| `_yellow` | `(text)` | — | `cli/commands/demo_uart.py:51` |
| `_cyan` | `(text)` | — | `cli/commands/demo_uart.py:52` |
| `_bold` | `(text)` | — | `cli/commands/demo_uart.py:53` |
| `_red` | `(text)` | — | `cli/commands/demo_uart.py:54` |
| `_check_tool` | `(name)` | Check if a tool is available on PATH. | `cli/commands/demo_uart.py:57` |
| `_copy_template` | `(target_dir: Path)` | Copy template files to the target directory. | `cli/commands/demo_uart.py:65` |
| `_build_host` | `(target_dir: Path)` | Run host-mode cmake + make in the target directory. | `cli/commands/demo_uart.py:85` |
| `cmd_demo_uart` | `(target_dir: str, do_build: bool, skip_cmake: bool)` | Create and optionally build the UART demo project. | `cli/commands/demo_uart.py:142` |
| `_osh_home` | `()` | 延迟解析 OSH_HOME（默认当前目录）。 | `cli/commands/gap.py:37` |
| `_load_gap_details` | `(project_dir: str)` | 运行 aspice_gap_check(json) 并解析 gap_detail 列表。 | `cli/commands/gap.py:44` |
| `_status_priority` | `(status: str)` | status（❌/⚠️）→ (priority, severity)。 | `cli/commands/gap.py:60` |
| `_summarize_missing` | `(gap: dict)` | missing_items 摘要（无缺失项时用 bp_title 兜底）。 | `cli/commands/gap.py:65` |
| `_compute_deadline` | `(priority: str, now: Optional[str])` | 与 rca_engine._compute_deadline 一致：P0=24h / P1=3d / P2=7d / P3=14d。 | `cli/commands/gap.py:73` |
| `_build_gap_ticket` | `(gap: dict, req: str, created_at: Optional[str])` | 构造与 Loop3 IMP-* 同构的改进工单 dict（ticket_id 用 GAP- 前缀）。 | `cli/commands/gap.py:87` |
| `_indent_block` | `(value: Any)` | 多行文本 → 每行 4 空格缩进（YAML folded scalar `>` 兼容）。 | `cli/commands/gap.py:148` |
| `write_gap_ticket` | `(ticket: dict, output_dir: str)` | 写入 improvement_tickets/{ticket_id}.yaml。 | `cli/commands/gap.py:154` |
| `_confirm` | `(prompt: str)` | 交互确认（y/yes → True，其余/EOF → False）。 | `cli/commands/gap.py:198` |
| `cmd_gap_close` | `(args)` | `yuleosh gap close` — 从 ASPICE 差距分析受控生成改进工单。 | `cli/commands/gap.py:209` |
| `build_parser` | `(subparsers)` | 注册 gap 子命令组: yuleosh gap close。 | `cli/commands/gap.py:278` |
| `cmd_template_init` | `(project_name, parent_dir, template_name)` | Initialize an ECU project from template | `cli/commands/init.py:11` |
| `_osh_home` | `()` | — | `cli/commands/methodology.py:28` |
| `_template_dir` | `()` | 定位方法论宿主模板目录（内置优先级）。 | `cli/commands/methodology.py:36` |
| `_render` | `(content: str, project_name: str, project_desc: str)` | 替换模板占位符 {{PROJECT_NAME}} / {{PROJECT_DESC}}。 | `cli/commands/methodology.py:49` |
| `cmd_methodology_init` | `(project_dir: str, force: bool)` | 在任意项目生成方法论宿主骨架（幂等：不覆盖已有文件）。 | `cli/commands/methodology.py:57` |
| `cmd_methodology_check` | `(project_dir: str, json_out: bool)` | 在任意项目独立运行 methodology gate。 | `cli/commands/methodology.py:151` |
| `build_parser` | `(sub)` | 构建 methodology 子命令 parser（供 cli/main.py _build_parser 调用）。 | `cli/commands/methodology.py:186` |
| `_osh_home` | `()` | — | `cli/commands/misc.py:32` |
| `ensure_osh_home` | `()` | — | `cli/commands/misc.py:46` |
| `cmd_template_list` | `()` | List all available templates in a formatted table (TG-REQ-004). | `cli/commands/misc.py:53` |
| `cmd_ecu_template_list` | `()` | List all available ECU templates in a formatted table. | `cli/commands/misc.py:75` |
| `cmd_template_init` | `(project_name: str, parent_dir: str, template_name: str | None)` | Create a new project from a built-in or user template (TG-REQ-003). | `cli/commands/misc.py:95` |
| `_interactive_template_init` | `(project_name: str, parent_dir: str)` | Interactive template selection (TG-REQ-003C). | `cli/commands/misc.py:197` |
| `_ensure_tool_deps` | `()` | Check tool dependencies (cppcheck) and suggest install commands. | `cli/commands/misc.py:228` |
| `cmd_init_autosar` | `(project_name: str, parent_dir: str, yuleasr_home: str | None)` | Initialize a yuleASR AUTOSAR BSW project from the yuleasr template. | `cli/commands/misc.py:269` |
| `cmd_init` | `(dir_path: str)` | Initialize a new yuleOSH project directory. | `cli/commands/misc.py:469` |
| `cmd_spec_merge` | `(delta_file: str, project_dir: str | None, dry_run: bool)` | Merge a spec-delta file into the main spec (QG-003). | `cli/commands/misc.py:506` |
| `cmd_spec_validate` | `(filepath: str)` | — | `cli/commands/misc.py:514` |
| `cmd_spec_diff` | `(old: str, new: str)` | — | `cli/commands/misc.py:533` |
| `cmd_spec_cp` | `(args)` | Dispatch `yuleosh spec cp <sub>` — Change Proposal management. | `cli/commands/misc.py:544` |
| `_cmd_spec_cp_auto` | `(project_dir: str, mock: bool)` | Auto-implement approved CPs by running the pipeline (non-intrusive). | `cli/commands/misc.py:627` |
| `_cmd_spec_cp_review` | `(project_dir: str)` | Standalone CP review via LLM (no pipeline session). | `cli/commands/misc.py:671` |
| `cmd_pipeline_run` | `(spec_path: str, mock: bool, from_step: int)` | — | `cli/commands/misc.py:704` |
| `cmd_pipeline_status` | `(name: str)` | — | `cli/commands/misc.py:711` |
| `cmd_review_auto` | `()` | — | `cli/commands/misc.py:717` |
| `cmd_review_task` | `(task: str, kind: str)` | — | `cli/commands/misc.py:723` |
| `cmd_demo_uart` | `(target_dir: str, do_build: bool, skip_cmake: bool)` | Create and run the STM32+ESP32 UART demo project. | `cli/commands/misc.py:741` |
| `cmd_ci_run` | `(layer: str)` | — | `cli/commands/misc.py:747` |
| `cmd_evidence_pack` | `()` | — | `cli/commands/misc.py:760` |
| `_cmd_coverage_c` | `(build_dir: str, src_dir: str)` | Run C/C++ coverage report via gcov/lcov (``yuleosh coverage c``). | `cli/commands/misc.py:765` |
| `cmd_audit_code_style` | `(project_dir: str, save: bool, block: bool, json_out: bool)` | Run SWC 软件编程规范 code-style scan (``yuleosh audit code-style``). | `cli/commands/misc.py:796` |
| `cmd_audit_sync_check` | `(project_dir: str, base_ref: str, save: bool)` | Run doc sync gate check (``yuleosh audit sync-check``). | `cli/commands/misc.py:828` |
| `_cmd_coverage_gate` | `(args)` | Run Python coverage gate (``yuleosh coverage gate --fail-under=50``). | `cli/commands/misc.py:844` |
| `_cmd_coverage_trend` | `(args)` | Show coverage trend (``yuleosh coverage trend``). | `cli/commands/misc.py:898` |
| `_collect_audit_log_verification` | `(project_dir: Path, out_path: Path)` | 安全可审计: verify the audit log hash chain and collect the proof. | `cli/commands/misc.py:911` |
| `cmd_audit_evidence` | `(output_dir: str | None, create_zip: bool)` | Generate CL2 audit evidence bundle. | `cli/commands/misc.py:963` |
| `cmd_kpi_status` | `(args)` | Show current KPI dashboard (violations, coverage, trend). | `cli/commands/misc.py:1261` |
| `cmd_kpi_baseline_save` | `(args)` | Save current state as KPI baseline. | `cli/commands/misc.py:1271` |
| `cmd_kpi_baseline_compare` | `(args)` | Compare current state against baseline. | `cli/commands/misc.py:1294` |
| `cmd_stats` | `(json_output: bool)` | — | `cli/commands/misc.py:1304` |
| `cmd_kpi_ci_alert` | `(args)` | Check KPI baseline thresholds and emit CI warnings (MP-16). | `cli/commands/misc.py:1312` |
| `cmd_audit_verify` | `(tenant: str, from_date: str, to_date: str, as_json: bool)` | Verify audit log hash-chain integrity (安全可审计, 2026-08-07). | `cli/commands/misc.py:1391` |
| `_osh_home` | `()` | Resolve OSH_HOME, honoring cli.main's live value (A5 compat). | `cli/commands/misra.py:28` |
| `cmd_misra_deviate` | `(args)` | Handle ``yuleosh misra deviate`` subcommands. | `cli/commands/misra.py:42` |
| `_parse_dev_id` | `(dev_id: str)` | Parse a dev_id string 'rule_id:file_pattern' into its components. | `cli/commands/misra.py:134` |
| `_cli_add_deviation` | `(project_dir: str, rule: str, file_pat: str, reason: str, approved_by: str, expires: str, status: str)` | Non-interactive CLI to add a new deviation to ci-config.yaml. | `cli/commands/misra.py:143` |
| `_interactive_add_deviation` | `(project_dir: str)` | Interactive prompt to add a new deviation to ci-config.yaml. | `cli/commands/misra.py:184` |
| `cmd_misra_trend` | `(args)` | Handle ``yuleosh misra trend`` — display or export trend data. | `cli/commands/misra.py:242` |
| `cmd_misra_profile_list` | `()` | List available MISRA profiles — both from ci-config.yaml and misra-rules.yaml. | `cli/commands/misra.py:259` |
| `cmd_misra_profile_set` | `(name: str)` | Switch active MISRA profile. | `cli/commands/misra.py:312` |
| `cmd_misra_report` | `(args)` | Handle ``yuleosh misra report`` — read latest report and output. | `cli/commands/misra.py:353` |
| `_print_misra_report_summary` | `(report: dict)` | Print a human-readable summary of the MISRA report. | `cli/commands/misra.py:388` |
| `_render_misra_report_html` | `(report: dict)` | Render MISRA report as a simple HTML page to stdout. | `cli/commands/misra.py:440` |
| `build_parser` | `(sub)` | Register the misra command group (A5). | `cli/commands/misra.py:529` |
| `_confidence_distribution` | `(store: KGStore)` | 从临时 store 回读各 C 实体类型的置信度分桶。 | `cli/commands/reverse.py:36` |
| `_build_report` | `(project_base: str, summary: dict, dist: dict)` | 组装报告 dict（扫描统计 + 实体计数 + 置信度分布）。 | `cli/commands/reverse.py:53` |
| `_render_text` | `(report: dict)` | 把报告 dict 渲染为人类可读文本。 | `cli/commands/reverse.py:99` |
| `cmd_reverse_scan` | `(args)` | ``yuleosh reverse scan <path>`` — 逆向扫描并输出报告。 | `cli/commands/reverse.py:151` |
| `build_parser` | `(sub)` | 向主解析器注册 ``reverse`` 命令组 (B1-11)。 | `cli/commands/reverse.py:203` |
| `_osh_home` | `()` | Resolve OSH_HOME, honoring cli.main's live value (A5 compat). | `cli/commands/review_diff.py:28` |
| `cmd_review_diff` | `(args)` | Diff two review results. | `cli/commands/review_diff.py:42` |
| `build_parser` | `(rsub)` | Register the review diff subcommand on the existing review parser (A5). | `cli/commands/review_diff.py:144` |
| `_osh_home` | `()` | Resolve OSH_HOME, honoring cli.main's live value (A5 compat). | `cli/commands/swe6.py:28` |
| `cmd_swe6_status` | `(args)` | Show SWE.6 qualification test status (三段式). | `cli/commands/swe6.py:42` |
| `cmd_swe6_check` | `(args)` | Run SWE.6 qualification test check. | `cli/commands/swe6.py:103` |
| `build_parser` | `(sub)` | Register the swe6 command group (A5). | `cli/commands/swe6.py:218` |
| `ensure_osh_home` | `()` | Ensure OSH_HOME directory exists | `cli/commands/template.py:12` |
| `cmd_template_list` | `()` | List available project templates | `cli/commands/template.py:16` |
| `cmd_ecu_template_list` | `()` | List available ECU templates | `cli/commands/template.py:31` |
| `_osh_home` | `()` | Resolve OSH_HOME, honoring cli.main's live value (A5 compat). | `cli/commands/traceability.py:31` |
| `cmd_traceability_report` | `(args)` | Generate full traceability report (Requirement ↔ Code ↔ Test ↔ Review). | `cli/commands/traceability.py:45` |
| `cmd_traceability_export` | `(args)` | Export traceability matrix in OEM-compatible format. | `cli/commands/traceability.py:99` |
| `cmd_traceability_matrix` | `(args)` | Generate LRM / LRT matrix as JSON and print formatted overview. | `cli/commands/traceability.py:132` |
| `_load_improvement_tickets` | `(project_dir: str)` | 扫描 ``improvement_tickets/*.yaml``，提取工单的需求关联。 | `cli/commands/traceability.py:234` |
| `_extract_requirement_ids` | `(text: str)` | 从文本中提取 REQ 风格需求 ID（去重、保序、大写归一）。 | `cli/commands/traceability.py:277` |
| `_extract_ticket_ids` | `(text: str)` | 从文本中提取 IMP- 风格工单 ID（去重、保序）。 | `cli/commands/traceability.py:284` |
| `_load_kb_lessons` | `(project_dir: str)` | 读取 KB lessons 并提取需求 / 工单关联（只读，不修改 kb）。 | `cli/commands/traceability.py:291` |
| `_build_closure_stats` | `(requirements: list[dict], tickets: list[dict], lessons: list[dict])` | 构建每需求（requirement_id）的工单 / lesson 关联统计。 | `cli/commands/traceability.py:366` |
| `_print_closure_section` | `(closure: dict)` | 打印「问题与知识闭环」统计表（与控制台整体风格一致）。 | `cli/commands/traceability.py:463` |
| `cmd_traceability_check` | `(args)` | Check traceability integrity; exit 1 when broken links / orphans exist. | `cli/commands/traceability.py:496` |
| `build_parser` | `(sub)` | Register the traceability command group (A5). | `cli/commands/traceability.py:562` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_CliCI` | `()` | CLI 用的最小 CI 记录器（适配 run_methodology_gate 的 ci.add_stage 接口）。 | `cli/commands/methodology.py:141` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_CliCI.__init__` | `(self)` | — | `cli/commands/methodology.py:144` |
| `_CliCI.add_stage` | `(self, name: str, status: str, msg: str)` | — | `cli/commands/methodology.py:147` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |
| `YULEASR_HOME` | _(见源码)_ |
| `YULEOSH_KB_DB` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.cli`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/_entry.py:6
directly from the yuleosh package (yuleosh.cli.main), which works in both

# src/yuleosh/__main__.py:11
from yuleosh.cli.main import main as cli_main

```

> 共 2 个文件引用本子系统；完整调用图见 `docs/modules/cli.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 3 处生产引用(Grep `yuleosh.cli` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/cli/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

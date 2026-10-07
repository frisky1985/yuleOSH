# 报表 (`report`) API 参考

> 代码根:`src/yuleosh/report/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`report` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/report.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `main` | `()` | CLI entry point for ``yuleosh audit-report``. | `report/audit_report.py:938` |
| `_load_json` | `(path: Path)` | Load a JSON file, returning None on failure. | `report/card_generator.py:30` |
| `_load_jsonl_latest` | `(path: Path)` | Load the last line of a JSONL file. | `report/card_generator.py:41` |
| `_format_delta` | `(current: float, previous: float, higher_is_better: bool)` | Format a delta with ▲/▼ emoji. | `report/card_generator.py:55` |
| `generate_quality_card` | `(project_dir: str, misra_report_path: Optional[Path], coverage_report_path: Optional[Path], selftest_report_path: Optional[Path])` | Generate a compact quality summary card in Markdown. | `report/card_generator.py:68` |
| `generate_feishu_card_json` | `(project_dir: str)` | Generate a Feishu interactive card (JSON) from the quality card. | `report/card_generator.py:250` |
| `_load_ci_results` | `(project_dir: str, layer: int)` | Load the most recent CI result JSON for a given layer. | `report/exporter.py:39` |
| `_load_misra_report` | `(project_dir: str)` | Load the latest MISRA report JSON if it exists. | `report/exporter.py:59` |
| `_load_coverage_report` | `(project_dir: str)` | Load the latest C coverage JSON if it exists. | `report/exporter.py:71` |
| `_serialize_layer_to_summary` | `(results: dict)` | Extract a short summary from a layer result dict. | `report/exporter.py:82` |
| `_collect_all_layers` | `(project_dir: str)` | Collect summaries from layers 1, 2, 2.5, 3. | `report/exporter.py:119` |
| `generate_json_report` | `(project_dir: str, layers_data: list[dict], misra: Optional[dict], coverage: Optional[dict], is_final: bool)` | Build the full JSON report dict. | `report/exporter.py:134` |
| `_status_emoji` | `(status: str)` | — | `report/exporter.py:172` |
| `generate_markdown_report` | `(project_dir: str, layers_data: list[dict], misra: Optional[dict], coverage: Optional[dict], is_final: bool)` | Generate a Markdown CI report. | `report/exporter.py:177` |
| `_write_excel_report` | `(layers_data: list[dict], output_path: Path)` | Write a formatted Excel report if openpyxl is available. | `report/exporter.py:283` |
| `generate_layer_report` | `(project_dir: str, layer: int)` | Generate report files for a single CI layer run. | `report/exporter.py:365` |
| `generate_final_report` | `(project_dir: str)` | Generate the final comprehensive CI report after run_all. | `report/exporter.py:406` |
| `_auto_feishu_notify` | `(project_dir: str)` | 如果环境变量 FEISHU_WEBHOOK_URL 已设置，自动推送质量卡片到飞书。 | `report/exporter.py:456` |
| `_post_json` | `(url: str, payload: dict, timeout: int)` | POST JSON 负载到指定 URL。 | `report/feishu_notifier.py:41` |
| `post_quality_card_to_feishu` | `(webhook_url: str, project_dir: str)` | 将质量摘要卡片推送到飞书 Webhook。 | `report/feishu_notifier.py:77` |
| `_resolve_webhook_url` | `(cli_url: Optional[str])` | 解析 Webhook URL：优先 CLI 参数，其次环境变量。 | `report/feishu_notifier.py:127` |
| `main` | `()` | — | `report/feishu_notifier.py:140` |
| `_load_jsonl` | `(path: Path)` | Load all entries from a JSONL file. Returns [] on failure. | `report/trend_exporter.py:59` |
| `_get_project_name` | `(project_dir: str)` | Derive a project name from the project directory basename. | `report/trend_exporter.py:78` |
| `_normalize_timestamp` | `(ts_str: str)` | Normalize various timestamp formats to ISO 8601 (YYYY-MM-DDTHH:MM:SS). | `report/trend_exporter.py:83` |
| `_safe_float` | `(val)` | Safely convert a value to float, returning 0.0 on failure. | `report/trend_exporter.py:98` |
| `_safe_int` | `(val)` | Safely convert a value to int, returning 0 on failure. | `report/trend_exporter.py:106` |
| `export_misra_trend` | `(project_dir: str, project_id: Optional[str], max_entries: int, project_name: Optional[str])` | 导出 MISRA 违规趋势 JSON。 | `report/trend_exporter.py:119` |
| `export_ut_trend` | `(project_dir: str, project_id: Optional[str], max_entries: int, project_name: Optional[str])` | 导出单元测试 / 覆盖率趋势 JSON。 | `report/trend_exporter.py:199` |
| `export_all_trends` | `(project_dir: str, project_id: Optional[str], max_entries: int)` | 导出 MISRA 和 UT 两个维度的完整趋势数据。 | `report/trend_exporter.py:299` |
| `export_trend_for_project` | `(project_dir: str, report_type: str, project_id: Optional[str], max_entries: int)` | 为指定项目导出趋势数据（基于文件目录隔离）。 | `report/trend_exporter.py:355` |
| `main` | `()` | CLI entry point for trend export. | `report/trend_exporter.py:396` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `EvidenceItem` | `()` | A single piece of evidence for a process dimension. | `report/audit_report.py:55` |
| `ProcessDimension` | `()` | ASPICE process dimension evaluation (evidence-coverage grading, P0-4). | `report/audit_report.py:75` |
| `AspiceReport` | `()` | Full ASPICE audit report. | `report/audit_report.py:91` |
| `EvidenceScanner` | `()` | Scans yuleOSH evidence artifacts and organizes by ASPICE dimension. | `report/audit_report.py:114` |
| `AuditReportGenerator` | `()` | Generates ASPICE-aligned audit reports from yuleOSH evidence data. | `report/audit_report.py:372` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `EvidenceItem.to_dict` | `(self)` | — | `report/audit_report.py:70` |
| `ProcessDimension.to_dict` | `(self)` | — | `report/audit_report.py:86` |
| `AspiceReport.to_dict` | `(self)` | — | `report/audit_report.py:105` |
| `EvidenceScanner.__init__` | `(self, evidence_dir: str)` | — | `report/audit_report.py:196` |
| `EvidenceScanner.scan_all` | `(self)` | Scan all evidence files and organize by ASPICE process. | `report/audit_report.py:200` |
| `AuditReportGenerator.__init__` | `(self, evidence_dir: str, requirements_file: str, tests_file: str)` | — | `report/audit_report.py:375` |
| `AuditReportGenerator.generate_aspice_report` | `(self, project_name: str, version: str)` | Generate a full ASPICE audit report. | `report/audit_report.py:386` |
| `AuditReportGenerator.export_json` | `(self, report: AspiceReport, output_path: str)` | Export the ASPICE report to JSON format. | `report/audit_report.py:656` |
| `AuditReportGenerator.export_html` | `(self, report: AspiceReport, output_path: str)` | Export the ASPICE report to a self-contained HTML file. | `report/audit_report.py:677` |
| `AuditReportGenerator.export_pdf` | `(self, report: AspiceReport, output_path: str)` | Export the ASPICE report to PDF. | `report/audit_report.py:843` |
| `AuditReportGenerator.export_text` | `(self, report: AspiceReport, output_path: str)` | Export the ASPICE report as plain text. | `report/audit_report.py:878` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `FEISHU_WEBHOOK_URL` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.report`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/ci/runner.py:324
from yuleosh.report.exporter import generate_final_report

# src/yuleosh/ci/layers/layer_executor.py:50
from yuleosh.report.exporter import generate_layer_report as _generate_layer_report

```

> 共 2 个文件引用本子系统；完整调用图见 `docs/modules/report.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 8 处生产引用(Grep `yuleosh.report` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/report/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

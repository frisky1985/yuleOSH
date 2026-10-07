# 应用生命周期管理 (`alm`) API 参考

> 代码根:`src/yuleosh/alm/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`alm` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/alm.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `register_adapter` | `(name: str, cls: type[AlmBackend])` | Register an ALM adapter class. | `alm/__init__.py:40` |
| `create_adapter` | `(kind: str, **conn_kw)` | Factory: create an ALM adapter by kind name. | `alm/__init__.py:45` |
| `list_available_adapters` | `()` | Return the list of registered ALM adapter names. | `alm/__init__.py:56` |
| `_is_table_separator` | `(line: str)` | Check if a line is a markdown table separator. | `alm/traceability.py:52` |
| `_is_shall_table_header` | `(col_names: list[str])` | Detect if a list of column names indicates a SHALL requirement table. | `alm/traceability.py:69` |
| `scan_req_annotations` | `(src_dir: Path)` | Scan source files for @req annotations linking code to requirements. | `alm/traceability.py:90` |
| `scan_test_code_links` | `(project_dir: Path)` | Scan test files for @tests annotations linking tests to source code. | `alm/traceability.py:140` |
| `_parse_req_trace_links` | `(project_dir: str)` | 解析 docs/*requirements*.md 的 "测试追溯" 字段 → 需求→测试链接。 | `alm/traceability.py:231` |
| `extract_shall_statements` | `(spec_path: str)` | Extract SHALL statements from a specification file (markdown). | `alm/traceability.py:279` |
| `extract_shall_from_text` | `(text: str)` | Extract SHALL statements from raw text (no file I/O). | `alm/traceability.py:431` |
| `scan_review_artifacts` | `(project_dir: str)` | Scan .yuleosh/sessions/ for code-review.json artifacts. | `alm/traceability.py:523` |
| `scan_test_reports` | `(project_dir: str)` | Scan .yuleosh/sessions/ for *test*.json reports. | `alm/traceability.py:608` |
| `scan_ci_results` | `(project_dir: str)` | Scan .osh/ci/ for layer result JSON files. | `alm/traceability.py:661` |
| `load_swr_mapping_table` | `(project_dir: str)` | Read ``docs/requirement-traceability-matrix.md`` (SWR mapping table). | `alm/traceability.py:719` |
| `generate_lrm` | `(project_dir: str, spec_path: Optional[str])` | Generate LRM (Lateral Requirements Matrix). | `alm/traceability.py:785` |
| `generate_lrt` | `(project_dir: str, spec_path: Optional[str])` | Generate LRT (Lateral Requirements Traceability). | `alm/traceability.py:1013` |
| `generate_traceability_report` | `(project_dir: str, spec_path: Optional[str], output_dir: Optional[str])` | Generate full traceability report with LRM + LRT + recommendations. | `alm/traceability.py:1071` |
| `_find_step_handlers_for_requirement` | `(project_dir: str, req_id: str, shall: dict)` | Find step handler reports that reference a given requirement. | `alm/traceability.py:1155` |
| `_scan_comments_for_requirements` | `(src_dir: Path, shalls: list[dict])` | Scan source files for comments referencing SHALL IDs. | `alm/traceability.py:1218` |
| `_extract_keywords` | `(statement: str, project_dir: str | None)` | Extract meaningful keywords from a SHALL statement. | `alm/traceability.py:1263` |
| `_find_code_by_keywords` | `(src_dir: Path, keywords: list[str])` | Find source files matching the given keywords. | `alm/traceability.py:1296` |
| `_find_code_by_keywords_for_id` | `(src_dir: Path, req_id: str)` | Find source files matching a req_id (RS-001, SWR-001.1, etc.). | `alm/traceability.py:1322` |
| `_find_reviews_for_requirement` | `(reviews: list[dict], req_id: str, statement: str)` | Find reviews referencing a specific requirement. | `alm/traceability.py:1347` |
| `_find_orphaned_tests` | `(test_reports: list[dict], requirements: list[dict])` | Find test files not associated with any requirement. | `alm/traceability.py:1367` |
| `_scan_test_pytest_files` | `(project_dir: str, req_id: str)` | Scan pytest files for test functions matching a requirement ID. | `alm/traceability.py:1382` |
| `_find_tests_for_requirement` | `(test_reports: list[dict], req_id: str, statement: str, project_dir: Optional[str])` | Find test reports and pytest files referencing a specific requirement. | `alm/traceability.py:1431` |
| `compute_trace_integrity` | `(project_dir: str, spec_path: Optional[str])` | Compute a tamper-evident traceability integrity summary. | `alm/traceability.py:1465` |
| `load_traceability_config` | `(project_dir: str | Path)` | Load traceability config from <project_dir>/.yuleosh/traceability.yaml. | `alm/traceability_config.py:77` |
| `_default_config` | `()` | — | `alm/traceability_config.py:167` |
| `get_stop_words` | `(project_dir: str | Path | None)` | Convenience: return effective stop_words for keyword extraction. | `alm/traceability_config.py:176` |
| `get_test_id_prefixes` | `(project_dir: str | Path | None)` | Convenience: return effective test_id_prefixes. | `alm/traceability_config.py:183` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `JiraAdapter` | `(AlmBackend)` | Atlassian Jira adapter (stub). | `alm/__init__.py:66` |
| `PolarionAdapter` | `(AlmBackend)` | Siemens Polarion WorkItem adapter (stub). | `alm/__init__.py:86` |
| `AlmTicket` | `()` | A ticket/issue in the ALM system. | `alm/base.py:31` |
| `AlmBackend` | `(ABC)` | Abstract base for ALM system backends. | `alm/base.py:64` |
| `JiraBackend` | `(AlmBackend)` | Jira ALM adapter with bidirectional evidence sync. | `alm/jira.py:55` |
| `PolarionBackend` | `(AlmBackend)` | Polarion ALM adapter with bidirectional evidence sync. | `alm/polarion.py:55` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `JiraAdapter.__init__` | `(self, url: str, api_token: str, **_)` | — | `alm/__init__.py:69` |
| `JiraAdapter.create_ticket` | `(self, ticket: AlmTicket)` | — | `alm/__init__.py:73` |
| `JiraAdapter.update_status` | `(self, ticket_id: str, status: str)` | — | `alm/__init__.py:77` |
| `JiraAdapter.find_by_label` | `(self, label: str)` | — | `alm/__init__.py:81` |
| `PolarionAdapter.__init__` | `(self, url: str, api_token: str, **_)` | — | `alm/__init__.py:89` |
| `PolarionAdapter.create_ticket` | `(self, ticket: AlmTicket)` | — | `alm/__init__.py:93` |
| `PolarionAdapter.update_status` | `(self, ticket_id: str, status: str)` | — | `alm/__init__.py:97` |
| `PolarionAdapter.find_by_label` | `(self, label: str)` | — | `alm/__init__.py:101` |
| `AlmBackend.create_ticket` | `(self, ticket: AlmTicket)` | Create a ticket in the ALM system. | `alm/base.py:72` |
| `AlmBackend.update_status` | `(self, ticket_id: str, status: str)` | Update the workflow status of an existing ticket. | `alm/base.py:89` |
| `AlmBackend.find_by_label` | `(self, label: str)` | Find tickets by label (e.g. ``'misra'``, ``'compliance'``). | `alm/base.py:107` |
| `JiraBackend.__init__` | `(self, url: str, api_token: str, project_key: str, **kwargs)` | — | `alm/jira.py:70` |
| `JiraBackend.create_ticket` | `(self, ticket: AlmTicket)` | Create a Jira issue. | `alm/jira.py:118` |
| `JiraBackend.update_status` | `(self, ticket_id: str, status: str)` | Transition a Jira issue to a new status. | `alm/jira.py:167` |
| `JiraBackend.find_by_label` | `(self, label: str)` | Search Jira issues by label (JQL). | `alm/jira.py:219` |
| `JiraBackend.sync_evidence_to_ticket` | `(self, ticket_id: str, evidence_data: dict, label: str)` | Sync evidence data to a Jira issue as a comment + attachment link. | `alm/jira.py:268` |
| `JiraBackend.sync_ticket_to_evidence` | `(self, ticket_id: str)` | Sync Jira issue changes back to evidence. | `alm/jira.py:341` |
| `JiraBackend.bulk_sync` | `(self, label: str)` | Bidirectional bulk sync: Jira ↔ yuleOSH evidence. | `alm/jira.py:406` |
| `PolarionBackend.__init__` | `(self, url: str, api_token: str, project_id: str, **kwargs)` | — | `alm/polarion.py:70` |
| `PolarionBackend.create_ticket` | `(self, ticket: AlmTicket)` | Create a Polarion WorkItem. | `alm/polarion.py:125` |
| `PolarionBackend.update_status` | `(self, ticket_id: str, status: str)` | Transition a Polarion WorkItem to a new status. | `alm/polarion.py:175` |
| `PolarionBackend.find_by_label` | `(self, label: str)` | Search Polarion WorkItems by label/tag. | `alm/polarion.py:223` |
| `PolarionBackend.sync_evidence_to_ticket` | `(self, ticket_id: str, evidence_data: dict, label: str)` | Sync evidence data to a Polarion WorkItem as a comment/linked document. | `alm/polarion.py:277` |
| `PolarionBackend.sync_ticket_to_evidence` | `(self, ticket_id: str)` | Sync Polarion WorkItem changes back to evidence. | `alm/polarion.py:339` |
| `PolarionBackend.bulk_sync` | `(self, label: str)` | Bidirectional bulk sync: Polarion ↔ yuleOSH evidence. | `alm/polarion.py:424` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |
| `YULEOSH_AUDIT_ROOT` | _(见源码)_ |
| `YULEOSH_JIRA_PROJECT` | _(见源码)_ |
| `YULEOSH_JIRA_TOKEN` | _(见源码)_ |
| `YULEOSH_JIRA_URL` | _(见源码)_ |
| `YULEOSH_POLARION_PROJECT` | _(见源码)_ |
| `YULEOSH_POLARION_TOKEN` | _(见源码)_ |
| `YULEOSH_POLARION_URL` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.alm`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/cli/commands/traceability.py:47
from yuleosh.alm.traceability import generate_traceability_report

# src/yuleosh/cli/commands/swe6.py:44
from yuleosh.alm.traceability import generate_lrt

# src/yuleosh/api/matrix.py:12
``yuleosh.alm.traceability.generate_lrt`` — this module reuses it and

```

> 共 3 个文件引用本子系统；完整调用图见 `docs/modules/alm.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 9 处生产引用(Grep `yuleosh.alm` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/alm/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

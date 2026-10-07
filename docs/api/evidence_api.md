# 证据管理 (`evidence`) API 参考

> 代码根:`src/yuleosh/evidence/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`evidence` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/evidence.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from .evidence import handle_evidence` |
| `"evidence": handle_evidence,` |
| `ev_dir = Path(OSH_HOME) / ".osh" / "evidence"` |
| `from yuleosh.evidence.collection import _validate_review_session_json` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `parse_scenario_refs` | `(text: str)` | Parse Scenario-Ref: markers from docstring or comment text. | `evidence/analysis.py:24` |
| `parse_module_covers` | `(tree: ast.AST)` | Parse module-level docstring Covers: marker. | `evidence/analysis.py:48` |
| `parse_comment_covers` | `(content: str)` | Parse # Covers: line comments (fallback when no module docstring). | `evidence/analysis.py:65` |
| `_strip_scenario_ref` | `(text: str)` | Remove Scenario-Ref segments from a Covers: line. | `evidence/analysis.py:80` |
| `parse_function_covers` | `(tree: ast.AST)` | Parse Covers: from each test function's docstring. | `evidence/analysis.py:85` |
| `infer_covers_from_function_names` | `(tree: ast.AST, stop_words: set[str] | None)` | Infer Covers keywords from test function names. | `evidence/analysis.py:103` |
| `parse_c_comment_covers` | `(content: str)` | Parse C-style Covers markers: ``// Covers:`` 行注释与 ``/* ... */`` 块注释. | `evidence/analysis.py:128` |
| `infer_covers_from_c_function_names` | `(content: str, stop_words: set[str] | None)` | Infer Covers keywords from C test function names. | `evidence/analysis.py:153` |
| `parse_covers_from_file` | `(test_path: str, stop_words: set[str] | None)` | Multi-layer Covers marker parser. | `evidence/analysis.py:181` |
| `categorize_uncovered` | `(uncovered: list[dict])` | Categorize uncovered SHALLs into critical (core logic) and warn (non-functional). | `evidence/analysis.py:223` |
| `aspice_gap_check` | `(project_dir: str, output_format: str, template_path: Optional[str], profile_name: str)` | Run ASPICE gap-oriented compliance check (A1-08: profile 驱动). | `evidence/aspice_check.py:137` |
| `_format_gap_markdown` | `(report: dict, project_dir: str)` | Format gap check as Markdown — what you're MISSING, not what you have. | `evidence/aspice_check.py:192` |
| `_add_cli_hints` | `(lines: list[str], bp_id: str)` | Add context-sensitive CLI hints for each BP. | `evidence/aspice_check.py:325` |
| `_format_gap_json` | `(report: dict)` | Format gap check as JSON. | `evidence/aspice_check.py:377` |
| `_sha256_file` | `(filepath: str)` | Compute SHA-256 of a file. | `evidence/check.py:64` |
| `_load_json_safe` | `(path: Path)` | Load and parse a JSON file, returning None on failure. | `evidence/check.py:77` |
| `check_files_present` | `(evidence_dir: str)` | Layer 1: All required files exist (audit-manifest.json + required entries). | `evidence/check.py:90` |
| `check_fields_complete` | `(evidence_dir: str)` | Layer 2: Every JSON file has valid, non-empty structure. | `evidence/check.py:122` |
| `check_values_reasonable` | `(evidence_dir: str)` | Layer 3: Numeric values (coverage, etc.) within reasonable bounds. | `evidence/check.py:145` |
| `check_timestamps_ordered` | `(evidence_dir: str)` | Layer 4: Pipeline step timestamps are monotonically increasing. | `evidence/check.py:190` |
| `check_cross_refs_resolved` | `(evidence_dir: str)` | Layer 5: Cross-references in traceability data resolve to known IDs. | `evidence/check.py:236` |
| `check_sha256_integrity` | `(evidence_dir: str)` | Layer 6: SHA-256 hashes for all manifest files verified. | `evidence/check.py:280` |
| `check_signature_valid` | `(evidence_dir: str)` | Layer 7: RSA-SHA256 digital signature (optional — always passes if absent). | `evidence/check.py:315` |
| `run_full_evidence_check` | `(evidence_dir: str, checks: Optional[List[Callable[[str], CheckItem]]])` | Run the complete multi-layer evidence check. | `evidence/check.py:377` |
| `format_check_result` | `(result: EvidenceCheckResult)` | Format EvidenceCheckResult as a human-readable string. | `evidence/check.py:449` |
| `cli_error_warning` | `()` | Print a friendly error if evidence_check is loaded incorrectly. | `evidence/check.py:482` |
| `_validate_session_json` | `(data: dict, source: str)` | Validate session JSON data against the SESSION_JSON_SCHEMA. | `evidence/collection.py:61` |
| `_validate_review_session_json` | `(data: dict, source: str)` | Validate review-session.json data against REVIEW_SESSION_JSON_SCHEMA. | `evidence/collection.py:70` |
| `_validate_json_schema` | `(data: dict, source: str, schema: dict, label: str)` | Generic JSON schema validator (no external jsonschema lib dependency). | `evidence/collection.py:85` |
| `_compute_sha256` | `(file_path: str)` | Compute SHA256 hex digest of a file. | `evidence/compliance.py:24` |
| `_build_manifest_entry` | `(file_path: Path, arcname: str)` | Build a manifest entry with path, SHA256, size, and timestamp. | `evidence/compliance.py:34` |
| `pack_compliance_zip` | `(collector: 'EvidenceCollector')` | Create compliance pack ZIP for ASPICE audit. | `evidence/compliance.py:46` |
| `_check_pipeline_not_running` | `(project_dir: str)` | Check that no pipeline is currently writing to avoid race conditions. | `evidence/compliance.py:118` |
| `generate_evidence` | `(project_dir: str, spec_path: str)` | Generate full evidence chain. | `evidence/compliance.py:160` |
| `main` | `()` | CLI entry point for evidence generation. | `evidence/compliance.py:242` |
| `_sha256_file` | `(filepath: str)` | Compute SHA-256 hash of a file. | `evidence/evidence_check.py:47` |
| `_ensure_dir` | `(path: Path)` | Create directory if it doesn't exist. | `evidence/evidence_check.py:60` |
| `pack_evidence_bundle` | `(project_dir: str, output_dir: Optional[str], components: Optional[list[str]])` | Generate a CL2 audit evidence bundle with integrity verification (§22.1~§22.9). | `evidence/evidence_check.py:70` |
| `check_evidence_integrity` | `(bundle_dir: str, subdirs: Optional[list[str]])` | Check evidence bundle integrity (§22.8). | `evidence/evidence_check.py:456` |
| `main` | `()` | CLI entry point for evidence pack/check. | `evidence/evidence_check.py:653` |
| `_make_hyperlink` | `(target: str, display: Optional[str])` | Create a hyperlink formula string for Excel. | `evidence/excel_writer.py:70` |
| `_apply_header_style` | `(ws, row: int, max_col: int)` | Apply standard header styling to a row. | `evidence/excel_writer.py:81` |
| `_apply_body_style` | `(ws, row: int, max_col: int, font: Font)` | Apply standard body styling to a row. | `evidence/excel_writer.py:91` |
| `_auto_column_width` | `(ws, max_col: int, max_width: int)` | Auto-adjust column widths based on content. | `evidence/excel_writer.py:103` |
| `_to_absolute_path` | `(file_path: str)` | Convert a relative file path to an absolute file:// URI. | `evidence/excel_writer.py:117` |
| `_severity_fill` | `(misra_sev: str)` | Return the appropriate row fill for a MISRA severity category. | `evidence/excel_writer.py:126` |
| `_status_fill` | `(status: str)` | Return the appropriate row fill for a test status. | `evidence/excel_writer.py:138` |
| `_coverage_fill` | `(rate: float)` | Return fill based on coverage rate thresholds. | `evidence/excel_writer.py:150` |
| `_sha256_file` | `(filepath: str)` | Compute SHA-256 hex digest for a file. | `evidence/manifest.py:118` |
| `_detect_content_type` | `(path: str)` | Guess content type from file extension. | `evidence/manifest.py:131` |
| `_describe_file` | `(rel_path: str)` | Generate a human-readable file description based on path. | `evidence/manifest.py:137` |
| `_walk_evidence_files` | `(evidence_root: str)` | Recursively walk evidence directory and return file entries. | `evidence/manifest.py:164` |
| `_check_cross_references` | `(files: List[ManifestFileEntry])` | Validate that all cross-references resolve to file paths. | `evidence/manifest.py:188` |
| `_check_coverage_reasonableness` | `(files: List[ManifestFileEntry])` | Check coverage data for reasonableness. | `evidence/manifest.py:201` |
| `generate_audit_manifest` | `(evidence_dir: str, build_id: str, evidence_pack_version: str)` | Scan evidence_dir and produce a complete AuditManifest. | `evidence/manifest.py:231` |
| `manifest_to_dict` | `(manifest: AuditManifest)` | Convert AuditManifest to a JSON-serializable dict. | `evidence/manifest.py:289` |
| `save_manifest` | `(manifest: AuditManifest, output_path: str)` | Write manifest to a JSON file (with signing placeholder). | `evidence/manifest.py:309` |
| `load_manifest` | `(manifest_path: str)` | Load a manifest from a JSON file. | `evidence/manifest.py:334` |
| `get_template` | `(template_name: str)` | Look up an OEM template by name. Falls back to 'generic' on unknown names. | `evidence/oem_templates.py:308` |
| `register_oem_template` | `(name: str, template: dict)` | 在运行时注册一个 OEM / 标准追溯矩阵模板（A1-08 注册表接口）。 | `evidence/oem_templates.py:316` |
| `list_oem_templates` | `()` | 返回所有已注册模板名（含内建与运行时注册）。 | `evidence/oem_templates.py:342` |
| `_build_trace_rows` | `(store, filter_layer: Optional[str], include_test_evidence: bool)` | Build internal trace rows from the KG store. | `evidence/oem_templates.py:352` |
| `_map_and_sort_rows` | `(rows: list[_TraceRow], template: dict)` | Map internal row fields to OEM column names, then sort. | `evidence/oem_templates.py:557` |
| `_format_markdown` | `(mapped_rows: list[dict], template: dict)` | Format mapped rows as a markdown table. | `evidence/oem_templates.py:589` |
| `_format_csv` | `(mapped_rows: list[dict], template: dict)` | Format mapped rows as CSV. | `evidence/oem_templates.py:626` |
| `_format_json` | `(mapped_rows: list[dict], template: dict)` | Format mapped rows as JSON. | `evidence/oem_templates.py:639` |
| `export_traceability_matrix` | `(store, template: str, output_format: str, filter_layer: Optional[str], include_test_evidence: bool)` | Export traceability matrix in OEM-compatible format. | `evidence/oem_templates.py:670` |
| `generate_evidence` | `(project_dir: str, spec_path: str)` | Generate full evidence chain. | `evidence/pack.py:37` |
| `main` | `()` | CLI entry point for evidence generation. | `evidence/pack.py:83` |
| `format_maturity_label` | `(score: int)` | Convert a maturity score (0-100) into a human-readable label. | `evidence/report.py:13` |
| `format_status_icon` | `(status: str)` | Return a status icon for the given status string. | `evidence/report.py:26` |
| `format_coverage_summary` | `(total: int, covered: int)` | Format a coverage percentage summary line. | `evidence/report.py:34` |
| `make_table_row` | `(*cells, sep: str)` | Join cells into a Markdown table row. | `evidence/report.py:40` |
| `make_header_row` | `(*cells)` | Create a Markdown table header. | `evidence/report.py:45` |
| `make_acceptance_row` | `(req_id: str, name: str, shall: str, verification: str, test_str: str, mode: str, confidence: str, status: str)` | Build a single row of the acceptance matrix table. | `evidence/report.py:52` |
| `make_coverage_table_row` | `(metric: str, value: str, threshold: str, status: str)` | Build a code-coverage table row. | `evidence/report.py:60` |
| `dedent` | `(text: str)` | Remove common leading whitespace from a multi-line string. | `evidence/report.py:66` |
| `generate_timestamp` | `()` | Return an ISO-8601 timestamp string. | `evidence/report.py:79` |
| `generate_keypair` | `(key_size: int)` | Generate an RSA key pair. | `evidence/signer.py:60` |
| `save_keys` | `(private_key: object, public_key: object, private_path: str, public_path: str, password: Optional[bytes])` | Serialize and save key pair to PEM files. | `evidence/signer.py:84` |
| `load_private_key` | `(path: str, password: Optional[bytes])` | Load an RSA private key from a PEM file. | `evidence/signer.py:144` |
| `load_public_key` | `(path: str)` | Load an RSA public key from a PEM file. | `evidence/signer.py:161` |
| `sign_manifest` | `(manifest_json: str, private_key: object)` | Sign a manifest JSON string and return base64-encoded signature. | `evidence/signer.py:182` |
| `verify_manifest` | `(manifest_json: str, signature_b64: str, public_key: object)` | Verify an RSA-SHA256 signature of a manifest JSON string. | `evidence/signer.py:206` |
| `sign_manifest_file` | `(manifest_path: str, private_key_path: str)` | Load, sign, and save signature into an existing manifest JSON file. | `evidence/signer.py:241` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `CheckItem` | `()` | Result of a single evidence check layer. | `evidence/check.py:40` |
| `EvidenceCheckResult` | `()` | Complete multi-layer evidence check result. | `evidence/check.py:49` |
| `DataCollectionMixin` | `()` | Mixin adding data-collection methods to EvidenceCollector. | `evidence/collection.py:125` |
| `ExcelReportWriter` | `()` | Generate structured .xlsx reports for MISRA C compliance and self-test results. | `evidence/excel_writer.py:166` |
| `EvidenceCollector` | `(DataCollectionMixin, ReportBuilderMixin)` | Collects and organizes evidence for ASPICE compliance. | `evidence/generator.py:39` |
| `ManifestFileEntry` | `()` | A single file recorded in the audit manifest. | `evidence/manifest.py:43` |
| `AuditManifest` | `()` | Top-level evidence-pack manifest. | `evidence/manifest.py:56` |
| `_TraceRow` | `()` | One row in the traceability matrix, before OEM column mapping. | `evidence/oem_templates.py:43` |
| `ReportBuilderMixin` | `()` | Mixin adding report-generation methods to EvidenceCollector. | `evidence/report_builder.py:22` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `DataCollectionMixin.collect_requirements` | `(self, spec_path: str)` | Collect requirements from ALL spec files. | `evidence/collection.py:128` |
| `DataCollectionMixin.collect_reviews` | `(self)` | Collect review records from .osh/reviews/. | `evidence/collection.py:299` |
| `DataCollectionMixin.collect_ci_results` | `(self)` | Collect CI layer results from .osh/ci/. | `evidence/collection.py:339` |
| `DataCollectionMixin.collect_sil_reports` | `(self)` | Collect SIL test reports from .osh/ci/. | `evidence/collection.py:355` |
| `DataCollectionMixin.collect_session_data` | `(self)` | Collect pipeline session data from .osh/sessions/. | `evidence/collection.py:381` |
| `ExcelReportWriter.__init__` | `(self, output_dir: Path)` | — | `evidence/excel_writer.py:175` |
| `ExcelReportWriter.write_misra_report` | `(self, violations: list[dict], groups: dict, summary: dict, rule_defs: dict, deviations: Optional[list], output_path: Optional[Path])` | Generate MISRA C compliance report Excel with 4 sheets. | `evidence/excel_writer.py:183` |
| `ExcelReportWriter.write_selftest_report` | `(self, review: dict, output_path: Optional[Path])` | Generate self-test report Excel with 4 sheets. | `evidence/excel_writer.py:451` |
| `EvidenceCollector.__init__` | `(self, project_dir: str, version: str)` | — | `evidence/generator.py:46` |
| `ReportBuilderMixin.generate_traceability_matrix` | `(self)` | Generate a markdown traceability matrix + JSON export. | `evidence/report_builder.py:25` |
| `ReportBuilderMixin.generate_requirement_coverage` | `(self)` | Generate a markdown requirements coverage report. | `evidence/report_builder.py:149` |
| `ReportBuilderMixin.generate_code_coverage_report` | `(self)` | Generate a markdown code coverage report. | `evidence/report_builder.py:191` |
| `ReportBuilderMixin.aggregate_review_logs` | `(self)` | Aggregate review logs into a markdown summary + JSON export. | `evidence/report_builder.py:210` |
| `ReportBuilderMixin.generate_acceptance_matrix` | `(self)` | Generate a markdown acceptance matrix. | `evidence/report_builder.py:303` |
| `ReportBuilderMixin.pack_compliance_zip` | `(self)` | Delegate compliance ZIP packing to the compliance module. | `evidence/report_builder.py:364` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `BUILD_ID` | _(见源码)_ |
| `GIT_BRANCH` | _(见源码)_ |
| `GIT_COMMIT` | _(见源码)_ |
| `OSH_HOME` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.evidence`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/ui/routes/api_routes.py:100
from yuleosh.evidence.collection import _validate_review_session_json

# src/yuleosh/pipeline/step_handlers/review_selftest/core.py:1460
from yuleosh.evidence.excel_writer import ExcelReportWriter

# src/yuleosh/ci/misra_report/cli.py:134
from yuleosh.evidence.excel_writer import ExcelReportWriter

# src/yuleosh/cli/onboard.py:382
from yuleosh.evidence.pack import generate_evidence

# src/yuleosh/cli/commands/misc.py:761
from yuleosh.evidence.pack import generate_evidence

# src/yuleosh/cli/commands/gap.py:51
from yuleosh.evidence.aspice_check import aspice_gap_check  # 延迟 import 便于测试 mock

# src/yuleosh/cli/commands/traceability.py:101
from yuleosh.evidence.oem_templates import export_traceability_matrix

# src/yuleosh/cli/main.py:710
from yuleosh.evidence.aspice_check import aspice_gap_check

# src/yuleosh/api/demo_wow.py:546
from yuleosh.evidence.generator import EvidenceCollector

# src/yuleosh/api/demo_quick.py:174
from yuleosh.evidence.generator import EvidenceCollector

# src/yuleosh/api/dashboard.py:1072
from .evidence import snapshot_bundle

# src/yuleosh/api/router.py:28
from .evidence import handle_evidence

```

> 共 12 个文件引用本子系统；完整调用图见 `docs/modules/evidence.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 19 处生产引用(Grep `yuleosh.evidence` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/evidence/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

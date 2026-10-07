# 规格 (`spec`) API 参考

> 代码根:`src/yuleosh/spec/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`spec` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/spec.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from .spec import handle_spec` |
| `"spec": handle_spec,` |
| `"spec": str(spec),` |
| `"spec": str(spec_md) if spec_md.exists() else "",` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_parse_frontmatter` | `(text: str)` | Parse YAML-ish frontmatter block. Returns (meta, body). | `spec/changes.py:114` |
| `find_changes_dir` | `(project_dir: str | Path)` | Locate the .osh/changes directory (created on demand). | `spec/changes.py:133` |
| `list_changes` | `(project_dir: str | Path)` | Return all change proposals sorted by change_id. | `spec/changes.py:139` |
| `load_proposal` | `(project_dir: str | Path, change_id: str)` | Load a single change proposal, or None if missing/invalid id. | `spec/changes.py:154` |
| `_parse_tasks` | `(text: str)` | Parse tasks.md into a list of task descriptions. | `spec/changes.py:179` |
| `validate_proposal` | `(project_dir: str | Path, change_id: str)` | Validate a change proposal's structure. Returns {valid, errors, warnings}. | `spec/changes.py:189` |
| `_read_proposal_body` | `(cp: ChangeProposal)` | — | `spec/changes.py:214` |
| `propose_change` | `(project_dir: str | Path, change_id: str, title: str, affects: str, created: Optional[str])` | Create a new change proposal directory with template files. | `spec/changes.py:220` |
| `set_status` | `(project_dir: str | Path, change_id: str, new_status: str)` | Advance a CP's status along the state machine. | `spec/changes.py:244` |
| `mark_implemented` | `(project_dir: str | Path, change_id: str, pipeline_run_id: str)` | Mark a CP implemented with pipeline-run evidence (fail-closed archive). | `spec/changes.py:261` |
| `_update_frontmatter_status` | `(cp: ChangeProposal, new_status: str)` | — | `spec/changes.py:315` |
| `archive_change` | `(project_dir: str | Path, change_id: str)` | Archive an implemented CP to changes/archive/<date>-<id>/. | `spec/changes.py:321` |
| `get_blocking_cps` | `(project_dir: str | Path)` | Return approved-but-not-implemented CPs (gate consumers). | `spec/changes.py:352` |
| `main` | `()` | — | `spec/diff.py:15` |
| `_print_human` | `(delta: dict)` | — | `spec/diff.py:35` |
| `parse_delta_file` | `(delta_path: str)` | Parse a spec-delta markdown file. | `spec/merge.py:70` |
| `detect_conflicts` | `(delta: DeltaParseResult, spec_text: str)` | Detect conflicts between delta statements and existing spec. | `spec/merge.py:228` |
| `_extract_shalls` | `(spec_text: str)` | Extract all normalized SHALL/SHOULD/MAY texts from spec. | `spec/merge.py:282` |
| `_normalize_shall_text` | `(text: str)` | Normalize a SHALL statement for comparison. | `spec/merge.py:294` |
| `_check_negation` | `(norm_text: str, existing_shalls: list[str])` | Check if a statement contradicts existing statements. | `spec/merge.py:305` |
| `merge_delta` | `(delta_path: str, project_dir: Optional[str], dry_run: bool)` | Merge a spec-delta file into the main spec. | `spec/merge.py:338` |
| `_build_merged_spec` | `(spec_text: str, delta: DeltaParseResult, new_version: str)` | Build the merged spec text by incorporating delta statements. | `spec/merge.py:525` |
| `_generate_diff_text` | `(delta: DeltaParseResult, new_version: str, old_version: str)` | Generate a human-readable diff summary. | `spec/merge.py:597` |
| `validate_delta_format` | `(delta_path: str)` | Validate that a spec-delta file has the correct format. | `spec/merge.py:629` |
| `cmd_spec_merge` | `(delta_path: str, project_dir: Optional[str], dry_run: bool)` | CLI handler for ``yuleosh spec merge``. | `spec/merge.py:679` |
| `detect_pattern` | `(req: 'SpecRequirement')` | Return the best matching pattern key for *req*, or None. | `spec/patterns.py:130` |
| `_norm_time_ms` | `(value: float, unit: str)` | — | `spec/patterns.py:148` |
| `check_conflicts` | `(doc: 'SpecDocument')` | Detect conflicts in *doc*. | `spec/patterns.py:157` |
| `suggest_missing_patterns` | `(doc: 'SpecDocument')` | Return suggestions for requirements that match a pattern but are missing key SHALLs. | `spec/patterns.py:257` |
| `validate_spec_with_patterns` | `(doc: 'SpecDocument')` | Full validation: issues + conflict checks + pattern suggestions. | `spec/patterns.py:287` |
| `_parse_id` | `(req_id: str)` | Parse a requirement ID into (prefix, major, minor). | `spec/validate.py:120` |
| `_id_to_level` | `(req_id: str)` | Derive level from ID prefix. | `spec/validate.py:134` |
| `_id_to_parent` | `(req_id: str)` | Derive parent ID. SWR-001.1 parent = RS-001. | `spec/validate.py:142` |
| `validate_status_transition` | `(old_status: str, new_status: str)` | Check if a status transition is valid. | `spec/validate.py:159` |
| `_detect_status_from_lines` | `(lines: list[str], start_idx: int)` | Scan lines around start_idx for a status marker. | `spec/validate.py:174` |
| `_is_table_separator` | `(line: str)` | Check if a line is a markdown table separator. | `spec/validate.py:196` |
| `_is_shall_table_header` | `(col_names: list[str])` | Detect table header for SHALL requirement tables. | `spec/validate.py:213` |
| `parse_spec` | `(filepath: str)` | Parse an OpenSpec markdown file into structured data. | `spec/validate.py:229` |
| `validate_spec` | `(doc: SpecDocument)` | Validate spec completeness. Returns list of issues. | `spec/validate.py:470` |
| `diff_specs` | `(old_path: str, new_path: str)` | Diff two OpenSpec files, producing delta with impact analysis. | `spec/validate.py:544` |
| `_compute_impact_analysis` | `(old_doc: SpecDocument, new_doc: SpecDocument, added: list[str], removed: list[str], modified: list[dict])` | Compute impact analysis based on spec changes. | `spec/validate.py:605` |
| `find_spec_files` | `(spec_dir: str)` | Find OpenSpec spec files under a directory. | `spec/validate.py:704` |
| `aggregate_docs` | `(spec_paths: list[str])` | Parse multiple spec files into a single aggregated SpecDocument. | `spec/validate.py:733` |
| `validate_spec_dir` | `(spec_dir: str)` | Validate all OpenSpec spec files under a directory. | `spec/validate.py:772` |
| `_compute_coverage` | `(doc: SpecDocument)` | Compute spec coverage score. | `spec/validate.py:838` |
| `main` | `()` | — | `spec/validate.py:870` |
| `_print_human` | `(result: dict)` | — | `spec/validate.py:921` |
| `parse_version` | `(version_str: str)` | Parse a semver string into (major, minor, patch). | `spec/version.py:87` |
| `compare_versions` | `(a: str, b: str)` | Compare two version strings. | `spec/version.py:102` |
| `increment_version` | `(current: str, part: str, delta_version: Optional[str])` | Increment a semantic version. | `spec/version.py:119` |
| `_auto_bump` | `(current: str, part: str)` | Auto-bump the version by incrementing the specified part. | `spec/version.py:153` |
| `read_spec_version` | `(project_dir: Optional[str], version_file: Optional[str])` | Read spec version from ``.yuleosh/spec-version.json``. | `spec/version.py:175` |
| `_parse_version_from_spec_header` | `(spec_path: str)` | Extract version from the spec.md header line. | `spec/version.py:220` |
| `write_spec_version` | `(sv: SpecVersion, project_dir: Optional[str], version_file: Optional[str])` | Write spec version to ``.yuleosh/spec-version.json``. | `spec/version.py:238` |
| `detect_spec_path` | `(project_dir: str)` | Detect the main spec file path. | `spec/version.py:270` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `ChangeProposal` | `()` | A single change proposal loaded from disk. | `spec/changes.py:83` |
| `DeltaStatement` | `()` | A single statement from a spec-delta file. | `spec/merge.py:50` |
| `DeltaParseResult` | `()` | Result of parsing a spec-delta file. | `spec/merge.py:61` |
| `Conflict` | `()` | A conflict between a delta statement and existing spec. | `spec/merge.py:219` |
| `SpecRequirement` | `()` | — | `spec/validate.py:44` |
| `SpecScenario` | `()` | — | `spec/validate.py:84` |
| `SpecDocument` | `()` | — | `spec/validate.py:100` |
| `SpecVersion` | `()` | Spec version information. | `spec/version.py:39` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `ChangeProposal.proposal_path` | `(self)` | — | `spec/changes.py:96` |
| `ChangeProposal.tasks_path` | `(self)` | — | `spec/changes.py:100` |
| `ChangeProposal.is_blocking` | `(self)` | True when an approved change has not been implemented yet. | `spec/changes.py:104` |
| `ChangeProposal.has_implementation_evidence` | `(self)` | True when a pipeline run id is recorded as implementation evidence. | `spec/changes.py:109` |
| `SpecRequirement.__init__` | `(self, name: str, shall: list[str], should: list[str], may: list[str], reason: str, req_id: str, level: str, parent: str, status: str)` | — | `spec/validate.py:45` |
| `SpecRequirement.to_dict` | `(self)` | — | `spec/validate.py:67` |
| `SpecScenario.__init__` | `(self, name: str, given: list[str], when: list[str], then: list[str])` | — | `spec/validate.py:85` |
| `SpecScenario.to_dict` | `(self)` | — | `spec/validate.py:91` |
| `SpecDocument.__init__` | `(self, path: str)` | — | `spec/validate.py:101` |
| `SpecDocument.to_dict` | `(self)` | — | `spec/validate.py:106` |
| `SpecVersion.to_dict` | `(self)` | — | `spec/version.py:62` |
| `SpecVersion.from_dict` | `(cls, data: dict)` | — | `spec/version.py:72` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.spec import <公共符号>
# 详见 docs/modules/spec.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 10 处生产引用(Grep `yuleosh.spec` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/spec/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

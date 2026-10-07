# 预览 (`preview`) API 参考

> 代码根:`src/yuleosh/preview/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`preview` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/preview.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `"preview": ("yuleosh.api.preview", "handle_preview"),` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `analyze_directory` | `(source_dir: Union[str, Path])` | Analyze a source code directory and produce analysis data. | `preview/analyzer.py:51` |
| `_discover_files` | `(source_dir: Path)` | Discover and categorize all files in source directory. | `preview/code_parser.py:22` |
| `_scan_frameworks` | `(source_dir: Path)` | Detect embedded frameworks from source content/signatures. | `preview/code_parser.py:57` |
| `_find_matching_files` | `(source_dir: Path, pattern: str)` | Find files whose content matches the given regex pattern. | `preview/code_parser.py:125` |
| `_measure_complexity` | `(source_dir: Path)` | Measure code complexity metrics. | `preview/code_parser.py:144` |
| `_measure_max_nesting` | `(source_dir: Path)` | Measure maximum nesting depth of control structures in .c files. | `preview/code_parser.py:196` |
| `_measure_per_file_complexity` | `(source_dir: Path)` | Measure per-file complexity metrics for top-level source files. | `preview/code_parser.py:217` |
| `_detect_test_framework` | `(source_dir: Path)` | Detect which test framework is used. | `preview/code_parser.py:280` |
| `_scan_risks` | `(source_dir: Path, complexity: dict)` | Scan for compliance risk factors (PREVIEW-REQ-004.2). | `preview/compliance_analyzer.py:15` |
| `_recommend_template` | `(frameworks: list, complexity: dict, risks: list)` | Recommend a pipeline template based on analysis (PREVIEW-REQ-004.3). | `preview/config_recommender.py:11` |
| `_predict_coverage` | `(test_density: float, test_framework: str, complexity_score: float)` | Predict current and projected coverage (PREVIEW-REQ-004.1). | `preview/coverage_predictor.py:11` |
| `build_assessment_report` | `(analysis: dict)` | Build a complete assessment report from raw analysis data. | `preview/reporter.py:24` |
| `_build_project_summary` | `(analysis: dict)` | Build project summary section with enhanced metrics. | `preview/reporter.py:46` |
| `_build_coverage_prediction` | `(analysis: dict)` | Build coverage prediction section (PREVIEW-REQ-004.1). | `preview/reporter.py:76` |
| `_build_compliance_risks` | `(analysis: dict)` | Build compliance risks section (PREVIEW-REQ-004.2). | `preview/reporter.py:88` |
| `_build_recommended_pipeline` | `(analysis: dict)` | Build recommended pipeline section (PREVIEW-REQ-004.3). | `preview/reporter.py:93` |
| `_count_total_lines` | `(files: list[Path])` | — | `preview/score_engine.py:23` |
| `_count_by_extension` | `(files: list[Path])` | — | `preview/score_engine.py:33` |
| `_extract_lines` | `(files: list[Path])` | — | `preview/score_engine.py:41` |
| `_detect_languages` | `(all_files: list[Path], source_dir: Path)` | Detect programming language distribution in the project. | `preview/score_engine.py:52` |
| `_assess_documentation` | `(source_dir: Path)` | Assess documentation quality (README, docstrings, code comments). | `preview/score_engine.py:80` |
| `_estimate_effort` | `(all_files: list[Path], frameworks: list[dict], complexity: dict)` | Estimate person-hours based on code volume and complexity. | `preview/score_engine.py:149` |
| `_compute_maturity` | `(test_framework: str, test_density: float, test_file_count: int, complexity: dict, doc_quality: dict, frameworks: list[dict], coverage: dict)` | Compute overall project maturity rating (0-100). | `preview/score_engine.py:186` |

### 3.2 公共类

_(无顶层类)_

### 3.3 类关键公共方法(节选)

_(无)_

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.preview import <公共符号>
# 详见 docs/modules/preview.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 4 处生产引用(Grep `yuleosh.preview` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/preview/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

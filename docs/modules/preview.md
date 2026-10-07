# 模块设计速写：preview（AI Preview 评估服务）

> 包：`src/yuleosh/preview/` ｜ 规模：8 .py ≈ 1132 行
> 定位：已投产、路由驱动、纯静态分析

## 职责
纯静态代码分析与评估报告（"AI Preview Assessment"），用于项目接入流水线前的代码可采纳性评估。**无 LLM 调用、无硬件执行**。证据：`preview/__init__.py:1-9`、`api/preview.py:17`（"Analysis is purely static (no LLM calls, no hardware execution)"）。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `preview/analyzer.py` (143) | 目录分析入口 | `analyze_directory` `:51`；`LANGUAGE_MAP` `:43`；`SUPPORTED_EXTENSIONS` `:33` |
| `preview/code_parser.py` (300) | 文件发现 + 度量 | `SUPPORTED_EXTENSIONS` `:17`；`_discover_files` `:22`；`_measure_complexity` `:144`；`_measure_max_nesting` `:196`；`_detect_test_framework` `:280` |
| `preview/coverage_predictor.py` (69) | 覆盖率预测 | `_predict_coverage` `:11` |
| `preview/compliance_analyzer.py` (167) | 合规风险扫描 | `_scan_risks` `:15` |
| `preview/config_recommender.py` (89) | 模板推荐 | `_recommend_template` `:11` |
| `preview/score_engine.py` (245) | 评分 / 估算 | `_count_total_lines` `:23`；`_assess_documentation` `:80`；`_estimate_effort` `:149`；`_compute_maturity` `:186` |
| `preview/reporter.py` (101) | 报告装配 | `build_assessment_report` `:24` |

## 公共 API / 入口点
- `analyze_directory(source_dir)`（`analyzer.py:51`）
- `build_assessment_report(analysis)`（`reporter.py:24`）
- `SUPPORTED_EXTENSIONS`（`code_parser.py:17`）、`LANGUAGE_MAP`（`analyzer.py:43`）

## 生产接线（真实调用方）
- **唯一生产调用方** `api/preview.py:206-207` 在 `_run_analysis()` 内调 `analyze_directory` + `build_assessment_report`。仓库内 `grep yuleosh.preview` 仅此 + 包内互相导入 + tests。
- 路由注册：`api/router.py:46` `"preview": ("yuleosh.api.preview","handle_preview")`；`handle_preview()`（`api/preview.py:605`）覆盖 `POST/GET/DELETE /api/v1/preview/assess*`。

## 运行时触发方式
- 后台线程：`_analyze_in_background`（`api/preview.py:214`）→ `_run_analysis`（`:201`）。支持 ZIP 上传 + git URL 两种输入（`:253`、`:338`）。

## 环境变量 / 配置
- **包内不读环境变量**。配置为 `api/preview.py` 硬编码常量：`MAX_ZIP_SIZE` `:92`、`MAX_CLONED_SIZE` `:93`、`CLONE_TIMEOUT` `:94`、`RESULT_TTL` `:96`、zip-bomb 限制 `:102-104`、限流 `:446-449`。
- 注意 `api/preview.py:95` `ANALYSIS_TIMEOUT=300` 疑似未被引用（死常量，待确认）。

## 偏差 / 待注意（设计文档必记）
- `preview/__init__.py` 把多个 `_` 私有辅助（`_predict_coverage`/`_scan_risks` 等）当公共导出，API 面略宽。
- 纯静态、无 LLM——与命名 "AI Preview" 略有反差（评估算法非 LLM 驱动）。

## 规模
8 .py ≈ 1132 行。

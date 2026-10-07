# 架构评审 (`review`) API 参考

> 代码根:`src/yuleosh/review/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`review` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/review.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from .review import handle_review` |
| `"review": handle_review,` |
| `KANBAN_STATUS_EN = ["requirement", "development", "review", "testing", "release"]` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_get_llm_client` | `()` | Lazy-load the LLM client, supporting both relative and direct imports. | `review/c_review.py:33` |
| `_llm_review_snippet` | `(code: str, max_retries: int)` | Use LLM to review a code snippet for embedded C issues. | `review/c_review.py:135` |
| `_check_content` | `(content: str, filepath: str, rel_path: str)` | Run all static analysis checks on C source content. | `review/c_review.py:176` |
| `review_embedded_c` | `(task_name: str, project_dir: str, changed_files: list[str])` | Review embedded C source files for common firmware defects. | `review/c_review.py:376` |
| `_get_llm_client` | `()` | Lazy-load the LLM client, supporting both relative and direct imports. | `review/resource_predictor.py:25` |
| `_detect_platform` | `(content: str)` | Detect target platform from C source content. | `review/resource_predictor.py:96` |
| `_count_global_ram` | `(content: str)` | Estimate RAM usage from global/static variables (BSS + data). | `review/resource_predictor.py:113` |
| `_count_rom_estimate` | `(content: str)` | Estimate ROM (code section) usage. | `review/resource_predictor.py:151` |
| `_assess_stack_risk` | `(content: str)` | Assess stack overflow risk: low/medium/high. | `review/resource_predictor.py:183` |
| `_estimate_isr_latency` | `(content: str, platform: str)` | Estimate worst-case ISR latency in microseconds. | `review/resource_predictor.py:241` |
| `_llm_predict_resources` | `(content: str)` | Use LLM to generate resource predictions. | `review/resource_predictor.py:284` |
| `predict_resources` | `(file_path: str)` | AI resource usage predictor. | `review/resource_predictor.py:314` |
| `predict_all_in_project` | `(project_dir: str)` | Run resource prediction on all C/H files in the project. | `review/resource_predictor.py:389` |
| `review_architecture` | `(task_name: str, project_dir: str, changed_files: list[str])` | Architecture reviewer: checks layering, dependency inversion, clean architecture. | `review/run.py:171` |
| `review_domain_modeling` | `(task_name: str, project_dir: str, changed_files: list[str])` | Domain modeling reviewer: checks ubiquitous language, bounded contexts, value objects. | `review/run.py:224` |
| `review_code_style` | `(task_name: str, project_dir: str, changed_files: list[str])` | Code style reviewer: checks formatting, naming, docstrings. | `review/run.py:258` |
| `review_embedded_c` | `(task_name: str, project_dir: str, changed_files: list[str])` | Embedded C reviewer: static analysis for firmware defects. | `review/run.py:302` |
| `review_coverage` | `(task_name: str, project_dir: str, changed_files: list[str])` | Coverage guardian: checks test coverage meets thresholds. | `review/run.py:314` |
| `run_review` | `(task_name: str, task_kind: str, project_dir: str, changed_files: list[str])` | Run multi-agent review for a task. | `review/run.py:369` |
| `auto_review` | `(project_dir: str)` | Auto-review all changed tasks. | `review/run.py:415` |
| `main` | `()` | — | `review/run.py:460` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `ReviewFinding` | `()` | — | `review/run.py:24` |
| `ReviewResult` | `()` | — | `review/run.py:53` |
| `ReviewSession` | `()` | Manages multi-agent review for a task. | `review/run.py:107` |
| `FindingTracker` | `()` | — | `review/tracker.py:32` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `ReviewFinding.__init__` | `(self, severity: str, category: str, file: str, line: int, message: str)` | — | `review/run.py:25` |
| `ReviewFinding.to_dict` | `(self)` | Serialize finding to dictionary. | `review/run.py:39` |
| `ReviewResult.__init__` | `(self, task_name: str, reviewer: str)` | — | `review/run.py:54` |
| `ReviewResult.add_finding` | `(self, finding: ReviewFinding)` | Add a finding to this review result. | `review/run.py:63` |
| `ReviewResult.decide` | `(self)` | Voting logic: pass/fail/retry based on findings. | `review/run.py:67` |
| `ReviewResult.to_dict` | `(self)` | Serialize review result to dictionary. | `review/run.py:88` |
| `ReviewSession.__init__` | `(self, task_name: str, project_dir: str)` | — | `review/run.py:110` |
| `ReviewSession.add_review` | `(self, result: ReviewResult)` | Add an agent review result to this session. | `review/run.py:118` |
| `ReviewSession.final_decision` | `(self)` | Aggregate all agent reviews into final decision. | `review/run.py:122` |
| `ReviewSession.save` | `(self)` | Persist review session to disk as JSON. | `review/run.py:142` |
| `ReviewSession.to_dict` | `(self)` | Serialize review session to dictionary. | `review/run.py:149` |
| `FindingTracker.__init__` | `(self, project_dir: str, task_name: str)` | — | `review/tracker.py:33` |
| `FindingTracker.record_findings` | `(self, session: 'ReviewSession')` | Append all open findings from *session* to findings.jsonl. | `review/tracker.py:41` |
| `FindingTracker.close_finding` | `(self, finding_id: str, resolution: str, resolver: str)` | Append a close event for *finding_id*. Returns True if the finding existed. | `review/tracker.py:60` |
| `FindingTracker.get_open_findings` | `(self, req_id: str | None)` | Return findings not yet closed, optionally filtered by req_id. | `review/tracker.py:79` |
| `FindingTracker.closure_report` | `(self, req_ids: list[str])` | Return per-req closure stats: {req_id: {open, closed, findings}}. | `review/tracker.py:97` |
| `FindingTracker.auto_close_if_verified` | `(self, req_id: str, verifier_result: dict)` | Auto-close all open findings for *req_id* when verifier reports passed. | `review/tracker.py:112` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.review import <公共符号>
# 详见 docs/modules/review.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 3 处生产引用(Grep `yuleosh.review` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/review/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

# `yuleosh.review` 模块设计文档

> 子系统定位：OSH Review Engine —— 多 Agent 审查矩阵（per-task 阻塞审查）
> 代码根：`src/yuleosh/review/`
> 文档性质：详细设计（SWE.3），基于源码实地盘点。

---

## 0. 命名澄清（重要）

仓库内存在**多个同名 `review` 模块**，职责各不相同，**切勿混淆**：

| 模块 | 路径 | 职责 |
|---|---|---|
| **本引擎** | `src/yuleosh/review/` | 多 Agent 代码审查矩阵（本文档） |
| api 审查端点 | `src/yuleosh/api/review.py` | HTTP 端点 `handle_review`（`api/router.py:27` 引用） |
| ci stage | `src/yuleosh/ci/stages/review.py` | CI 审查阶段 |
| pipeline step | `src/yuleosh/pipeline/step_handlers/review.py` | 流水线审查步骤（`step_hermes_review` 等） |

本文档仅描述 `src/yuleosh/review/`。

---

## 1. 职责边界

- **OSH Review Engine**：多 Agent 审查矩阵，按任务类型选择审查器组合（`run.py:7-13`）。
- 双轨语义（仅 docstring 描述，无代码枚举）：Track A 自检查（非阻塞）、Track B 自动审查器（阻塞，pass/fail/retry）（`run.py:10-12`）。
- 另含嵌入式 C 静态分析 + LLM 增强（`c_review.py`）、嵌入式资源占用预估（`resource_predictor.py`）、finding 生命周期持久化（`tracker.py`）。

---

## 2. 目录结构与规模

> **注意：该目录无 `__init__.py`**，不能作为包整体 `import yuleosh.review`，只能以子模块访问（`yuleosh.review.run`、`yuleosh.review.c_review` 等）。

| 文件 | 行数 | 职责 |
|---|---|---|
| `run.py` | 486 | 审查矩阵、数据模型、`run_review` / `auto_review` 入口 |
| `tracker.py` | 153 | finding 生命周期持久化（append-only JSONL） |
| `c_review.py` | 464 | 嵌入式 C 静态分析 + LLM 增强 |
| `resource_predictor.py` | 412 | RAM/ROM/CPU/stack/ISR 资源预估 |

---

## 3. 数据模型（均为**普通 class，非 dataclass / 非 pydantic**）

**`ReviewFinding`**（`run.py:24`）：
`severity: str`（`critical|major|minor|info`，`:26`）、`category: str`（`architecture|domain|style|security|coverage`，注释 `:27`）、`file: str`、`line: int`、`message: str`、`finding_id: str`（`sha256(f"{file}{line}{message}")[:8]`，`:32-35`）、`req_ids: list[str] = []`、status `open|fixed|accepted|wont_fix`（`open` 默认，`:37`）

**`ReviewResult`**（`run.py:53`）：
`task_name`、`reviewer`、`timestamp`、`findings: list[ReviewFinding] = []`、`status: pending|running|passed|failed|retry`、`summary: str = ""`、`retry_count: int = 0`（`:59`）

**`ReviewSession`**（`run.py:107`）：
`task_name`、`project_dir`、`created_at`、`status: running|completed`、`reviews: list[ReviewResult] = []`、`decision: Optional[str]`

**`FindingTracker`**（`tracker.py:32`）：
`_findings_path = <project_dir>/.osh/reviews/<task_name>/findings.jsonl`（`tracker.py:36-38`）；JSONL 记录字段：`event, finding_id, severity, category, file, line, message, req_ids, status, opened_at`，close 记录含 `resolution, resolver, resolved_at`。

---

## 4. 审查轨道 / 范畴 / 决策传播

- **无 `verdict` 关键字**，亦无 `propagat` / `consolidat`。结论以 `status` / `decision` 表达。
- **任务类型 → 审查器映射 `REVIEWER_MAP`**（`run.py:358-366`）：
  `feature → [architecture, domain_modeling, code_style, coverage]`、`bugfix → [code_style, coverage]`、`refactor → [architecture, code_style, coverage]`、`docs → []`（自动通过）、`config → [code_style]`、`embedded → [architecture, embedded_c, code_style, coverage]`、`firmware → [embedded_c, code_style]`
- **单结果投票 `ReviewResult.decide()`**（`run.py:67-86`）：critical 或 major>3 → `retry`（retry_count<5）否则 `failed`；有 major → `passed`（带警告）；否则 `passed`。
- **会话级汇总 `ReviewSession.final_decision()`**（`run.py:122-140`）：任一 `retry`→`retry`；任一 `failed`→`failed`；全 `passed`→`passed`；无 reviews → `failed`。
- severity 注释枚举：`critical|major|minor|info`（`run.py:26`）；覆盖率阈值 80%（`:331`）；retry 上限 5（`:73`）；git 子进程超时 30s。

---

## 5. 集成点

- 引擎内部相对依赖：`run.py:305` → `from .c_review import review_embedded_c`；`c_review.py:388` → `from .run import ReviewResult, ReviewFinding`；`c_review.py:39` / `resource_predictor.py:31` → `from ..llm import client`（依赖 `yuleosh.llm`）。
- **外部对本引擎的调用**：
  - `src/yuleosh/pipeline/step_handlers/review_arch.py:29` — `from yuleosh.review.run import review_architecture`
  - `src/yuleosh/cli/commands/misc.py:718,725` — `auto_review` / `run_review`
  - `src/yuleosh/cli/yuleosh.sh:59,65` — `python3 -m yuleosh.review.run auto` / `task`

---

## 6. 已知偏差 / 待决（高影响，务必知悉）

1. **`tracker.py` 与 `resource_predictor.py` 当前无生产调用方**（grep `review.tracker` / `review.resource_predictor` 在 `src/` 全仓**零命中**）。二者仅被测试引用，疑似**孤儿模块**或尚未接线。设计文档据实标注，不应假设其已在流水线生效。
2. 目录**无 `__init__.py`**，跨子模块引用靠相对导入，包级 `import yuleosh.review` 不可用。
3. 审查“双轨”仅存在于 docstring，**代码层面无 Track A/B 枚举**，实际由 `REVIEWER_MAP` + `decide()` 阻塞逻辑承载。
4. 与 `api/review.py`、`ci/stages/review.py`、`pipeline/step_handlers/review.py` 并存，命名易混，重构时建议收敛。

---

## 7. 测试

`tests/test_review_engine.py`、`test_review_engine_extended.py`、`test_review_run.py`、`test_review_run_ext.py`、`test_review_tracker.py`、`test_review_jsonl.py`、`test_review_smoke.py`、`test_c_review.py`、`test_c_review_deep.py`、`test_review_resource_deep.py`、`test_mmio_review.py`、`test_phase0_coverage_boost.py`、`test_step_handlers_steps_ext.py`、`test_cli.py`（patch `auto_review`/`run_review`）、`test_e2e.py:281,296`（子进程调用）。

> 注意：名称含 `review` 的部分测试（如 `test_api_review_ext.py`、`test_pipeline_review_*`）指向**其他** review 模块，切勿误归。

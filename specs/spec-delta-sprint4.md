# Sprint 4: step_handlers 覆盖率提升 + execution.py 子拆分预备

> **Version**: 1.0.0-draft
> **基于**: Sprint 3 有条件通过 — 审查报告 `docs/review-sprint3-pipeline.md`
> **审查条件**:
>   1. step_handlers 行覆盖率从 70–77% 拉升到 ≥80%
>   2. execution.py (498 行) 监控行数增长，必要时子拆分
> **格式**: RFC 2119 (SHALL / SHOULD / MAY) + GIVEN/WHEN/THEN
> **作者**: 小马 🐴 (质量架构师)

---

## 背景

Sprint 3 完成 Pipeline 拆分（run.py 瘦身 + step_handlers 子拆分），正式审查结论 **有条件通过**。两个条件对应 Sprint 4 的两个核心需求：

### 覆盖率缺口现状

| 文件 | Sprint 3 行覆盖率 | 目标 | 缺口(百分点) |
|:-----|:----------------:|:----:|:----------:|
| `step_handlers/spec.py` | 73% | ≥80% | 7 |
| `step_handlers/analysis.py` | 77% | ≥80% | 3 |
| `step_handlers/execution.py` | 72% | ≥80% | 8 |
| `step_handlers/review.py` | 70% | ≥80% | 10 |
| `step_handlers/__init__.py` | 70% | ≥80% | 10 |
| `stages.py` | 89% | ≥80% (维持) | 0 ✅ |
| `orchestrator.py` | 82% | ≥80% (维持) | 0 ✅ |

### execution.py 行数风险

| 文件 | 当前行数 | 门禁 |
|:-----|:-------:|:----:|
| `step_handlers/execution.py` | **498** | ≤500 ✅ (临界) |
| 其中 `step_claude_dev` 单个函数 | ~200 | 最大单体 |
| 其余 3 个函数 | ~80–90 each | 合理 |

> **风险**: 再增加任意一行即超限。Sprint 4 若在此文件增加测试辅助或修复覆盖，行数必然突破 500。因此需要同时做子拆分或拆分预备。

---

## S4-REQ-001: step_handlers 覆盖率提升（行覆盖率 ≥80%）

- The system **SHALL** increase line coverage of each `step_handlers/` submodule to ≥80%, measured by `pytest --cov=yuleosh.pipeline.step_handlers --cov-report=term-missing --cov-fail-under=80`.
- The coverage **SHALL** be measured against the full module, not just deltas.
- Coverage gaps in `step_handlers/spec.py` **SHALL** be closed by adding tests for:
  - `subprocess.TimeoutExpired` path (line: spec.py catch clause)
  - `subprocess.CalledProcessError` path (line: spec.py catch clause)
  - `data.get("error_count", 0) > 0` error branch (non-zero error count)
  - Generic `Exception` catch block
- Coverage gaps in `step_handlers/analysis.py` **SHALL** be closed by adding tests for:
  - `step_super_analysis`: spec file not found / unreadable path
  - `step_hermes_prd`: `super_path` artifact missing or not exists
  - `step_internal_review`: fallback template path when `_call_llm` fails (the try/except `(RuntimeError, PipelineStepError)` branch)
- Coverage gaps in `step_execution.py` **SHALL** be closed by adding tests for:
  - `step_claude_arch`: `src_dir` does not exist path, `_call_llm` exception handling, `out_path.write_text` OSError
  - `step_claude_dev`: git subprocess exception path, `out_path.write_text` OSError, `artifacts_read` returning None for missing artifacts
  - `step_test_planning`: missing spec file path, `out_path.write_text` OSError
  - `step_claude_test`: Go project (`go.mod` exists) subprocess paths (success, timeout, error), `FileNotFoundError` for pytest, `TimeoutExpired` for pytest, generic `Exception` in test runner, `re.search` fallback when no "passed"/"failed" in output, `re.search` alternative match for numbers
  - `artifacts_read`: key not in artifacts dict, file does not exist, read exception
- Coverage gaps in `step_handlers/review.py` **SHALL** be closed by adding tests for:
  - `step_hermes_review`: `src_dir` not existing, `json.dump` OSError, `_try_parse_hermes_json` fallback producing `retry` status
  - `step_final_report`: `_call_llm` failure → template fallback path (the try/except block), `out_path.write_text` OSError, artifact file read exception
- Coverage gaps in `step_handlers/__init__.py` **SHALL** be closed by adding tests for:
  - `_have_step_classes = True` path (when `get_step_instance` is available)
  - `_resolve_handler` returning a `PipelineStep` instance
  - `_have_step_classes = False` path continuing to use legacy function

- Each step handler module **SHALL** have a corresponding deep test file:
  - `tests/test_step_handlers_spec_deep.py`
  - `tests/test_step_handlers_analysis_deep.py`
  - `tests/test_step_handlers_execution_deep.py`
  - `tests/test_step_handlers_review_deep.py`
  - `tests/test_step_handlers_init_deep.py`

- Tests **SHALL** use `mock.patch` to inject LLM failures, subprocess exceptions, I/O errors, and other edge cases without real API calls.

- All new and existing tests **SHALL** pass with exit code 0.

- The target file `tests/test_step_handlers_execution_deep.py` **MAY** use a pre-canned mock test plan to avoid pulling in real artifacts.

### 逐步覆盖路径分析

#### spec.py (当前 73% → 目标 ≥80%)
```
未覆盖分支:
  1. subprocess.TimeoutExpired catch
  2. subprocess.CalledProcessError catch
  3. data["error_count"] > 0 → 非零错误路径
  4. Generic Exception catch (最终安全网)
测试追加: mock subprocess.run 返回 非零 returncode / timeout / calledprocesserror / 非 JSON stdout
```

#### analysis.py (当前 77% → 目标 ≥80%)
```
未覆盖分支:
  5.  step_super_analysis: spec_path not exists → "(spec file not found)"
  6.  step_hermes_prd: super-content not in artifacts → 空字串路径
  7.  step_internal_review: _call_llm (RuntimeError / PipelineStepError) → template fallback
测试追加: mock spec file missing, mock artifact missing, mock LLM failure in internal_review
```

#### execution.py (当前 72% → 目标 ≥80%)
```
未覆盖分支:
  8.  step_claude_arch: src_dir not exists → 跳过文件扫描
  9.  step_claude_arch: _call_llm exception → PipelineStepError
  10. step_claude_arch: write_text OSError
  11. step_claude_dev: git log subprocess exception → (git log 异常路径)
  12. step_claude_dev: write_text OSError
  13. step_claude_dev: artifacts_read returns None for missing artifacts
  14. step_test_planning: spec file not exists → "(spec file not found)"
  15. step_test_planning: write_text OSError
  16. step_claude_test: has_go = True → Go test path
  17. step_claude_test: go test TimeoutExpired
  18. step_claude_test: go test generic Exception
  19. step_claude_test: FileNotFoundError (pytest not installed)
  20. step_claude_test: pytest TimeoutExpired
  21. step_claude_test: pytest generic Exception
  22. step_claude_test: re.search fallback when no "passed"/"failed" in output
  23. step_claude_test: write_text OSError
  24. artifacts_read: key not in dict
  25. artifacts_read: file does not exist
  26. artifacts_read: read exception (non-OSError)
测试追加: mock os.walk / mock subprocess.run / mock Path.write_text raising OSError
```

#### review.py (当前 70% → 目标 ≥80%)
```
未覆盖分支:
  27. step_hermes_review: src_dir not exists → 跳过源文件扫描
  28. step_hermes_review: json.dump OSError
  29. step_hermes_review: _try_parse_hermes_json 未覆盖的 brace-tracking fallback
  30. step_final_report: artifact file read exception → "(cannot read)"
  31. step_final_report: _call_llm failure → template fallback (fallback行)
  32. step_final_report: write_text OSError (after LLM)
  33. step_final_report: write_text OSError (after template fallback)
测试追加: mock os.walk / mock json.dump raising OSError / mock LLM failure in final_report
```

#### __init__.py (当前 70% → 目标 ≥80%)
```
未覆盖分支:
  34. ImportError of get_step_instance → _have_step_classes = False
  35. Import success → _have_step_classes = True
  36. _resolve_handler: _have_step_classes = True + get_step_instance returns non-None
测试追加: 不 mock get_step_instance 导入 (正常导入路径), mock ImportError 绕回
```

### GIVEN/WHEN/THEN

**GIVEN** `step_handlers/spec.py` with line coverage at 73%, missing the subprocess exception paths and error-returncode path
**WHEN** deep test file `tests/test_step_handlers_spec_deep.py` is added with mock subprocess scenarios
**THEN** spec.py line coverage SHALL reach ≥80%

**GIVEN** `step_handlers/analysis.py` with line coverage at 77%, missing the LLM-fallback and missing-artifact paths
**WHEN** deep tests cover `spec_path` not found, artifact key missing, and `_call_llm` failure in `step_internal_review`
**THEN** analysis.py line coverage SHALL reach ≥80%

**GIVEN** `step_handlers/execution.py` with line coverage at 72%, missing ~15 branch paths including Go test, subprocess exceptions, write failures, and artifact read edge cases
**WHEN** deep test file `tests/test_step_handlers_execution_deep.py` is added with mock subprocess, mock filesystem, and mock OSError scenarios
**THEN** execution.py line coverage SHALL reach ≥80%

**GIVEN** `step_handlers/review.py` with line coverage at 70%, missing the src_dir-not-found path, LLM-fallback path, and write-failure paths
**WHEN** deep test file `tests/test_step_handlers_review_deep.py` is added with mock file system and mock LLM failure scenarios
**THEN** review.py line coverage SHALL reach ≥80%

**GIVEN** `step_handlers/__init__.py` with line coverage at 70%, missing both the import-success and import-failure paths for `get_step_instance`
**WHEN** deep test file `tests/test_step_handlers_init_deep.py` covers both import branches and `_resolve_handler` return values
**THEN** __init__.py line coverage SHALL reach ≥80%

**GIVEN** all five deep test files are added to the test suite
**WHEN** running `pytest tests/ --cov=yuleosh.pipeline --cov-report=term-missing --cov-fail-under=80 -q`
**THEN** all tests SHALL pass (exit code 0) and overall line coverage of `yuleosh.pipeline` SHALL be ≥80%

---

## S4-REQ-002: execution.py 子拆分

- If `step_handlers/execution.py` exceeds 500 lines after adding coverage tests, the system **SHALL** split it into ≤500-line submodules.
- The split **SHALL** preserve the existing import path `from yuleosh.pipeline.step_handlers import step_claude_arch, step_claude_dev, step_test_planning, step_claude_test` via the `__init__.py` re-export mechanism.
- The split **SHOULD** group functions as follows:
  - `exec_dev.py`: `step_claude_dev` (largest function, ~200 lines) + `step_claude_arch` (~80 lines)
  - `exec_test_arch.py` (or `exec_planning.py`): `step_test_planning` (~80 lines) + `step_claude_test` (~90 lines)
  - `artifacts_read` **SHOULD** stay in the execution subpackage or move to a shared location like `stages.py`.
- If execution.py stays ≤500 lines (measurement conducted after adding coverage tests), the system **SHALL** retain it as-is but:
  - **SHALL** add a file-level comment noting the 500-line guardrail
  - **SHALL** reject any future commit that pushes the file past 500 lines (enforced by CI or pre-commit hook)
- refactoring **MAY** lift `artifacts_read` to a shared utility module (`step_handlers/_utils.py`) to be reused across submodules.

### GIVEN/WHEN/THEN

**GIVEN** execution.py at 498 lines prior to Sprint 4 changes
**WHEN** coverage-boost tests and any new code are added
**THEN** execution.py SHALL be either ≤500 lines with a guardrail comment, or split into submodules ≤500 lines each

**GIVEN** execution.py is split into submodules (e.g. exec_dev.py, exec_test_arch.py)
**WHEN** running `python -c "from yuleosh.pipeline.step_handlers import step_claude_dev"`
**THEN** the import SHALL succeed (via __init__.py re-exports)

**GIVEN** execution.py is retained but ≤500 lines
**WHEN** a future commit touches execution.py
**THEN** a CI check or pre-commit hook SHALL enforce the ≤500 line limit

---

## 验收标准总表

| ID | 描述 | SHALL/SHOULD/MAY | 验证方式 | 门禁 |
|:---|:-----|:--------------:|:---------|:----:|
| AC-01 | spec.py 行覆盖率 ≥80% | SHALL | `pytest --cov=yuleosh.pipeline.step_handlers.spec --cov-fail-under=80 tests/test_step_handlers_spec_deep.py` + 人工确认覆盖缺失分支 | 🔴 阻塞 |
| AC-02 | analysis.py 行覆盖率 ≥80% | SHALL | 同上 (analysis) | 🔴 阻塞 |
| AC-03 | execution.py 行覆盖率 ≥80% | SHALL | 同上 (execution) | 🔴 阻塞 |
| AC-04 | review.py 行覆盖率 ≥80% | SHALL | 同上 (review) | 🔴 阻塞 |
| AC-05 | `__init__.py` 行覆盖率 ≥80% | SHALL | 同上 (__init__) | 🔴 阻塞 |
| AC-06 | 所有测试 100% PASS | SHALL | `pytest tests/ -q --tb=short` | 🔴 阻塞 |
| AC-07 | pipeline 整体行覆盖率 ≥80% | SHALL | `pytest --cov=yuleosh.pipeline --cov-fail-under=80` | 🔴 阻塞 |
| AC-08 | execution.py ≤500 行或已拆分子模块 | SHALL | `wc -l src/yuleosh/pipeline/step_handlers/execution.py` + 检查是否存在子模块 | 🔴 阻塞 |
| AC-09 | 拆分子模块后导入兼容 | SHALL | `python -c "from yuleosh.pipeline.step_handlers import step_claude_dev"` | 🔴 阻塞 |
| AC-10 | 保留时添加 500 行 guardrail 注释 | SHOULD | 人工审阅文件顶部有 guardrail 注释 | 🟡 警告 |
| AC-11 | 无循环依赖 | SHALL | `python -c "import yuleosh.pipeline.orchestrator; import yuleosh.pipeline.session; import yuleosh.pipeline.stages"` 无 ImportError | 🔴 阻塞 |
| AC-12 | stages.py 和 orchestrator.py 覆盖率维持 ≥80% | SHALL | `pytest --cov=yuleosh.pipeline.stages --cov=yuleosh.pipeline.orchestrator --cov-fail-under=80` | 🔴 阻塞 |
| AC-13 | 新增 deep 测试文件 5 个 | SHALL | 文件存在性检查 | 🔴 阻塞 |

---

## 验收判定矩阵

> **版本**: v1.0.0 | **基于**: specs/spec-delta-sprint4.md  
> **规范文体**: RFC 2119 (SHALL / SHOULD / MAY)

---

### S4-REQ-001: step_handlers 覆盖率提升

| 需求 ID | 类型 | 语句 | AC ID | 验证方式 | 门禁 | 前置条件 |
|:--------|:---:|:------|:-----:|:---------|:----:|:--------|
| S4-REQ-001.1 | SHALL | spec.py 行覆盖率 ≥80% | AC-01 | `pytest --cov=yuleosh.pipeline.step_handlers.spec --cov-fail-under=80 tests/test_step_handlers_spec_deep.py` | 🔴 | — |
| S4-REQ-001.2 | SHALL | 覆盖 spec.py 缺失路径：subprocess 异常、非零 error_count、非 JSON 输出 | AC-01 | 人工审阅 + coverage 报告确认分支覆盖 | 🔴 | AC-01 |
| S4-REQ-001.3 | SHALL | analysis.py 行覆盖率 ≥80% | AC-02 | `pytest --cov=yuleosh.pipeline.step_handlers.analysis --cov-fail-under=80 tests/test_step_handlers_analysis_deep.py` | 🔴 | — |
| S4-REQ-001.4 | SHALL | 覆盖 analysis.py 缺失路径：spec 不存在、artifact 缺失、LLM 失败 fallback | AC-02 | 人工审阅 + coverage 报告 | 🔴 | AC-02 |
| S4-REQ-001.5 | SHALL | execution.py 行覆盖率 ≥80% | AC-03 | `pytest --cov=yuleosh.pipeline.step_handlers.execution --cov-fail-under=80 tests/test_step_handlers_execution_deep.py` | 🔴 | — |
| S4-REQ-001.6 | SHALL | 覆盖 execution.py 缺失路径：Go test 分支、subprocess 异常、I/O 错误、artifacts_read 缺失 | AC-03 | 人工审阅 + coverage 报告确认覆盖 ~15 个分支 | 🔴 | AC-03 |
| S4-REQ-001.7 | SHALL | review.py 行覆盖率 ≥80% | AC-04 | `pytest --cov=yuleosh.pipeline.step_handlers.review --cov-fail-under=80 tests/test_step_handlers_review_deep.py` | 🔴 | — |
| S4-REQ-001.8 | SHALL | 覆盖 review.py 缺失路径：src_dir 不存在、json.dump 失败、template fallback | AC-04 | 人工审阅 + coverage 报告 | 🔴 | AC-04 |
| S4-REQ-001.9 | SHALL | `__init__.py` 行覆盖率 ≥80% | AC-05 | `pytest --cov=yuleosh.pipeline.step_handlers --cov-fail-under=80 tests/test_step_handlers_init_deep.py` | 🔴 | — |
| S4-REQ-001.10 | SHALL | 覆盖 `__init__.py` 缺失路径：_have_step_classes 两种状态 | AC-05 | 人工审阅 + coverage 报告 | 🔴 | AC-05 |
| S4-REQ-001.11 | SHALL | 创建 5 个 deep 测试文件 | AC-13 | `ls tests/test_step_handlers_*_deep.py` | 🔴 | — |
| S4-REQ-001.12 | SHALL | 所有新老测试 100% PASS | AC-06 | `pytest tests/ -q --tb=short` | 🔴 | AC-01~11 |
| S4-REQ-001.13 | SHALL | pipeline 整体行覆盖率 ≥80% | AC-07 | `pytest --cov=yuleosh.pipeline --cov-fail-under=80 -q` | 🔴 | AC-06 |
| S4-REQ-001.14 | SHOULD | stages.py 和 orchestrator.py 维持 ≥80% 覆盖 | AC-12 | `pytest --cov=yuleosh.pipeline.stages --cov=yuleosh.pipeline.orchestrator --cov-fail-under=80` | 🟡 | AC-07 |
| S4-REQ-001.15 | SHALL | 无循环依赖 | AC-11 | `python -c "import yuleosh.pipeline.orchestrator; import yuleosh.pipeline.session; import yuleosh.pipeline.stages"` 无 ImportError | 🔴 | AC-01~10 |

#### GIVEN/WHEN/THEN 映射

| # | GIVEN | WHEN | THEN | AC |
|:--|:------|:-----|:-----|:--:|
| GWT-01 | step_handlers 各子模块覆盖率在 70–77% | 添加 5 个 deep 测试文件 | 每个子模块行覆盖率 ≥80% | AC-01 ~ AC-05 |
| GWT-02 | `spec.py` 未覆盖 subprocess.TimeoutExpired / CalledProcessError | 用 mock_run 注入 subprocess 异常 | `spec.py` 覆盖异常捕获语句 | AC-01 |
| GWT-03 | `analysis.py` 未覆盖 `step_internal_review` 的 LLM fallback | 注入 `_call_llm` 抛出 RuntimeError | 验证输出含 `⚠️ AI-powered analysis unavailable` 回退模板 | AC-02 |
| GWT-04 | `execution.py` 未覆盖 Go 项目路径 | mock `Path(project_dir / "go.mod").exists()` 返回 True | Go test 分支被执行，覆盖 `subprocess.run(["go", "test"...])` | AC-03 |
| GWT-05 | `execution.py` 未覆盖 subprocess FileNotFoundError | mock subprocess.run 抛出 FileNotFoundError | 日志含 `pytest not installed` | AC-03 |
| GWT-06 | `execution.py` 未覆盖 `write_text` OSError | mock `Path.write_text` 抛出 OSError | `PipelineStepError` 被提升 | AC-03 |
| GWT-07 | `review.py` 未覆盖 `step_final_report` 的 LLM fallback | mock `_call_llm` 抛出 RuntimeError | 验证输出含 `⚠️ AI-powered summary unavailable` 回退模板 | AC-04 |
| GWT-08 | `__init__.py` 未覆盖 `_have_step_classes` 分支 | 不 mock `get_step_instance` 导入 | `_have_step_classes = True` 路径被执行 | AC-05 |
| GWT-09 | `__init__.py` 未覆盖 `_have_step_classes = False` 分支 | mock `from yuleosh.pipeline.steps import get_step_instance` 抛出 ImportError | `_have_step_classes = False` 路径被执行 | AC-05 |
| GWT-10 | sprint3 所有测试通过 | sprint4 deep tests 加入后全量回归 | 所有 97+ 测试 100% PASS | AC-06 |

---

### S4-REQ-002: execution.py 子拆分

| 需求 ID | 类型 | 语句 | AC ID | 验证方式 | 门禁 | 前置条件 |
|:--------|:---:|:------|:-----:|:---------|:----:|:--------|
| S4-REQ-002.1 | SHALL | execution.py ≤500 行或拆分 | AC-08 | `wc -l src/yuleosh/pipeline/step_handlers/execution.py` + 是否具有子模块文件 | 🔴 | S4-REQ-001 |
| S4-REQ-002.2 | SHALL | 拆分后导入兼容 | AC-09 | `python -c "from yuleosh.pipeline.step_handlers import step_claude_dev, step_claude_arch, step_test_planning, step_claude_test"` | 🔴 | AC-08 (拆分路径) |
| S4-REQ-002.3 | SHOULD | 保留时为文件添加 guardrail 注释 | AC-10 | 文件顶部有 `# 500-line guardrail` 注释 | 🟡 | AC-08 (保留路径) |
| S4-REQ-002.4 | SHOULD | 子拆分分组推荐：exec_dev.py + exec_test_arch.py | AC-08 | 人工审阅分组合理性 | 🟡 | S4-REQ-002.1 |
| S4-REQ-002.5 | MAY | 提取 `artifacts_read` 到 `_utils.py` | — | 文件存在性 + 导入测试 | 🟢 | AC-09 |

#### 推荐拆分方案

| 新文件 | 包含函数 | 预估行数 | 备注 |
|:-------|:---------|:--------:|:-----|
| `exec_dev.py` | `step_claude_dev` | ~200 | 最大单体函数单独抽出 |
| `exec_test_arch.py` | `step_claude_test`, `step_claude_arch`, `step_test_planning` | ~250 | 测试+架构相关的 step 函数 |
| `_utils.py` | `artifacts_read` | ~15 | 共享辅助函数 |

如果 deep 测试追加后 execution.py 仍然 ≤500 行，可以推迟拆分但必须添加 guardrail。

#### GIVEN/WHEN/THEN 映射

| # | GIVEN | WHEN | THEN | AC |
|:--|:------|:-----|:-----|:--:|
| GWT-11 | execution.py 当前 498 行 | Sprint 4 覆盖增强后行数可能超 500 | 要么 split 成 ≤500 子模块，要么保留并添加 guardrail | AC-08 |
| GWT-12 | execution.py 拆成 exec_dev.py + exec_test_arch.py | import `from yuleosh.pipeline.step_handlers import step_claude_dev` | 导入成功 (via __init__.py re-export) | AC-09 |
| GWT-13 | execution.py 保留且 ≤500 行 | 人工审阅文件顶部 | 有 `# 500-line guardrail` 明确注释 | AC-10 |
| GWT-14 | execution.py 拆分子模块 | 验证循环依赖 | `import yuleosh.pipeline.orchestrator` 无 ImportError | AC-11 |

---

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|:-----|:----:|:----:|:-----|
| mock subprocess 不传播 coverage（子进程不在 coverage 内） | 低 | 中 | 使用 `mock.patch('subprocess.run')` 替换而非运行真实子进程 |
| Go 项目路径测试依赖 `go` 二进制 | 低 | 低 | 用 `mock.patch('pathlib.Path.exists', return_value=True)` + mock subprocess.run |
| `_have_step_classes` 覆盖需在进程中隔离 import 状态 | 中 | 中 | 使用 `importlib.reload` 或子进程测试，或精确 mock 导入路径 |
| execution.py 拆分后需更新所有 import 引用 | 中 | 高 | 通过 `__init__.py` 统一 re-export，外部引用不需要修改 |
| deep tests 增加后测试总运行时间上升 | 中 | 低 | 新增 ~5 个文件，预估增加 2-5 秒，在 CI timeout 内 |

---

## 实施顺序

```
Phase 1: 创建 deep 测试文件（5 files）
  ├── tests/test_step_handlers_spec_deep.py
  ├── tests/test_step_handlers_analysis_deep.py
  ├── tests/test_step_handlers_execution_deep.py
  ├── tests/test_step_handlers_review_deep.py
  └── tests/test_step_handlers_init_deep.py

Phase 2: 逐模块覆盖验证
  ├── pytest --cov=yuleosh.pipeline.step_handlers.spec --cov-fail-under=80
  ├── pytest --cov=yuleosh.pipeline.step_handlers.analysis --cov-fail-under=80
  ├── pytest --cov=yuleosh.pipeline.step_handlers.execution --cov-fail-under=80
  ├── pytest --cov=yuleosh.pipeline.step_handlers.review --cov-fail-under=80
  ├── pytest --cov=yuleosh.pipeline.step_handlers --cov-fail-under=80
  └── 若未达到 80% 则补充测试用例

Phase 3: execution.py 行数检查
  ├── wc -l execution.py
  ├── 若 >500: 拆分为 exec_dev.py + exec_test_arch.py
  ├── 若 ≤500: 添加 # 500-line guardrail 注释
  └── pytest 回归验证

Phase 4: 全量回归
  ├── pytest tests/ --tb=short -q
  ├── pytest --cov=yuleosh.pipeline --cov-fail-under=80
  └── 验证所有 AC 全部通过
```

---

## 版本历史

| 版本 | 日期 | 变更说明 | 审批人 |
|:----|:-----|:---------|:------|
| v1.0.0-draft | 2026-06-15 | 初始版本：基于 Sprint 3 有条件通过的两项约束设计 Sprint 4 | 小马 🐴 |

---

*本文档使用 RFC 2119 规范语言。SHALL 级条件阻塞 Sprint 验收，SHOULD 级优先完成，MAY 级可选。*

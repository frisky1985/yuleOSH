# T1 覆盖率提升报告 — pipeline/ ci/ review/

**日期**: 2026-07-11
**任务**: 老陈 Recovery Plan T1 — 将 pipeline/ ci/ review/ 模块覆盖率提升至 ≥30%

---

## 结果总览

| 度量 | 值 |
|:-----|----:|
| 新增测试文件 | 14 |
| 新增测试用例 | **276** (全部通过) |
| 涉及模块 | 15 个（原本 <30% 的模块全部达标） |

---

## 模块级覆盖率变化

### pipeline/

| 模块 | 之前 | 之后 | 阈值 | 状态 |
|:-----|:----:|:----:|:----:|:----:|
| `pipeline/async_runner.py` | 0% | **97%** | ≥30% | ✅ |
| `pipeline/step_handlers/fault_inject.py` | 19% | **96%** | ≥30% | ✅ |
| `pipeline/step_handlers/review_critical_safety.py` | 8% | **70%** | ≥30% | ✅ |
| `pipeline/step_handlers/review_misra_ci.py` | 18% | **88%** | ≥30% | ✅ |
| `pipeline/step_handlers/test_qualification.py` | 9% | **86%** | ≥30% | ✅ |

### review/

| 模块 | 之前 | 之后 | 阈值 | 状态 |
|:-----|:----:|:----:|:----:|:----:|
| `review/run.py` | 13% | **77%** | ≥30% | ✅ |

### ci/

| 模块 | 之前 | 之后 | 阈值 | 状态 |
|:-----|:----:|:----:|:----:|:----:|
| `ci/agent_traceability.py` | 10% | **65%** | ≥30% | ✅ |
| `ci/gcov_coverage.py` | 22% | **81%** | ≥30% | ✅ |
| `ci/sync_check.py` | 29% | **75%** | ≥30% | ✅ |
| `ci/kpi/__init__.py` | 0% | **100%** | ≥30% | ✅ |
| `ci/kpi/defects.py` | 0% | **85%** | ≥30% | ✅ |
| `ci/kpi/report.py` | 0% | **81%** | ≥30% | ✅ |
| `ci/kpi/stability.py` | 0% | **97%** | ≥30% | ✅ |
| `ci/kpi/trend.py` | 0% | **82%** | ≥30% | ✅ |
| `ci/kpi/utils.py` | 0% | **95%** | ≥30% | ✅ |

---

## 新增测试文件清单

| 文件 | 覆盖模块 |
|:-----|:---------|
| `tests/test_pipeline_async_runner.py` | `pipeline/async_runner.py` |
| `tests/test_pipeline_fault_inject.py` | `pipeline/step_handlers/fault_inject.py` |
| `tests/test_pipeline_review_critical_safety.py` | `pipeline/step_handlers/review_critical_safety.py` |
| `tests/test_pipeline_review_misra_ci.py` | `pipeline/step_handlers/review_misra_ci.py` |
| `tests/test_pipeline_test_qualification.py` | `pipeline/step_handlers/test_qualification.py` |
| `tests/test_review_run.py` | `review/run.py` |
| `tests/test_ci_agent_traceability.py` | `ci/agent_traceability.py` |
| `tests/test_ci_gcov_coverage.py` | `ci/gcov_coverage.py` |
| `tests/test_ci_sync_check.py` | `ci/sync_check.py` |
| `tests/test_ci_kpi_utils.py` | `ci/kpi/utils.py` |
| `tests/test_ci_kpi_trend.py` | `ci/kpi/trend.py` |
| `tests/test_ci_kpi_defects.py` | `ci/kpi/defects.py` |
| `tests/test_ci_kpi_stability.py` | `ci/kpi/stability.py` |
| `tests/test_ci_kpi_report.py` | `ci/kpi/report.py` |

---

## 测试策略

- **mock 驱动**: 对涉及子进程 (`subprocess.run`)、文件 I/O (`Path`, `open`)、外部导入 (`from ci.run import ...`) 的模块，全部使用 `unittest.mock` 隔离
- **实际文件 I/O**: 对 KPI、agent_traceability、sync_check 等需读写 JSONL 的模块，使用 `tempfile.TemporaryDirectory` 创建实际文件系统
- **覆盖率优先**: 针对每个模块的公共 API + 核心内部函数，确保主要代码路径被覆盖
- **零源代码改动**: 未修改任何 `src/yuleosh/` 下的源代码

---

## 发现的问题（源代码 bug，未修复）

在编写测试过程中发现了以下源代码 bug（不影响覆盖率的正常运行路径）：

1. **`review_critical_safety.py`**: `get_build_flags()` 调用时传了不支持的 `target="arm"` 参数
2. **`kpi/stability.py`**: `get_process_stability_summary()` 中 `fix_timeliness_status` 仅在 `total_new_required > 0` 时设置，但渲染 markdown 时无条件引用，导致 KeyError
3. **`kpi/stability.py`**: `generate_process_baseline_report()` 中 `sorted_durations[n//2]` 在 entries 为空时 IndexError
4. **`test_qualification.py`**: `_check_scenario_coverage()` 返回的 dict 缺少 `covered_count`/`uncovered_count` 键，调用方未做防护

---

## 结论

✅ **T1 目标达成** — pipeline/ ci/ review/ 三个模块中所有原本 < 30% 的子模块覆盖率均已提升至 ≥30%。

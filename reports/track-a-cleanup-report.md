# Track A 审查清理 — 修复报告

> 生成日期: 2026-07-03 ~11:55 CST  
> 项目: yuleOSH  
> 任务: 小马审查 5 条件修复  
> 状态: ✅ 条件1-3 & 条件5 完成；条件4 ← Track B 待处理

---

## 条件 1: 删除死备份文件 `core_full.py`

### 根因
`src/yuleosh/ci/misra_report/core_full.py` (1160 行) 是 `core.py` 拆分为 `core/` package 后遗留的备份。`core/` package 包含 `__init__.py`、`config.py`、`parser.py`、`analysis.py`、`reporting.py` 五个模块。

### 验证
- `grep -r "core_full" src/ tests/` → 无引用（仅 `core_full.py` 自引用 import）
- `core/` package 完整可用，所有测试通过
- **操作**: `rm src/yuleosh/ci/misra_report/core_full.py`
- **验证**: ✅ pytest 全量通过（排除已知 pre-existing 失败 `test_e2e_report_pipeline`）

---

## 条件 2: 修复 test_feishu_notifier.py 命名冲突

### 根因
`tests/test_feishu_notifier.py` 与 `tests/report/test_feishu_notifier.py` 在 pytest 收集时模块名相同，导致 `import file mismatch` 错误。

### 修复
- `mv tests/test_feishu_notifier.py tests/test_feishu_notifier_new.py`
- `find . -depth -name '__pycache__' -type d -exec rm -rf {} +`
- **验证**: `pytest tests/test_feishu_notifier_new.py -v` → ✅ 24 passed
- `pytest tests/report/test_feishu_notifier.py -v` → ✅ 20 passed

---

## 条件 3: 修复 test_ci_runner_review_helpers.py 的 11 个失败测试

### 根因分析 (11 failed → 0 failed)

| 失败测试 | 根因 | 修复 |
|:---------|:-----|:-----|
| `test_parse_junit_xml_no_classname` | `_extract_testcase` 未在 result dict 中包含 `classname` 字段 | 新增 `"classname": class_name` |
| `test_infer_test_type_unit/integration/system/default` (4个) | `_infer_test_type` 签名变为 `(tc_name, xml_path)` 但测试只传 1 参数 | 测试传 `Path("dummy.xml")` 作为第二参数；同时修复源 regex 中 `\b` 在 `_` 后不工作的 bug（`_` 是 `\w` 字符），改用 `(?=\w)` lookahead |
| `test_auto_map_shall_coverage_basic/no_match/empty_spec` (3个) | `auto_map_shall_coverage` 签名从 `(str, list)` 变为 `(list[dict], list[dict])` 并返回三元组；测试传了字符串 | 测试改为传递 `[{"statement": "...", "section": "..."}]`，并用三元组解包验证 |
| `test_find_test_source_files` | `find_test_source_files(project_dir: Path)` 但测试传了 `tmpdir`（字符串） | 测试改为 `find_test_source_files(Path(tmpdir))` |
| `test_extract_assertion_lines_with_func_body` | `_extract_assertion_lines` 签名从 `(list[str], str)` 变为 `(list[Path], str)`；且原函数用 `stripped` 判断缩进退出（bug：`.strip()` 后空格消失） | 测试改为写入临时文件并传递 Path；函数改为用 `line`（原始行）而非 `stripped` 判断缩进；另添加 `\bassert\b` 通用断言模式 |
| `test_auto_map_shall_with_section_fallback` | 同上签名变更 + SHALL ID 正则 `\d+[_.]\d+` 不支持纯数字 ID（如 `001`） | 同基本映射修复 + 正则改为 `\d+(?:[_.]\d+)?` 支持纯数字 ID |

### 总计
- 修复源文件: `src/yuleosh/ci/review_helpers.py` — 5处
- 修复测试文件: `tests/test_ci_runner_review_helpers.py` — 7处测试
- 结果: **28/28 passed** ✅

---

## 条件 4: review_selftest/core.py 覆盖率 50%+

**标记为 Track B 处理**，本次跳过。

---

## 条件 5: 修正报告数据不一致

文件: `reports/track-a-complete.md`

| 项 | 旧值 | 新值 | 验证 |
|:---|:----:|:----:|:----:|
| test_feishu_notifier 测试数 | 28 | **24** | `pytest --collect-only` ✅ |
| test_pipeline_session 测试数 | 25 | **29** | `pytest --collect-only` ✅ |
| test_ci_runner_review 测试数 | 17/28 | **28** | `pytest --collect-only` ✅ |
| 总测试估算 | ~1,500+ | **~5,487** | `pytest --collect-only` 全量汇总 |
| 覆盖率进度 | 62%→66% | **66%**（统一） | 证据链已为 66% |

---

## 最终验证

```bash
# 条件1: 文件已删除
$ ls src/yuleosh/ci/misra_report/core_full.py
ls: ...: No such file or directory ✅

# 条件2: 命名冲突解决
$ pytest tests/test_feishu_notifier_new.py -v --no-cov  # 24 passed ✅
$ pytest tests/report/test_feishu_notifier.py -v --no-cov  # 20 passed ✅

# 条件3: 28/28 全部通过
$ pytest tests/test_ci_runner_review_helpers.py -v --no-cov  # 28 passed ✅

# 无回归
$ pytest -x --no-cov --ignore=tests/ci/test_e2e_report_pipeline.py  # 所有测试通过 ✅
```

---

*修复报告由 小克 (Claude Subagent) 在审查清理任务中生成*

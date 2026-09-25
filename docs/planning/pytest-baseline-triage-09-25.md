# pytest 基线失败清理 — 立项（2026-09-25）

## 1. 立项理由

`.ai-rules.md` 第七章的红线要求「零回归三连（pytest + tsc/jest + build）全绿才提交」。
但全量 pytest **长期非绿**，导致每次提交只能退化为「影响闭包 A/B」自证，红线的自动化能力被架空。
2026-09-24 已取得**可复现基线**并完成一次分诊，具备立项清理的条件。

## 2. 基线（可复现，2026-09-24 实测）

| 运行方式 | 结果 | 耗时 |
|---|---|---|
| 固定序（`-p no:randomly`） | **125 failed / 14371 passed / 132 skipped / 77 warnings** | 47m12s |
| 随机序（默认） | 126 failed / 14357 passed / 132 skipped / 13 errors | 1h53m |

失败分布在 **35 个文件**。

**复现命令（必须固定序，否则结果不可复现）**

```bash
cd /Users/ingeek/workspace/yuleOSH
.venv/bin/python -m pytest -o addopts= --no-cov -p no:cacheprovider -p no:randomly \
  --basetemp=/tmp/osh-full-det -q --tb=no > /tmp/full-det.txt 2>&1
```

> ⚠️ `pytest-randomly 4.1.0` 是自动加载的插件（未写在 `pytest.ini` / `conftest.py`）。
> 同一条命令连跑两次失败集不同（实测 27 vs 28）→ **不加 `-p no:randomly` 的全量数字不能当基线**。
> `-p no:cacheprovider` 关不掉随机序（两者独立）。

## 3. 分诊结果（四类，合计 125）

### A 类｜死 mock —— `safe_run` 迁移遗留 · **42 项 / 4 文件**（最高优先）

**根因**：`pipeline/safe_run.py` 改用 `subprocess.Popen`（`:72` / `:177`），**全文不再调用 `subprocess.run`**。
7 个 step handler 已迁移到 `safe_subprocess_run` / `run_captured`：

| 已迁移 handler | 新助手 |
|---|---|
| `step_handlers/test_qemu.py` | `safe_subprocess_run` |
| `step_handlers/test_c_unit.py` | `safe_subprocess_run` |
| `step_handlers/c_coverage_gate.py` | `safe_subprocess_run` |
| `step_handlers/fault_inject.py` | `safe_subprocess_run` |
| `step_handlers/execution.py` | `safe_subprocess_run` |
| `step_handlers/test_integration.py` | `run_captured`（pytest/Go 段仍是 `subprocess.run`，**混用**） |
| `step_handlers/test_qualification.py` | `run_captured` |

但一批**老 coverage 测试**仍在 `patch("...<handler>.subprocess.run")`。
`patch("m.subprocess.run")` 打的是 **stdlib `subprocess` 的 `run` 属性**，而代码走 `Popen` —— **另一个属性**
→ mock 永不生效 → **测试真跑 qemu / cmake / ctest / gcovr / gcc**，断言必然失败。

**证据（可静态验证）**：
- `test_qemu.py:193` 调 `safe_subprocess_run(["which", binary])`，而
  `TestQemuHelpers::test_find_qemu_via_which` patch `.subprocess.run` 并断言 mock 返回的路径。
- `test_coverage_phase5_qemu.py` 的 **26 项失败 = 8 处 `test_qemu` patch + 18 处
  `patch.object(ccg.subprocess, "run")`**，与该文件实际 patch 点数**逐一对应**。
- `test_integration.py` 的 ctest 段（`:254` / `:280` / `:292`）已走 `run_captured`，而
  `test_ctest_runner_success` 的 `side_effect` 列表仍按「4 次都走 `subprocess.run`」编排。

**受影响文件与失败数**：`test_coverage_phase5_qemu.py` 26、`test_step_handlers_steps_ext.py` 8、
`test_step_handlers_execution_deep.py` 7、`test_backlog_p1_v350.py` 1。

**状态**：✅ 本轮已修**并验证**（见 §4.1）。定向 A/B 实测：该 4 文件不通过数 **138 → 2**，净修 136 项；
残留 2 项经定性**均非死 mock 根因**（见 §4.2），已转分诊其它类。

### B 类｜鉴权 / 租户 / 计费 / 路由 · **38 项 / 10 文件**

| 文件 | 失败 | 主题 |
|---|---|---|
| `test_coverage_phase2_lowcov.py` | 11 | billing routes 5 + tenant routes 6（`test_require_auth_no_token` / `test_update_non_admin` …） |
| `test_api.py` | 8 | `TestPipeline` 7 + `TestProject::test_create_project_duplicate` |
| `test_coverage_phase3_lowcov.py` | 6 | `TestProjectHelpers` / `TestProjectRoutes` 的 `*_auth_failure` |
| `test_tenant_security_ei_m2b.py` | 5 | credentials 读写/权限/注入 |
| `test_api_small_modules.py` | 2 | `handle_pipeline_list_*` |
| `test_api_pipeline_ext.py` | 2 | `test_run_pipeline_timeout` / `_exception` |
| `test_api_project_ext.py` | 1 | `test_create_project` |
| `test_coverage_phase4_pipeline_routes.py` | 1 | `test_run_post_without_spec` |
| `test_ui_routes_api_ext.py` | 1 | `test_unauthorized_invalid_session` |
| `test_security.py` | 1 | `test_pipeline_run_path_traversal` |

**疑似同源**：`tenant` 路由 Bearer-only 与前端 `apiFetch`（`credentials: same-origin` cookie）鉴权不匹配
→ 401。需先确认这一条主因，再决定逐条修还是统一改鉴权口径。

### C 类｜工具链 / 子进程真跑 · **27 项 / 10 文件**

| 文件 | 失败 | 主题 |
|---|---|---|
| `test_coverage_phase6_demo.py` | 8 | `TestDemoUartBuildHost`（真跑 cmake/make/demo） |
| `test_v370_track1_track4.py` | 6 | sandbox read dirs + subprocess timeout（W5/W7） |
| `test_codegen_cflags.py` | 5 | `TestVerifyCCFlags`（需真编译器验 CFLAGS） |
| `test_codegen_engine.py` | 2 | `TestCompileVerification` |
| `test_ci_run_deep.py` | 1 | `TestRunClangTidy::test_with_c_files_fails` |
| `test_pipeline_step_handlers_ut.py` | 1 | `test_gcc_fallback_with_unity_src` |
| `test_g6_g7_double_main_fix.py` | 1 | `test_g6_gpio_template_compiles_with_macro` |
| `test_coverage_phase10_review.py` | 1 | `test_stack_overflow_uint16_array` |
| `test_test_qualification.py` | 1 | `test_pipeline_error_propagated` |
| `test_step_handlers_init_deep.py` | 1 | `TestGatesContract::test_gate_status_worst_wins` |

**判据**：这些测试**不依赖 subprocess mock**（`test_coverage_phase6_demo.py` 打的是 `demo_uart`
自己的 `subprocess.run`，该模块**未迁移**，patch 仍有效）→ 失败来自真实工具链调用/环境差异，
需逐条判定「是环境缺件、还是断言过期」。

### D 类｜其它，待逐个分诊 · **18 项 / 11 文件**

`test_prompts.py` 6、`test_pipeline_prompts_ext.py` 2、`test_merge_gate.py` 2、
`test_d2_parallel_groups.py` 1、`test_repo_facts.py` 1、`test_hooks.py` 1、`test_plugins.py` 1、
`test_llm_smoke.py` 1、`test_llm_client_deep.py` 1、`test_session_index.py` 1、
`test_v380_a5_cli_split.py` 1（自身守卫：「测试里不得 `sys.path.insert`」——可能由新增测试触发）。

### 已排除

- **与 P0 修复（`fc1febc5`）无关**：闭包内 15 项（`test_api` 8 + `test_merge_gate` 2 +
  `test_api_pipeline_ext` 2 + `test_d2_parallel_groups` 1 + `test_security` 1 +
  `test_step_handlers_init_deep` 1）在工作区与 HEAD 基线**两侧逐项相同**，失败差集为空。
- **与 P0 **相关**但从未被验证**：44 项位于闭包外（`step_handlers/__init__.py:94` 转发 `gates` 符号
  → 任何 import step_handlers 子模块的测试都传递性 import `gates.py`）。**闭包构造缺陷已单独立项**。

## 4. 本轮已做（A 类修复清单）

| 文件 | 改动 | 处数 |
|---|---|---|
| `tests/test_coverage_phase5_qemu.py` | `test_qemu.subprocess.run` → `test_qemu.safe_subprocess_run` | 8 |
| `tests/test_coverage_phase5_qemu.py` | `patch.object(ccg.subprocess, "run")` → `patch.object(ccg, "safe_subprocess_run")` | 18 |
| `tests/test_step_handlers_execution_deep.py` | `execution.subprocess.run` → `execution.safe_subprocess_run` | 24 |
| `tests/test_step_handlers_steps_ext.py` | `test_c_unit.subprocess.run` → `test_c_unit.safe_subprocess_run` | 6 |
| `tests/test_step_handlers_steps_ext.py` | 2 个 ctest 测试：`subprocess.run` 只留 probe/pytest 两次，新增 `run_captured` 打桩承接 `cmake --build` + `ctest` | 2 |
| `tests/test_backlog_p1_v350.py` | `fault_inject.subprocess.run` → `fault_inject.safe_subprocess_run` | 1 |

**未改（经判定 patch 仍有效，勿动）**：
`tests/test_coverage_phase6_demo.py`（`demo_uart` 未迁移）、`tests/test_tenant_security_ei_m2b.py`
（`engine/container_executor.py` 未迁移）、`tests/test_coverage_phase5_ci.py`
（`ci/verify_c_coverage_gate` 未迁移）、`tests/test_pipeline_step_handlers_ut.py` /
`test_codegen_behavior_guardrail.py` / `test_pipeline_fault_inject.py` /
`test_pipeline_test_qualification.py` / `test_test_integration.py`（**迁移时已同步改过**，可作修法样板）。

### 4.1 验证结果（2026-09-25 实测，固定序）

| 侧 | passed | 不通过 | 合计 |
|---|---|---|---|
| **before**（`git stash` 回 `fc1febc5`，即修复前） | 45 | **138 errors** | 183 |
| **after**（本轮修复后） | **181** | **2 failed** | 183 |

命令两侧一致：`pytest <该 4 文件> -o addopts= --no-cov -p no:cacheprovider -p no:randomly -q`。

- **零回归成立**：after 的 2 项失败**全部 ⊆ before 的不通过集**（`test_find_elf_files_empty` /
  `test_c_project_tests_counted`）→ 失败差集为空；不通过数 **138 → 2**。
- 修复前大量呈现为 `ERROR` 而非 `FAILED`：mock 打空后测试**真跑** qemu / cmake / ctest，触发环境缺件与
  污染，许多用例在 setup/teardown 阶段即崩 —— 这也是「真跑子进程」的旁证（与环境无关的纯断言失败才会
  记 `FAILED`）。
- **漏网自检**（§6 两条命令）已跑：`test_coverage_phase5_qemu.py` **零残留**；剩余命中均为**未迁移**模块
  （`ci/verify_c_coverage_gate`、`cli/onboard`、`kb/cli`、`api/preview`、`engine/subprocess_executor`
  —— 逐条核源码确认仍在用 `subprocess.run`）→ **patch 有效，正确不动**。

### 4.2 残留 2 项（非死 mock 根因，转分诊）

| 用例 | 现象 | 定性 |
|---|---|---|
| `test_coverage_phase5_qemu.py::TestQemuHelpers::test_find_elf_files_empty` | 期望 `[]`，实得 3 个 elf（含同文件 `test_find_elf_files_all_locations` 写在 `<sessions_root>/project/.osh/.yuleosh/pipeline/l2/c.elf` 的产物） | **测试隔离缺陷**：`OSH_SESSIONS_DIR` 指向**会话级共享**临时根 → 同文件跨用例共享 `project/` 目录；修法需改测试取 `project_dir` 的方式（归 D 类） |
| `test_step_handlers_execution_deep.py::TestClaudeDevCProjectMetrics::test_c_project_tests_counted` | 断言 `"Source lines: 20" in user_prompt` 失败 | **断言过期**：`prompts.py:475-479`（2026-09-13 修正）已**刻意不再罗列** `Source lines` / `Test functions`（防 LLM 转述为文档指标表）→ 断言须改指 `Repository Facts` 块（归 D 类） |

> 两项在 2026-09-24 全量固定序基线中**即为 `FAILED`**（`/tmp/full-det.txt:542` / `:592`），
> 与本轮改动无关。

## 5. 验收标准（DoD）

1. **A 类归零**：上述 4 个文件不通过数 **138 → 2**（净修 136，§4.1 已实测），残留 2 项非死 mock 根因
   （§4.2，已转 D 类）。全量固定序 `failed` 预期 125 → **约 85**（−40），待全量复跑确认。
2. **基线可复现**：同一条固定序命令**连跑两次**，`failed` 数与失败用例集合完全一致。
3. **B 类**：确认「Bearer-only vs cookie」是否为主因并出具结论；是则统一鉴权口径，否则逐条修。
4. **C 类**：每条给出「环境缺件（→ skip/xfail 带理由）」或「断言过期（→ 改断言）」的二选一裁决，
   不允许留 `failed`。
5. **防复发 gate（机制项，必须做）**：
   - 任何 handler 从 `subprocess.run` 迁到 `safe_run` 时，**必须同步 grep 其测试的 patch 目标**
     （见 §6）。
   - 零回归的「影响闭包」改为 **src 侧 import 图的反向可达闭包**，禁止对 `tests/` 目录 grep 关键词。

## 6. 防复发：两条硬规则

1. **迁移即改 patch**：`patch("m.subprocess.run")` 在迁移后必然打空。正确写法是
   `patch("m.safe_subprocess_run")`（或 `m.run_captured`）；用 `patch.object(mod.subprocess, "run")`
   的等价写法是 `patch.object(mod, "safe_subprocess_run")`。
   自查命令：
   ```bash
   grep -rnE '(test_qemu|test_c_unit|c_coverage_gate|fault_inject|execution|test_integration|test_qualification)\.subprocess\.run' tests/
   grep -rnE 'patch\.object\(\s*[A-Za-z_0-9]+\.subprocess' tests/
   ```
   应返回空。
2. **闭包必须传递性**：`pipeline/step_handlers/__init__.py` 转发 `gates` 符号，
   `pipeline/safe_run.py` 被多 handler 引入 —— grep 测试文件会漏掉整类测试。

## 7. 风险与前置条件

- ~~本轮 A 类修复未经测试执行验证：会话内 shell（Bash）整轮不可用~~ ✅ **已验证**（2026-09-25，§4.1）：
  会话内 shell 已恢复，定向 A/B 实测 138 → 2、失败差集为空。
- A 类修复若出错，最坏后果是「测试仍红」（不制造新的假绿），风险可控 —— 实测未出现假绿。
- **全量固定序复跑（约 47 分钟）尚未做**：DoD 第 2 条「连跑两次失败集一致」与全量 `failed` 收敛数
  （预期 ≈ 85）待确认。

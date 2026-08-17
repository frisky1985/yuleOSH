# 事故复盘 — window-anti-pinch r20p 凌晨 RED（2026-08-17）

## 事件概述

window-anti-pinch（车窗防夹，`~/workspace/window-anti-pinch/window-anti-pinch`）
yuleOSH pipeline run-20260817-015541（r20p）**PIPELINE_EXIT=1，RED，失败于
step 32/36（P0 关键安全门禁），5 errors**。

**结论先行**：5 个报错中 4 个是工具链误报/陈旧构建态，不是代码缺陷；当前代码
手动验证全绿（391+94 CHECKS、coverage 93%）。**真正的新信号只有 1 个**：
MISRA 全量扫描 24 条业务代码违规（CI L1 拦下正确，pipeline 内部评审读陈旧报告
漏掉）。

## 根因链（4 个独立缺陷叠加）

| # | 缺陷 | 类型 | 表现 |
|---|------|------|------|
| 1 | P0 门禁 CRIT-DIV-001 注释误报 | 平台 bug | `_scan_division_by_zero` 纯正则不剥离注释，`"memcpy/memset"`、`"4/max=200"` 等注释文本被当除法 → 4 条假 critical |
| 2 | guardrail 回滚覆盖人工修复 | 平台 bug | 断点续跑 → 兜底备份（23:16 旧备份）原子写回 src → 覆盖已提交的 2b431b9 回绕修复 → ctest 从全绿变红 |
| 3 | 陈旧构建目录 | 环境/流程 | cmake-build-coverage 混入 ARM objcopy/linker 产物 → c-unit-test / integration-test 对损坏构建跑 → 假失败 |
| 4 | misra-review 读陈旧报告 | 平台 bug | misra-review 读 `.yuleosh/reports/misra-report.json`（CI 生成）。代码更新后未重跑 CI → 报告仍 0 违规 → 假绿放行 24 条真实违规（CI 全量 66 条 vs 内部评审 0 条） |

## 平台修复（4 commit，全部 RED→GREEN 回归）

| commit | 修复 | 验证 |
|--------|------|------|
| 44b889d0 | `review_critical_safety.py`：除零扫描器剥离注释+字符串字面量，维护跨行块注释状态 | 25 passed |
| ed1f9862 | `guardrail.py`：回滚前检查 src 未提交改动（git 仓库）→ 拒绝回滚 → RED 人工介入 | 28 passed |
| 3f03aee9 | `review_misra_ci.py`：`_check_report_staleness` 报告新鲜度校验，陈旧→warning 永不 passed | 37 passed（4 新回归） |
| 7e70da2 | `test_c_unit.py`：CMakeLists 变更后 build 目录自动 reconfigure — 陈旧构建假失败机制化 | 55 passed（+1 新回归 test_stale_cmakelists_triggers_reconfigure） |

规则沉淀：RULES.md §10「证据新鲜度」已追加（模板 + 仓库副本同步）。

## 防复发机制（新增护栏）

1. **P0 门禁**：注释/字符串字面量不再触发除法误报（真实除法仍检出，负例测试覆盖）。
2. **guardrail**：src/ 有未提交改动（人工/主 agent 修复）时绝不回滚，宁可 RED 让人看。
3. **misra-review**：报告比最新代码旧 → warning + `stale_report` 字段 + 推荐重跑
   `yuleosh ci run 1`；required 违规优先仍 failed。
4. **c-unit-test**：CMakeLists.txt 比 build 目录 CMakeCache.txt 新 → 步骤内自动
   reconfigure（不删目录，保留增量产物）— 陈旧构建不再导致 ctest 假失败。
5. **验收纪律**（流程层）：验收时先比 session 时间戳 vs 最新 commit 时间，session
   早于提交 = 证据过期，需重跑 pipeline。

## 遗留项（真实，按优先级）

1. **MISRA 24 条业务代码违规**（真实代码问题，r20n 回绕修复 2b431b9 引入 + 老账）
   —— window_position.c（17.7 返回值未检查 / 12.1 括号）、window_control.c
   （15.7/10.8/12.1）、hal_nvm.h（2.5 未用宏）。CI L1 拦下正确。
2. **陈旧构建目录**：`cmake-build-coverage` 混入 ARM 产物 → 清理后重建。
3. window-anti-pinch 11 commits 未推送（含 2b431b9 回绕修复）。
4. code-review 27 条陈旧 findings（引 v1.1.9/v1.1.6 spec）需重跑确认。

## 下一步

1. 修 MISRA 24 条（或补 approved deviations 到 ci-config.yaml）
2. `rm -rf cmake-build-coverage && cmake -B cmake-build-coverage -DENABLE_COVERAGE=ON` 重建
3. 推送 11 commits + 更新 TASK_STATUS（CI Layer1 按当前 misra 实际修正）
4. 重跑 pipeline（从 step 14 起，带上已提交的扫描器修复），预期 P0 门禁 /
   code-review / integration 三关转绿

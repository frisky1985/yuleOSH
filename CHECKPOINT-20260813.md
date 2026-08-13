# CHECKPOINT — 2026-08-13 CI 控制面加固 (branch gate + PRD 重试 + block 升级)

## Session Info
- Repo: /Users/stefan/workspace/tasks/yuleOSH-check (main)
- Commit: e10aa9ba (已推) — feat(ci): branch coverage gate 全链路 + PRD section 覆盖重试
- 接力来源: 上一 session 迭代上限截断，本 session 完成检视→修复→收尾

## Current Task
✅ 完成（Phase A + Phase B 全绿，收尾已推）

## Work Completed

### Phase A — branch coverage 解锁（Evaluator 发现的 gate 假绿陷阱）
- [x] gate 三处统一加 'found==0 必红'：coverage_pipeline / gcov_coverage / verify_c_coverage_gate
      （配置了 branch 阈值但无 branch 数据 → FAIL，封死 0.0>=0.0 真空通过）
- [x] ci-config 新增 c_fail_under_branch 字段（None=关闭，向后兼容）
- [x] honesty gate H9 check_coverage_branch_data（branch gate 开启但 found=0 → 红）
- [x] lcov 2.x rc 键兼容：branch_coverage 新名优先，lcov_branch_coverage 回退
- [x] **关键修复**: lcov --remove filter 步骤缺 --rc branch_coverage=1 会剥离 BRF 数据
      （lcov 2.x 每个子命令独立读 rc，capture 开了 filter 没开 → 数据被丢）
- [x] window-anti-pinch 实测: branch_rate 0.0 (found=0) → 64.81% (found=216, hit=140)
- [x] window-anti-pinch 启用 branch gate: c_fail_under_branch=60.0 (warn 不阻塞, 1b10a4a 已推)

### Phase B — PRD 重试循环
- [x] step_hermes_prd 生成后跑 section 覆盖校验 (_check_prd_section_coverage, SR-XXX/SW-XXX)
- [x] 缺失 → 带缺失清单反馈重试 ≤2 轮 (_prd_retry_prompt)
- [x] 耗尽 → best-effort 写 PRD + prd-coverage-gap.json sidecar（不落模板、不静默通过）
- [x] 新测试 12+ 全过

### 接力检视修复（本 session）
- [x] ruff 新增错误 6 个清零: UP045/PLW1510×2/BLE001×2/ISC004/DTZ005→UTC
      （src 89 ≤ 基线 90，tests 10 < 基线 15，新增 0）
- [x] 全量回归: **12585 passed / 130 skipped / 0 failed** (619.7s)
- [x] git push: yuleOSH e10aa9ba + window-anti-pinch 1b10a4a

### 后续轮次（2026-08-13 下午，老板指示"按建议推进"）
- [x] Python 环境确认/切换 3.12: 全量回归 **12588 passed / 0 failed / 127 skipped**
      （之前 13 个 pre-existing coverage 失败 = Python 3.13 环境，切换后清零）
- [x] 修复 test_ui_auth_import 过时断言（SEC-C3 fail-closed: 无 env 时 AUTH_ENABLED=True；
      历史断言 False 是 6/29 fail-open 时代的，8/2 v3.6.1 改 fail-closed 未同步；
      全量靠顺序依赖假绿，单独跑必失败 → 已改为 monkeypatch+reload 显式验证两态）
- [x] **branch gate 升级 block 语义**: run_c_coverage_check 消费 c_fail_under_branch
      （原为 record-only 不 block；新增 4 测试: 达标通过/低于 block/数据缺失必红/未配置不误伤）
- [x] 三场景真实验证（window-anti-pinch）: 64.8>=60 passed / 64.8<70 block / found=0 必红
- [x] window-anti-pinch ci-config 注释更新为 block 语义

## Next Steps
- 待全量回归确认后 push（stages/test.py + 2 测试文件）

## 待办 (老板后续决策)
- Feishu webhook 通知: 需要老板提供 YULEOSH_NOTIFY_FEISHU_URL

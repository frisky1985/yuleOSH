# Sprint Contract: yuleOSH CI 方向2 — 步骤级智能裁剪 (diff planner)

## Scope
- What: 按 git diff 只跑相关步骤，跳过无关步骤（省 LLM token / CI 时间）
- In Scope:
  - `src/yuleosh/ci/diff_planner.py`（新增）: 核心裁剪规划器
  - `src/yuleosh/pipeline/step_handlers/__init__.py`: STEP_FILE_GLOBS 元数据（旁挂 dict，不改四元组）
  - `src/yuleosh/pipeline/orchestrator.py`: 裁剪集成（profile 过滤后、执行循环前）
  - `tests/test_diff_planner.py`（新增） + `tests/test_honesty_regression_suite.py` 加 H9 用例
  - sprint-contract + checkpoint
- Out of Scope:
  - 不改 PIPELINE_STEPS 四元组形状
  - 不改 gate_policy.py（方向3 已交付，作为不可裁剪依据）
  - 不改 profile.py（方向1 已交付）
  - 默认关闭：仅显式开启（env OSH_DIFF_SKIP=1），不改变现有默认行为

## 现状证据（Evaluator 反对意见 + 代码确认，2026-08-11）
1. **Evaluator 明确反对方向2**（评分 2.0）："假 skip 是 honesty 套件点名的攻击向量；空 diff=绿；glob 误声明=静默漏跑"
2. 已存在的 diff 机器（可复用）:
   - `runner.get_changed_files(base_ref)` — git diff --name-only（失败返回 []）
   - `review_collect._collect_delta_files` — 3 源 union（committed + working tree + untracked）
   - `review_collect._matches_glob` — 真 ** glob（fnmatch 的 ** 不跨目录）
   - `review_collect._expand_header_dependents` — header 依赖展开（仅 C）
3. **现有教训**（review_collect.py L84-88）: naive delta 只扫变更 .c/.cpp 会漏 header 依赖
4. **诚实性套件攻击向量**（test_honesty_regression_suite.py）: mock 伪装/假 skip/数字不一致

## 前置门槛（Evaluator 要求，全部必须满足才能放行）
- [ ] G1: **空 diff 判红/不裁剪** — 非 git checkout / git 失败 → changed=[] → **不裁剪任何步骤**（fail-safe，绝不静默全绿）
- [ ] G2: **skip 显式报告** — 被裁剪步骤必须写入报告（session + 控制台），含原因（"diff 未触及 glob"），禁止静默消失
- [ ] G3: **跨切面步骤不可跳过** — methodology-gate / docsync-gate / requirements-trace / traceability / final-report / evidence-pack / merge-gate / review-critical-safety / test-qualification / coverage-review 无文件 glob 或全局影响 → 强制保留
- [ ] G4: **H9 honesty 用例** — 注入假 skip（diff planner 报告跳过但实际上需要跑的步骤）→ 门禁必须红
- [ ] G5: **仅 warn/info 级可裁剪** — gate_policy 为 block 的步骤严禁裁剪（复用方向3）

## Architecture Decision
- architect-lead: 小明 (Hermes)
- 元数据: `STEP_FILE_GLOBS: dict[str, list[str]]` 旁挂于 step_handlers/__init__.py（不改 PIPELINE_STEPS 四元组）
- 规划器: `diff_planner.plan_skips(steps, changed_files, gate_policy, project_dir) -> list[SkipDecision]`
  - SkipDecision = (step_key, reason)
  - 纯函数核心（可单测）+ git 收集封装
- 触发: 仅 `OSH_DIFF_SKIP=1` 显式开启（默认全跑，零回归）
- 执行位置: orchestrator profile 过滤后、步骤循环前，打印 SKIPPED 摘要 + 写入 session
- 不可裁剪集（G3）: ALWAYS_INCLUDE + gate_policy block 级 + 跨切面硬编码集

## Testable Behaviors
- [ ] B1: plan_skips 纯函数：changed=[linker.ld] → 只有 review-linker 被 skip（或按 glob）
- [ ] B2: G1: changed=[]（git 失败/空）→ 无任何 skip
- [ ] B3: G2: skip 决策带 reason，可序列化进报告
- [ ] B4: G3: 跨切面步骤（final-report/merge-gate 等）永不 skip
- [ ] B5: G5: gate_policy=block 的步骤（review-critical-safety）永不 skip
- [ ] B6: 集成：OSH_DIFF_SKIP=1 时 orchestrator 打印 SKIPPED 摘要
- [ ] B7: 默认（无 env）→ 全跑（零回归）
- [ ] B8: H9 honesty 用例：注入假 skip → 门禁红
- [ ] B9: 现有测试套件不回归

## Acceptance Criteria
| ID | Criterion | Pass Condition | Fail Condition | Priority | Owner |
|----|-----------|----------------|----------------|----------|-------|
| AC1 | G1 空 diff fail-safe | 空 diff 无 skip | 空 diff 全跳过 | P0 | 小明 |
| AC2 | G2 skip 显式报告 | skip 带 reason 写入 session | 静默消失 | P0 | 小明 |
| AC3 | G3 跨切面保留 | 关键步骤永不 skip | 被裁剪 | P0 | 小明 |
| AC4 | G5 block 级保留 | gate_policy block 步骤永不 skip | 被裁剪 | P0 | 小明 |
| AC5 | H9 honesty | 注入假 skip 门禁红 | 门禁绿 | P0 | 小明 |
| AC6 | 默认零回归 | 无 env 全跑 + 现有测试绿 | 回归 | P0 | 小明 |

## Responsibility Matrix
| Criterion | Responsible | Fallback |
|-----------|-------------|----------|
| diff_planner.py 设计 | 小明 | — |
| STEP_FILE_GLOBS 元数据 | 小明（先给 8-10 个核心 handler） | — |
| orchestrator 集成 | 小明 | — |
| H9 honesty 用例 | 小明 | — |
| 测试 + 验收 | 小明（Evaluator 角色） | — |

## Negotiation Log
| Round | Party | Action | Notes |
|-------|-------|--------|-------|
| 1 | Evaluator | 反对 | 假 skip 是点名攻击向量；空 diff=绿；glob 误声明静默漏跑 |
| 2 | 老板 | 拍板 | "继续推进，完成后观察 CI"（2026-08-11） |
| 3 | Evaluator | 门槛 | G1-G5 前置门槛必须全部满足才放行 |

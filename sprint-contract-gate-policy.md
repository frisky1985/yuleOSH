# Sprint Contract: yuleOSH CI 方向3 — 门禁强度矩阵 (Gate Policy Matrix)

## Scope
- What: 把 pipeline 步骤的 verdict 处置从"一刀切软失败"显式化为**三档门禁强度矩阵**（block / warn / info）
- In Scope:
  - 新增 `src/yuleosh/ci/gate_policy.py`：默认矩阵 + `resolve_gate()` 纯函数 + YAML 覆盖加载
  - `ci/config.py`：CiConfig 增加 `gate_policy` 字段 + YAML 解析（`ci.gate_policy` 节）
  - `pipeline/orchestrator.py`：`_propagate_step_verdict` 按门禁强度分流（block → 中断；warn → 现状记 errors；info → 仅记录）
  - 新增 `tests/test_gate_policy.py`
  - sprint-contract 文件 + checkpoint
- Out of Scope:
  - 不改 PIPELINE_STEPS 注册表形状（四元组不变）
  - 不改 profile.py（方向1 后续）
  - 不做 diff 裁剪（方向2 明确暂缓）
  - 不动 layer_executor 聚合逻辑（保持现状 passed/failed 二元）

## 现状证据（Evaluator 确认，2026-08-11）
1. `_propagate_step_verdict`（orchestrator.py:565）：artifact JSON `status=failed` → step 标记 failed + session.errors 记录，**从不中断 pipeline**（一刀切软失败）
2. 已存在的同构先例：`MisraProfile.block_on`（config.py:96）、`code_categories.action/block_on`（config.py:169）、`is_strict()` / `is_misra_fail_fast()`（config.py:629/638）、review finding `severity`（review_linker.py: critical/major/minor/info）
3. ⛔ `review-critical-safety` 标注 "P0 GATE" 但实际是软门禁（verdict failed 不断链）——语义与实现不符，方向3 修复
4. CIResult.add_stage status 是自由字符串（passed/failed/error/running），天然支持扩展

## Architecture Decision
- architect-lead: 小明 (Hermes)
- 门禁强度三档:
  - `block`: verdict failed → **中断 pipeline**（依赖步骤不再执行，session.status=failed）
  - `warn`: verdict failed → 标记 failed + 记 errors + **继续**（现状行为，默认）
  - `info`: verdict failed → 仅 stage 记录，不进 errors（纯信息）
- 默认矩阵（DEFAULT_GATE_POLICY）:
  - block: review-critical-safety, merge-gate, c-coverage-gate, coverage-gate, test-qualification（关键门禁）
  - warn: 其余 review/gate 步骤（保持现状）
  - info: spec-check, final-report（低风险记录）
- 覆盖机制: `ci-config.yaml` → `ci.gate_policy: {step_key: block|warn|info}`，合并到默认矩阵（显式覆盖优先）
- 纯函数 `resolve_gate(step_key, policy=None) -> str`，无 IO，可单测

## Testable Behaviors
- [ ] B1: `resolve_gate()` 对未声明步骤返回默认档（warn）
- [ ] B2: 默认矩阵：review-critical-safety=block、merge-gate=block、普通 review=warn
- [ ] B3: YAML 覆盖：ci-config.yaml 指定 step 覆盖默认档
- [ ] B4: block 档 verdict=failed → orchestrator 中断（后续步骤不执行）
- [ ] B5: warn 档 verdict=failed → 继续执行 + errors 记录（现状保持）
- [ ] B6: info 档 verdict=failed → 仅记录，errors 无新增
- [ ] B7: 现有 26 步注册表形状不变
- [ ] B8: 现有测试套件不回归（pytest 关键文件）

## Acceptance Criteria
| ID | Criterion | Pass Condition | Fail Condition | Priority | Owner |
|----|-----------|----------------|----------------|----------|-------|
| AC1 | resolve_gate 纯函数 | 单测通过，三档语义正确 | 返回错误档位 | P0 | 小明 |
| AC2 | block 中断生效 | 注入 block 档 failed verdict → pipeline 中断 | 继续跑完 | P0 | 小明 |
| AC3 | warn 行为保持 | 默认档 verdict failed → 现状行为（记 errors 继续） | 行为改变/回归 | P0 | 小明 |
| AC4 | YAML 覆盖 | ci-config.yaml gate_policy 节生效 | 覆盖被忽略 | P0 | 小明 |
| AC5 | 无回归 | pytest 相关文件全绿 | 新红 | P0 | 小明 |

## Responsibility Matrix
| Criterion | Responsible | Fallback |
|-----------|-------------|----------|
| gate_policy.py 设计 | 小明 | — |
| config.py 解析 | 小明 | — |
| orchestrator 分流 | 小明 | — |
| 测试 + 验收 | 小明（Evaluator 角色） | — |

## Negotiation Log
| Round | Party | Action | Notes |
|-------|-------|--------|-------|
| 1 | 三角色 | 讨论 | Planner/Generator/Evaluator 一致推荐方向3先行（4.5/4-6人天/4.5） |
| 2 | 老板 | 拍板 | "按建议推进"（2026-08-11） |
| 3 | Evaluator | 约束 | 默认保行为；block 默认给关键门禁；杜绝降级默认 |

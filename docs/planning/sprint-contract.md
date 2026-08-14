# Sprint Contract: Pipeline 优化 — 审查锚定 + 断点续跑 + fail-fast

> 谈判方：Generator (Hermes) / Evaluator (Hermes 自评) / architect-lead (Hermes)
> 日期：2026-08-12
> 背景：window-anti-pinch run-20260812-033339 完成 34/34 步但带 6 个 verdict errors——
> 根因：codegen 被护栏拒绝（deployed=[]），但代码审查步骤照常执行、审的是基线/失败产物。

## Scope

### What（本次范围）
yuleOSH pipeline 引擎 5 项优化：
1. **审查锚定部署状态**：代码审查步骤读 `.yuleosh/reports/codegen-deploy.json`，本次 run 无代码部署时 honest-skip（不再审基线/失败产物）
2. **INCOMPLETE verdict 传播 + 合格性测试 fail-fast**：`_propagate_step_verdict` 识别 INCOMPLETE；test-qualification 无系统级测试文件时提前判定
3. **断点续跑**：`yuleosh pipeline run --from-step N <spec>`（复用已存在 artifacts）
4. **审查输入裁剪**：LLM 审查只喂 deployed 变更文件（diff 聚焦）
5. **报告 summary 分级**：绿/黄/红 + Feishu 通知打通

### In Scope
- `src/yuleosh/pipeline/` 各 handler + orchestrator
- `src/yuleosh/ci/gate_policy.py`
- `src/yuleosh/cli/` pipeline run 入口
- 单测（tests/ 新增或扩展）

### Out of Scope
- 自动内容寻址步骤缓存（hash 复用）——设计留接口，本期只做 `--from-step`
- 新审查步骤的添加/删除
- window-anti-pinch 项目代码本身

## Architecture Decision
- **审查锚定中心**：新增 `src/yuleosh/pipeline/deploy_state.py`，唯一事实源（读 codegen-deploy.json）
- **skip 语义**：`maybe_skip_code_review(session, step_key)` 工具——无部署时写 `status=skipped` JSON 报告（复用 handler_base._write_skip_report 语义），verdict 传播对 skipped 不记 errors
- **P0 门禁例外**：review-critical-safety 永远执行（全局安全门禁不因部署状态关闭）
- **verdict 扩展**：`_propagate_step_verdict` 增加 `incomplete` → 按 gate 强度处理（block gate → 中断）

## Testable Behaviors
- B1: codegen-deploy 报告 skipped_codegen_failed 时，代码审查步骤输出 status=skipped
- B2: skipped 审查不进 session.errors，pipeline 不标红
- B3: codegen 正常部署时，代码审查照常执行（回归：不误伤真审查）
- B4: test-qualification 无测试文件 → status=incomplete 且 (block gate) 中断 pipeline
- B5: `--from-step 15` 从第 15 步开始，前 14 步标记 skipped/保留
- B6: review-critical-safety 即使无部署也执行

## Acceptance Criteria
| ID | Criterion | Pass Condition | Fail Condition | Priority | Owner |
|----|-----------|----------------|----------------|----------|-------|
| A1 | 审查锚定 skip | 重跑 window-anti-pinch：6 errors 中代码审查类 error 消失，替换为 skipped | 代码审查仍审基线代码 | P0 | Hermes |
| A2 | P0 门禁存活 | critical-safety 仍执行并通过 | critical-safety 被 skip | P0 | Hermes |
| A3 | INCOMPLETE 传播 | test-qualification incomplete → 记 error/中断（按 gate） | incomplete 静默通过 | P0 | Hermes |
| A4 | --from-step | 从 N 步续跑成功，前序 artifacts 被复用 | 报错/丢 artifacts | P1 | Hermes |
| A5 | 单测 | 新增/更新的单测全绿（pytest tests/ -x） | 单测红 | P0 | Hermes |
| A6 | 回归 | 现有测试套件不破坏（pytest tests/ 全绿） | 现有测试红 | P0 | Hermes |

## Responsibility Matrix
| Criterion | Responsible | Fallback |
|-----------|-------------|----------|
| A1-A3 | pipeline handlers + orchestrator | deploy_state 模块 |
| A4 | cli/main.py + orchestrator | -- |
| A5-A6 | Hermes | -- |

## Negotiation Log
| Round | Party | Action | Notes |
|-------|-------|--------|-------|
| 1 | Generator | 提案 | 老板确认 7 项优化，本期收 5 项（缓存降级为 --from-step） |

## Done Definition
- A1-A6 全过
- window-anti-pinch 重跑：`completed` 且 errors 不含代码审查类 failed（允许 prd-review WARNING 类文档审查保留）
- git 推送

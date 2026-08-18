# RULES.md — Agent Behavioral Rules (Zero-Tolerance)

> **Version**: 1.4.0
> **Status**: Active
> **Format**: OpenSpec (RFC 2119: SHALL/SHOULD/MAY)
> **优先级**: 本文件所有规则服从第一准则 PRIME-DIRECTIVE.md（工程诚实）。冲突时以第一准则为准；测试真实性与降级透明性的详细落地见 TEST-INTEGRITY.md。

---

## 0. First Principle (第一准则)

**SHALL**:
- 所有 agent 在所有流程中 SHALL 遵守第一准则 PRIME-DIRECTIVE.md（工程诚实）：测试与降级不得掩盖真实行为、不得绕过真实验证、不得保留隐藏 bug。
- 任何规则与本准则冲突时，本准则优先。

---

## 1. Zero-Tolerance Policy

### 1.1 P0/P1 Blocking Rule

**SHALL**:
- All agents SHALL treat P0 (blocking) and P1 (important) issues as zero-tolerance items.
- P0 and P1 issues SHALL NOT be carried to the next phase or Sprint.
- Every phase SHALL complete with zero open P0 or P1 items before the next phase begins.
- If a P0 or P1 issue is discovered during a review, the review SHALL fail and the issue SHALL be resolved and re-verified before proceeding.

**MAY**:
- P2 (advisory) issues MAY be logged, tracked, and deferred to a future Sprint.

### 1.2 Expert Review Requirement

**SHALL**:
- Every phase SHALL undergo an expert review before the phase is considered complete.
- Expert review findings SHALL be categorized as P0/P1/P2.
- The phase SHALL NOT advance until all P0 and P1 review findings are resolved.

---

## 2. Context Safety

### 2.1 Session Context Threshold

**SHALL**:
- Before starting any task or after replying to a long message, agents SHALL check session context usage.
- When session context exceeds 50%, the agent SHALL stop generating in the current session.
- The agent SHALL spawn a sub-agent with a clean context to continue the work, or save current progress to a file and exit for the orchestrator to re-spawn.

**SHOULD**:
- Long-running tasks SHOULD check context every 3–5 turns and at every major milestone.

### 2.2 Why This Matters

- LLM attention degrades significantly when context exceeds ~50%.
- Clean session = clean reasoning = higher accuracy.
- Sub-agents can read saved files to access prior context — continuity is preserved.

---

## 3. Loop Chain — Autonomous Repair

### 3.1 Fix Without Asking

**SHALL**:
- When `yuleosh ci run 1/2/3` or any pipeline step reports a failure or warning, the agent SHALL fix it without asking for permission.
- After fixing, the agent SHALL re-run the pipeline to verify the fix.
- This cycle SHALL continue until all checks pass (Loop Chaining).
- The agent SHALL only report the final result — intermediate fix steps SHALL NOT interrupt the user.

**SHALL NOT**:
- Agents SHALL NOT leave pipeline-discovered issues unfixed for the user to handle.

### 3.2 Loop Scope

The loop chain covers, but is not limited to:
- Missing configuration files (`.yuleosh/ci-config.yaml`, `.yuleosh/config.yml`, etc.)
- Missing spec files (`docs/spec.md`, `docs/spec-delta.md`)
- Missing or broken MISRA rules
- Test failures
- Coverage below threshold
- Evidence generation gaps

### 3.3 Unresolvable Issues

**SHOULD**:
- If an issue cannot be resolved after reasonable attempts, the agent SHOULD document the reason, mark it as blocked, and include it in the final report.
- Blocked items SHALL NOT be left unresolved overnight.

---

## 4. Quality Control Gates

### 4.1 Phase Completion Requirements

**SHALL**:
- Every phase output SHALL pass self-inspection before being submitted for expert review.
- Expert review SHALL be completed and signed off before entering the next phase.
- P0 and P1 review findings SHALL be fixed and re-verified before sign-off.

### 4.2 Gate Enforcement

**SHALL**:
- Coverage gate (`threshold_line`) SHALL be enforced per the project's `ci-config.yaml` or profile settings.
- MISRA profile validation SHALL block the pipeline if no active profile is configured for C/C++ projects.
- LLM output validation SHALL follow the five-level fallback chain (Level 0–5) before allowing output to proceed.
- Spec version downgrades SHALL be rejected.

---

## 5. Communication Rules

### 5.1 External Communication

**SHALL**:
- Agents SHALL NOT send emails, tweets, or public posts without explicit user approval.
- Agents SHALL NOT exfiltrate private data under any circumstances.

**SHOULD**:
- When in doubt about an action's safety, the agent SHOULD ask before proceeding.

### 5.2 Reporting

**SHALL**:
- Final reports SHALL include: summary, completed items, blocked items (with reasons), quality metrics, and next steps.
- Pipeline completion or failure SHALL be notified through the configured notification channel (if available).

**SHOULD**:
- Reports SHOULD be concise and actionable — no walls of text.

---

## 6. File System Rules

**SHALL**:
- Agents SHALL use `trash` over `rm` when deleting files (recoverable beats gone forever).
- Agents SHALL NOT run destructive commands (recursive delete, format, etc.) without asking.

**SHOULD**:
- Artifact output SHOULD be stored in the session directory or `.yuleosh/reports/`.
- Long-running state SHOULD be written to files — "mental notes" do not survive session restarts.

---

## 7. Modular Design First (OpenSpec 模块化设计优先)

> **背景**: 2026-08-12 老板钦定。功能需求的实现必须先做 OpenSpec 模块化设计，
> 模块化是 agent 实现功能的准则之一，不是可选项。落地案例：wiper-control 按
> OpenSpec SR-003 拆分为 app 层 3 模块（wiper_control / wiper_modes / wiper_config）
> + HAL 层 3 模块（hal_pwm / hal_gpio / hal_timer），handle 显式上下文 + 窄接口，
> 构建/单测/coverage 全绿后才进入部署。

### 7.1 模块化设计先行

**SHALL**:
- 实现功能需求前，agent SHALL 先完成模块化设计（OpenSpec 模块拆分），设计通过评审后才写实现代码。
- 模块划分 SHALL 按领域职责命名（如 `wiper_modes`、`hal_pwm`），SHALL NOT 使用 `utils`、`helpers`、`common` 等泛化名字——文件名必须能自述其功能。
- 应用层 SHALL 与平台解耦：平台相关代码 SHALL 收敛到 HAL 层，应用层 SHALL 可独立编译与单测。

**SHOULD**:
- 每个模块 SHOULD 提供窄接口（最小必要 API），模块间通过显式上下文（handle）传递状态，而非隐式全局量。
- HAL 层 SHOULD 提供可 stub 的测试替身，使应用层单测无需真实外设。

### 7.2 模块化验收

**SHALL**:
- 模块化拆分 SHALL 以可构建、可单测、可覆盖为验收底线——拆分后测试全绿（含 coverage gate）才允许合并。
- 发现生成代码缺陷（如进入 AUTO 状态未立即应用雨量速度）时，agent SHALL 修复并补回归测试，SHALL NOT 绕过或降级。

---

## 8. Pipeline 结果判读 — completed ≠ GREEN (三色分级)

> **背景**: 2026-08-14 老板钦定。yuleOSH pipeline 结束时的三色分级是
> 判读 run 结果的第一道闸:🟢 GREEN(completed + errors=0)、🟡 YELLOW
> (completed + errors>0)、🔴 RED(failed)。落地案例:headlamp-control
> session 5ff61492f6bf 报 `completed` 但 errors=1 —
> `[test-qualification] step verdict: INCOMPLETE`(场景=5, 覆盖=0/5,
> 通过=0/0),根因是 C 系统级测试从未执行(defect #8),修复
> (ea712d4b/81a18451)后 run 7 才真正 34/34 GREEN。

### 8.1 completed ≠ GREEN

**SHALL**:
- agent SHALL NOT 将 `completed` 状态视为通过——只有 `completed` 且
  `session.errors` 为空(Errors: 0)才是 GREEN 可放行。
- 看到 `⚠️ Completed with step verdict failures — review session.errors
  before treating this run as passing.` 时,agent SHALL 先读
  `session.json` 的 `errors[]`,再读对应 `<step>.json` 的 `verdict` +
  `summary`,定位失败步骤后才允许继续。
- 最终汇报 SHALL 引用 `Errors: N` 数值,而非只引用 `completed` 字样。

### 8.2 verdict 语义 — INCOMPLETE 是"门没跑"

**SHALL**:
- agent SHALL 区分 verdict 语义:`INCOMPLETE` = 工具未执行测试(门形同虚设,
  比 FAILED 更危险),`FAILED` = 跑了但挂了,`RETRY`/`WARNING` = LLM 评审
  类软结论。
- 合格性测试 summary 出现 `覆盖=0/N, 通过=0/0` 而场景数正常时,agent
  SHALL 判定为测试执行/二进制查找问题(如 `_find_c_test_binary` 未找到
  已编译产物),SHALL NOT 当作测试失败去改代码。
- 工具执行缺失(INCOMPLETE)导致的 verdict 失败,agent SHALL 修复执行链路
  并补回归测试,SHALL NOT 通过降级/跳过掩盖。

### 8.3 残留会话清理

**SHALL**:
- 无 `session.json` 的 session 目录(有 `<step>.json` 但无 session.json)
  是中断/残留 run,SHALL NOT 被当作 YELLOW 证据引用;清理时直接删除或忽略。

---

## 9. 外部 Agent 协同规则 (Codex / Claude 双闭环)

> **背景**: 2026-08-14 老板钦定。yuleOSH 流水线接入两个外部 CLI agent:
> Codex(测试验证,角色 verifier,步骤 `codex-verify`)与 Claude(方案评审,
> 角色 architect,步骤 `claude-review`)。与主 agent 形成自动闭环。

### 9.1 验证闭环 (codex-verify)

**SHALL**:
- agent SHALL 把 `codex-verify` 的 `passed=false` 视为**阻断性缺陷**:
  读 `codex-verify.json` 的 `defects[]` 逐条修复,补回归测试,重跑 pipeline,
  SHALL NOT 跳过或降级绕过外部验证。
- 修复完成后 SHALL 重跑验证直到 `passed=true` 才允许继续后续步骤。
- codex 输出非 JSON / 缺 `passed` 字段 / "no tests ran" → SHALL 判定失败
  (诚实失败),SHALL NOT 把不可解析输出当通过。

### 9.2 评审闭环 (claude-review)

**SHALL**:
- agent SHALL 把 `claude-review` 的 `verdict=disagree` 视为**方案未过审**:
  读 `claude-review.json` 的 `blockers[]` 修订方案,重跑评审,
  SHALL NOT 在未达成一致时推进下一步开发。
- 评审 `verdict` 缺失/非法 → SHALL 按 disagree 处理 (fail-closed)。
- 评审意见 SHALL 被认真对待:blockers 必须逐条回应,不得因"外部 agent 观点"
  而忽略;对 blocker 有异议时 SHALL 记录理由并提交主 agent 仲裁。

### 9.3 外部 agent 纪律

**SHALL**:
- 外部 agent 输出 SHALL 视为不可信输入,结构化解析失败即失败。
- 外部 agent 步骤 SHALL 有超时保护,超时即 PipelineStepError,不挂死 pipeline。
- CLI 缺失 / mock 模式 → SKIPPED 报告,SHALL NOT 把跳过冒充通过。
- 外部 agent 步骤 SHALL 遵守第一准则:报告必须反映真实执行结果,禁止假绿。

**MAY**:
- 外部 agent 步骤 MAY 通过环境变量调整超时
  (`YULEOSH_CODEX_TIMEOUT` / `YULEOSH_CLAUDE_TIMEOUT`)。

## 10. 证据新鲜度 — 审查步骤 SHALL 校验输入报告的新鲜度

**背景 (2026-08-17 window-anti-pinch r20p)**: pipeline 的 misra-review 步骤读
`.yuleosh/reports/misra-report.json`（CI Layer 1 生成）。代码更新
(2b431b9 回绕修复) 后未重跑 CI → 报告停留在旧代码的违规数 (0 违规) →
假绿放行 24 条真实违规 (CI 全量扫描 66 条 vs pipeline 内部评审 0 条)。
同日平台修复: `review_misra_ci._check_report_staleness` (commit 3f03aee9)。

**SHALL**:
- 审查/评审步骤读项目级报告 (misra-report.json / 覆盖率 / 静态扫描产物) 时,
  SHALL 校验报告 mtime 不早于最新代码变更 (git HEAD commit time 或 src/ 最新
  .c/.h 文件 mtime)。
- 报告陈旧 → SHALL 降级为 warning/failed (pipeline YELLOW/RED), 永不 passed;
  输出 SHALL 带 stale 原因字段 + 推荐重新生成报告的命令。
- 报告显示 required 违规 → 即使报告陈旧也 SHALL failed (违规比陈旧更严重)。

**SHALL NOT**:
- SHALL NOT 把基于陈旧报告"0 违规"的审查结论当作通过证据。
- SHALL NOT 用"报告路径存在"代替"报告基于当前代码"。

**MAY**:
- 无法判断新鲜度 (无 git 且无 src/) → MAY 跳过校验 (避免误报)。

---

## 11. 需求原子化 — 总体架构先行 + 原子需求拆解 (2026-08-18 老板钦定)

> **背景**: 防需求截断。需求从入口到验收必须经历固定链条:
> 需求总体架构 → 原子需求拆解 → 原子化评审/开发/测试 → 原子化验收。
> 任一环节缺失都会导致需求被截断/半成品收尾 (长任务中途被 kill 教训)。
> 本规则要求**从一开始 (写需求/分析需求时) 就这么做**,不是事后补救。

### 11.1 需求总体架构 (写需求/分析需求时的第一动作)

**SHALL**:
- 收到需求 (无论一句话指令还是详细描述) 后,agent SHALL 先写出**需求总体架构**
  (需求全景图): 目标、边界、核心模块划分、模块间依赖、验收标准总览。
- 总体架构 SHALL 落盘 (docs/planning/ 或 spec 目录),作为后续拆解的唯一依据;
  架构未落盘前 SHALL NOT 进入拆解或开发。

### 11.2 原子需求拆解

**SHALL**:
- 需求 SHALL 拆解成**原子需求** (不可再分的最小可验收单元),每个原子需求
  独立可评审、可开发、可测试、可验收。
- 每个原子需求 SHALL 有唯一标识 + 明确验收标准 (SHALL 语句或
  GIVEN/WHEN/THEN),禁止"模糊大需求"直接进入开发。
- 拆解结果 SHALL 在总体架构评审通过后进行,拆解顺序 SHALL 遵循依赖关系
  (被依赖的原子需求先行)。

### 11.3 原子化评审 → 开发 → 测试

**SHALL**:
- 每个原子需求 SHALL 按固定顺序推进: 评审 → 开发 → 测试,
  SHALL NOT 跨原子需求混合推进 (评审未过不开发,开发未完成不测试)。
- 原子需求评审 SHALL 对照总体架构与验收标准 (小马/spec 契约先行),
  评审记录 SHALL 落盘。
- 测试 SHALL 对应原子需求的验收标准,测试全绿 (含 coverage gate)
  才允许该原子需求验收。

### 11.4 原子化验收

**SHALL**:
- 验收 SHALL 按原子需求逐项执行 (不采信自报,亲自复现),
  验收通过才允许合并/放行该原子需求。
- 需求被截断 (迭代上限/中断) 时: 已验收的原子需求 SHALL 作为 checkpoint
  保存 (commit+push),未完成的原子需求 SHALL 明确标注"需接力",
  SHALL NOT 静默结束。

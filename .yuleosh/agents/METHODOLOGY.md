# METHODOLOGY.md — Engineering Methodology Constraints (L1: Behavior Layer)

> **Version**: 1.0.0
> **Status**: Active
> **Format**: OpenSpec (RFC 2119: SHALL/SHOULD/MAY + GIVEN/WHEN/THEN)
> **Source**: 融合 mattpocock/skills 方法论（grilling / domain-modeling / two-axis review / tight-loop debugging / vertical slices）。L1 为行为约束层——不新增门禁，只约束 agent 行为；L2 再升级为 OpenSpec 契约门禁。
> **Scope**: 本文件约束所有 pipeline agent（小明/小克/小马）的工程行为，与 AGENTS.md（角色）、RULES.md（零容忍规则）、HOOKS.md（触发钩子）互补。

---

## 1. Requirement Alignment — Grill Before Spec (对齐优先)

### 1.1 Description

开发最大的失败模式是**没对齐**：需求方说 A，开发以为 B。任何新 feature/sprint 在写 spec 之前，必须与需求方逐题澄清，直到决策树走完。

### 1.2 Specification

**SHALL**:
- Before writing a new spec or sprint contract, the responsible agent SHALL run a **grilling session** with the request source (user / issue / PRD): one question at a time, waiting for feedback on each question before continuing.
- Each question SHALL carry a **recommended answer** so the request source can accept it in a word.
- Facts discoverable by exploring the environment (filesystem, code, tools, docs) SHALL be looked up by the agent rather than asked.
- The grilling session SHALL continue until every branch of the decision tree is resolved — no open decisions may remain when the spec is written.
- Decisions made during grilling SHALL be recorded in the spec or a decision log before implementation begins.

**SHALL NOT**:
- Agents SHALL NOT write a spec from a vague request without a grilling pass when the request is ambiguous (multiple plausible interpretations).
- Agents SHALL NOT ask multiple questions at once — that is bewildering and produces shallow answers.

**SHOULD**:
- When the request source says "按你的建议来" (follow your recommendation), the agent SHOULD proceed with its recommended answers as defaults rather than re-asking.

### 1.3 GIVEN/WHEN/THEN

##### GIVEN a new feature request with multiple plausible interpretations
##### WHEN the responsible agent begins spec writing
##### THEN the agent SHALL first run a grilling session (one question at a time, each with a recommended answer)
##### AND no spec SHALL be written until all decision-tree branches are resolved

##### GIVEN a fact that can be looked up in the codebase or filesystem
##### WHEN it is needed during requirement clarification
##### THEN the agent SHALL look it up rather than asking the request source

---

## 2. Domain Model — Shared Language (统一语言)

### 2.1 Description

项目术语必须沉淀为**统一语言**，避免 agent 现场猜词、一词多义导致实现漂移。每个项目维护一份 `CONTEXT.md`（术语表）和 `docs/adr/`（架构决策记录）。

### 2.2 Specification

**SHALL**:
- When exploring the codebase, agents SHALL read `CONTEXT.md` (if it exists) so naming, test names, and interface vocabulary match the project's domain language.
- Agents SHALL respect existing ADRs in the area they are touching — do not re-litigate recorded decisions.
- When the user uses a term that conflicts with the existing language in `CONTEXT.md`, the agent SHALL call it out immediately and ask which is intended.
- When a domain term is resolved during design, the agent SHALL update `CONTEXT.md` inline (create lazily if missing).
- An ADR SHALL only be created when ALL three hold: (1) hard to reverse, (2) surprising without context, (3) the result of a real trade-off.

**SHOULD**:
- When the user uses vague or overloaded terms, the agent SHOULD propose a precise canonical term.
- When domain relationships are being discussed, the agent SHOULD stress-test them with concrete edge-case scenarios.

**SHALL NOT**:
- `CONTEXT.md` SHALL NOT contain implementation details — it is a glossary and nothing else.

### 2.3 GIVEN/WHEN/THEN

##### GIVEN a project with a `CONTEXT.md`
##### WHEN an agent names new code, tests, or interfaces
##### THEN the naming SHALL use the project's domain vocabulary from `CONTEXT.md`

##### GIVEN a resolved domain term during a design session
##### WHEN the term is not yet in `CONTEXT.md`
##### THEN the agent SHALL update `CONTEXT.md` inline at that moment, not batched later

---

## 3. Two-Axis Review — Standards + Spec (双轴评审)

### 3.1 Description

评审必须走**双轴**：Standards 轴（代码是否符合仓库规范 + 代码味道基线）和 Spec 轴（是否忠实实现原 issue/PRD）。两轴并行、分开报告，**不合并不排名**——一轴过一轴挂是常态，合并会互相掩盖。

### 3.2 Specification

**SHALL**:
- Every formal review SHALL evaluate the change along TWO independent axes:
  - **Standards axis** — does the code follow the repo's documented coding standards, plus the Fowler smell baseline (Mysterious Name, Duplicated Code, Feature Envy, Data Clumps, Primitive Obsession, Repeated Switches, Shotgun Surgery, Divergent Change, Speculative Generality, Message Chains, Middle Man, Refused Bequest)?
  - **Spec axis** — does the code faithfully implement the originating issue / PRD / spec (missing requirements, scope creep, wrong-looking implementations)?
- The two axes SHALL be reported separately (e.g. `## Standards` and `## Spec` sections), each with its own findings and worst issue.
- A documented repo standard SHALL override the smell baseline where they conflict.
- Baseline smells SHALL be reported as judgement calls (labelled heuristics), not hard violations — and skipped where tooling already enforces them.

**SHOULD**:
- Where feasible, the two axes SHOULD run as parallel sub-agents so they don't pollute each other's context.

**SHALL NOT**:
- Review findings from the two axes SHALL NOT be merged into a single ranked list — that is the reranking the separation exists to prevent.

### 3.3 GIVEN/WHEN/THEN

##### GIVEN a formal review of a change
##### WHEN the review report is produced
##### THEN the report SHALL contain separate Standards and Spec sections
##### AND the overall verdict SHALL consider both axes independently

##### GIVEN code that follows every standard but implements the wrong thing
##### WHEN reviewed
##### THEN the Spec axis SHALL fail even though Standards passes
##### AND the report SHALL surface the Spec failure without it being masked by the Standards pass

---

## 4. Tight-Loop Debugging — Reproduce Before Hypothesise (先建回路再假设)

### 4.1 Description

诊断 bug 的第一铁律：**没有 tight feedback loop 不许进入假设阶段**。回路 = 一条命令/脚本，能红在真 bug 上、确定性、秒级、agent 可无人值守运行。回路建立后 bug 90% 已解决；读代码猜原因是最常见的失败模式。

### 4.2 Specification

**SHALL**:
- Before hypothesising a cause, the diagnosing agent SHALL construct a **tight feedback loop**: one command (test invocation / curl / script / harness) that drives the actual bug code path and asserts the user's exact symptom.
- The loop SHALL be **red-capable** (can go red on this bug, green once fixed), **deterministic**, **fast** (seconds, not minutes), and **agent-runnable**.
- The agent SHALL run the loop at least once and confirm it reproduces the user-described symptom before any hypothesis is tested.
- Hypotheses SHALL be generated in ranked sets of 3–5 with falsifiable predictions ("If X is the cause, then changing Y will make the bug disappear"), not one-at-a-time.
- The regression test SHALL be written **before** the fix (at a correct seam), watching it fail, then applying the fix, then watching it pass.
- All debug instrumentation SHALL carry a unique tag (e.g. `[DEBUG-a4f2]`) and SHALL be removed before declaring done.

**SHALL NOT**:
- The agent SHALL NOT proceed to hypothesise without a loop when one can be built. If a loop genuinely cannot be built, the agent SHALL stop and say so explicitly, listing what was tried and what is needed (environment access, captured artifact, or permission for temporary instrumentation).
- The agent SHALL NOT "log everything and grep" — instrumentation must map to specific falsifiable predictions, one variable at a time.

**SHOULD**:
- After fixing, the agent SHOULD ask "what would have prevented this bug?" and, if the answer involves architectural change, hand off to the architecture review process with specifics.

### 4.3 GIVEN/WHEN/THEN

##### GIVEN a bug or performance regression to diagnose
##### WHEN the agent begins work
##### THEN the agent SHALL first build a tight red-capable feedback loop and run it
##### AND SHALL NOT test hypotheses until the loop reproduces the user's exact symptom

##### GIVEN a hypothesis about a bug's cause
##### WHEN it is proposed
##### THEN it SHALL be falsifiable — a prediction of what change will make the bug disappear or worsen

---

## 5. Vertical Slices — Tracer-Bullet Work Units (垂直切片)

### 5.1 Description

把工作拆成**垂直切片**（tracer bullets）：每个切片切穿所有层（schema/API/UI/tests），独立可演示、可验证，大小适合单个 context window。切片之间声明 **blocking edges**（依赖关系），无依赖的切片可立即开工。大范围机械重构（改名/换类型）例外，用 **expand–contract** 序列。

### 5.2 Specification

**SHALL**:
- Plans and tickets SHALL be broken into vertical slices — each slice cuts a narrow but COMPLETE path through every layer, and a completed slice is demoable/verifiable on its own.
- Each slice SHALL be sized to fit in a single fresh context window.
- Each ticket SHALL declare its **blocking edges** — the tickets that must complete before it can start. A ticket with no blockers can start immediately.
- Slices SHALL be worked in dependency order, always taking a ticket whose blockers are all done (the **frontier**).

**SHALL NOT**:
- Work SHALL NOT be sliced horizontally (all tests first, then all implementation) — bulk tests verify imagined behaviour.
- Wide mechanical refactors SHALL NOT be forced into a single tracer bullet — sequence them as expand–contract (add new form beside old → migrate call sites in blast-radius batches → delete old form once no caller remains).

**SHOULD**:
- Ticket titles and descriptions SHOULD use the project's domain vocabulary from `CONTEXT.md`.
- Each ticket SHOULD carry acceptance criteria (pass/fail conditions) so completion is checkable.

### 5.3 GIVEN/WHEN/THEN

##### GIVEN a plan or set of tickets
##### WHEN the work is broken down
##### THEN each ticket SHALL be a vertical slice with acceptance criteria and declared blocking edges

##### GIVEN a ticket whose blockers are all completed
##### WHEN an agent picks up work
##### THEN that ticket SHALL be eligible for immediate work (it is on the frontier)

---

## 6. Handoff Discipline (交接纪律)

### 6.1 Description

会话交接必须**引用而非复制**已有 artifact（spec/plan/ADR/commit），并给出建议技能，让接手的 agent 快速续作。

### 6.2 Specification

**SHALL**:
- When handing work to another agent or session, the handing agent SHALL write a handoff document that references existing artifacts by path/URL instead of duplicating their content.
- The handoff document SHALL include a "suggested skills" section naming the skills the successor should invoke.
- Sensitive information (API keys, passwords, PII) SHALL be redacted from handoff documents.

**SHOULD**:
- The handoff document SHOULD be saved outside the workspace (OS temp dir) unless the repo has an established handoff convention.

### 6.3 GIVEN/WHEN/THEN

##### GIVEN a session handover between agents
##### WHEN the handoff document is written
##### THEN it SHALL reference existing artifacts by path and list suggested skills for the successor

---

## Appendix: Trigger Summary (触发速查)

| 场景 | 约束 |
|:-----|:-----|
| 新 feature / spec 写作前 | §1 grilling 对齐（一次一问、带推荐答案） |
| 探索代码库 / 命名 | §2 读 CONTEXT.md，用统一语言 |
| 正式评审 | §3 双轴（Standards + Spec）分开报告 |
| bug / 性能回归 | §4 先建 tight loop，再假设 |
| 计划拆解 | §5 垂直切片 + blocking edges |
| 会话交接 | §6 引用 artifact + 建议技能 |

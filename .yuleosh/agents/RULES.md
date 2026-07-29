# RULES.md — Agent Behavioral Rules (Zero-Tolerance)

> **Version**: 1.0.0
> **Status**: Active
> **Format**: OpenSpec (RFC 2119: SHALL/SHOULD/MAY)

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

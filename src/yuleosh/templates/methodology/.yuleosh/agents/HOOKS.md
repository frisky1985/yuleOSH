# HOOKS.md — Agent Trigger Hooks

> **Version**: 1.0.0
> **Status**: Active
> **Format**: OpenSpec (RFC 2119: SHALL/SHOULD/MAY)

---

## 1. Task-Init Hook

### 1.1 Description

Triggered when the pipeline or any agent task is initialized. Loads agent constraints and configuration before any step begins execution.

### 1.2 Specification

**SHALL**:
- When the pipeline starts (`run_pipeline`), the system SHALL detect the presence of `.yuleosh/agents/` directory.
- If `.yuleosh/agents/` exists, the system SHALL read all `*.md` files from the directory.
- The content of all agent constraint files SHALL be concatenated and injected into the LLM system prompt for every LLM call within the pipeline.
- If `.yuleosh/agents/` does not exist, the system SHALL use the default agent spec from `ci-config.yaml` (`.default_agent_spec` section or the built-in fallback).

**SHOULD**:
- The loading of agent constraints SHOULD be logged at `INFO` level: `"Loaded {N} agent constraint file(s) from .yuleosh/agents/"`.

**MAY**:
- The Task-Init Hook MAY validate that the agent constraint files are well-formed (contain at least one SHALL/SHOULD/MAY statement).

### 1.3 GIVEN/WHEN/THEN

##### GIVEN a project with `.yuleosh/agents/AGENTS.md`, `.yuleosh/agents/RULES.md`, `.yuleosh/agents/HOOKS.md`
##### WHEN `run_pipeline` is called
##### THEN the system SHALL load all three files as LLM system context
##### AND every subsequent `_call_llm(session, system_prompt, ...)` SHALL have agent constraints prepended to the `system_prompt`

##### GIVEN a project WITHOUT `.yuleosh/agents/`
##### WHEN `run_pipeline` is called
##### THEN the system SHALL fall back to the default agent spec from `ci-config.yaml` or built-in fallback

---

## 2. CI Failure Hook

### 2.1 Description

Triggered when CI (L1, L2, or L3) reports a failure. Automatically assigns a fix agent to resolve the issue through the Loop Chain mechanism.

### 2.2 Specification

**SHALL**:
- When a CI run reports a failure, the pipeline SHALL analyze the failure and identify the root cause category (config, code, spec, test, coverage).
- The system SHALL dispatch the appropriate fix agent based on the failure category:
  - Config/missing file failures → orchestrator agent (小明)
  - Code/MISRA/test failures → developer agent (小克)
  - Spec/quality failures → quality architect agent (小马)
- The fix agent SHALL be invoked within the same pipeline session as a new step or sub-session.
- The fix agent SHALL follow the Loop Chain rules (fix, re-verify, iterate until green).

**SHOULD**:
- The CI Failure Hook SHOULD log each failure and its resolution to `.yuleosh/reports/ci-failure-hook.jsonl`.

### 2.3 GIVEN/WHEN/THEN

##### GIVEN a CI run that fails on a code coverage step
##### WHEN `coverage_gate_step` reports coverage below `threshold_line`
##### THEN the hook SHALL auto-assign 小克 to investigate and fix the coverage gap
##### AND the fix SHALL be verified by re-running the coverage gate

##### GIVEN a CI run that fails on a MISRA compliance step
##### WHEN MISRA violations exceed the configured threshold for the active profile
##### THEN the hook SHALL auto-assign 小克 to fix the violations
##### AND re-run the MISRA step to verify

---

## 3. Review Required Hook

### 3.1 Description

Triggered before code is merged or a phase is completed. Forces a review by the appropriate reviewer agent if review artifacts are missing or incomplete.

### 3.2 Specification

**SHALL**:
- Before any `final-report` step runs, the system SHALL check that all preceding review steps have completed successfully.
- If a required review step was skipped or failed, the hook SHALL block the `final-report` step.
- The hook SHALL assign the missing review to the appropriate review agent (小马 for quality reviews, 小克 for technical reviews).
- The hook SHALL verify that the review artifacts exist in the session directory before allowing progression.

**SHOULD**:
- The Review Required Hook SHOULD not block on P2-level advisory findings — only P0 and P1 items are blocking.

**MAY**:
- The Review Required Hook MAY allow an override via an explicit `--skip-review` flag, which SHALL be logged as an audit event.

### 3.3 GIVEN/WHEN/THEN

##### GIVEN a pipeline where step `arch-review` (architecture review) was skipped
##### WHEN the pipeline reaches the `final-report` step
##### THEN the hook SHALL check that `.artifacts["arch-review"]` exists
##### IF the artifact is missing, the hook SHALL block progression with error: `❌ Blocked: arch-review required but not completed`
##### AND assign 小马 to perform the architecture review before `final-report` can run

##### GIVEN a pipeline where all review steps completed successfully
##### WHEN the pipeline reaches the `final-report` step
##### THEN the hook SHALL allow progression without interruption

---

## 4. Hook Configuration

### 4.1 Enabling/Disabling

**SHALL**:
- All hooks SHALL be enabled by default.
- Hooks MAY be individually disabled by setting the corresponding key to `false` in the pipeline's `yuleosh.yaml` or `ci-config.yaml`.

### 4.2 Hook Metadata

Hooks SHALL log the following metadata for every trigger:
- `hook_name` — which hook triggered
- `trigger_time` — ISO 8601 timestamp
- `trigger_step` — which pipeline step triggered the hook
- `result` — `"blocked"`, `"dispatched"`, `"skipped"`
- `details` — human-readable description of the trigger context

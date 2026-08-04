# {{PROJECT_NAME}} — Methodology Spec (L3 宿主包模板)

> 版本: 1.0.0 | 格式: OpenSpec (RFC 2119)

## 1. 方法论契约

### 1.1 Requirement Alignment — Grill Before Spec

**SHALL**:
- Before writing a new spec or sprint contract, the responsible agent SHALL run a grilling session with the request source (one question at a time, each with a recommended answer).
- Decisions made during grilling SHALL be recorded in the spec or a decision log before implementation begins.

**SHALL NOT**:
- Agents SHALL NOT write a spec from a vague request without a grilling pass when the request is ambiguous.

### 1.2 Domain Model — Shared Language

**SHALL**:
- Agents SHALL read `CONTEXT.md` (if it exists) so naming matches the project's domain language.
- When a domain term is resolved during design, the agent SHALL update `CONTEXT.md` inline.

**SHALL NOT**:
- `CONTEXT.md` SHALL NOT contain implementation details — it is a glossary and nothing else.

### 1.3 Two-Axis Review — Standards + Spec

**SHALL**:
- Every formal review SHALL evaluate the change along two independent axes: Standards (repo coding standards + smell baseline) and Spec (faithful implementation of the originating issue/PRD).
- The two axes SHALL be reported separately.

### 1.4 Tight-Loop Debugging — Reproduce Before Hypothesise

**SHALL**:
- Before hypothesising a cause, the diagnosing agent SHALL construct a tight feedback loop: one command that drives the actual bug code path and asserts the user's exact symptom.
- The loop SHALL be red-capable, deterministic, fast, and agent-runnable.

### 1.5 Vertical Slices — Tracer-Bullet Work Units

**SHALL**:
- Plans and tickets SHALL be broken into vertical slices — each slice cuts a narrow but COMPLETE path through every layer.
- Each ticket SHALL declare its blocking edges.

**SHALL NOT**:
- Work SHALL NOT be sliced horizontally (all tests first, then all implementation).

### 1.6 Handoff Discipline

**SHALL**:
- When handing work to another agent or session, the handing agent SHALL write a handoff document that references existing artifacts by path/URL instead of duplicating their content.
- The handoff document SHALL include a "suggested skills" section.

## 2. 门禁验收场景

##### GIVEN a project mounted with the methodology host package
##### WHEN `yuleosh methodology check .` is run
##### THEN hard violations SHALL block (exit 1) and soft violations SHALL warn (exit 0)

##### GIVEN a project WITHOUT methodology markers (no spec/CONTEXT/.yuleosh)
##### WHEN `yuleosh methodology check .` is run
##### THEN the gate SHALL skip and exit 0 (non-methodology projects are not blocked)

##### GIVEN a project where CONTEXT.md has been edited by the user
##### WHEN `yuleosh methodology init .` is run again
##### THEN the existing CONTEXT.md SHALL NOT be overwritten (idempotent mount)

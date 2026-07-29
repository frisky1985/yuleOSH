# spec-delta: 质量体系缺口修复

> **版本**: 0.1.0
> **状态**: 草稿 — 待评审
> **来源**: 2026-07-29 yuleOSH 架构全量审查 (老陈+商业专家评审 + 小明架构分析)
> **格式**: RFC 2119 (SHALL/SHOULD/MAY) + GIVEN/WHEN/THEN
> **编号**: QG-xxx (Quality Gap)

---

## 背景

2026-07-29 对 yuleOSH v3.3.0 进行完整架构审查，发现以下系统性质量缺口：

| 缺口 | 严重度 | 摘要 |
|:-----|:------:|:------|
| QG-001 | P0 | **覆盖率门禁形同虚设** — threshold_line=5.0, strict=false |
| QG-002 | P0 | **MISRA profiles 空置** — 无活跃 profile，质量控制实际未分层 |
| QG-003 | P1 | **需求版本基线未锁定** — spec-delta 散落，无 merge 流程 |
| QG-004 | P1 | **LLM 输出无回退策略** — 不合格生成结果直接通过 |
| QG-005 | P2 | **Agent 约束未嵌入工具自身** — 团队分工/行为定义在 workspace，不在 yuleOSH |
| QG-006 | P2 | **C 覆盖率门禁未端到端验证** — c_fail_under=70 但从未真正触发 |
| QG-007 | P2 | **Pipeline Profile 缺失** — 无 CI profile 环境区分 |

---

## QG-001: 覆盖率门禁加固

### SHALL

- The system SHALL raise `threshold_line` from 5.0 to a minimum of 50 for all production code paths
- The system SHALL enforce `strict: true` as the default for all new project initializations
- The system SHALL reject CI runs when coverage drops below the module-level threshold
- The system SHALL NOT allow setting `strict: false` without an explicit approval from a project admin

### Reason

5% 覆盖率门禁不产生任何质量约束力。嵌入式量产产品要求 ≥ 80% 行覆盖、≥ 60% 分支覆盖。当前配置下任何代码变更都无法被门禁拦截。

### GIVEN/WHEN/THEN

##### GIVEN a project with coverage threshold configured to 5%
##### WHEN a developer runs `yuleosh ci run 2`
##### THEN the CI runner SHALL emit a warning (`⚠️ threshold_line=5 is below recommended minimum (50)`)
##### AND the CI runner SHALL NOT block the pipeline on coverage failure alone
##### BUT the CI runner SHALL log the coverage delta to `.yuleosh/reports/coverage-trend.jsonl`

##### GIVEN a project with `strict: true` and `threshold_line: 80`
##### WHEN a code change drops coverage below 80%
##### THEN the CI pipeline SHALL fail at the coverage gate
##### AND the failure SHALL include a per-module breakdown of which files dropped coverage

##### GIVEN a project with `strict: false`
##### WHEN running `yuleosh ci run 2`
##### THEN the CI runner SHALL log a warning: `⚠️ strict: false — coverage gate is advisory-only`
##### AND the CI runner SHALL require `--override-strict` flag to proceed in strict-blocked scenarios

### Migration

- yuleOSH 自身覆盖率（当前 ~24%）需提升到 ≥ 50% 后才能设置 `strict: true`
- 过渡期：将自身项目的 `threshold_line` 设为 24（当前值），设置 `strict: false` 但记录趋势
- 每个 Sprint 提升 10 个百分点，4 个 Sprint 后切换到 `strict: true`

---

## QG-002: MISRA Profiles 激活

### SHALL

- The system SHALL require at least one active MISRA profile for all projects with C/C++ code
- The system SHALL support at minimum three profiles: `safety`, `motor`, `benchmark`
- The system SHALL apply profile-specific deviation rules when a profile is active
- The system SHALL fail CI L1 when the `active_profile` is empty or undefined

### Reason

当前 `profiles: {}` 和 `active_profile: safety` 但 profiles 为空导致 safety profile 无实际内容。MISRA 检查没有按 profile 分层，benchmark 和 safety 项目跑同样的规则集不公平，也不安全。

### GIVEN/WHEN/THEN

##### GIVEN a `.yuleosh/ci-config.yaml` with `profiles: {}` and `active_profile: safety`
##### WHEN `yuleosh ci run 1` is executed
##### THEN the CI runner SHALL emit an error: `❌ active_profile 'safety' has no rules defined in profiles`
##### AND the CI SHALL abort with exit code 1

##### GIVEN a configured profile with 3 tiers of checks
##### WHEN the active profile is `safety`
##### THEN the CI SHALL enforce all mandatory rules + safety-critical rules + advisory rules as warnings
##### WHEN the active profile is `benchmark`
##### THEN the CI SHALL enforce only mandatory rules + advisory rules as suggestions

### Default Profiles

```yaml
misra:
  profiles:
    safety:
      rules: [mandatory, required, advisory]
      block_on: [mandatory, required]
      exclude_paths: [tests/**, third_party/**]
    motor:
      rules: [mandatory, required]
      block_on: [mandatory]
      exclude_paths: [tests/**, third_party/**, examples/**]
    benchmark:
      rules: [mandatory]
      block_on: [mandatory]
      exclude_paths: [tests/**, third_party/**, examples/**, demos/**]
  active_profile: safety
```

---

## QG-003: 需求版本基线锁定

### SHALL

- The system SHALL maintain a spec version lock file (`.yuleosh/spec-version.json`)
- Each spec-delta merge SHALL increment the spec version
- The system SHALL reject a spec change that would downgrade the spec version
- The system SHALL support spec-merge command: `yuleosh spec merge <delta-file>`
- The merge command SHALL validate all SHALL statements in the delta against the base spec

### Reason

当前 spec-delta 文件（`spec-delta-sprint2.md` 到 `spec-delta-sprint5.md` + `spec-delta-kg-next.md` + `spec-delta-loop-engineering.md`）散落在 `docs/` 和 `specs/` 目录中。没有版本基线意味着无法知道某个需求当前是否被接受了，审计时也无法解释为什么需求发生了变化。

### GIVEN/WHEN/THEN

##### GIVEN a project with `docs/spec.md` (v2.5.0) and `docs/spec-delta-loop-engineering.md`
##### WHEN `yuleosh spec merge spec-delta-loop-engineering.md` is executed
##### THEN the system SHALL:
- Parse all SHALL/SHOULD/MAY statements from the delta
- Validate no SHALL conflicts with existing spec
- Create `.yuleosh/spec-version.json` with incremented version
- Output merged `docs/spec.md` and backup previous as `docs/spec.md.v2.5.0`
- Print diff summary

##### GIVEN `.yuleosh/spec-version.json` exists with version 2.6.0
##### WHEN a user attempts to merge a delta that would produce version 2.5.0
##### THEN the system SHALL reject with: `❌ spec-version downgrade: 2.6.0 → 2.5.0 is not allowed`

##### GIVEN a merged spec with new version
##### WHEN `yuleosh traceability check` runs
##### THEN the traceability matrix SHALL reflect the new spec version

---

## QG-004: LLM 输出回退策略

### SHALL

- The system SHALL validate all LLM-generated output against a schema or structural template
- The system SHALL define fallback behavior for each pipeline step that invokes an LLM
- A pipeline step SHALL NOT proceed when LLM output validation fails with no valid fallback
- The system SHALL log LLM validation failures to `.yuleosh/reports/llm-validation-failures.jsonl`

### Reason

yuleOSH 的 Pipeline 多个步骤（review/spec/plan/template-gen）强依赖 LLM 输出质量。当前 LLM 输出未经结构验证就直接进入下一步，如果 LLM 输出格式错误/内容无效，pipeline 会产生不可用的中间产物。

### GIVEN/WHEN/THEN

##### GIVEN a pipeline step that calls an LLM for spec generation
##### WHEN the LLM returns malformed JSON (invalid SHALL/SHOULD format)
##### THEN the step SHALL retry the LLM call up to 2 times with `{"valid": false, "error": "...", "instructions": "..."}`
##### AFTER 2 failed retries, the step SHALL fall back to a default template
##### AND log the failure to `llm-validation-failures.jsonl`

##### GIVEN a pipeline step whose LLM fallback also fails
##### WHEN no valid output exists after 2 retries + fallback
##### THEN the pipeline step SHALL be marked as `failed` with `reason: "LLM output validation failed after 2 retries + fallback"`
##### AND the pipeline SHALL NOT proceed to dependent steps

### Fallback Levels

```
Level 0: Raw LLM output (current — no validation)
Level 1: Schema validation → reject if format violation, retry 2x
Level 2: Content validation → reject if missing required fields, retry 2x
Level 3: Semantic validation → reject if contradiction with existing context, retry 1x
Level 4: Template fallback → use default template with LLM suggestions as comments
Level 5: Abort step → mark failed, block pipeline
```

---

## QG-005: Agent 约束嵌入工具自身

### MAY

- The system MAY embed agent behavior contracts as `.yuleosh/agents/` directory
- The agents/ directory MAY contain:
  - `AGENTS.md` — Agent roles, responsibilities, handover protocol
  - `RULES.md` — Behavior rules all agents must follow
  - `HOOKS.md` — Git/webhook hooks that trigger agent actions
- The pipeline SHALL load these files at startup and hand them as system context to LLM calls

### Reason

当前 Agent 约束定义在 OpenClaw workspace 层（`AGENTS.md`、`SOUL.md`、`MEMORY.md`），不在 yuleOSH 内部。这意味着：
1. yuleOSH 无法自我约束 Agent 行为
2. Agent 切换项目后约束文件不同，行为不一致
3. 新 Agent 加入时不知道规则

### GIVEN/WHEN/THEN

##### GIVEN a project with `.yuleosh/agents/AGENTS.md`
##### WHEN the pipeline starts a new agent task
##### THEN the LLM context SHALL include the full agent behavior spec from `AGENTS.md`

##### GIVEN a project WITHOUT `.yuleosh/agents/`
##### WHEN the pipeline starts a new agent task
##### THEN the LLM SHALL receive a minimal default agent spec (defined in `ci-config.yaml`)

---

## QG-006: C 覆盖率门禁端到端验证

### SHALL

- The system SHALL run a weekly end-to-end C coverage pipeline that exercises `c_fail_under` gate
- The weekly run SHALL target a real or QEMU-compiled C project
- The result SHALL be posted to `.yuleosh/reports/c-coverage-gate-verification.json`
- If the C coverage gate fails, the CI maintainer SHALL be notified within 24 hours

### Reason

`c_fail_under: 70` 已配置但从未在真实 pipeline 中验证过。端到端未跑通的门禁等于没有门禁。

### GIVEN/WHEN/THEN

##### GIVEN a C project with compiled `.gcda` files
##### WHEN `yuleosh ci run 2` executes the C coverage stage
##### THEN the stage SHALL:
1. Run `gcovr --json` on the project
2. Parse line/branch coverage
3. Compare against `c_fail_under` threshold
4. Generate `.yuleosh/reports/c-coverage-gate-verification.json`
5. Block L2 if below threshold

##### GIVEN the weekly C coverage pipeline
##### WHEN the result file indicates the gate is unreachable (no `.gcda` data)
##### THEN the system SHALL log a P0 alert to `.yuleosh/reports/p0-alerts.jsonl`

---

## QG-007: Pipeline Profile 环境区分

### SHOULD

- The system SHOULD support CI environment profiles: `development`, `ci`, `production`
- Each profile SHOULD have independent coverage thresholds and MISRA profiles
- The system SHOULD use `dev` profile (low gate) for local development, `ci` for PR checks, and `production` for release

### Reason

本地开发、CI PR 检查、正式发布使用同样的质量门禁不合理。本地开发需要快速迭代，CI 需要适度检查，发布需要严格门禁。

### GIVEN/WHEN/THEN

##### GIVEN a developer runs `yuleosh ci run 2 --profile development`
##### WHEN coverage is between 5% and 50%
##### THEN the pipeline SHALL pass but warn: `⚠️ coverage 12% below production threshold (50%)`

##### GIVEN a release pipeline `yuleosh ci run 2 --profile production`
##### WHEN coverage is below 80%
##### THEN the pipeline SHALL fail: `❌ coverage gate (80%) not met: got 65%`

---

## 优先级与排期

| ID | 优先级 | 估时 | 依赖 |
|:---|:------:|:----:|:-----|
| QG-001 | P0 | 3 天 | 自身覆盖率先提升到 50% |
| QG-002 | P0 | 1 天 | 无 |
| QG-003 | P1 | 2 天 | 无 |
| QG-004 | P1 | 2 天 | 无 |
| QG-005 | P2 | 1 天 | 无 |
| QG-006 | P2 | 2 天 | QG-001 (门禁配置好才能验) |
| QG-007 | P2 | 1 天 | QG-001, QG-002 |

### 执行顺序

```
Sprint 1: QG-002 (MISRA profiles) + QG-003 (spec version)          → 3 天
Sprint 2: QG-004 (LLM fallback) + QG-001 (coverage gate + self)    → 5 天
Sprint 3: QG-006 (C coverage verify) + QG-007 (pipeline profiles)  → 3 天
Sprint 4: QG-005 (agent constraints)                                → 1 天
```

---

## 附录：涉及的源文件

| 文件 | 修改类型 | 涉及缺口 |
|------|---------|:--------:|
| `.yuleosh/ci-config.yaml` | 修改 | QG-001, QG-002, QG-007 |
| `src/yuleosh/ci/runner.py` | 修改 | QG-001, QG-006 |
| `src/yuleosh/ci/layers.py` | 修改 | QG-001, QG-007 |
| `src/yuleosh/ci/config.py` | 修改 | QG-002, QG-007 |
| `src/yuleosh/pipeline/orchestrator.py` | 修改 | QG-004 |
| `src/yuleosh/spec/` | 新建 | QG-003 |
| `.yuleosh/agents/` | 新建 | QG-005 |
| `docs/spec.md` | 修改 | QG-003 |

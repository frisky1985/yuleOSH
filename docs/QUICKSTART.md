# yuleOSH Quickstart — 3 Steps, 2 Minutes

> Get from zero to a running pipeline in three commands and under two minutes.

---

## Prerequisites

- **Python 3.10+** (`python3 --version`)
- **pip** (`python3 -m pip --version`)

No Git, no clones, no system dependencies.

---

## Step 1: Install ⏱ 15s

```bash
pip install yuleosh
```

That's it. No extra dependencies, no platform setup scripts. `pytest`, `coverage`, and all other tooling come bundled.

**Verify it works:**

```bash
yuleosh help
```

Expected output shows all available commands:

```
Usage: yuleosh <command> [options]

Commands:
  init           Create a new project
  pipeline       Run the full agent pipeline
  spec           Validate and diff OpenSpec files
  ci             Run CI layers
  review         Run AI code review
  evidence       Generate compliance evidence pack
  ...
```

---

## Step 2: Initialize ⏱ 15s

```bash
yuleosh init my-project
cd my-project
```

This creates a ready-to-run project structure:

```
my-project/
├── docs/
│   └── spec.md           # Starter spec with 3 requirements + 3 scenarios
├── src/                   # Source code directory (ready for your code)
├── tests/                 # Test directory (ready for your tests)
├── pyproject.toml
└── .gitignore
```

The starter `docs/spec.md` includes a sample BLINKY LED spec with `SHALL`/`SHOULD`/`MAY` requirements and `GIVEN`/`WHEN`/`THEN` scenarios — all ready to validate and run.

---

## Step 3: Run ⏱ 90s

```bash
yuleosh pipeline run docs/spec.md
```

You'll see the 9-step agent pipeline in action:

```
🚀 Pipeline started: run-20260613-220300

  [1/9] 小明: OpenSpec 合规检查          ✅
  [2/9] 小明: S.U.P.E.R 启动分析          ✅
  [3/9] Hermes: 产品需求分析               ✅
  [4/9] 小明: 内部评审                     ✅
  [5/9] Claude: 架构设计                   ✅
  [6/9] Claude: 开发实现                   ✅
  [7/9] Claude: 自测验证                   ✅
  [8/9] Hermes: 代码审查                   ✅
  [9/9] 小明: 最终报告                     ✅

═══════════════════════════════════════
Pipeline: completed 🎉
Session: .osh/sessions/run-20260613-220300
```

**What you get:**

| Artifact | File | What it contains |
|:---------|:-----|:-----------------|
| Spec check | `.osh/sessions/*/spec-check.json` | Validation results |
| Design docs | `.osh/sessions/*/architecture.md` | System architecture + ADRs |
| Generated code | `src/` | Auto-generated firmware source |
| Review report | `.osh/sessions/*/code-review.json` | 4-agent review findings |
| Final report | `.osh/sessions/*/final-report.md` | Aggregated project summary |

---

## Optional: Generate Compliance Evidence ⏱ 30s

```bash
yuleosh evidence pack
```

Produces an ASPICE-compliant compliance archive:

```
.osh/evidence/
├── traceability-matrix.md       # Req ↔ Design ↔ Code ↔ Test
├── acceptance-matrix.md         # Acceptance criteria trace
├── code-coverage-report.md      # Line/condition metrics
├── review-log-summary.md        # Human-readable audit trail
├── review-log.json              # Machine-readable audit trail
└── compliance-pack.zip           # All-in-one for audit 🎯
```

---

## Total: 2 Minutes

| Step | Command | Time |
|:-----|:--------|:----:|
| 1. Install | `pip install yuleosh` | 15s |
| 2. Init | `yuleosh init my-project` | 15s |
| 3. Run | `yuleosh pipeline run docs/spec.md` | 90s |
| **Total** | | **2 min** |

---

## Next Steps

| Goal | Command / Resource |
|:-----|:-------------------|
| Full CLI reference | [USAGE.md](USAGE.md) |
| FAQ & troubleshooting | [FAQ.md](FAQ.md) |
| API reference | [API Reference](api-reference.md) |
| Architecture deep dive | [Architecture](architecture.md) |
| Deploy to production | [Deploy Guide](deploy-guide.md) |
| Commercial info | [Pricing](../README.md#pricing) |

---

> **Tip:** Run `yuleosh help --examples` for inline usage patterns.

# yuleOSH Quickstart — 5 Minutes to Running

> Get from zero to running your first pipeline in 5 minutes.

---

## Prerequisites

- **Python 3.10+** (`python3 --version`)
- **Git** (`git --version`)
- **pip** (`python3 -m pip --version`)

---

## 1. Install (30 seconds)

```bash
# Clone the repo
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH

# Install dependencies
python3 -m pip install pytest coverage

# Make the CLI available
sudo ln -sf "$(pwd)/src/cli/yuleosh.sh" /usr/local/bin/yuleosh

# Verify
yuleosh help
```

**Expected output:**
```
OSH Platform CLI — 嵌入式开发全流程平台
Usage: osh-cli <command> [options]
...
```

---

## 2. Create a Project (30 seconds)

Use the starter template to create a new project with a sample spec:

```bash
yuleosh template init my-sensor
cd my-sensor
```

This creates:

```
my-sensor/
├── docs/
│   └── spec.md              # Starter spec with 3 requirements
├── src/                      # Source code directory
├── tests/                    # Test directory
├── pyproject.toml
└── .gitignore
```

---

## 3. Validate Your Spec (30 seconds)

Every yuleOSH project needs an OpenSpec requirements file. Let's validate the starter:

```bash
yuleosh spec validate docs/spec.md
```

**Expected output (example):**

```
📋 OpenSpec Validation: docs/spec.md
══════════════════════════════════════════
  Requirements: 3
  Scenarios:    3
  Total SHALLs: 8

🔬 Coverage Score: 100.0%
   (threshold: 80%) ✅ PASS
```

**What to look for:**
- ✅ `PASS` — your spec meets the 80% coverage threshold
- Requirements count and SHALL statement count
- Any warnings about missing sections

> **Spec format tip:** Each requirement needs at least one `SHALL` statement and a `#### Reason` section. Scenarios need `GIVEN`/`WHEN`/`THEN`.

---

## 4. Run CI Layer 1 (30 seconds)

Run development verification — unit tests and code coverage:

```bash
yuleosh ci run 1
```

**Expected output (example):**

```
🔬 CI Layer 1: Development Verification
   Commit: abc1234
   Project: /Users/you/my-sensor

  🔍 CI: plan-lint...
    ✅ plan-lint passed
  🔎 CI: clang-tidy...
    ⏭️  No C/C++ files — skipped
  🧪 CI: unit tests...
    ✅ All pytest tests passed
  📊 CI: coverage check...
    Line coverage: 42.0% (threshold: 40.0%)
    ✅ Coverage thresholds met

═══════════════════════════════════════
✅ CI Layer 1: ALL STAGES PASSED
```

**What CI does for you:**
| Stage | Purpose | Gate |
|:------|:--------|:-----|
| plan-lint | Check task/plan format | Warning only |
| clang-tidy | C/C++ static analysis | Warning only |
| unit-tests | Discover and run all tests | ❌ Blocks on failure |
| coverage | Line + condition coverage | ❌ Blocks if below 40% |

---

## 5. Run the Full Pipeline (60 seconds)

The Agent Pipeline orchestrates 9 automated steps through 小明 (PM), Hermes (Product), Claude (Arch/Dev):

```bash
yuleosh pipeline run docs/spec.md
```

**What happens:**

```
🚀 Pipeline started: run-20260604-120000
   Spec: docs/spec.md

  [1/9] 小明: OpenSpec 合规检查
  [2/9] 小明: S.U.P.E.R 启动分析
  [3/9] Hermes: 产品需求分析
  [4/9] 小明: 内部评审
  [5/9] Claude: 架构设计
  [6/9] Claude: 开发实现
  [7/9] Claude: 自测验证
  [8/9] Hermes: 代码审查
  [9/9] 小明: 最终报告

═══════════════════════════════════════
Pipeline: completed 🎉
Session: .osh/sessions/run-20260604-120000
```

**Pipeline artifacts** are saved to `.osh/sessions/run-YYYYMMDD-HHMMSS/`:

| Artifact | Agent | What it contains |
|:---------|:------|:-----------------|
| `spec-check.json` | 小明 | Spec validation results |
| `startup-analysis.md` | 小明 | S.U.P.E.R analysis |
| `prd.md` | Hermes | Product requirements doc |
| `review-result.md` | 小明 | Internal review |
| `architecture.md` | Claude | System architecture |
| `development-log.md` | Claude | Implementation log |
| `self-test-report.md` | Claude | Test results |
| `code-review.json` | Hermes | Code review findings |
| `final-report.md` | 小明 | Aggregated final report |

---

## 6. Generate Compliance Evidence (30 seconds)

Produce a complete ASPICE-compliant evidence pack:

```bash
yuleosh evidence pack
```

**Expected output:**

```
📦 OSH Evidence Generation
══════════════════════════════════════════
  📋 Collected 3 requirements, 3 scenarios
  📋 Collected 1 review session(s)
  📋 Collected 2 CI result(s)

══════════════════════════════════════════
  ✅ Traceability matrix generated: .osh/evidence/traceability-matrix.md
  ✅ Requirement coverage report: .osh/evidence/requirement-coverage.md
  ✅ Code coverage report: .osh/evidence/code-coverage-report.md
  ✅ Review logs aggregated: .osh/evidence/review-log-summary.md
  📦 Compliance pack created: .osh/evidence/compliance-pack.zip

══════════════════════════════════════════
✅ Evidence generation complete
```

**What's in the pack:**

```
.osh/evidence/
├── traceability-matrix.md       # Req ↔ Design ↔ Code ↔ Test
├── requirement-coverage.md      # Per-requirement coverage
├── code-coverage-report.md      # Line/condition metrics
├── review-log-summary.md        # Audit trail (human-readable)
├── review-log.json              # Audit trail (machine-readable)
└── compliance-pack.zip           # All-in-one for audit 🎯
```

---

## 7. Bonus: Dashboard

```bash
yuleosh ui start
# → Open http://localhost:8080 in your browser
```

---

## 3 Command Examples

### Example 1: Validate a custom spec

```bash
cat > docs/my-spec.md << 'EOF'
### Req-001: Hello World
- The system SHALL print "Hello, yuleOSH!"
- The system SHALL include the current timestamp

#### Reason
Demo requirement for quickstart

### Scenario: Basic operation
- GIVEN the system is started
- WHEN the user triggers the hello command
- THEN the system SHALL print "Hello, yuleOSH!"
- AND the system SHALL include the current timestamp
EOF

yuleosh spec validate docs/my-spec.md
```

### Example 2: Track requirement changes

```bash
# Edit your spec, then compare:
yuleosh spec diff docs/spec.md docs/spec.md
# → Should show "0 changes" (same file)

# After editing, you'll see added/modified/removed requirements
```

### Example 3: Run all CI layers at once

```bash
for layer in 1 2 3; do
  echo "=== CI Layer $layer ==="
  yuleosh ci run $layer
  echo ""
done
```

---

## Troubleshooting

### "command not found: yuleosh"

```bash
# The CLI wasn't symlinked. Use one of these:
bash path/to/yuleOSH/src/cli/yuleosh.sh help
# Or symlink it:
sudo ln -sf "$(pwd)/src/cli/yuleosh.sh" /usr/local/bin/yuleosh
```

### "No module named 'coverage'"

```bash
# Install missing dependencies:
python3 -m pip install pytest coverage
```

### "Pipeline failed with errors"

Check the JIT error output — each step prints what went wrong. Common fixes:

| Error | Fix |
|:------|:----|
| "Spec has errors" | Run `yuleosh spec validate` first and fix issues |
| "File not found" | Check the spec path is correct and file exists |
| "No changed files" | `yuleosh review auto` needs git-tracked files; make a commit first |
| Permission denied | Ensure you have write access to the project directory |

### "Git commands fail"

Some yuleOSH features need a git context:

```bash
git init
git add -A
git commit -m "initial commit"
```

### "Port 8080 already in use"

```bash
# Use a different port:
OSH_PORT=9090 yuleosh ui start
```

### "CLI help format looks different"

The help examples are auto-generated from command definitions. Run:

```bash
yuleosh help --examples
```

for real-world usage patterns.

---

## Next Steps

| Resource | What you'll learn |
|:---------|:------------------|
| [USAGE.md](USAGE.md) | Full CLI reference, all commands |
| [FAQ.md](FAQ.md) | Common questions answered |
| `bin/yuleosh-demo` | One-command demo (full workflow) |
| `yuleosh help --examples` | Inline usage examples |

---

> **Tip:** Run `bin/yuleosh-demo` for a complete walkthrough with a realistic BLE sensor firmware project. It runs all 7 steps automatically.

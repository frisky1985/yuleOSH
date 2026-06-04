# yuleOSH FAQ — Frequently Asked Questions

> Last updated: 2026-06-04

---

## General

### Q1: What is yuleOSH?

**yuleOSH** (you-unify-Lifecycle-of-OpenSpec-Superpowers-Harness) is an embedded AI development platform that combines three frameworks:

| Framework | What it provides |
|:----------|:-----------------|
| **OpenSpec** | RFC 2119 requirements format (SHALL/SHOULD/MAY + GIVEN/WHEN/THEN scenarios) |
| **Superpowers** | 14 Rules + S.U.P.E.R analysis engine for prioritization |
| **Harness Engineering** | Agent pipeline + 3-layer CI/CD for automated development |

It's designed for embedded MCU/SoC teams that need ASPICE compliance, AI-assisted development, and automated CI/CD.

### Q2: What kind of projects is yuleOSH for?

yuleOSH is built for **embedded systems development** — MCU firmware, SoC drivers, BLE sensors, IoT devices, and any project requiring structured requirements-to-test traceability. It's especially useful for teams that need:

- ASPICE / ISO 26262 compliance evidence
- AI Agent-assisted development workflow
- Automated CI/CD with cross-compilation, static analysis, and HIL readiness
- Requirements traceability from spec to test

### Q3: How is yuleOSH different from regular CI/CD tools?

Standard CI/CD tools (GitHub Actions, Jenkins etc.) don't address embedded-specific needs:

| Need | Standard CI/CD | yuleOSH |
|:-----|:---------------|:--------|
| Requirements format | Free-form or none | OpenSpec (RFC 2119) |
| ASPICE compliance | Manual evidence collection | Auto-generated traceability matrix + compliance pack |
| Cross-compilation matrix | Manual setup | Built-in Layer 2 support for ARM/RISC-V/x86 |
| AI Agent workflow | Not available | 小明→Hermes→Claude pipeline (9 steps) |
| Review matrix | PR-based only | 4-agent review matrix (architecture/domain/style/coverage) |

### Q4: Do I need AI API keys to use yuleOSH?

**No.** The Agent pipeline simulates agents (小明/Hermes/Claude) with template-based artifacts. The platform is fully functional out of the box without any external AI API. The "agents" are orchestration steps that generate structured documents, not external LLM calls.

### Q5: Can I use yuleOSH with existing projects?

Yes. Run `yuleosh init my-project` inside your existing project directory (or point it at a new directory). It creates the required directory structure without modifying your existing files. Then write your OpenSpec in `docs/spec.md` and you're ready.

---

## Setup & Installation

### Q6: What are the system requirements?

- **Python 3.10+** (tested on 3.10–3.13)
- **Git 2.20+** (for review and diff features)
- **macOS** or **Linux** (Windows via WSL)
- **Disk**: ~100 MB for the project
- **Optional**: `pytest` + `coverage` (for CI Layer 1), `cppcheck` (for Layer 2 static analysis)

### Q7: How do I install yuleOSH?

```bash
# Option 1: Clone from GitHub
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
python3 -m pip install -e .
sudo ln -sf "$(pwd)/src/cli/yuleosh.sh" /usr/local/bin/yuleosh

# Option 2: One-click install
curl -fsSL https://raw.githubusercontent.com/frisky1985/yuleOSH/main/install.sh | bash
```

### Q8: Can I install without sudo?

Yes — you can add the bin directory to your PATH instead:

```bash
export PATH="$PATH:$(pwd)/bin"
# Or add to ~/.zshrc / ~/.bashrc
echo 'export PATH="$PATH:'$(pwd)'/bin"' >> ~/.zshrc
```

### Q9: Why do I get "command not found: yuleosh"?

The CLI script needs to be on your PATH. Fix it with:

```bash
# Symlink to a PATH directory:
sudo ln -sf /path/to/yuleOSH/src/cli/yuleosh.sh /usr/local/bin/yuleosh

# Or add directly:
export PATH="/path/to/yuleOSH/bin:$PATH"
```

### Q10: How do I update yuleOSH?

```bash
cd /path/to/yuleOSH
git pull --ff-only
# Re-run install if dependencies changed
python3 -m pip install -e .
```

---

## Usage

### Q11: What is OpenSpec format?

OpenSpec is a structured markdown format for embedded systems requirements:

```markdown
### Req-001: Feature Name
- The system SHALL <mandatory behavior>
- The system SHOULD <recommended behavior>
- The system MAY <optional behavior>

#### Reason
Why this requirement exists

### Scenario: Workflow Name
- GIVEN <precondition>
- WHEN <trigger>
- THEN <expected outcome>
- AND <another outcome>
```

Each requirement must have:
- At least one **SHALL** statement (mandatory)
- A **Reason** section (justification)
- Optional: SHOULD, MAY statements

Each scenario must have:
- **GIVEN** (precondition)
- **WHEN** (trigger)
- **THEN** (expected outcome)

### Q12: What does spec coverage score mean?

The coverage score (0–100%) measures **spec completeness**, not code coverage:

| Component | Weight | What counts |
|:----------|:------:|:------------|
| SHALL statements | 40% | Each requirement has ≥1 SHALL |
| Reason sections | 20% | Each requirement has a Reason |
| Complete scenarios | 40% | Each scenario has GIVEN/WHEN/THEN |

**Threshold**: 80% to pass. This ensures your spec captures mandatory requirements, justifications, and testable scenarios.

### Q13: What are the 3 CI layers?

| Layer | Name | When | What it checks |
|:-----:|:-----|:-----|:---------------|
| **1** | Development Verification | Every commit | task format, C static analysis, unit tests, coverage ≥40% |
| **2** | Integration Verification | Every PR/MR | Cross-compilation, cppcheck, integration tests, memory safety |
| **3** | System Verification | Every release | E2E tests, version check, evidence pack generation |

### Q14: What happens if CI fails?

- **Layer 1**: Failed stages print error messages. Common failures:
  - `unit-tests failed` — a test assertion failed; fix the test or code
  - `coverage failed` — coverage below 40% threshold; add more tests
  - `plan-lint warning` — non-blocking, just a format suggestion
- **Layer 2/3**: Stages are progressive. Run `yuleosh ci run 2` after Layer 1 passes.

Check logs in `.osh/ci/layer-*.json`.

### Q15: What agents are in the pipeline?

The pipeline has 9 steps with 3 agents:

| Agent | Role | Steps |
|:------|:-----|:------|
| **小明** (Xiao Ming) | PM / orchestrator | Spec check, S.U.P.E.R analysis, internal review, final report |
| **Hermes** | Product / review | PRD writing, code review |
| **Claude** | Architect / developer | Architecture, development, self-test |

### Q16: How do review categories work?

The 4 reviewer agents check different aspects:

| Reviewer | What it checks | Threshold |
|:---------|:---------------|:----------|
| **Architecture** | Module coupling, function length, import count | Functions ≤ 20 lines, imports ≤ 30 |
| **Domain Modeling** | Mutable defaults, naming consistency | No mutable default args |
| **Code Style** | Docstrings, tab characters, formatting | Functions should have docstrings |
| **Coverage Guardian** | Line/condition coverage | ≥ 80% line coverage |

Task kinds determine which reviewers run:

| Task Kind | Reviewers | Use Case |
|:----------|:----------|:---------|
| `feature` | All 4 | New feature development |
| `bugfix` | Style + Coverage | Bug fixes |
| `refactor` | Architecture + Style + Coverage | Code restructuring |
| `docs` | None (auto-pass) | Documentation changes |
| `config` | Style | Configuration changes |

### Q17: What's in the compliance pack?

Run `yuleosh evidence pack` to generate:

| Artifact | Content | Audit use |
|:---------|:--------|:----------|
| `traceability-matrix.md` | Req → Design → Code → Test links | ASPICE SYS.5 / SWE.1 |
| `requirement-coverage.md` | Per-requirement coverage table | ASPICE SWE.2 |
| `code-coverage-report.md` | Line/condition coverage metrics | ASPICE SWE.4 |
| `review-log-summary.md` | Human-readable audit trail | ASPICE SWE.3 |
| `review-log.json` | Machine-readable review records | Toolchain processing |
| `compliance-pack.zip` | All artifacts bundled | ASPICE auditor submission |

### Q18: How do I run the dashboard?

```bash
yuleosh ui start
# → Opens http://localhost:8080
```

To change the port:

```bash
OSH_PORT=9090 yuleosh ui start
```

The dashboard shows:
- Project status summary
- Pipeline run history
- CI results per layer
- Spec coverage metrics
- Evidence pack status

---

## Troubleshooting

### Q19: Tests fail with import errors

```bash
# Make sure you're in the project root:
cd /path/to/yuleOSH
pip install -e .
python3 -m pytest tests/
```

### Q20: "No pipeline sessions found" when running status

The pipeline saves sessions to `.osh/sessions/`. Ensure you ran `yuleosh pipeline run docs/spec.md` successfully first. Check CWD is your project root.

### Q21: Review says "No changed files"

`yuleosh review auto` compares against git HEAD. Make sure your changes are tracked:

```bash
git add -A
git status  # Verify files are tracked
yuleosh review auto
```

### Q22: Coverage check is slow or times out

Coverage runs `.pytest` on the entire project. For faster runs, skip coverage when not needed:

```bash
# CI runs with coverage by default
# For faster iteration:
python3 -m pytest tests/ -q
```

### Q23: Layer 3 evidence pack fails

Layer 3 needs a `pyproject.toml` for version checking. If missing:

```bash
# Create minimal pyproject.toml:
cat > pyproject.toml << 'EOF'
[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.10"
EOF
```

### Q24: Can I contribute or report bugs?

Yes! The project is open source under MIT license. File issues and PRs at the [GitHub repository](https://github.com/frisky1985/yuleOSH).

---

## Reference

### CLI Quick Reference

```text
yuleosh init [dir]                         Initialize project
yuleosh template init <name>               Create from template
yuleosh spec validate <file>               Validate OpenSpec
yuleosh spec diff <old> <new>              Compare specs
yuleosh pipeline run <spec>                Run 9-step pipeline
yuleosh pipeline status [name]             Show pipeline status
yuleosh ci run <layer>                     Run CI layer (1/2/3)
yuleosh review auto                        Auto-review changes
yuleosh review task <name> [kind]          Review specific task
yuleosh evidence pack                      Generate compliance pack
yuleosh ui start                           Start dashboard
yuleosh stats [--json]                     Show project statistics
yuleosh help [--examples]                  Show help / examples
```

### Directory Structure

```
project/
├── docs/
│   └── spec.md              # Your OpenSpec requirements
├── src/                      # Source code
├── tests/                    # Test files
│   ├── integration/          # Integration tests (Layer 2)
│   └── e2e/                  # End-to-end tests (Layer 3)
├── specs/                    # Additional spec files
├── tasks/                    # Task definitions
├── .osh/                     # Runtime data (gitignored)
│   ├── sessions/             # Pipeline artifacts
│   ├── ci/                   # CI results
│   ├── reviews/              # Review records
│   └── evidence/             # Compliance evidence
└── pyproject.toml            # Project config
```

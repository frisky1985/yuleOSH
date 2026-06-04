# yuleOSH Usage Guide

> **Version**: 0.1.0 | **Last updated**: 2026-06-04

---

## Table of Contents

1. [Quick Start Guide](#quick-start-guide)
2. [CLI Reference](#cli-reference)
3. [Example Workflow](#example-workflow)
4. [Configuration Reference](#configuration-reference)

---

## Quick Start Guide

### 1. Install yuleOSH

```bash
# Clone the repository
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH

# Install dependencies
pip install -r requirements.txt  # or: pip install pytest coverage

# Make CLI available (pick one)
# Option A — Symlink the shell script
sudo ln -sf "$(pwd)/src/cli/yuleosh.sh" /usr/local/bin/yuleosh

# Option B — Use pip install (Python CLI entry point)
pip install -e .
```

### 2. Onboard a New Project

There are two ways to create a project:

**Option A — Starter template (recommended for new projects):**

```bash
yuleosh template init my-awesome-project
cd my-awesome-project
```

This creates:
```
my-awesome-project/
├── docs/
│   └── spec.md              # Starter spec with 3 requirements
├── src/                      # Source code directory
├── tests/                    # Test directory
├── pyproject.toml
└── .gitignore
```

**Option B — Manual initialization (for existing projects):**

```bash
yuleosh init my-existing-project
cd my-existing-project
```

Creates the directory structure (`specs/`, `tasks/`, `src/`, `docs/`, `evidence/`).

### 3. Edit Your Spec

Edit `docs/spec.md` to define your requirements using OpenSpec format:

```markdown
### Req-001: Feature Name
- The system SHALL <behavior>
- The system SHALL <another behavior>
- The system SHOULD <nice-to-have>
- The system MAY <optional>

#### Reason
Why this requirement exists

### Scenario: Workflow Name
- GIVEN <precondition>
- WHEN <trigger>
- THEN <expected outcome>
- AND <another outcome>
```

### 4. Validate Your Spec

```bash
yuleosh spec validate docs/spec.md
```

Expected output:
```
📋 OpenSpec Validation: docs/spec.md
==================================================
  Requirements: 3
  Scenarios:    3
  Total SHALLs: 8

🔬 Coverage Score: 100.0%
   (threshold: 80%) ✅ PASS
```

### 5. Run CI

```bash
# Layer 1: Development Verification (unit tests + coverage)
yuleosh ci run 1

# Layer 2: Integration Verification (cross-compile + static analysis)
yuleosh ci run 2

# Layer 3: System Verification (E2E + evidence pack)
yuleosh ci run 3
```

### 6. Run the Full Agent Pipeline

```bash
yuleosh pipeline run docs/spec.md
```

This orchestrates: 小明 (PM) → Hermes (Product/Review) → Claude (Arch/Dev) through 9 automated steps, producing session artifacts in `.osh/sessions/`.

### 7. Run Reviews

```bash
# Auto-review all changed files
yuleosh review auto

# Review a specific task
yuleosh review task my-feature feature
```

### 8. Generate Compliance Pack

```bash
yuleosh evidence pack
```

Produces in `.osh/evidence/`:
- `traceability-matrix.md` — Req ↔ Design ↔ Code ↔ Test links
- `requirement-coverage.md` — Coverage per requirement
- `code-coverage-report.md` — Line/condition coverage
- `review-log-summary.md` + `review-log.json` — Audit trail
- `compliance-pack.zip` — All-in-one for ASPICE audit

### 9. View Project Dashboard

```bash
yuleosh ui start
# → http://localhost:8080
```

### 10. Check Project Stats

```bash
yuleosh stats
```

---

## CLI Reference

### Global Options

| Flag | Description |
|:-----|:------------|
| `--help` | Show help message |
| `--json` | Output in JSON format (where supported) |

### Commands

#### `yuleosh init [dir]`

Initialize a new yuleOSH project directory structure.

| Argument | Description | Default |
|:---------|:------------|:--------|
| `dir` | Target directory | Current directory |

Creates: `specs/`, `tasks/`, `src/`, `docs/`, `evidence/`, `.osh/`

---

#### `yuleosh template init <project-name>`

Create a new project from the OpenSpec starter template.

| Argument | Required | Description |
|:---------|:---------|:------------|
| `project-name` | ✅ | Name for the new project directory |

Creates a fully initialized project with:
- Starter `docs/spec.md` with 3 SHALL requirements and 3 scenarios
- Empty `src/` and `tests/` directories
- `pyproject.toml` and `.gitignore`
- Placeholder test file

---

#### `yuleosh stats [--json]`

Show project metrics summary.

| Flag | Description |
|:-----|:------------|
| `--json` | Output as JSON |

Displays:
- **Source Code**: Total files, lines of code, per-language breakdown
- **Tests**: Test file count, test function count
- **Spec Coverage**: Score, thresholds, requirement/scenario counts
- **Pipeline Runs**: Completed/failed counts, recent runs
- **CI Runs**: By layer, pass/fail counts

---

#### `yuleosh spec validate <file>`

Validate an OpenSpec format file.

| Argument | Required | Description |
|:---------|:---------|:------------|
| `file` | ✅ | Path to the spec `.md` file |

Validates:
- All requirements have SHALL statements
- All requirements have Reason sections
- All scenarios have GIVEN/WHEN/THEN
- Coverage score (threshold: 80%)

Exit code: `0` if no errors, `1` if errors found.

---

#### `yuleosh spec diff <old> <new>`

Compare two OpenSpec files.

| Argument | Required | Description |
|:---------|:---------|:------------|
| `old` | ✅ | Path to the old spec file |
| `new` | ✅ | Path to the new spec file |

Output: Added, removed, and modified requirements with per-statement changes.

---

#### `yuleosh pipeline run <spec>`

Run the full Agent pipeline for a spec file.

| Argument | Required | Description |
|:---------|:---------|:------------|
| `spec` | ✅ | Path to the spec `.md` file |

Pipeline steps (9 total):
| # | Agent | Step | Description |
|:-:|:------|:-----|:------------|
| 1 | 小明 | OpenSpec Check | Validates spec format |
| 2 | 小明 | S.U.P.E.R Analysis | Generates startup analysis |
| 3 | Hermes | PRD | Writes product requirements |
| 4 | 小明 | Internal Review | Checks artifact consistency |
| 5 | Claude | Architecture | Designs system architecture |
| 6 | Claude | Development | Creates development log |
| 7 | Claude | Self-Test | Generates test report |
| 8 | Hermes | Code Review | Code quality check |
| 9 | 小明 | Final Report | Aggregates all artifacts |

Session artifacts stored in `.osh/sessions/run-YYYYMMDD-HHMMSS/`.

Exit code: `0` on success, `1` on failure.

---

#### `yuleosh pipeline status [name]`

Show pipeline session status.

| Argument | Description |
|:---------|:------------|
| `name` | Specific session name (omit for all) |

---

#### `yuleosh review auto`

Auto-review all changed files (compares against `HEAD`).

Determines task kind from changed file paths. Runs appropriate reviewers:
- **feature**: Architecture + Domain + Style + Coverage
- **bugfix**: Style + Coverage
- **refactor**: Architecture + Style + Coverage
- **docs**: No reviewers (auto-pass)
- **config**: Style only

---

#### `yuleosh review task <name> [kind]`

Review a specific task.

| Argument | Required | Default | Description |
|:---------|:---------|:--------|:------------|
| `name` | ✅ | — | Task name |
| `kind` | — | `feature` | Task kind: `feature`, `bugfix`, `refactor`, `docs`, `config` |

---

#### `yuleosh ci run <layer>`

Run a CI layer.

| Argument | Required | Description |
|:---------|:---------|:------------|
| `layer` | ✅ | CI layer: `1`, `2`, or `3` |

**Layer 1** — Development Verification (every commit):
1. plan-lint — Check task kind and T00 format
2. clang-tidy — Static analysis for C/C++
3. unit-tests — Discover and run test suites
4. coverage — Line + condition coverage (threshold: 40%)

**Layer 2** — Integration Verification (on MR):
1. Cross-compilation check
2. Static analysis (cppcheck)
3. Integration tests
4. Memory safety check (ASan)

**Layer 3** — System Verification (on Release):
1. End-to-end tests
2. Version check
3. Evidence pack generation

Exit code: `0` if all stages pass, `1` if any stage fails.

---

#### `yuleosh evidence pack`

Generate complete ASPICE compliance evidence pack.

Produces:
| Artifact | Format | Description |
|:---------|:-------|:------------|
| `traceability-matrix.md` | Markdown | Req ↔ Design ↔ Code ↔ Test |
| `requirement-coverage.md` | Markdown | Per-requirement coverage |
| `code-coverage-report.md` | Markdown | CI coverage metrics |
| `review-log-summary.md` | Markdown | Aggregated review records |
| `review-log.json` | JSON | Raw review data |
| `compliance-pack.zip` | ZIP | All artifacts bundled |

---

#### `yuleosh ui start`

Start the web dashboard.

| Environment Variable | Default | Description |
|:--------------------|:--------|:------------|
| `OSH_PORT` | `8080` | HTTP server port |

Open `http://localhost:8080` in your browser.

---

## Example Workflow

### End-to-End: Adding a New Feature

This walkthrough shows the complete spec → pipeline → CI → evidence flow for adding a "Temperature sensor driver" feature to an embedded project.

#### Step 1: Create a New Project

```bash
yuleosh template init temperature-monitor
cd temperature-monitor
```

#### Step 2: Define Requirements

Edit `docs/spec.md` and add a new requirement:

```markdown
### Req-004: Temperature Sensor Driver
- The system SHALL initialize the I2C sensor on boot
- The system SHALL read temperature at 1 Hz sampling rate
- The system SHALL convert raw ADC values to Celsius
- The system SHALL report errors when sensor is unresponsive
- The system SHOULD support sensor re-initialization after failure

#### Reason
Core sensor requirement for the temperature monitoring subsystem

### Scenario: Sensor initialization
- GIVEN the system is powered on
- WHEN the I2C bus is available
- THEN the system SHALL detect the temperature sensor
- AND the system SHALL report the sensor status as READY

### Scenario: Temperature reading
- GIVEN the sensor is initialized
- WHEN 1 second has elapsed
- THEN the system SHALL read a new temperature value
- AND the system SHALL convert it to Celsius with 0.1°C precision
```

#### Step 3: Validate

```bash
yuleosh spec validate docs/spec.md
# → Should show 4 requirements, 5 scenarios, 100% coverage
```

#### Step 4: Write Tests (TDD RED phase)

Create `tests/test_sensor.py`:

```python
def test_sensor_initialization():
    assert init_sensor() == READY

def test_temperature_reading():
    temp = read_temperature()
    assert -40 <= temp <= 125
```

#### Step 5: Implement Code

Create `src/sensor.py`:

```python
def init_sensor():
    # I2C initialization logic
    return READY

def read_temperature():
    # ADC → Celsius conversion
    return 25.5
```

#### Step 6: Run Layer 1 CI

```bash
yuleosh ci run 1
# → plan-lint ✅, clang-tidy ✅, unit-tests ✅, coverage ✅
```

#### Step 7: Run Auto-Review

```bash
yuleosh review auto
# → 4 agents check architecture, domain modeling, style, coverage
```

#### Step 8: Run Full Pipeline

```bash
yuleosh pipeline run docs/spec.md
# → 小明 → Hermes → Claude → 小明 (9 steps)
```

#### Step 9: Generate Evidence

```bash
yuleosh evidence pack
# → Traceability matrix, coverage report, compliance pack
```

#### Step 10: Verify with Dashboard

```bash
yuleosh ui start
# → http://localhost:8080
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|:---------|:--------|:------------|
| `OSH_HOME` | `pwd` at CLI invocation | Root directory for the project |
| `YULEOSH_DB` | `$OSH_HOME/.yuleosh/store.db` | SQLite database path |
| `OSH_PORT` | `8080` | Dashboard HTTP server port |

### Artifact Storage

```
.osh/
├── sessions/                  # Pipeline run artifacts
│   └── run-YYYYMMDD-HHMMSS/
│       ├── session.json       # Pipeline session state
│       ├── spec-check.json    # Spec validation results
│       ├── startup-analysis.md
│       ├── prd.md
│       ├── review-result.md
│       ├── architecture.md
│       ├── development-log.md
│       ├── self-test-report.md
│       ├── code-review.json
│       └── final-report.md
├── ci/                         # CI run artifacts
│   ├── layer1-<hash>.json
│   ├── layer2-<hash>.json
│   └── layer3-<hash>.json
├── review/                     # Review session artifacts
│   └── <task-name>/
│       └── review-session.json
└── evidence/                   # Compliance evidence
    ├── traceability-matrix.md
    ├── requirement-coverage.md
    ├── code-coverage-report.md
    ├── review-log-summary.md
    ├── review-log.json
    └── compliance-pack.zip
```

### Project Directory Layout

```
project-root/
├── docs/
│   └── spec.md            # OpenSpec requirements
├── src/                    # Source code
├── tests/                  # Test files (prefix: test_)
│   ├── integration/        # Integration tests (Layer 2)
│   └── e2e/                # End-to-end tests (Layer 3)
├── specs/                  # Additional spec files
├── tasks/                  # Task definitions
├── .osh/                   # Runtime data (gitignored)
└── pyproject.toml          # Project configuration
```

### CI Coverage Thresholds

| Layer | Threshold | Description |
|:------|:----------|:------------|
| Layer 1 | Line ≥ 40% | MVP threshold (increase as tests grow) |
| Layer 1 | Condition ≥ 40% | Branch coverage MVP threshold |

### CI Default Behavior

- **plan-lint**: Warnings only, non-blocking
- **clang-tidy**: Warnings only if not installed
- **unit-tests**: Auto-discovers Python, Java, Go, C/C++ test files
- **coverage**: Uses `pytest-cov` if available, non-blocking if not installed
- **cross-compile**: Discovery only (no actual cross-compiler required)
- **static-analysis**: Uses cppcheck if available
- **memory-safety**: Discovery only (ASan tests directory)

### Reviewer Configuration

| Kind | Reviewers | Description |
|:-----|:----------|:------------|
| `feature` | 4 agents | Full check for new features |
| `bugfix` | 2 agents | Style + coverage |
| `refactor` | 3 agents | Architecture + style + coverage |
| `docs` | 0 agents | No technical review needed |
| `config` | 1 agent | Style only |

Max retries per review session: **5**
Coverage gate threshold: **98% line coverage** (coverage-guardian)

# Contributing to yuleOSH

Thank you for your interest in contributing to **yuleOSH**! This document outlines the process for contributing code, documentation, plugins, and bug reports.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Submit an Issue](#how-to-submit-an-issue)
- [How to Submit a Pull Request](#how-to-submit-a-pull-request)
- [Code Style & Conventions](#code-style--conventions)
- [Testing](#testing)
- [Plugin Development](#plugin-development)
- [Documentation](#documentation)
- [Commit Convention](#commit-convention)
- [Release Process](#release-process)

---

## Code of Conduct

This project is governed by the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you agree to uphold this code.

---

## Getting Started

1. Fork the repository on GitHub.
2. Clone your fork: `git clone git@github.com:<your-username>/yuleOSH.git`
3. Add upstream remote: `git remote add upstream https://github.com/frisky1985/yuleOSH.git`

---

## Development Setup

### Prerequisites

- Python 3.10+
- pip / pip3
- (Optional) Docker for CI testing

### Install

```bash
cd yuleOSH
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Verify

```bash
yuleosh --help
python3 -m pytest tests/ -q --tb=short
```

---

## How to Submit an Issue

### Bug Reports

Use the GitHub [Issues](https://github.com/frisky1985/yuleOSH/issues) page. Include:

- **Title**: Clear, concise description
- **Environment**: Python version, OS, yuleOSH version (`yuleosh --version`)
- **Steps to reproduce**: Minimal, complete, and verifiable
- **Expected vs actual behavior**: What you expected to happen vs what happened
- **Logs/stack traces**: If applicable, include full output
- **Spec file (if relevant)**: The OpenSpec `.md` input that triggered the issue

### Feature Requests

- Describe the problem you're trying to solve, not just a proposed solution
- Provide use cases and context
- If you have a spec draft, include it

### Labels

Maintainers will apply labels. Common ones:

| Label | Meaning |
|:------|:--------|
| `bug` | Confirmed defect |
| `enhancement` | Feature request |
| `good first issue` | Beginner-friendly |
| `help wanted` | Needs community input |
| `spec` | Relates to OpenSpec format |
| `pipeline` | Agent pipeline issue |
| `hardware` | HIL/flash/debug related |

---

## How to Submit a Pull Request

### Workflow

1. **Create a branch** from `main`:
   ```bash
   git checkout -b fix/my-bug-fix
   ```

2. **Make your changes** following [code conventions](#code-style--conventions).

3. **Write tests** — ensure coverage does not decrease.

4. **Update specs** if your change affects requirements (add/modify `docs/spec-delta-v*.md`).

5. **Run all tests locally**:
   ```bash
   python3 -m pytest tests/ -q --cov=src
   ```

6. **Self-review** your spec:
   ```bash
   python3 -m src.spec.validate docs/spec.md --json
   ```

7. **Commit** using [conventional commits](#commit-convention) and push.

8. **Open a PR** against `main` with a clear description:
   - What problem does this solve?
   - What approach did you take?
   - How did you test it?
   - Screenshots/logs if UI-related

### PR Checklist

Before marking your PR as ready for review:

- [ ] Spec updated (if requirements changed)
- [ ] Tests added and all passing
- [ ] Coverage not decreased
- [ ] No bare `except Exception:` without logging
- [ ] GIVEN/WHEN/THEN test patterns used
- [ ] Self-review passed (`spec validate` → 0 errors)
- [ ] Commits follow the convention
- [ ] Documentation updated (if public API changed)

### Review Process

1. **Automated CI** runs on every PR (Layer 1 tests, spec validation)
2. **At least one maintainer review** required
3. **Blocking review gate** — critical findings must be resolved before merge
4. Maintainer merges after approval

---

## Code Style & Conventions

### Python

- **Line length**: 100 characters max
- **Indentation**: 4 spaces (no tabs)
- **Type hints**: Use type annotations for all function signatures
- **Docstrings**: Google-style for public functions
- **Imports**: standard library → third-party → local; one per group

### Embedded C (in generated code)

- MISRA C:2012 guidelines (enforced by CI Layer 2 static analysis)
- No dynamic allocation in interrupt context
- All functions must have doc-comment blocks

### General Rules

1. **No bare `except Exception:`** — always log the error with context
2. **Write GIVEN/WHEN/THEN tests** — Mirror the OpenSpec format
3. **Spec-first: new features require spec delta docs** in `docs/spec-delta-v*.md`
4. **Self-review before PR** — run `src.spec.validate` on your spec
5. **CI must stay green** — all 4 CI layers must pass
6. **No silent degradation** — pipeline LLM failures must be hard errors
7. **No silent skips** — CI steps must explicitly report status

---

## Testing

### Running Tests

```bash
# All tests
python3 -m pytest tests/ -q

# Specific module
python3 -m pytest tests/test_jwt_auth.py -v

# With coverage
python3 -m pytest tests/ --cov=src --cov-report=term-missing

# With coverage threshold
python3 -m pytest tests/ --cov=src --cov-fail-under=38
```

### Test Structure

```
tests/
├── conftest.py              Shared fixtures
├── test_*.py                Unit tests per module
├── test_ci_end_to_end.py    CI integration tests
└── e2e/                     End-to-end pipeline tests
```

- Unit tests go in `tests/test_<module>.py`
- Integration tests for multi-step workflows
- Every test follows GIVEN/WHEN/THEN docstring format

### Coverage Target

- Minimum threshold: **38%** (overall)
- No decrease on PR (enforced by CI)

---

## Plugin Development

yuleOSH supports a plugin system for custom hardware adapters, review rules, and CI steps.

### Plugin Structure

```
my-plugin/
├── __init__.py          # Plugin metadata (name, version, hooks)
├── adapter.py           # Optional: hardware adapter
├── review_rules.py      # Optional: custom review checks
└── ci_steps.py          # Optional: custom CI steps
```

### Plugin Registration

Plugins are registered via the `src/plugins/registry.py` system:

```python
# In your plugin's __init__.py
from src.plugins.registry import register_plugin

register_plugin(
    name="my-custom-flasher",
    version="1.0.0",
    hooks=["flash", "monitor"],
    entry_point="my_plugin.adapter:MyFlasher",
)
```

### Plugin Sandbox

Plugins run in a sandboxed environment. See `src/plugins/sandbox.py` for details.

For the full plugin specification, see [docs/plugin-spec.md](docs/plugin-spec.md).

---

## Documentation

- All public APIs must have docstrings
- User-facing changes should update `docs/` guides
- Spec changes require a delta document: `docs/spec-delta-v<version>.md`
- Documentation is maintained in Markdown; HTML builds are generated

---

## Commit Convention

```
<type>: <short description>

[optional body]

[optional footer]
```

### Types

| Type | Emoji | Usage |
|:-----|:------|:------|
| `fix` | 🔧 | Bug fix |
| `feat` | ✨ | New feature |
| `coverage` | 📈 | Test/coverage improvement |
| `docs` | 📋 | Documentation |
| `test` | 🧪 | Test additions |
| `release` | 🎯 | Version release |
| `refactor` | ♻️ | Code restructuring |
| `ci` | 👷 | CI configuration changes |
| `perf` | ⚡️ | Performance improvement |
| `chore` | 🧹 | Maintenance tasks |

### Examples

```
✨ feat: add ESP32-S3 target config

Support ESP32-S3 with custom flash layout and dual-core debug.

Closes #42
```

```
🔧 fix: handle empty requirement ID in spec parser

GIVEN a spec with an unnamed requirement block
WHEN the parser encounters an empty ID
THEN it should skip without crashing

Fixes #57
```

---

## Release Process

1. **Spec freeze**: All spec deltas merged for the target version
2. **Feature freeze**: Only bug fixes after spec freeze
3. **Release branch**: `release/v<major>.<minor>.<patch>`
4. **QA**: Full CI pipeline run + smoke test
5. **Tag**: `git tag v<major>.<minor>.<patch>`
6. **Release notes**: Generated from commit history
7. **Publish**: PyPI release + Docker image tag

---

## Need Help?

- Open a [Discussion](https://github.com/frisky1985/yuleOSH/discussions)
- Check the [FAQ](docs/FAQ.md)
- Read the [User Guide](docs/user-guide.md)

---

Thank you for contributing to yuleOSH! 🚀

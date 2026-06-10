# Contributing to yuleOSH

## Development Setup

```bash
git clone git@github.com:frisky1985/yuleOSH.git
cd yuleOSH
pip3 install -e ".[dev]"
pip3 install bcrypt PyJWT pytest pytest-cov pytest-mock
```

## Project Structure

```
src/
├── ui/           # Web UI + auth (server.py, auth.py, auth_extended.py)
├── api/          # REST API v1 (router + 14 resource handlers)
├── pipeline/     # Workflow engine (steps, run, prompts)
├── ci/           # CI/CD (4-layer pipeline)
├── llm/          # LLM agent client
├── spec/         # OpenSpec parser + validator + diff
├── evidence/     # Traceability + acceptance matrix
├── cross/        # Cross-compilation + HIL + SIL
└── store.py      # Multi-tenant SQLite database
```

## Testing

```bash
# All tests
python3 -m pytest tests/ -q

# Specific module
python3 -m pytest tests/test_jwt_auth.py -v

# With coverage
python3 -m pytest tests/ --cov=src --cov-report=term-missing
```

## Code Quality Rules

1. **No bare `except Exception:`** — always log the error
2. **GIVEN/WHEN/THEN test patterns** — every test follows the spec format
3. **Spec-first**: new features require `docs/spec-delta-v*.md`
4. **Self-review**: run `python3 -m src.spec.validate docs/spec.md --json` before PR
5. **CI green**: all 4 CI layers must pass

## Commit Convention

```
🔧 fix: description           # Bug fixes
✨ feat: description          # New features
📈 coverage: description      # Coverage improvements
📋 docs: description          # Documentation
🧪 test: description          # Test additions
🎯 release: description       # Version releases
```

## Pull Request Checklist

- [ ] Spec updated (`docs/spec-delta-v*.md`)
- [ ] Tests added and passing
- [ ] Coverage not decreased
- [ ] No bare `except Exception:` added
- [ ] Self-review passed (spec validate → 0 errors)

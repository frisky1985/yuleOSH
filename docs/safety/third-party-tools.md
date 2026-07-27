# Third-Party Tool Dependency Analysis

> **文档 ID**: G-08-TPT-001  
> **适用项目**: yuleOSH CI/CD + Agent Pipeline  
> **标准依据**: ISO 26262-8:2018 §11, ASPICE SUP.10  
> **版本**: 1.0  
> **生成日期**: 2026-07-26  

---

## 1. Overview

This document provides a comprehensive analysis of all third-party software tools used in the yuleOSH pipeline. For each tool, we analyze:

- Version and license
- Known limitations relevant to safety-related development
- Alternative tools and substitution feasibility
- Dependency chain depth
- Qualification status

---

## 2. Tool Inventory

### 2.1 Pipeline Tools

| # | Tool | Version | License | Used In Stage | Purpose | Qualification Status |
|:-:|:-----|:--------|:--------|:--------------|:--------|:--------------------|
| 1 | **cppcheck** | 2.17.1 | GPL v3 | MISRA Check | MISRA C:2023 static analysis | ✅ Qualified |
| 2 | **MISRA addon** | (bundled) | GPL v3 | MISRA Check | MISRA rule enforcement | ✅ Qualified |
| 3 | **lcov** | 2.x | GPL v2 | Coverage | C/C++ coverage data (geninfo/genhtml) | ✅ Qualified |
| 4 | **gcovr** | 8.x | BSD 3-Clause | Coverage | C/C++ coverage report generation | ✅ Qualified |
| 5 | **gcov** | (GCC built-in) | GPL v3 | Coverage | Code coverage instrumentation | ✅ Qualified |
| 6 | **Unity Test** | 2.6.x | MIT | Unit Test | C unit test framework | ✅ Qualified |
| 7 | **pytest** | 8.x | MIT | Unit Test, Integration Test | Python test framework | ✅ Qualified |
| 8 | **pytest-cov** | 6.x | MIT | Coverage | Python coverage plugin | ✅ Qualified |
| 9 | **pytest-xdist** | 3.x | MIT | Unit Test | Parallel test execution | ✅ Watch |
| 10 | **clang-tidy** | 18.x | Apache 2.0 | Code Review | Clang static analysis | ✅ Qualified |
| 11 | **arm-none-eabi-gcc** | 13.x | GPL v3 | Integration Test | ARM cross-compiler | ✅ Qualified |
| 12 | **riscv64-unknown-elf-gcc** | 13.x | GPL v3 | Integration Test | RISC-V cross-compiler | ✅ Watch |
| 13 | **Python 3** | 3.13.x | PSF | All Stages | Pipeline runtime environment | ✅ Qualified |
| 14 | **PyYAML** | 6.x | MIT | All Stages | YAML config parsing | ✅ Qualified |
| 15 | **tomllib** | (stdlib) | PSF | Report Generation | TOML config parsing | ✅ Qualified |

### 2.2 Agent Pipeline Tools (AI/LLM)

| # | Tool/Service | Version | License | Used In Stage | Purpose | Qualification Status |
|:-:|:-------------|:--------|:--------|:--------------|:--------|:--------------------|
| 16 | **Claude (Anthropic)** | API v1 | Commercial | Code Review, Safety Check, Report Generation | AI agent (小克 — 开发) | ✅ Controlled |
| 17 | **DeepSeek (DeepSeek)** | API v4 | Commercial | All Agent Stages | AI agent (小明/小马/Hermes) | ✅ Controlled |
| 18 | **Mock LLM** | (yuleOSH built-in) | MIT | All Agent Stages (mock mode) | Test mode without real API | ✅ N/A |

### 2.3 Infrastructure Tools

| # | Tool/Service | Version | License | Purpose | Qualification Status |
|:-:|:-------------|:--------|:--------|:---------|:--------------------|
| 19 | **Git** | 2.x | GPL v2 | Version control / Evidence source | ✅ Qualified |
| 20 | **Make** | 4.x | GPL v3 | Build orchestration | ✅ Qualified |
| 21 | **Docker** | 27.x | Apache 2.0 | Cross-compilation container | ✅ Watch |
| 22 | **OpenSSL** | 3.x | Apache 2.0 | Evidence pack SHA-256 + RSA signing | ✅ Qualified |
| 23 | **RSA key generation** | (OpenSSL) | Apache 2.0 | Key generation for evidence signing | ✅ Qualified |

---

## 3. Detailed Tool Analysis

### 3.1 cppcheck + MISRA addon

| Attribute | Detail |
|:----------|:--------|
| **Current Version** | 2.17.1 |
| **License** | GPL v3 (copyleft — static analysis only, no linking into product) |
| **Pipeline Stage** | MISRA Check (Layer 1) |
| **Call Signature** | `cppcheck --addon=misra --enable=all --std=c11 <src>` |
| **Output Format** | Text (default), JSON (via --xml), Markdown (via misra_report.py) |

**Known Limitations:**

| Limitation | Details | Workaround | Status |
|:-----------|:--------|:-----------|:-------|
| MISRA rule coverage | ~120/169 rules (~71%), ~49 rules not auto-detectable | AI + manual review supplement | Active |
| False positive rate | 20–30% overall; Required rules 10–15% | Deviation management + suppresses | Active |
| Control flow analysis | Limited for complex CFG, pointer aliasing | AI review supplement | Active |
| MISRA C:2023 addon | Separate addon, not core cppcheck | Version-lock the addon | Active |
| macOS compatibility | No known regression vs Linux | Platform-agnostic outputs | Monitor |
| Multi-threaded analysis | cppcheck v2.17.1 has --jobs support | Use --jobs=4 for CI | Active |

**Alternatives:**

| Alternative | Pros | Cons | Feasibility |
|:------------|:-----|:-----|:-------------|
| **Axivion Suite** | Full MISRA C:2023, ASIL D certified | €15K+/seat/year | Low (cost) |
| **PC-lint** | Comprehensive rule set | Commercial license | Low (cost) |
| **Clang-tidy** | Open source, fast | Limited MISRA support | Partial |
| **Helix QAC** | ASIL D certified | €20K+/seat/year | Low (cost) |
| **SonarQube** | Good UI, broad rules | Not MISRA-specific | Low |

**Dependency Chain:** `cppcheck → MISRA addon → Python 3 (misra_report.py) → PyYAML`

**Substitution Feasibility:** Medium — open source alternatives exist but lack ASIL certification. Cost of certified tools is prohibitive (10–20x yuleOSH pricing). Compensation via AI + manual review is the pragmatic approach.

### 3.2 lcov + gcovr

| Attribute | Detail |
|:----------|:--------|
| **Current Version** | lcov 2.x, gcovr 8.x |
| **License** | lcov: GPL v2, gcovr: BSD 3-Clause |
| **Pipeline Stage** | Coverage (Layer 1) |
| **Call Signature** | `lcov --capture --directory <build>`, `gcovr --json <build>` |

**Known Limitations:**

| Limitation | Details | Workaround | Status |
|:-----------|:--------|:-----------|:-------|
| macOS no branch coverage | `--branch-coverage` not fully supported | Linux CI + platform annotation | Active |
| gcovr JSON precision | Percentage rounding may lose small values | Use lcov INFO as primary source | Monitor |
| .gcda file dependency | Requires clean execution of instrumented binary | Retry on failure + consistency check | Active |
| Cross-compilation | gcovr needs matching target gcov | Add target-specific gcov path | Active |
| Large project performance | genhtml on 1000+ files is slow | Use `--output-name` for targeted reports | Active |

**Alternatives:**

| Alternative | Pros | Cons | Feasibility |
|:------------|:-----|:-----|:-------------|
| **Coveralls** | SaaS, UI, history tracking | Cost, data leaves CI env | Partial |
| **Codecov** | Same as Coveralls | Same | Partial |
| **BullseyeCoverage** | Branch + condition, certified | Commercial, €2K/seat | Low (cost) |
| **Tessy** | Unit + integration coverage, ISO 26262 certified | €5K+/seat | Low (cost) |

**Dependency Chain:** `lcov → gcov (GCC) | gcovr → gcov (GCC)`

**Substitution Feasibility:** High — gcovr's BSD license allows commercial use. Multiple free and paid alternatives exist.

### 3.3 Unity Test Framework

| Attribute | Detail |
|:----------|:--------|
| **Current Version** | 2.6.x |
| **License** | MIT (permissive) |
| **Pipeline Stage** | Unit Test (Layer 1) |
| **Usage** | C unit test runner with assertion macros |

**Known Limitations:**

| Limitation | Details | Workaround | Status |
|:-----------|:--------|:-----------|:-------|
| No built-in mocking | Requires hand-written stubs | MockHAL abstraction layer | Active |
| No test case description field | Uses function name as description | TDD-style naming convention | Active |
| Limited assertion types | Missing floating-point comparison | Custom assert macros | Active |

**Alternatives:**

| Alternative | Pros | Cons | Feasibility |
|:------------|:-----|:-----|:-------------|
| **Google Test** | Rich assertions, mocking | C++ only, heavy | Low |
| **CMock** | Auto mock generation | Requires Ruby | Medium |
| **Ceedling** | Unity + CMock bundle | Build system coupling | Medium |
| **CMocka** | C only, lightweight | Less assertion variety | Medium |

**Dependency Chain:** Unity (standalone C library, no runtime deps)

**Substitution Feasibility:** High — MIT license, minimal dependencies.

### 3.4 pytest + pytest-cov

| Attribute | Detail |
|:----------|:--------|
| **Current Version** | pytest 8.x, pytest-cov 6.x |
| **License** | MIT (permissive) |
| **Pipeline Stage** | Unit Test, Integration Test (Layers 1, 2, 3) |
| **Usage** | Python test runner integrated with yuleOSH CLI |

**Known Limitations:**

| Limitation | Details | Workaround | Status |
|:-----------|:--------|:-----------|:-------|
| Large parametrized datasets | May timeout | Use -x mode + timeout config | Active |
| Python 3.13 regressions | Early versions may have compatibility | Version-lock to stable releases | Monitor |

**Alternatives:**

| Alternative | Pros | Cons | Feasibility |
|:------------|:-----|:-----|:-------------|
| **unittest (stdlib)** | No dependency, stdlib | Less features, no plugin | High |
| **nose2** | Plugin-based | Less maintained | Medium |

**Dependency Chain:** `pytest → pytest-cov → coverage.py`

**Substitution Feasibility:** High — MIT license, ubiquitous.

### 3.5 AI/LLM Services (Claude + DeepSeek)

| Attribute | Detail |
|:----------|:--------|
| **Tool Type** | External API service |
| **Pipeline Stage** | All Agent Pipeline Stages |
| **Role** | AI agent: 小明 (spec/safety), 小克 (dev/test), Hermes/小马 (review) |

**Known Limitations:**

| Limitation | Details | Workaround | Status |
|:-----------|:--------|:-----------|:-------|
| Output non-determinism | Same input → possibly different output | Prompt version locking + temperature=0 | Active |
| API availability | Dependent on service provider uptime | Mock mode for CI without API | Active |
| Model version changes | Provider may update model silently | API version pinning in CI config | Active |
| Token cost | Large specs consume significant tokens | Spec chunking + cost tracking | Active |
| No formal certification | AI models not ISO 26262 qualified | Human review gate + redundancy | Active |

**Alternatives:**

| Alternative | Pros | Cons | Feasibility |
|:------------|:-----|:-----|:-------------|
| **No AI (manual only)** | Full control, certifiable | 10x slower, 5x cost | Low (practicality) |
| **OpenAI GPT-4o** | Strong code generation | Different pricing, API SLA | High (substitutable) |
| **Local LLM (ollama)** | Data never leaves control | Lower quality | Medium |

---

## 4. Version Locking Strategy

### 4.1 Locking Mechanisms

| Tool | Locking Method | Location |
|:-----|:---------------|:---------|
| cppcheck | Version pinned in CI config + error on mismatch | `ci-config.yaml` + CI env |
| MISRA addon | Bundled with cppcheck package | CI image |
| lcov | Homebrew/apt version pin | `install.sh` |
| gcovr | pip version pin (pyproject.toml) | `pyproject.toml` |
| Unity | Git submodule pin | `.gitmodules` |
| pytest | pip version pin (pyproject.toml) | `pyproject.toml` |
| Python | CI image version pin | Dockerfile |
| LLM models | API version header + model string | CI config env |
| gcc-arm-none-eabi | apt/homebrew version pin | `install.sh` |

### 4.2 Version Matrix

```yaml
# tool-versions.yaml — CI environment lock file
tools:
  cppcheck: "2.17.1"
  misra_addon: "bundled-cppcheck-2.17.1"
  lcov: "2.0"
  gcovr: "8.0"
  unity: "2.6.0"
  pytest: "8.3"
  pytest-cov: "6.0"
  python: "3.13"
  arm-gcc: "13.2"
  riscv-gcc: "13.2"
  openssl: "3.2"

llm:
  claude_model: "claude-sonnet-4-20250514"
  deepseek_model: "deepseek/deepseek-v4-flash"
  temperature: 0
  max_tokens: 4096
```

---

## 5. License Compliance Summary

| Tool | License | Type | Commercial Use | Copyleft Risk |
|:-----|:--------|:-----|:---------------|:--------------|
| cppcheck | GPL v3 | Copyleft strong | ✅ (static analysis only) | ✅ No risk (no linking) |
| lcov | GPL v2 | Copyleft | ✅ (output is data, not code) | ✅ No risk (data only) |
| gcovr | BSD 3-Clause | Permissive | ✅ | ✅ None |
| Unity | MIT | Permissive | ✅ | ✅ None |
| pytest | MIT | Permissive | ✅ | ✅ None |
| clang-tidy | Apache 2.0 | Permissive | ✅ | ✅ None |
| GCC (arm/riscv) | GPL v3 | Copyleft strong | ✅ (output is compiled code) | ✅ Exception (GCC runtime) |
| Python 3 | PSF | Permissive | ✅ | ✅ None |
| OpenSSL | Apache 2.0 | Permissive | ✅ | ✅ None |

**Risk Classification:**
- ✅ Safe — no restriction for commercial closed-source products
- ⚠️ Conditional — requires compliance action
- ❌ Restricted — cannot use in target product

All tools in yuleOSH pipeline are categorized as **✅ Safe** for use in commercial AUTOSAR ECU development.

---

## 6. Dependencies Between Pipeline Stages

### 6.1 Stage Dependency Graph

```
code_review ← (no tool dependency, AI-based)
     ↓
misra_check ← cppcheck
     ↓
coverage ← lcov, gcovr, gcov, pytest-cov
     ↓
unit_test ← Unity, pytest
     ↓
integration_test ← pytest, MockHAL, cross-compiler
     ↓
evidence_pack ← OpenSSL (SHA-256 + RSA), all prior stage outputs
     ↓
safety_check ← AI + expert review
     ↓
report_generation ← LLM, Python stdlib
```

### 6.2 Shared Dependencies

| Shared Dependency | Used By |
|:------------------|:--------|
| Python 3 + stdlib | All stages (pipeline runtime) |
| Git | All stages (source + evidence) |
| OpenSSL | Evidence Pack (signing + hashing) |
| JSON parser (stdlib) | All stages (data serialization) |

---

## 7. Version Lifecycle Management

### 7.1 Tool Retirement Criteria

A tool should be considered for replacement when any of the following occur:

1. **Tool no longer maintained** — no updates in > 2 years after a major platform change
2. **License changes** — incompatible with commercial distribution
3. **CVE severity ≥ Critical** — vendor fails to patch within 30 days
4. **Accuracy regression** — detection rate drops > 10% over two consecutive minor releases
5. **Better alternative available** — compelling cost/accuracy improvement

### 7.2 Known EOL/Deprecation Risks

| Tool | Risk Level | Expected EOL | Mitigation |
|:-----|:----------:|:-------------|:-----------|
| lcov (genhtml) | Low | Community maintained | gcovr 已覆盖相同功能 |
| gcovr | Low | Active development | BSD license, widely adopted |
| Unity | Low | Active community | 单一文件 C 框架，几乎无依赖 |
| cppcheck | Low | Active development | MISRA addon 持续更新 |

---

## 8. Conclusion

All third-party tools used in the yuleOSH pipeline:

1. ✅ Are **openly licensed** for commercial use in AUTOSAR ECU development
2. ✅ Have **known limitation documentation** with established workarounds
3. ✅ Have **feasible substitution paths** if needed
4. ✅ Are **version-locked** and regression-tested per release
5. ✅ Have **manageable dependency chains** with no recursive risky dependencies

The single TCL2 classification (cppcheck MISRA addon) is compensated by:
- AI-based supplementary analysis covering the ~29% gap in rule coverage
- Human review for all safety-relevant violations
- Formal deviation management process
- Per-release regression benchmarking

---

*本文档由 yuleOSH CI 框架自动管理*
*版本 1.0 | 2026-07-26*
*下次复审: 下一个 Release 版本前*

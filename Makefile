# =============================================================================
# yuleOSH — Cross-compilation Makefile
#
# Targets:
#   make TARGET=arm      — Build ARM .elf
#   make TARGET=riscv    — Build RISC-V .elf  (optional)
#   make TARGET=all      — Build all targets
#   make clean           — Remove build artifacts
#   make check-tools     — Verify toolchain availability
# =============================================================================

TARGET     ?= arm
BUILD_DIR  ?= build
SRC_DIR    ?= src/cross
SOURCES     = $(wildcard $(SRC_DIR)/*.c)

# Output files
ARM_ELF    = $(BUILD_DIR)/hello-arm.elf
RISCV_ELF  = $(BUILD_DIR)/hello-riscv.elf

# Toolchain definitions
ARM_CC     = arm-none-eabi-gcc
RISCV_CC   = riscv64-unknown-elf-gcc
ARM_CFLAGS = -mcpu=cortex-m4 -mthumb -Wall -Wextra -O2 -specs=nano.specs
RISCV_CFLAGS = -march=rv64imac -mabi=lp64 -Wall -Wextra -O2

# 静态代码检查编译模式 (P0 GATE — 全部静态分析)
# make MODE=safe 时启用 — 所有告警转错误
ifeq ($(MODE),safe)
ARM_CFLAGS += -Werror -Wconversion -Wuninitialized \
	-Wmaybe-uninitialized -Wnull-dereference \
	-Wdouble-promotion -Wformat=2 -Wfloat-equal \
	-Wdiv-by-zero -fstack-protector-strong -fstack-clash-protection
endif

# Detect available tools
HAS_ARM   := $(shell command -v $(ARM_CC) 2>/dev/null && echo yes || echo no)
HAS_RISCV := $(shell command -v $(RISCV_CC) 2>/dev/null && echo yes || echo no)

.PHONY: all arm riscv clean check-tools

# ------------------------------------------------------------------
# Default: build selected target
# ------------------------------------------------------------------
ifeq ($(TARGET),arm)
all: arm
else ifeq ($(TARGET),riscv)
all: riscv
else ifeq ($(TARGET),all)
all: arm riscv
else
$(error Unknown TARGET "$(TARGET)". Use: arm, riscv, or all)
endif

# ------------------------------------------------------------------
# ARM target
# ------------------------------------------------------------------
arm: $(ARM_ELF)

$(ARM_ELF): $(SOURCES) | $(BUILD_DIR)
ifeq ($(HAS_ARM),yes)
	$(ARM_CC) $(ARM_CFLAGS) -o $@ $^
	@echo "  ✅ ARM ELF: $@"
else
	@echo "  ⏭️  ARM toolchain not found — install gcc-arm-none-eabi"
	@exit 1
endif

# ------------------------------------------------------------------
# RISC-V target
# ------------------------------------------------------------------
riscv: $(RISCV_ELF)

$(RISCV_ELF): $(SOURCES) | $(BUILD_DIR)
ifeq ($(HAS_RISCV),yes)
	$(RISCV_CC) $(RISCV_CFLAGS) -o $@ $^
	@echo "  ✅ RISC-V ELF: $@"
else
	@echo "  ⏭️  RISC-V toolchain not found — skipping"
endif

# ------------------------------------------------------------------
# Build directory
# ------------------------------------------------------------------
$(BUILD_DIR):
	mkdir -p $@

# ------------------------------------------------------------------
# Clean
# ------------------------------------------------------------------
clean:
	rm -rf $(BUILD_DIR)
	@echo "  ✅ Cleaned build artifacts"

# ------------------------------------------------------------------
# Toolchain verification
# ------------------------------------------------------------------
check-tools:
	@echo "=== Toolchain check ==="
	@echo -n "arm-none-eabi-gcc: "; \
		if [ "$(HAS_ARM)" = "yes" ]; then \
			$(ARM_CC) --version | head -1; \
		else \
			echo "NOT FOUND"; \
		fi
	@echo -n "riscv64-unknown-elf-gcc: "; \
		if [ "$(HAS_RISCV)" = "yes" ]; then \
			$(RISCV_CC) --version | head -1; \
		else \
			echo "NOT FOUND (optional)"; \
		fi
	@echo "=== Done ==="

# =============================================================================
# CI Targets — yuleOSH CI Pipeline
# =============================================================================

.PHONY: ci ci-layer1 ci-layer2 ci-layer25 ci-layer3 ci-mock

# Make Python invocation portable
PYTHON ?= python3

# ------------------------------------------------------------------
# CI Layer 1: Development Verification (plan-lint, unit-tests, coverage)
# ------------------------------------------------------------------
ci-layer1:
	@echo "=== CI Layer 1: Development Verification ==="
	cd $(CURDIR) && $(PYTHON) -m src.ci.run 1

# ------------------------------------------------------------------
# CI Layer 2: Integration Verification
# ------------------------------------------------------------------
ci-layer2:
	@echo "=== CI Layer 2: Integration Verification ==="
	cd $(CURDIR) && $(PYTHON) -m src.ci.run 2

# ------------------------------------------------------------------
# CI Layer 2.5: Hardware-in-the-Loop (mock mode by default)
# ------------------------------------------------------------------
ci-layer25:
	@echo "=== CI Layer 2.5: Hardware-in-the-Loop (mock) ==="
	cd $(CURDIR) && $(PYTHON) -m src.ci.run 25

# ------------------------------------------------------------------
# CI Layer 3: System Verification
# ------------------------------------------------------------------
ci-layer3:
	@echo "=== CI Layer 3: System Verification ==="
	cd $(CURDIR) && $(PYTHON) -m src.ci.run 3

# ------------------------------------------------------------------
# Full CI pipeline: L1 → L2 → L2.5 → L3
# Fails fast on first error
# ------------------------------------------------------------------
ci:
	@echo "=== yuleOSH Full CI Pipeline ==="
	@echo "Layer 1: Dev Verify + Coverage Gate"
	cd $(CURDIR) && $(PYTHON) -m src.ci.run 1 || exit 1
	@echo "Layer 2: Integration Verify"
	cd $(CURDIR) && $(PYTHON) -m src.ci.run 2 || exit 1
	@echo "Layer 2.5: HIL (mock mode)"
	cd $(CURDIR) && $(PYTHON) -m src.ci.run 25 || exit 1
	@echo "Layer 3: System Verify"
	cd $(CURDIR) && $(PYTHON) -m src.ci.run 3 || exit 1
	@echo "✅ Full CI Pipeline: ALL LAYERS PASSED"

# ------------------------------------------------------------------
# Quick CI: plan-lint + unit tests only (for development iteration)
# ------------------------------------------------------------------
ci-quick:
	@echo "=== Quick CI: unit tests + coverage ==="
	cd $(CURDIR) && $(PYTHON) -m pytest --cov=cross --cov-branch --cov-report=term-missing -q
	@echo "=== Done ==="

# ------------------------------------------------------------------
# Semgrep targets
# ------------------------------------------------------------------

.PHONY: semgrep semgrep-python semgrep-c semgrep-dataflow

# Run all Semgrep rules
semgrep:
	@echo "=== Semgrep: SAST + 数据流分析 ==="
	cd $(CURDIR) && bash scripts/run-semgrep.sh

# Run Python security rules only
semgrep-python:
	@echo "=== Semgrep: Python Security ==="
	semgrep --config=.semgrep/security-python.yml --error --metrics=off src/

# Run C/C++ security rules only
semgrep-c:
	@echo "=== Semgrep: C/C++ Security ==="
	semgrep --config=.semgrep/security-c.yml --error --metrics=off src/ || true

# Run data flow analysis (taint tracking)
semgrep-dataflow:
	@echo "=== Semgrep: Data Flow Analysis ==="
	semgrep --config=.semgrep/dataflow-python.yml --error --metrics=off src/

# ------------------------------------------------------------------
# CodeQL targets
# ------------------------------------------------------------------

.PHONY: codeql codeql-python codeql-clean

# Run full CodeQL analysis (requires codeql CLI installed)
codeql:
	@echo "=== CodeQL: 深度安全 + 数据流分析 ==="
	cd $(CURDIR) && bash scripts/run-codeql.sh

codeql-python:
	@echo "=== CodeQL: Python 深度分析 ==="
	@if ! command -v codeql &>/dev/null; then \
		echo "❌ codeql not installed. See scripts/run-codeql.sh for install instructions."; \
		exit 1; \
	fi
	$(eval DB_DIR := .codeql-db)
	rm -rf $(DB_DIR)
	codeql database create $(DB_DIR) --language=python --source-root=. --overwrite
	codeql database analyze $(DB_DIR) --format=sarif-latest --output=codeql-python.sarif codeql/python-queries:codeql-suites/python-security-extended.qls
	rm -rf $(DB_DIR)
	@echo "  ✅ CodeQL complete — report: codeql-python.sarif"

# Full CI pipeline with SAST
ci-sast:
	@echo "=== yuleOSH SAST Pipeline ==="
	$(MAKE) semgrep-python
	$(MAKE) semgrep-c
	$(MAKE) semgrep-dataflow
	@echo "  ✅ SAST Pipeline: All passes"

# ------------------------------------------------------------------
# CVE Security Scan
# ------------------------------------------------------------------

.PHONY: cve-scan cve-scan-python cve-scan-npm

# Run full CVE scan (Python + npm)
cve-scan:
	@echo "=== CVE Security Scan ==="
	cd $(CURDIR) && bash scripts/cve-scan.sh --all
	@echo "  ✅ CVE scan complete"

# Python dependencies only
cve-scan-python:
	@echo "=== CVE Security Scan: Python ==="
	cd $(CURDIR) && bash scripts/cve-scan.sh --python
	@echo "  ✅ Python CVE scan complete"

# npm dependencies only
cve-scan-npm:
	@echo "=== CVE Security Scan: npm ==="
	cd $(CURDIR) && bash scripts/cve-scan.sh --npm
	@echo "  ✅ npm CVE scan complete"

# ------------------------------------------------------------------
# C Coverage targets
# ------------------------------------------------------------------

.PHONY: c-coverage c-coverage-gate

# Run C coverage and save report
c-coverage:
	@echo "=== C Coverage ==="
	cd $(CURDIR) && $(PYTHON) scripts/run_c_coverage.py

# Run C coverage with gate enforcement (exit 1 if below threshold)
c-coverage-gate:
	@echo "=== C Coverage Gate (>=60%) ==="
	cd $(CURDIR) && $(PYTHON) scripts/run_c_coverage.py --fail-under=60
	@echo "  ✅ C coverage gate passed"

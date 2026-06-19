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

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

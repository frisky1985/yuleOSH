# =============================================================================
# yuleOSH — SIL test firmware Makefile
#
# Builds hello-arm.elf for lm3s6965evb / Cortex-M3 QEMU target.
#
# Requirements:
#   arm-none-eabi-gcc (from gcc-arm-none-eabi package)
#
# Targets:
#   make                — Build hello-arm.elf
#   make install-prebuilt — Copy .elf to tests/fixtures/prebuilt/ for CI
#   make clean          — Remove build artifacts
# =============================================================================

TARGET   ?= hello-arm.elf
BUILD_DIR ?= build

CC       = arm-none-eabi-gcc
CFLAGS   = -mcpu=cortex-m3 -mthumb \
           -Wall -Wextra -Wpedantic \
           -O2 -ffreestanding -nostartfiles \
           -specs=nano.specs
LDFLAGS  = -Wl,-Ttext=0x08000000 -Wl,--gc-sections

SRCS     = hello.c startup.c
OBJS     = $(SRCS:.c=.o)

# ------------------------------------------------------------------
# Detect toolchain
# ------------------------------------------------------------------
HAS_ARM := $(shell command -v $(CC) 2>/dev/null && echo yes || echo no)

# ------------------------------------------------------------------
# Targets
# ------------------------------------------------------------------
.PHONY: all clean install-prebuilt

all: $(BUILD_DIR)/$(TARGET)

$(BUILD_DIR)/$(TARGET): $(OBJS) | $(BUILD_DIR)
ifeq ($(HAS_ARM),yes)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(OBJS)
	@echo "  ✅ SIL test firmware: $@"
else
	@echo "  ⏭️  ARM toolchain not found — install gcc-arm-none-eabi"
	@echo "     sudo apt install gcc-arm-none-eabi"
	@exit 1
endif

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

$(BUILD_DIR):
	mkdir -p $@

# ------------------------------------------------------------------
# Convenience: copy .elf to prebuilt/ for CI pipeline
# ------------------------------------------------------------------
install-prebuilt: $(BUILD_DIR)/$(TARGET)
	cp $(BUILD_DIR)/$(TARGET) ../prebuilt/
	$(RM) $(BUILD_DIR)/hello-arm.elf
	@echo "  ✅ Installed to tests/fixtures/prebuilt/"

# ------------------------------------------------------------------
# Clean
# ------------------------------------------------------------------
clean:
	rm -rf $(BUILD_DIR) *.o
	@echo "  ✅ Cleaned"

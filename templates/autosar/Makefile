# =============================================================================
# Makefile — yuleASR AUTOSAR BSW Project (S32K312)
# =============================================================================
#
# Prerequisites:
#   - YULEASR_HOME: path to yuleASR BSW platform checkout
#   - arm-none-eabi-gcc: GNU Arm Embedded Toolchain
#
# Usage:
#   make              # Build project
#   make clean        # Clean build artifacts
#   make flash        # Flash to target via OpenOCD/JLink
#

# ── Project Configuration ──────────────────────────────────────────────────

PROJECT    ?= autosar-app
TARGET     ?= S32K312

# ── Toolchain ──────────────────────────────────────────────────────────────

CC         = arm-none-eabi-gcc
AS         = arm-none-eabi-as
LD         = arm-none-eabi-ld
OBJCOPY    = arm-none-eabi-objcopy
SIZE       = arm-none-eabi-size
GDB        = arm-none-eabi-gdb

# ── yuleASR Path ────────────────────────────────────────────────────────────

YULEASR_HOME ?= $(error YULEASR_HOME is not set. Point it to your yuleASR checkout.)

# ── Directories ─────────────────────────────────────────────────────────────

SRC_DIR       = src
BUILD_DIR     = build
CONFIG_DIR    = config
LINKER_DIR    = linker

# ── Include Paths ───────────────────────────────────────────────────────────

YULEASR_INCLUDES = \
    -I$(YULEASR_HOME)/include/autosar/classic \
    -I$(YULEASR_HOME)/src/bsw/services/dcm/include \
    -I$(YULEASR_HOME)/src/bsw/services/dem/include \
    -I$(YULEASR_HOME)/src/bsw/services/com/include \
    -I$(YULEASR_HOME)/src/bsw/services/nvm/include \
    -I$(YULEASR_HOME)/src/bsw/services/ecum/include \
    -I$(YULEASR_HOME)/src/bsw/services/bswm/include \
    -I$(YULEASR_HOME)/src/bsw/services/schm/include \
    -I$(YULEASR_HOME)/src/bsw/services/pdur/include \
    -I$(YULEASR_HOME)/src/bsw/services/e2e/include \
    -I$(YULEASR_HOME)/src/bsw/services/csm/include \
    -I$(YULEASR_HOME)/src/bsw/services/det/include \
    -I$(YULEASR_HOME)/src/bsw/services/wdgm/include \
    -I$(YULEASR_HOME)/src/bsw/services/e2e/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/mcu/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/port/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/dio/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/gpt/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/can/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/adc/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/spi/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/lin/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/pwm/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/fls/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/flash/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/eep/include \
    -I$(YULEASR_HOME)/src/bsw/mcal/wdg/include \
    -I$(YULEASR_HOME)/src/bsw/ecual/canif/include \
    -I$(YULEASR_HOME)/src/bsw/ecual/cantp/include \
    -I$(YULEASR_HOME)/src/bsw/ecual/linif/include \
    -I$(YULEASR_HOME)/src/bsw/ecual/lintp/include \
    -I$(YULEASR_HOME)/src/bsw/ecual/memif/include \
    -I$(YULEASR_HOME)/src/bsw/ecual/fee/include \
    -I$(YULEASR_HOME)/src/bsw/ecual/wdgif/include \
    -I$(YULEASR_HOME)/src/bsw/ecual/dlt/include \
    -I$(YULEASR_HOME)/cmake/modules

LOCAL_INCLUDES = \
    -I$(SRC_DIR) \
    -I$(CONFIG_DIR)

# ── Compiler Flags ──────────────────────────────────────────────────────────

ARCH_FLAGS   = -mcpu=cortex-m7 -mthumb -mfpu=fpv5-sp-d16 -mfloat-abi=hard
OPT_FLAGS    = -Os -g -ffunction-sections -fdata-sections
WARN_FLAGS   = -Wall -Wextra -Wshadow -Wconversion -Wunused-parameter

CFLAGS       = $(ARCH_FLAGS) $(OPT_FLAGS) $(WARN_FLAGS) \
               -std=c99 \
               -DUSE_AUTOSAR_OS \
               -D$(TARGET) \
               $(YULEASR_INCLUDES) \
               $(LOCAL_INCLUDES)

LDFLAGS      = $(ARCH_FLAGS) \
               -Wl,--gc-sections \
               -Wl,-Map=$(BUILD_DIR)/$(PROJECT).map \
               -T$(LINKER_DIR)/$(TARGET).ld

# ── Source Files ────────────────────────────────────────────────────────────

SRCS = \
    $(SRC_DIR)/main.c \
    $(SRC_DIR)/App_Swc.c \
    $(SRC_DIR)/SchM_App.c

OBJS = $(SRCS:$(SRC_DIR)/%.c=$(BUILD_DIR)/%.o)

# ── Targets ─────────────────────────────────────────────────────────────────

.PHONY: all clean flash size check-yuleasr

all: check-yuleasr $(BUILD_DIR)/$(PROJECT).elf $(BUILD_DIR)/$(PROJECT).hex $(BUILD_DIR)/$(PROJECT).bin size

# Check yuleASR path
check-yuleasr:
	@if [ ! -d "$(YULEASR_HOME)" ]; then \
		echo "ERROR: YULEASR_HOME='$(YULEASR_HOME)' not found."; \
		echo "Set YULEASR_HOME to your yuleASR checkout, e.g.:"; \
		echo "  export YULEASR_HOME=/path/to/yuleASR"; \
		exit 1; \
	fi
	@echo "yuleASR found at: $(YULEASR_HOME)"

# Compile
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

# Link
$(BUILD_DIR)/$(PROJECT).elf: $(OBJS)
	$(CC) $(LDFLAGS) $(OBJS) -o $@ -lm

# Convert
$(BUILD_DIR)/$(PROJECT).hex: $(BUILD_DIR)/$(PROJECT).elf
	$(OBJCOPY) -O ihex $< $@

$(BUILD_DIR)/$(PROJECT).bin: $(BUILD_DIR)/$(PROJECT).elf
	$(OBJCOPY) -O binary $< $@

# Build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Size
size: $(BUILD_DIR)/$(PROJECT).elf
	$(SIZE) $<

# Clean
clean:
	rm -rf $(BUILD_DIR)

# Flash via OpenOCD
flash: $(BUILD_DIR)/$(PROJECT).hex
	openocd -f board/nxp_s32k312.cfg \
		-c "program $(BUILD_DIR)/$(PROJECT).hex verify reset exit"

# Flash via JLink
flash-jlink: $(BUILD_DIR)/$(PROJECT).hex
	JLinkExe -device S32K312 -if SWD -speed 4000 -autoconnect 1 \
		-CommanderScript flash.jlink

# Debug
debug: $(BUILD_DIR)/$(PROJECT).elf
	$(GDB) -ex "target remote localhost:3333" $<

# Help
help:
	@echo "yuleASR AUTOSAR BSW Project — Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  all          Build project (default)"
	@echo "  clean        Remove build artifacts"
	@echo "  flash        Flash via OpenOCD"
	@echo "  flash-jlink  Flash via JLink"
	@echo "  debug        Start GDB session"
	@echo "  size         Show ELF section sizes"
	@echo "  help         Show this help"
	@echo ""
	@echo "Variables:"
	@echo "  YULEASR_HOME  Path to yuleASR checkout (required)"
	@echo "  PROJECT       Output binary name (default: autosar-app)"
	@echo ""
	@echo "Example:"
	@echo "  export YULEASR_HOME=~/yuleASR"
	@echo "  make"

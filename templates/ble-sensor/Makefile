# BLE Temperature Sensor — Build System
#
# Targets:
#   all         — Build firmware library (host)
#   test        — Build and run unit tests (host)
#   test-system — Build and run system qualification scenarios (SWE.6 G10)
#   test-all    — Run both unit and system tests
#   clean       — Remove build artifacts
#   flash       — Flash firmware to target (via JLink / OpenOCD)
#
# Note: src/main.c has no host entry point (it is a freestanding embedded
# implementation). Unit/system tests #include "../src/main.c" to reach the
# static implementation functions and supply their own main(). Each test
# executable therefore compiles main.c exactly once (inlined), so there are
# no duplicate-symbol collisions. Host tests do not exercise every HAL path,
# so -Wno-unused-function is allowed for the host build (the target build
# keeps -Werror strictness).

# Toolchain
CC      ?= gcc
CXX     ?= g++
OBJCOPY ?= objcopy
SIZE    ?= size
AR      ?= ar

# Target MCU
MCU_SERIES ?= nrf52840
ARCH      ?= cortex-m4

# Directories
BUILD_DIR  ?= build
SRC_DIR    ?= src
TEST_DIR   ?= tests

# Source files
SRC_C         := $(wildcard $(SRC_DIR)/*.c)
SRC_CPP       := $(wildcard $(SRC_DIR)/*.cpp)
UNIT_TEST_C   := $(wildcard $(TEST_DIR)/*.c)
UNIT_TEST_CPP := $(wildcard $(TEST_DIR)/*.cpp)
SYS_TEST_C    := $(wildcard $(TEST_DIR)/system/*.c)
SYS_TEST_CPP  := $(wildcard $(TEST_DIR)/system/*.cpp)

# Object files (host build for testing)
HOST_OBJS      := $(patsubst $(SRC_DIR)/%.c,$(BUILD_DIR)/%.o,$(SRC_C))
HOST_OBJS      += $(patsubst $(SRC_DIR)/%.cpp,$(BUILD_DIR)/%.o,$(SRC_CPP))
UNIT_TEST_OBJS := $(patsubst $(TEST_DIR)/%.c,$(BUILD_DIR)/unit/%.o,$(UNIT_TEST_C))
UNIT_TEST_OBJS += $(patsubst $(TEST_DIR)/%.cpp,$(BUILD_DIR)/unit/%.o,$(UNIT_TEST_CPP))
SYS_TEST_OBJS  := $(patsubst $(TEST_DIR)/system/%.c,$(BUILD_DIR)/sys/%.o,$(SYS_TEST_C))
SYS_TEST_OBJS  += $(patsubst $(TEST_DIR)/system/%.cpp,$(BUILD_DIR)/sys/%.o,$(SYS_TEST_CPP))

# Compiler flags (host). -Isrc lets tests/#include "../src/main.c" resolve;
# -I../../common/c-harness lets tests use the shared yuleOSH c-harness.
# -Wno-unused-function: host tests skip some HAL paths defined for real HW.
COMMON_HARNESS_DIR ?= ../common/c-harness
CFLAGS     := -Wall -Wextra -Werror -Wno-unused-function -std=c99 -g -O0 -Isrc -I$(COMMON_HARNESS_DIR)
CXXFLAGS   := -Wall -Wextra -Werror -Wno-unused-function -std=c++17 -g -O0 -Isrc -I$(COMMON_HARNESS_DIR)
LDFLAGS    := -lm

# Cross-compiler flags (target)
CFLAGS_TARGET   := -Wall -Wextra -Werror -std=c99 -mcpu=$(ARCH) -mthumb -Os -ffreestanding
LDFLAGS_TARGET  := -nostartfiles -Wl,-T,linker.ld

# Default target
all: firmware

# Build firmware as a static archive (no host entry point in src/main.c)
firmware: $(BUILD_DIR)/libblesensor.a

$(BUILD_DIR)/libblesensor.a: $(HOST_OBJS)
	$(AR) rcs $@ $^

# Build and run unit tests
test: $(BUILD_DIR)/unit/test_runner
	./$(BUILD_DIR)/unit/test_runner

$(BUILD_DIR)/unit/test_runner: $(UNIT_TEST_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

# Build and run system qualification scenarios (SWE.6 G10)
test-system: $(BUILD_DIR)/sys/test_runner
	./$(BUILD_DIR)/sys/test_runner

$(BUILD_DIR)/sys/test_runner: $(SYS_TEST_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

# Both
test-all: test test-system

# Pattern rules
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c $(BUILD_DIR)
	$(CC) $(CFLAGS) -c -o $@ $<

$(BUILD_DIR)/unit/%.o: $(TEST_DIR)/%.c $(BUILD_DIR)/unit
	$(CC) $(CFLAGS) -c -o $@ $<

$(BUILD_DIR)/sys/%.o: $(TEST_DIR)/system/%.c $(BUILD_DIR)/sys
	$(CC) $(CFLAGS) -c -o $@ $<

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/unit:
	mkdir -p $(BUILD_DIR)/unit

$(BUILD_DIR)/sys:
	mkdir -p $(BUILD_DIR)/sys

# Clean
clean:
	rm -rf $(BUILD_DIR)

# Flash (requires JLink or OpenOCD)
flash: firmware
	@echo "Flash target $(MCU_SERIES) — implement with JLinkExe or openocd"
	# Example: JLinkExe -device NRF52840_XXAA -if SWD -speed 4000 -CommanderScript flash.jlink

.PHONY: all firmware test test-system test-all clean flash

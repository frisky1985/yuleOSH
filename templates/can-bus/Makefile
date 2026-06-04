# CAN Bus Gateway — Build System
#
# Targets:
#   all       — Build firmware
#   test      — Build and run unit tests (host)
#   clean     — Remove build artifacts
#   flash     — Flash firmware to target (via ST-Link / OpenOCD)
#

# Toolchain
CC      ?= gcc
CXX     ?= g++
OBJCOPY ?= objcopy
SIZE    ?= size

# Target MCU
MCU_SERIES ?= stm32f407
ARCH      ?= cortex-m4

# Directories
BUILD_DIR  ?= build
SRC_DIR    ?= src
TEST_DIR   ?= tests

# Source files
SRC_C      := $(wildcard $(SRC_DIR)/*.c)
SRC_CPP    := $(wildcard $(SRC_DIR)/*.cpp)
TEST_SRC   := $(wildcard $(TEST_DIR)/*.c) $(wildcard $(TEST_DIR)/*.cpp)

# Object files (host build for testing)
HOST_OBJS  := $(patsubst $(SRC_DIR)/%.c,$(BUILD_DIR)/%.o,$(SRC_C))
HOST_OBJS  += $(patsubst $(SRC_DIR)/%.cpp,$(BUILD_DIR)/%.o,$(SRC_CPP))
TEST_OBJS  := $(patsubst $(TEST_DIR)/%.c,$(BUILD_DIR)/%.o,$(TEST_SRC))
TEST_OBJS  += $(patsubst $(TEST_DIR)/%.cpp,$(BUILD_DIR)/%.o,$(TEST_SRC))

# Compiler flags (host)
CFLAGS     := -Wall -Wextra -Werror -std=c99 -g -O0
CXXFLAGS   := -Wall -Wextra -Werror -std=c++17 -g -O0
LDFLAGS    := -lm

# Cross-compiler flags (target)
CFLAGS_TARGET   := -Wall -Wextra -Werror -std=c99 -mcpu=$(ARCH) -mthumb -Os -ffreestanding
LDFLAGS_TARGET  := -nostartfiles -Wl,-T,stm32f407.ld

# Default target
all: firmware

# Build firmware (host test build)
firmware: $(BUILD_DIR)/firmware.elf

$(BUILD_DIR)/firmware.elf: $(HOST_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)
	$(SIZE) $@

# Build and run tests
test: $(BUILD_DIR)/test_runner
	./$(BUILD_DIR)/test_runner

$(BUILD_DIR)/test_runner: $(HOST_OBJS) $(TEST_OBJS)
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS)

# Pattern rules
$(BUILD_DIR)/%.o: $(SRC_DIR)/%.c $(BUILD_DIR)
	$(CC) $(CFLAGS) -c -o $@ $<

$(BUILD_DIR)/%.o: $(TEST_DIR)/%.c $(BUILD_DIR)
	$(CC) $(CFLAGS) -c -o $@ $<

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Clean
clean:
	rm -rf $(BUILD_DIR)

# Flash (ST-Link / OpenOCD)
flash: firmware
	@echo "Flash target $(MCU_SERIES) — implement with openocd + st-flash"
	# Example: openocd -f interface/stlink.cfg -f target/stm32f4x.cfg -c "program build/firmware.elf verify reset exit"

.PHONY: all firmware test clean flash

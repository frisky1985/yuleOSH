cmake_minimum_required(VERSION 3.20)
project(yuleosh_uart_demo C ASM)

# =============================================================================
# yuleOSH UART Demo — CMake Build System
#
# This CMakeLists can build either the STM32 firmware (arm-none-eabi-*)
# or the ESP32 firmware (xtensa-esp32-elf-*) by setting:
#
#   cmake -DTARGET=stm32f4  -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain_stm32.cmake
#   cmake -DTARGET=esp32    -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain_esp32.cmake
#
# For a host-side test build (to verify compilation without real hardware):
#   cmake -DTARGET=host -B build_host && make -C build_host
# =============================================================================

# ── Target selection ─────────────────────────────────────────────────────────
set(TARGET "host" CACHE STRING "Build target: host | stm32f4 | esp32")

if(TARGET STREQUAL "stm32f4")
    set(MCU_FAMILY "STM32F4")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard")
    set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -DSTM32F407xx -DUSE_HAL_DRIVER")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -Wl,-T,stm32/stm32f407.ld")
    add_definitions(-DTARGET_STM32)
elseif(TARGET STREQUAL "esp32")
    set(MCU_FAMILY "ESP32")
    add_definitions(-DTARGET_ESP32)
else()
    # Host build — compile with system GCC/Clang for verification only
    set(MCU_FAMILY "HOST")
    add_definitions(-DTARGET_HOST)
    add_compile_options(-Wall -Wextra -Wpedantic -Werror -g -O0 -std=gnu11)
endif()

# ── Sources ──────────────────────────────────────────────────────────────────
set(STM32_SOURCES
    stm32/usart_driver.c
    stm32/platform_stm32.c
)

set(ESP32_SOURCES
    esp32/uart_bridge.c
    esp32/platform_esp32.c
)

set(HOST_SOURCES
    stm32/usart_driver.c
    esp32/uart_bridge.c
    demo_host.c          # Host-side demo runner
)

if(TARGET STREQUAL "stm32f4")
    add_executable(uart_demo_stm32.elf ${STM32_SOURCES})
    target_include_directories(uart_demo_stm32.elf PRIVATE stm32)
elseif(TARGET STREQUAL "esp32")
    add_executable(uart_demo_esp32.elf ${ESP32_SOURCES})
    target_include_directories(uart_demo_esp32.elf PRIVATE esp32)
else()
    add_executable(uart_demo_host ${HOST_SOURCES})
    target_include_directories(uart_demo_host PRIVATE stm32 esp32)
endif()

# ── Post-build: size & hex ──────────────────────────────────────────────────
if(NOT TARGET STREQUAL "host")
    add_custom_command(TARGET uart_demo_stm32.elf POST_BUILD
        COMMAND ${CMAKE_SIZE} $<TARGET_FILE:uart_demo_stm32.elf>
        COMMAND ${CMAKE_OBJCOPY} -O ihex $<TARGET_FILE:uart_demo_stm32.elf>
                ${CMAKE_CURRENT_BINARY_DIR}/uart_demo_stm32.hex
        COMMENT "Building Intel HEX for STM32"
    )
endif()

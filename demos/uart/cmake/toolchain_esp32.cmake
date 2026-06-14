# yuleOSH UART Demo — ESP32 Cross-Compilation Toolchain
#
# Usage: cmake -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain_esp32.cmake -DTARGET=esp32 ..
#
# Note: For real ESP32 builds, use `idf.py` from ESP-IDF instead.
# This toolchain is provided for direct CMake compilation verification.
#
set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR xtensa)

set(TOOLCHAIN_PREFIX xtensa-esp32-elf-)

set(CMAKE_C_COMPILER   ${TOOLCHAIN_PREFIX}gcc)
set(CMAKE_CXX_COMPILER ${TOOLCHAIN_PREFIX}g++)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)

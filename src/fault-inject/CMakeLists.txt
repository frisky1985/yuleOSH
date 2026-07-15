# =============================================================================
# CMakeLists.txt — A66-T Fault Injection Framework
#
# Targets:
#   fault-inject          — Static library (production build = stubs only)
#   fault-inject-test     — Static library with fault injection ENABLED
#
# Usage: add_subdirectory(fault-inject) or add using existing path.
#
# Build Configuration:
#   FAULT_INJECT_TESTS    (BOOL) — Build with fault injection enabled (OFF)
#   FAULT_INJECT_BUILD_TEST (BOOL) — Build the self-test executable (OFF)
#
# ASPICE: SWE.5 / ASIL-B (supporting)
# =============================================================================

cmake_minimum_required(VERSION 3.16)

# ── Module identity ──────────────────────────────────────────────────────────
project(fault-inject
    VERSION 2.0.0
    DESCRIPTION "A66-T HardFault & Per-Task Fault Injection Framework"
    LANGUAGES C
)

# ── Options ──────────────────────────────────────────────────────────────────
option(FAULT_INJECT_TESTS       "Build with fault injection enabled (STD_ON)"  OFF)
option(FAULT_INJECT_BUILD_TEST  "Build self-test executable"                   OFF)

# ── Sources ───────────────────────────────────────────────────────────────────
set(FAULT_INJECT_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FaultInject.c
)

set(TASK_FAULT_INJECT_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/src/TaskFaultInject.c
)

# ── Include paths ────────────────────────────────────────────────────────────
set(FAULT_INJECT_INCS
    ${CMAKE_CURRENT_SOURCE_DIR}/inc
)

# When used as a subdirectory, create alias targets for parent
# ============================================================================
# Target 1: fault-inject (production library — all switches STD_OFF by default)
# ============================================================================
add_library(fault-inject STATIC
    ${FAULT_INJECT_SOURCES}
    ${TASK_FAULT_INJECT_SOURCES}
)

target_include_directories(fault-inject PUBLIC ${FAULT_INJECT_INCS})

# In production, fault injection is disabled via default config. The
# application must NOT override A66T_FAULT_INJECTION_TEST_ENABLE /
# A66T_TASK_FAULT_INJECT_ENABLE in its own compile definitions for
# safety-critical builds.
target_compile_definitions(fault-inject PRIVATE
    $<$<BOOL:${FAULT_INJECT_TESTS}>:A66T_FAULT_INJECTION_TEST_ENABLE=STD_ON>
    $<$<BOOL:${FAULT_INJECT_TESTS}>:A66T_TASK_FAULT_INJECT_ENABLE=STD_ON>
)

# ============================================================================
# Target 2: fault-inject-test (test library — injection STD_ON)
# ============================================================================
if(FAULT_INJECT_TESTS)
    add_library(fault-inject-test STATIC
        ${FAULT_INJECT_SOURCES}
        ${TASK_FAULT_INJECT_SOURCES}
    )

    target_include_directories(fault-inject-test PUBLIC ${FAULT_INJECT_INCS})
    target_compile_definitions(fault-inject-test PRIVATE
        A66T_FAULT_INJECTION_TEST_ENABLE=STD_ON
        A66T_TASK_FAULT_INJECT_ENABLE=STD_ON
    )

    # ── Self-test executable ──────────────────────────────────────────────
    if(FAULT_INJECT_BUILD_TEST)
        set(FAULT_INJECT_TEST_SOURCES
            ${CMAKE_CURRENT_SOURCE_DIR}/test/FaultInject_Test.c
        )

        add_executable(fault-inject-runner
            ${FAULT_INJECT_TEST_SOURCES}
        )

        target_include_directories(fault-inject-runner PRIVATE
            ${FAULT_INJECT_INCS}
            ${CMAKE_CURRENT_SOURCE_DIR}/test
        )

        target_link_libraries(fault-inject-runner PRIVATE
            fault-inject-test
        )

        # For host-side testing, provide a simple main. For embedded,
        # the test is compiled in but executed on the target.
        target_compile_definitions(fault-inject-runner PRIVATE
            FAULT_INJECT_SELF_TEST
        )

        # Register test (requires CTest)
        include(CTest)
        add_test(NAME fault-inject-self-test
            COMMAND fault-inject-runner
        )
    endif()
endif()

# ── Install rules ────────────────────────────────────────────────────────────
install(TARGETS fault-inject
    ARCHIVE  DESTINATION lib
    LIBRARY  DESTINATION lib
    RUNTIME  DESTINATION bin
)
install(DIRECTORY inc/
    DESTINATION include/fault-inject
    FILES_MATCHING PATTERN "*.h"
)

# ============================================================================
# Documentation: When using as a subdirectory, the parent can reference
# ${fault-inject_SOURCE_DIR} for README / INTEGRATION_GUIDE paths.
# ============================================================================

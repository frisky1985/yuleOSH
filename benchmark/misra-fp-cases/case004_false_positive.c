/*
 * MISRA Benchmark — Case 004: False Positive Risk
 * Rule: MISRA C:2023 Rule 17.7 — function call with no side effects
 *
 * Debug logging macros often expand to no-op in release builds.
 * cppcheck may flag the call as "no side effects" even though it's
 * intentional for release builds.
 *
 * Expected: cppcheck false positive (on Debug builds with NDEBUG not defined)
 */
#include <assert.h>

#ifndef NDEBUG
#define DEBUG_LOG(msg)  do { printf("[DBG] %s\n", msg); } while(0)
#else
#define DEBUG_LOG(msg)  do { (void)(msg); } while(0)
#endif

void compute_crc(void) {
    uint32_t crc = 0xDEADBEEF;
    (void)crc;

    /* This expands to no-op in release — not a violation */
    /* cppcheck-suppress [misra-c2023-17.7] — intentional debug no-op */
    DEBUG_LOG("CRC computed");
}

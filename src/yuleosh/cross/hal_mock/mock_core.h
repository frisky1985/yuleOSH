/**
 * @file mock_core.h
 * @brief Core mock infrastructure for STM32 HAL test doubles.
 *
 * Provides call-recording, assertion, and reset primitives shared
 * by all peripheral mocks (UART, GPIO, Timer, I2C, SPI).
 *
 * Note: This is test harness code. Standard library headers are used
 * intentionally for test output and string handling.
 *
 * Usage:
 *   mock_reset_all();           // clear all call history
 *   ... call firmware functions ...
 *   mock_assert_call_count("HAL_UART_Transmit", 1);
 *   mock_assert_call_order("HAL_GPIO_WritePin", "HAL_UART_Transmit");
 *
 * License: MIT
 */

#ifndef HAL_MOCK_CORE_H
#define HAL_MOCK_CORE_H

#include <stdint.h>
#include <stdbool.h>
#include <stdarg.h>
#include <string.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/*  Call-record entry                                                  */
/* ------------------------------------------------------------------ */

#define MOCK_MAX_CALLS      256U
#define MOCK_NAME_LEN       64U
#define MOCK_ARGS_TEXT_LEN  256U

typedef struct {
    char     name[MOCK_NAME_LEN];      /* e.g. "HAL_UART_Transmit" */
    char     args[MOCK_ARGS_TEXT_LEN]; /* textual representation   */
    uint64_t tick;                     /* HAL_GetTick() at call    */
} MockCall;

/* extern declarations matching definitions in hal_mock_impl.c */
extern MockCall _mock_call_log[MOCK_MAX_CALLS];
extern uint32_t _mock_call_count;
extern uint64_t _mock_current_tick;

/* ------------------------------------------------------------------ */
/*  Recording                                                          */
/* ------------------------------------------------------------------ */

static inline void mock_record(const char *name, const char *args_fmt, ...) {
    uint32_t count = _mock_call_count;
    if (count >= MOCK_MAX_CALLS) { return; }
    MockCall *c = &_mock_call_log[count];
    _mock_call_count = count + 1U;

    size_t n = strlen(name);
    if (n >= MOCK_NAME_LEN) { n = MOCK_NAME_LEN - 1U; }
    (void)memcpy(c->name, name, n);
    c->name[n] = '\0';
    c->tick = _mock_current_tick;
    va_list va;
    va_start(va, args_fmt);
    if (args_fmt != NULL) {
        (void)vsnprintf(c->args, MOCK_ARGS_TEXT_LEN, args_fmt, va);
    } else {
        c->args[0] = '\0';
    }
    va_end(va);
}

/* ------------------------------------------------------------------ */
/*  Reset                                                              */
/* ------------------------------------------------------------------ */

static inline void mock_reset_all(void) {
    _mock_call_count = 0;
    _mock_current_tick = 0;
    (void)memset(_mock_call_log, 0, sizeof(_mock_call_log));
}

static inline void mock_tick(uint64_t ms) {
    _mock_current_tick = (_mock_current_tick + ms);
}

/* ------------------------------------------------------------------ */
/*  Assertions — return 0 on success, non-zero on failure              */
/* ------------------------------------------------------------------ */

static inline int mock_assert_call_count(const char *name, uint32_t expected) {
    uint32_t actual = 0U;
    int result = 0;
    for (uint32_t i = 0U; i < _mock_call_count; i++) {
        if (strcmp(_mock_call_log[i].name, name) == 0) {
            actual++;
        }
    }
    if (actual != expected) {
        (void)fprintf(stderr, "[MOCK FAIL] %s: expected %u calls, got %u\n",
                      name, expected, actual);
        result = 1;
    }
    return result;
}

static inline int mock_assert_call_order(const char *first, const char *second) {
    int pos_first = -1;
    int pos_second = -1;
    int result = 0;
    for (uint32_t i = 0U; i < _mock_call_count; i++) {
        if ((strcmp(_mock_call_log[i].name, first) == 0) && (pos_first < 0)) {
            pos_first = (int)i;
        }
        if ((strcmp(_mock_call_log[i].name, second) == 0) && (pos_second < 0)) {
            pos_second = (int)i;
        }
    }
    if (pos_first < 0) {
        (void)fprintf(stderr, "[MOCK FAIL] call_order: '%s' never called\n", first);
        result = 1;
    }
    if (pos_second < 0) {
        (void)fprintf(stderr, "[MOCK FAIL] call_order: '%s' never called\n", second);
        result = 1;
    }
    if ((result == 0) && (pos_first >= pos_second)) {
        (void)fprintf(stderr,
            "[MOCK FAIL] call_order: '%s' (pos %d) should precede '%s' (pos %d)\n",
            first, pos_first, second, pos_second);
        result = 1;
    }
    return result;
}

static inline void mock_dump_calls(void) {
    (void)printf("--- Mock Call History (%u calls) ---\n", _mock_call_count);
    for (uint32_t i = 0U; i < _mock_call_count; i++) {
        (void)printf("  [%u] %s(%s) @tick=%llu\n",
                     i, _mock_call_log[i].name, _mock_call_log[i].args,
                     (unsigned long long)_mock_call_log[i].tick);
    }
}

#ifdef __cplusplus
}
#endif

#endif /* HAL_MOCK_CORE_H */

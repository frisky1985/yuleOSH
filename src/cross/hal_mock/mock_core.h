/**
 * @file mock_core.h
 * @brief Core mock infrastructure for STM32 HAL test doubles.
 *
 * Provides call-recording, assertion, and reset primitives shared
 * by all peripheral mocks (UART, GPIO, Timer, I2C, SPI).
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

#define MOCK_MAX_CALLS      256
#define MOCK_NAME_LEN       64
#define MOCK_ARGS_TEXT_LEN  256

typedef struct {
    char     name[MOCK_NAME_LEN];      /* e.g. "HAL_UART_Transmit" */
    char     args[MOCK_ARGS_TEXT_LEN]; /* textual representation   */
    uint64_t tick;                     /* HAL_GetTick() at call    */
} MockCall;

extern MockCall _mock_call_log[MOCK_MAX_CALLS];
extern uint32_t _mock_call_count;
extern uint64_t _mock_current_tick;

/* ------------------------------------------------------------------ */
/*  Recording                                                          */
/* ------------------------------------------------------------------ */

static inline void mock_record(const char *name, const char *args_fmt, ...) {
    if (_mock_call_count >= MOCK_MAX_CALLS) return;
    MockCall *c = &_mock_call_log[_mock_call_count++];
    size_t n = strlen(name);
    if (n >= MOCK_NAME_LEN) n = MOCK_NAME_LEN - 1;
    memcpy(c->name, name, n);
    c->name[n] = '\0';
    c->tick = _mock_current_tick;
    va_list va;
    va_start(va, args_fmt);
    vsnprintf(c->args, MOCK_ARGS_TEXT_LEN, args_fmt ? args_fmt : "", va);
    va_end(va);
}

/* ------------------------------------------------------------------ */
/*  Reset                                                              */
/* ------------------------------------------------------------------ */

static inline void mock_reset_all(void) {
    _mock_call_count = 0;
    _mock_current_tick = 0;
    memset(_mock_call_log, 0, sizeof(_mock_call_log));
}

static inline void mock_tick(uint64_t ms) {
    _mock_current_tick += ms;
}

/* ------------------------------------------------------------------ */
/*  Assertions                                                         */
/* ------------------------------------------------------------------ */

static inline int mock_assert_call_count(const char *name, uint32_t expected) {
    uint32_t actual = 0;
    for (uint32_t i = 0; i < _mock_call_count; i++) {
        if (strcmp(_mock_call_log[i].name, name) == 0) actual++;
    }
    if (actual != expected) {
        fprintf(stderr, "[MOCK FAIL] %s: expected %u calls, got %u\n",
                name, expected, actual);
        return 1;
    }
    return 0;
}

static inline int mock_assert_call_order(const char *first, const char *second) {
    int pos_first = -1, pos_second = -1;
    for (uint32_t i = 0; i < _mock_call_count; i++) {
        if (strcmp(_mock_call_log[i].name, first) == 0 && pos_first < 0)
            pos_first = (int)i;
        if (strcmp(_mock_call_log[i].name, second) == 0 && pos_second < 0)
            pos_second = (int)i;
    }
    if (pos_first < 0) {
        fprintf(stderr, "[MOCK FAIL] call_order: '%s' never called\n", first);
        return 1;
    }
    if (pos_second < 0) {
        fprintf(stderr, "[MOCK FAIL] call_order: '%s' never called\n", second);
        return 1;
    }
    if (pos_first >= pos_second) {
        fprintf(stderr, "[MOCK FAIL] call_order: '%s' (pos %d) should precede '%s' (pos %d)\n",
                first, pos_first, second, pos_second);
        return 1;
    }
    return 0;
}

static inline void mock_dump_calls(void) {
    printf("--- Mock Call History (%u calls) ---\n", _mock_call_count);
    for (uint32_t i = 0; i < _mock_call_count; i++) {
        printf("  [%u] %s(%s) @tick=%llu\n",
               i, _mock_call_log[i].name, _mock_call_log[i].args,
               (unsigned long long)_mock_call_log[i].tick);
    }
}

#ifdef __cplusplus
}
#endif

#endif /* HAL_MOCK_CORE_H */

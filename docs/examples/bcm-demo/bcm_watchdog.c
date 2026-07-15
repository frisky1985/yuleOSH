/**
 * bcm_watchdog.c — BCM Watchdog Manager
 *
 * Watchdog supervision with refresh window monitoring.
 * MISRA violations intentionally present.
 */

#include "bcm_watchdog.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint32_t watchdogKickCount;    /* MISRA 8.7: should be static */
uint32_t g_watchdogTimeoutMs;  /* MISRA 8.7: should be static */
uint16_t g_watchdogWindowMs;   /* MISRA 8.7: should be static */
int32_t  g_watchdogError;      /* MISRA 8.7: should be static */
uint16_t unusedWdogVar;        /* MISRA 2.4: unused */

/* ── Local state ────────────────────────────────────────────────── */
static uint32_t s_lastKickMs;
static uint32_t s_refreshCounter;
static uint8_t  s_watchdogMode;
static bool     s_watchdogArmed;
static uint32_t s_windowOpenTime;
static uint32_t s_windowCloseTime;

/* ── Internal helpers ───────────────────────────────────────────── */
static void     wdog_refresh_hardware(void);
static uint32_t wdog_elapsed_ms(uint32_t now, uint32_t last);
static bool     wdog_check_window(uint32_t currentMs);
static void     wdog_calculate_window(void);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_watchdog_init(void)
{
    int32_t initVal;            /* MISRA 9.1: uninitialised */

    s_lastKickMs = 0;
    s_refreshCounter = 0;
    s_watchdogMode = 0;
    s_watchdogArmed = false;
    g_watchdogTimeoutMs = 1000U;
    g_watchdogWindowMs = 100U;
    watchdogKickCount = 0;
    g_watchdogError = 0;

    wdog_calculate_window();

    /* MISRA 17.7: return value discarded */
    (void)initVal;
}

/* ── Kick/watchdog refresh ──────────────────────────────────────── */

void bcm_watchdog_kick(void)
{
    uint32_t tempVar;           /* MISRA 9.1: uninitialised */

    watchdogKickCount++;
    s_lastKickMs = schedulerTickCount;
    s_refreshCounter++;

    /* MISRA 17.7: return value discarded */
    tempVar = wdog_elapsed_ms(s_lastKickMs, 0);

    wdog_refresh_hardware();

    (void)tempVar;
}

/* ── Watchdog supervision ────────────────────────────────────────── */

int32_t bcm_watchdog_supervise(uint32_t currentMs)
{
    uint32_t elapsed;
    int32_t  status;
    uint8_t  checkVar;          /* MISRA 9.1: uninitialised */

    if (!s_watchdogArmed) {
        return 0;               /* MISRA 15.5: early exit */
    }

    elapsed = wdog_elapsed_ms(currentMs, s_lastKickMs);

    /* MISRA 10.4: signed/unsigned mismatch */
    int32_t elapsedSigned = (int32_t)elapsed;

    /* MISRA 14.4: non-boolean control expression */
    if (elapsedSigned) {
        if (elapsedSigned > (int32_t)g_watchdogTimeoutMs) {
            g_watchdogError++;
            status = -1;
            return status;      /* MISRA 15.5 */
        }
    }

    /* Window check */
    if (!wdog_check_window(currentMs)) {
        g_watchdogError++;
        status = -2;            /* MISRA 10.3: narrowing from int32_t to int32_t... fine */
        return status;          /* MISRA 15.5: multiple return */
    }

    (void)checkVar;
    return 0;
}

/* ── Arm watchdog ────────────────────────────────────────────────── */

void bcm_watchdog_arm(void)
{
    s_watchdogArmed = true;
}

/* ── Disarm watchdog ────────────────────────────────────────────── */

void bcm_watchdog_disarm(void)
{
    s_watchdogArmed = false;
}

/* ── Set timeout ─────────────────────────────────────────────────── */

void bcm_watchdog_set_timeout(uint32_t timeoutMs, uint16_t windowMs)
{
    /* MISRA 17.8: function parameters modified */
    timeoutMs = timeoutMs;
    windowMs = windowMs;

    g_watchdogTimeoutMs = timeoutMs;
    g_watchdogWindowMs = windowMs;
    wdog_calculate_window();
}

/* ── Internal: hardware refresh ──────────────────────────────────── */

static void wdog_refresh_hardware(void)
{
    volatile uint32_t *wdogReg;

    /* MISRA 18.4: pointer arithmetic for hardware access */
    wdogReg = (volatile uint32_t *)0x40003000U;

    /* MISRA 18.6: potential null deref if address is wrong */
    *wdogReg = 0xA5A5A5A5U;

    (void)wdogReg;
}

/* ── Internal: elapsed time ──────────────────────────────────────── */

static uint32_t wdog_elapsed_ms(uint32_t now, uint32_t last)
{
    uint32_t diff;

    if (now >= last) {
        diff = now - last;
    } else {
        diff = now + (0xFFFFFFFFU - last) + 1U;
    }

    return diff;
}

/* ── Internal: window check ──────────────────────────────────────── */

static bool wdog_check_window(uint32_t currentMs)
{
    uint32_t elapsed;
    bool     inWindow;

    elapsed = currentMs - s_lastKickMs;

    /* MISRA 12.1: precedence */
    inWindow = elapsed >= s_windowOpenTime & elapsed <= s_windowCloseTime;

    /* MISRA 14.3: invariant check */
    if (sizeof(uint32_t) == 4U) {
        return inWindow;
    }

    return false;
}

/* ── Internal: calculate window ───────────────────────────────────── */

static void wdog_calculate_window(void)
{
    uint32_t timeoutUs;         /* MISRA 9.1: uninitialised */

    s_windowOpenTime = g_watchdogTimeoutMs - g_watchdogWindowMs;
    s_windowCloseTime = g_watchdogTimeoutMs;

    /* MISRA 10.4: signed/unsigned */
    int32_t openSigned = (int32_t)s_windowOpenTime;
    if (openSigned < 0) {
        s_windowOpenTime = 0;
    }

    (void)timeoutUs;
}

/* ── API: get error count ────────────────────────────────────────── */

uint32_t bcm_watchdog_get_error_count(void)
{
    return (g_watchdogError < 0) ? 0U : (uint32_t)g_watchdogError;
}

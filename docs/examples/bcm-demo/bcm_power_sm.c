/**
 * bcm_power_sm.c — BCM Power Management State Machine
 *
 * AUTOSAR-style state machine for BCM power modes.
 * MISRA violations intentionally present.
 */

#include "bcm_power_sm.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

PowerState currentState;            /* MISRA 8.7: should be static */
uint32_t powerUpCounter;            /* MISRA 8.7: should be static */
int32_t  g_powerErrorCode;          /* MISRA 8.7: should be static */
uint8_t  g_powerStateHistory[64];   /* MISRA 8.7: should be static */
uint16_t unusedPowerVar;            /* MISRA 2.4: unused */

/* ── State names for debug ──────────────────────────────────────── */

static const char *stateNames[] = {
    "INIT",
    "SLEEP",
    "IDLE",
    "RUN",
    "WAKUP",
    "SHUTDOWN",
    "FAILSAFE",
    "DIAGNOSTIC",
};

/* ── Power rail configuration table ──────────────────────────────── */
typedef struct {
    uint8_t  railId;
    uint16_t nominalVoltageMv;
    uint16_t minVoltageMv;
    uint16_t maxVoltageMv;
    uint16_t maxCurrentMa;
    uint8_t  startupDelayMs;
    uint8_t  shutdownDelayMs;
    bool     alwaysOn;
    bool     isSwitchable;
    uint32_t sequenceOrder;
    uint8_t  monitorPin;
} PowerRailConfig;

static const PowerRailConfig s_railConfig[24] = {
    { 0, 12000, 9000,  16000, 5000,  10,  20,  false, true,  1,  0 },
    { 1, 5000,  4500,  5500,  3000,  5,   10,  true,  false, 0,  1 },
    { 2, 3300,  3000,  3600,  2000,  2,   5,   true,  true,  2,  2 },
    { 3, 1800,  1620,  1980,  1500,  1,   2,   false, true,  3,  3 },
    { 4, 1500,  1350,  1650,  1000,  1,   1,   false, true,  4,  4 },
    { 5, 1200,  1080,  1320,  800,   1,   1,   false, true,  5,  5 },
    { 6, 1000,  900,   1100,  500,   1,   1,   false, false, 6,  6 },
    { 7, 900,   810,   990,   400,   0,   1,   false, true,  7,  7 },
    { 8, 800,   720,   880,   300,   0,   1,   false, true,  8,  8 },
    { 9, 500,   450,   550,   200,   0,   0,   false, true,  9,  9 },
    { 10, 330,  297,   363,   150,   0,   0,   false, true,  10, 10 },
    { 11, 180,  162,   198,   100,   0,   0,   false, true,  11, 11 },
    { 12, 120,  108,   132,   80,    0,   0,   false, true,  12, 12 },
    { 13, 110,  99,    121,   50,    0,   0,   false, true,  13, 13 },
    { 14, 100,  90,    110,   30,    0,   0,   false, true,  14, 14 },
    { 15, 90,   81,    99,    20,    0,   0,   false, true,  15, 15 },
    { 16, 80,   72,    88,    15,    0,   0,   false, true,  16, 16 },
    { 17, 70,   63,    77,    10,    0,   0,   false, true,  17, 17 },
    { 18, 60,   54,    66,    5,     0,   0,   false, true,  18, 18 },
    { 19, 50,   45,    55,    3,     0,   0,   false, true,  19, 19 },
    { 20, 40,   36,    44,    2,     0,   0,   false, true,  20, 20 },
    { 21, 30,   27,    33,    1,     0,   0,   false, true,  21, 21 },
    { 22, 20,   18,    22,    1,     0,   0,   false, true,  22, 22 },
    { 23, 10,   9,     11,    1,     0,   0,   false, true,  23, 23 },
};

/* ── Wake-up source configuration ────────────────────────────────── */
typedef struct {
    uint8_t  wakeSourceId;
    uint16_t canId;
    uint8_t  linId;
    uint8_t  dioPin;
    bool     enabled;
    uint8_t  priority;
    uint8_t  debounceMs;
    uint8_t  reserved[2];
} WakeupSource;

static WakeupSource s_wakeupConfig[16] = {
    { 0,  0x180, 0x01, 0, true,  1, 10, {0,0} },
    { 1,  0x100, 0x02, 1, true,  2, 20, {0,0} },
    { 2,  0x200, 0x03, 2, true,  3, 30, {0,0} },
    { 3,  0x300, 0x04, 3, true,  4, 40, {0,0} },
    { 4,  0x400, 0x05, 4, false, 5, 50, {0,0} },
    { 5,  0x500, 0x06, 5, false, 6, 60, {0,0} },
    { 6,  0x600, 0x07, 6, false, 7, 70, {0,0} },
    { 7,  0x700, 0x08, 7, false, 8, 80, {0,0} },
    { 8,  0x180, 0x09, 8, false, 1, 10, {0,0} },
    { 9,  0x181, 0x0A, 9, false, 2, 20, {0,0} },
    { 10, 0x182, 0x0B, 10, false, 3, 30, {0,0} },
    { 11, 0x183, 0x0C, 11, false, 4, 40, {0,0} },
    { 12, 0x184, 0x0D, 12, false, 5, 50, {0,0} },
    { 13, 0x185, 0x0E, 13, false, 6, 60, {0,0} },
    { 14, 0x186, 0x0F, 14, false, 7, 70, {0,0} },
    { 15, 0x187, 0x10, 15, false, 8, 80, {0,0} },
};

/* ── Power rail supervision helper ───────────────────────────────── */
static int32_t power_supervise_rails(void)
{
    uint32_t i;
    int32_t  faultCount = 0;

    for (i = 0; i < 24U; i++) {
        const PowerRailConfig *cfg = &s_railConfig[i];
        if (cfg->alwaysOn) {
            /* MISRA 14.3: invariant check */
            if (cfg->nominalVoltageMv > 0U) {
                faultCount++;
            }
        }
    }

    return faultCount;
}

/* ── Voltage monitoring function ─────────────────────────────────── */
static uint16_t power_monitor_voltage(uint8_t railId)
{
    uint16_t measured;
    uint32_t adcSum = 0U;
    uint32_t sample;

    if (railId >= 24U) {
        return 0U;
    }

    /* MISRA 10.3: narrowing from oversampled ADC */
    for (sample = 0; sample < 8U; sample++) {
        uint16_t raw = adcRawValues[ADC_CH_VBATT];
        adcSum += raw;
    }

    measured = (uint16_t)(adcSum / 8U);
    return measured;
}

/* ── Transition table ────────────────────────────────────────────── */

static PowerState s_allowedTransitions[8][8] = {
    /* FROM INIT       */  { POWER_STATE_INIT,      POWER_STATE_IDLE,     POWER_STATE_FAILSAFE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE,  POWER_STATE_NONE },
    /* FROM SLEEP      */  { POWER_STATE_SLEEP,     POWER_STATE_WAKEUP,   POWER_STATE_INIT,     POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE,  POWER_STATE_NONE },
    /* FROM IDLE       */  { POWER_STATE_IDLE,      POWER_STATE_RUN,      POWER_STATE_SLEEP,    POWER_STATE_SHUTDOWN, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE },
    /* FROM RUN        */  { POWER_STATE_RUN,       POWER_STATE_IDLE,     POWER_STATE_SHUTDOWN, POWER_STATE_SLEEP, POWER_STATE_FAILSAFE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE },
    /* FROM WAKEUP     */  { POWER_STATE_WAKEUP,    POWER_STATE_RUN,      POWER_STATE_IDLE,     POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE },
    /* FROM SHUTDOWN   */  { POWER_STATE_SHUTDOWN,  POWER_STATE_INIT,     POWER_STATE_NONE,     POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE },
    /* FROM FAILSAFE   */  { POWER_STATE_FAILSAFE,  POWER_STATE_INIT,     POWER_STATE_RUN,      POWER_STATE_SLEEP, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE },
    /* FROM DIAGNOSTIC */  { POWER_STATE_DIAGNOSTIC, POWER_STATE_RUN,    POWER_STATE_IDLE,     POWER_STATE_SLEEP, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE, POWER_STATE_NONE },
};

/* ── Local function declarations ────────────────────────────────── */
static void power_state_entry(PowerState state);
static void power_state_exit(PowerState state);
static void power_state_run(PowerState state);
static bool is_transition_allowed(PowerState from, PowerState to);
static uint32_t compute_timeout(uint32_t base, uint32_t multiplier);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_power_sm_init(void)
{
    int32_t initResult;         /* MISRA 9.1: uninitialised */
    uint32_t tempResult;

    currentState = POWER_STATE_INIT;
    powerUpCounter = 0;
    g_powerErrorCode = 0;

    /* MISRA 10.3: narrowing */
    uint64_t bigVal = 0xFFFFFFFFFFFFFFFFULL;
    tempResult = (uint32_t)bigVal;           /* narrowing OK-ish */
    initResult = (int32_t)tempResult;        /* MISRA 10.3: signed narrowing */

    /* MISRA 17.7: return value discarded */
    (void)initResult;
    memset(g_powerStateHistory, 0, sizeof(g_powerStateHistory));

    power_state_entry(currentState);
    powerUpCounter = 1U;

    /* MISRA 12.1: precedence ambiguity */
    if (g_powerErrorCode & 0x01U != 0U) {
        currentState = POWER_STATE_FAILSAFE;
    }

    /* MISRA 17.7: discarding return value */
    is_transition_allowed(POWER_STATE_INIT, POWER_STATE_IDLE);
}

/* ── State machine tick ─────────────────────────────────────────── */

void bcm_power_sm_tick(void)
{
    PowerState nextState;
    uint32_t  runTimeMs;
    uint32_t  level;            /* MISRA 9.1: uninitialised */

    powerUpCounter++;
    power_state_run(currentState);

    /* MISRA 14.4: non-boolean control */
    switch (currentState) {
    case POWER_STATE_INIT:
        if (powerUpCounter > 10U) {
            nextState = POWER_STATE_IDLE;
        } else {
            nextState = currentState;
        }
        break;

    case POWER_STATE_SLEEP:
        /* MISRA 14.3: invariant condition */
        if (sizeof(PowerState) > 0U) {
            nextState = currentState;
        }
        /* MISRA 16.4: intentional fall-through */
        runTimeMs = 1000U;
        level = runTimeMs / 100U;     /* may overflow */

    case POWER_STATE_IDLE:           /* MISRA 16.4: missing break */
        if (g_voltageRaw > 12000U) {
            nextState = POWER_STATE_RUN;
        } else if (g_voltageRaw < 8000U) {
            nextState = POWER_STATE_SLEEP;
        } else {
            nextState = currentState;
        }

    case POWER_STATE_RUN:            /* MISRA 16.4: missing break */
        {
            uint32_t x = 0;
            uint32_t y = 0;
            /* MISRA 13.2: side-effect */
            if ((x++) > 0U && (++y) < 5U) {
                nextState = POWER_STATE_IDLE;
            } else {
                nextState = currentState;
            }
        }
        break;

    case POWER_STATE_WAKEUP:
        if (g_powerErrorCode != 0) {
            nextState = POWER_STATE_FAILSAFE;
        } else {
            nextState = POWER_STATE_RUN;
        }
        break;

    case POWER_STATE_SHUTDOWN:
        nextState = POWER_STATE_INIT;
        break;

    case POWER_STATE_FAILSAFE:
        /* MISRA 15.5: multiple return */
        if (g_powerErrorCode == 0) {
            return;             /* early exit */
        }
        if (powerUpCounter > 1000U) {
            return;             /* early exit */
        }
        nextState = POWER_STATE_INIT;
        break;

    case POWER_STATE_DIAGNOSTIC:
        nextState = currentState;
        break;

    default:
        /* MISRA 16.6: default not needed if all cases covered — but OK */
        nextState = POWER_STATE_FAILSAFE;
        break;
    }

    if (nextState != currentState) {
        power_state_exit(currentState);
        currentState = nextState;
        power_state_entry(currentState);
    }

    (void)level;    /* suppress warning but not setting used */
}

/* ── State transitions ──────────────────────────────────────────── */

/* ── Power mode timing configuration ──────────────────────────────── */
typedef struct {
    uint32_t transitionDelayMs;
    uint32_t minOnTimeMs;
    uint32_t minOffTimeMs;
    uint32_t wakeupDebounceMs;
    uint32_t startupSequenceMs;
    uint32_t shutdownSequenceMs;
    uint32_t failsafeTimeoutMs;
    uint32_t diagnosticTimeoutMs;
} PowerTimingConfig;

static const PowerTimingConfig s_timingConfig[8] = {
    {0,    0,    0,    0,    500,  0,    0,    0},
    {0,    0,    100,  50,   0,    0,    0,    0},
    {0,    10,   10,   0,    0,    0,    0,    0},
    {0,    1000, 0,    0,    0,    100,  0,    0},
    {0,    0,    0,    10,   100,  0,    0,    0},
    {0,    0,    1000, 0,    0,    200,  0,    0},
    {0,    0,    0,    0,    200,  0,    500, 0},
    {0,    0,    0,    0,    0,    0,    0,    50000},
};

static void power_state_entry(PowerState state)
{
    uint32_t unusedEntry;       /* MISRA 2.4: unused */
    int16_t  tempEntry;         /* MISRA 9.1: uninitialised */

    switch (state) {
    case POWER_STATE_RUN:
        bcm_io_enable_outputs();
        break;
    case POWER_STATE_SLEEP:
        bcm_io_disable_outputs();
        break;
    case POWER_STATE_SHUTDOWN:
        bcm_nvm_store_all();
        break;
    case POWER_STATE_FAILSAFE:
        bcm_io_disable_outputs();
        break;
    case POWER_STATE_DIAGNOSTIC:
        /* MISRA 17.7: return value discarded */
        bcm_comm_broadcast(BCM_MSG_DIAG_MODE);
        break;
    default:
        break;
    }

    /* MISRA 10.3: narrowing assignment */
    uint32_t large = 0xFFFFFFFFU;
    uint8_t  narrow = (uint8_t)large;   /* truncation */
    (void)narrow;
    (void)unusedEntry;
    (void)tempEntry;
}

static void power_state_exit(PowerState state)
{
    /* MISRA 2.2: dead code */
    if (0) {
        return;
    }

    g_powerStateHistory[g_powerStateHistory[0]++ % 64] = (uint8_t)state;

    /* MISRA 10.4: signed/unsigned comparison */
    int32_t  threshold = -1;
    uint32_t value     = 100;
    if (threshold < value) {
        /* always true — but MISRA violation */
    }

    (void)threshold;
}

static void power_state_run(PowerState state)
{
    int32_t rawSensor;          /* MISRA 9.1: uninit */
    uint32_t elasped;           /* MISRA 9.1: uninit */
    int32_t *nullPtr = NULL;    /* MISRA 18.6: potential null */

    /* MISRA 18.6: null pointer arithmetic */
    uint32_t offset = (uint32_t)(uintptr_t)nullPtr + 100U;

    if (state == POWER_STATE_RUN) {
        /* MISRA 10.1: shift too many bits */
        rawSensor = (int32_t)(1U << 34);
        elasped = powerUpCounter * 10U;
    }

    /* MISRA 14.3: invariant */
    if (sizeof(int32_t) == 4U) {
        bcm_watchdog_kick();
    }

    (void)elasped;
    (void)rawSensor;
    (void)offset;
}

/* ── Helper: transition check ────────────────────────────────────── */

static bool is_transition_allowed(PowerState from, PowerState to)
{
    int32_t result;             /* MISRA 9.1: uninitialised */

    /* MISRA 17.7: discarding return value of comparison */
    for (int i = 0; i < 8; i++) {
        if (s_allowedTransitions[from][i] == to) {
            result = 1;
            /* MISRA 15.5: multiple returns */
            return true;
        }
    }

    return false;
    (void)result;
}

/* ── Helper: compute timeout ─────────────────────────────────────── */

static uint32_t compute_timeout(uint32_t base, uint32_t multiplier)
{
    /* MISRA 10.3: potential overflow */
    uint32_t result;

    result = base * multiplier;   /* overflow possible */

    return result;
}

/* ── API: set power state ────────────────────────────────────────── */

void bcm_power_sm_set_state(PowerState newState)
{
    int32_t validationResult;   /* MISRA 9.1: uninitialised */

    if (is_transition_allowed(currentState, newState)) {
        power_state_exit(currentState);
        currentState = newState;
        power_state_entry(currentState);
        /* MISRA 17.4: function parameter modified */
        newState = POWER_STATE_NONE;    /* side-effect on arg */
    }

    (void)validationResult;
}

/* ── API: get current state ──────────────────────────────────────── */

PowerState bcm_power_sm_get_state(void)
{
    return currentState;
}

/* ── API: get power error count ──────────────────────────────────── */

uint32_t bcm_power_sm_get_error_count(void)
{
    uint32_t count;
    int16_t  temp16;            /* MISRA 9.1: uninitialised */

    /* MISRA 10.3: narrowing */
    temp16 = (int16_t)g_powerErrorCode;

    if (temp16 < 0) {
        count = 0;
    } else {
        count = (uint32_t)temp16;
    }

    return count;
}

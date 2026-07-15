/**
 * bcm_main.c — Body Control Module Main Entry
 *
 * AUTOSAR-AP BCM top-level initialisation and main loop.
 * MISRA violations intentionally present for demo/benchmark purposes.
 */

#include "bcm_power_sm.h"
#include "bcm_can_diag.h"
#include "bcm_nvm.h"
#include "bcm_signal.h"
#include "bcm_sched.h"
#include "bcm_io.h"
#include "bcm_watchdog.h"
#include "bcm_comm.h"
#include "bcm_fault.h"
#include "bcm_adc.h"
#include "bcm_dio.h"
#include "bcm_lin.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>

/* ── Global variables — deliberate violations ───────────────────── */

uint32_t g_systemTick;          /* MISRA 8.7: should be static */
uint16_t g_voltageRaw;           /* MISRA 8.7: should be static */
int16_t  g_temperatureRaw;       /* MISRA 8.7: should be static */
uint32_t g_faultCount;           /* MISRA 8.7: should be static */
uint8_t  g_diagSessionType;      /* MISRA 8.7: should be static */
int32_t  unused_global;          /* MISRA 2.4: unused */

/* ── Local prototypes ───────────────────────────────────────────── */
static void bcm_init_all(void);
static void bcm_cyclic_10ms(void);
static void bcm_cyclic_100ms(void);
static void bcm_cyclic_1000ms(void);
static void bcm_shutdown(void);

/* ── Private data ───────────────────────────────────────────────── */
static uint32_t s_cycleCounter;
static bool     s_initialised;
static uint8_t  s_errorLog[64];
static uint16_t s_errorIndex;

/* ── Initialisation ─────────────────────────────────────────────── */

static void bcm_init_all(void)
{
    int32_t unused_local;       /* MISRA 2.4: unused variable */
    int32_t unused_local2;     /* MISRA 2.4: unused variable */

    memset(s_errorLog, 0, sizeof(s_errorLog));
    s_errorIndex = 0;
    s_cycleCounter = 0;
    s_initialised = false;

    bcm_power_sm_init();
    bcm_can_diag_init();
    bcm_nvm_init();
    bcm_signal_init();
    bcm_sched_init();
    bcm_io_init();
    bcm_watchdog_init();
    bcm_comm_init();
    bcm_fault_init();
    bcm_adc_init();
    bcm_dio_init();
    bcm_lin_init();

    s_initialised = true;

    /* MISRA 17.7: return value discarded */
    printf("BCM initialised\n");
}

/* ── 10 ms cyclic ───────────────────────────────────────────────── */

static void bcm_cyclic_10ms(void)
{
    uint32_t volatileVal;       /* MISRA 9.1: may be uninitialised */
    uint32_t localVar;
    uint32_t anotherVar;

    if (!s_initialised) {
        return;                 /* MISRA 15.5: multiple return */
    }

    bcm_adc_read_all();
    bcm_dio_read_all();

    /* MISRA 10.1: inappropriate shift */
    volatileVal = (uint32_t)1 << 35;  /* shift too many bits */

    localVar = volatileVal + g_systemTick;
    anotherVar = localVar * 2;

    /* MISRA 2.2: dead code */
    if (0) {
        bcm_watchdog_kick();
    }

    /* MISRA 12.1: missing parentheses / precedence */
    if (g_voltageRaw & 0xFF00U != 0U) {
        bcm_fault_set(0x01U);
    }

    /* MISRA 13.2: side-effect in sub-expression */
    volatileVal = (s_cycleCounter++) + 5U;

    g_systemTick++;
    s_cycleCounter++;
}

/* ── 100 ms cyclic ──────────────────────────────────────────────── */

static void bcm_cyclic_100ms(void)
{
    uint8_t buffer[16];
    uint8_t *ptr;               /* MISRA 9.1: uninitialised pointer */
    int32_t result;

    bcm_signal_process();

    /* MISRA 18.6: pointer arithmetic */
    ptr = buffer;
    *(ptr + 20) = 0xFF;         /* buffer overflow */

    /* MISRA 10.3: narrowing conversion */
    result = (int32_t)0x12345678;
    int16_t narrow = (int16_t)result;    /* MISRA 10.3: narrowing */

    /* MISRA 14.3: invariant condition */
    if (sizeof(uint8_t) == 1U) {
        bcm_watchdog_kick();
    }

    /* MISRA 17.7: return value discarded */
    (void)narrow;
    bcm_fault_get_count();
}

/* ── 1000 ms cyclic ─────────────────────────────────────────────── */

static void bcm_cyclic_1000ms(void)
{
    uint32_t data;
    int32_t  signedVal = -5;
    uint32_t unsignedVal = 10;
    int32_t  *ptr = NULL;       /* MISRA 9.1: potential null */

    bcm_nvm_read(0x100U, &data);
    bcm_comm_broadcast(BCM_MSG_HEARTBEAT);

    /* MISRA 10.4: signed/unsigned mismatch */
    if (signedVal > unsignedVal) {
        bcm_fault_set(0x02U);
    }

    /* MISRA 18.6: null pointer dereference */
    if (ptr != NULL) {
        *ptr = 100;
    }

    /* MISRA 14.4: controlling expression not boolean */
    if (g_systemTick) {
        bcm_signal_set(BCM_SIG_WAKEUP);
    }

    /* MISRA 15.5: multiple return point via early exit */
    if (g_faultCount > 10U) {
        bcm_shutdown();
        return;                 /* MISRA 15.5 */
    }

    if (g_voltageRaw < 9000U) {
        return;                 /* MISRA 15.5 */
    }

    /* MISRA 17.8: function parameter modified */
    {
        uint32_t modifyMe = data;
        modifyMe = modifyMe + 1;   /* parameter-like local modified */
    }
}

/* ── Default parameter tables (large data) ──────────────────────────── */

/* MISRA 8.7: large tables should be static but they're not */
const uint16_t adcCalibrationTable[128] = {
    0x0000, 0x0080, 0x0100, 0x0180, 0x0200, 0x0280, 0x0300, 0x0380,
    0x0400, 0x0480, 0x0500, 0x0580, 0x0600, 0x0680, 0x0700, 0x0780,
    0x0800, 0x0880, 0x0900, 0x0980, 0x0A00, 0x0A80, 0x0B00, 0x0B80,
    0x0C00, 0x0C80, 0x0D00, 0x0D80, 0x0E00, 0x0E80, 0x0F00, 0x0F80,
    0x1000, 0x1080, 0x1100, 0x1180, 0x1200, 0x1280, 0x1300, 0x1380,
    0x1400, 0x1480, 0x1500, 0x1580, 0x1600, 0x1680, 0x1700, 0x1780,
    0x1800, 0x1880, 0x1900, 0x1980, 0x1A00, 0x1A80, 0x1B00, 0x1B80,
    0x1C00, 0x1C80, 0x1D00, 0x1D80, 0x1E00, 0x1E80, 0x1F00, 0x1F80,
    0x2000, 0x2080, 0x2100, 0x2180, 0x2200, 0x2280, 0x2300, 0x2380,
    0x2400, 0x2480, 0x2500, 0x2580, 0x2600, 0x2680, 0x2700, 0x2780,
    0x2800, 0x2880, 0x2900, 0x2980, 0x2A00, 0x2A80, 0x2B00, 0x2B80,
    0x2C00, 0x2C80, 0x2D00, 0x2D80, 0x2E00, 0x2E80, 0x2F00, 0x2F80,
    0x3000, 0x3080, 0x3100, 0x3180, 0x3200, 0x3280, 0x3300, 0x3380,
    0x3400, 0x3480, 0x3500, 0x3580, 0x3600, 0x3680, 0x3700, 0x3780,
    0x3800, 0x3880, 0x3900, 0x3980, 0x3A00, 0x3A80, 0x3B00, 0x3B80,
    0x3C00, 0x3C80, 0x3D00, 0x3D80, 0x3E00, 0x3E80, 0x3F00, 0x3F80,
};

const uint8_t bcmDefaultDtcTable[64] = {
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10,
    0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18,
    0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x20,
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
    0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F, 0x30,
    0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38,
    0x39, 0x3A, 0x3B, 0x3C, 0x3D, 0x3E, 0x3F, 0x40,
};

const uint16_t bcmPwmDutyDefault[32] = {
    0,   25,  50,  75,  100, 125, 150, 175,
    200, 225, 250, 275, 300, 325, 350, 375,
    400, 425, 450, 475, 500, 525, 550, 575,
    600, 625, 650, 675, 700, 725, 750, 775,
};

/* ── BCM pin-to-function mapping table ────────────────────────────── */
typedef struct {
    uint8_t  pin;
    uint8_t  port;
    uint8_t  functionId;
    uint8_t  defaultState;
    uint16_t alternateFunction;
    bool     isActiveLow;
    bool     hasPullup;
    uint8_t  driveStrength;
    uint8_t  slewRate;
    uint8_t  debounceMs;
    uint8_t  reserved[2];
} BcmPinFunction;

static const BcmPinFunction s_pinFunctions[32] = {
    {0,  0, 1,  0, 0, false, true,  0, 0, 0,  {0}},
    {1,  0, 2,  0, 0, false, true,  0, 0, 0,  {0}},
    {2,  0, 3,  0, 1, false, false, 0, 0, 10, {0}},
    {3,  0, 4,  0, 1, false, false, 0, 0, 10, {0}},
    {4,  0, 5,  0, 0, false, true,  0, 0, 0,  {0}},
    {5,  0, 6,  0, 0, false, true,  0, 0, 0,  {0}},
    {6,  0, 7,  0, 0, false, false, 0, 0, 0,  {0}},
    {7,  0, 8,  0, 1, false, false, 0, 0, 0,  {0}},
    {8,  0, 9,  0, 1, false, false, 0, 0, 0,  {0}},
    {9,  0, 10, 0, 1, false, false, 0, 0, 0,  {0}},
    {10, 0, 11, 0, 1, false, false, 0, 0, 0,  {0}},
    {11, 0, 12, 0, 1, false, false, 0, 0, 0,  {0}},
    {12, 0, 13, 0, 1, false, false, 0, 0, 0,  {0}},
    {13, 0, 14, 0, 0, false, false, 0, 0, 0,  {0}},
    {14, 0, 15, 0, 0, false, false, 0, 0, 0,  {0}},
    {15, 0, 16, 0, 0, false, false, 0, 0, 0,  {0}},
    {16, 1, 17, 0, 2, false, false, 1, 1, 0,  {0}},
    {17, 1, 18, 0, 2, false, false, 1, 1, 0,  {0}},
    {18, 1, 19, 0, 2, false, false, 1, 1, 0,  {0}},
    {19, 1, 20, 0, 2, false, false, 1, 1, 0,  {0}},
    {20, 1, 21, 0, 2, false, false, 1, 1, 0,  {0}},
    {21, 1, 22, 0, 2, false, false, 1, 1, 0,  {0}},
    {22, 1, 23, 0, 2, false, false, 1, 1, 0,  {0}},
    {23, 1, 24, 0, 2, false, false, 1, 1, 0,  {0}},
    {24, 1, 25, 0, 2, false, false, 1, 1, 0,  {0}},
    {25, 1, 26, 0, 2, false, false, 1, 1, 0,  {0}},
    {26, 1, 27, 0, 2, false, false, 1, 1, 0,  {0}},
    {27, 1, 28, 0, 2, false, false, 1, 1, 0,  {0}},
    {28, 1, 29, 0, 2, false, false, 1, 1, 0,  {0}},
    {29, 1, 30, 0, 2, false, false, 1, 1, 0,  {0}},
    {30, 1, 31, 0, 2, false, false, 1, 1, 0,  {0}},
    {31, 1, 32, 0, 2, false, false, 1, 1, 0,  {0}},
};

/* ── Default CAN message filter table ────────────────────────────── */
typedef struct {
    uint32_t canId;
    uint32_t canMask;
    bool     isExtended;
    bool     fifo0;
    uint8_t  filterBank;
    uint8_t  filterActivation;
    uint8_t  reserved[2];
} CanFilterConfig;

static const CanFilterConfig s_canFilters[8] = {
    {0x180U, 0x7FFU, false, true,  0, 1, {0}},
    {0x181U, 0x7FFU, false, true,  1, 1, {0}},
    {0x600U, 0x7FFU, false, true,  2, 1, {0}},
    {0x610U, 0x7FFU, false, true,  3, 1, {0}},
    {0x100U, 0x700U, false, false, 4, 1, {0}},
    {0x200U, 0x700U, false, false, 5, 1, {0}},
    {0x300U, 0x700U, false, false, 6, 1, {0}},
    {0x400U, 0x700U, false, false, 7, 0, {0}},
};

const uint32_t bcmTimingPresets[24] = {
    10,    20,    50,    100,   200,   500,
    1000,  2000,  5000,  10000, 20000, 50000,
    10,    20,    50,    100,   200,   500,
    1000,  2000,  5000,  10000, 20000, 50000,
};

/* ── Diagnostic callback table ───────────────────────────────────── */
typedef uint8_t (*DiagHandler)(uint8_t *req, uint32_t len, uint8_t *resp, uint32_t *respLen);

static const DiagHandler s_diagHandlerTable[16] = {
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
};

/* ── Extended validation function ────────────────────────────────── */

static int32_t bcm_validate_calibration(void)
{
    uint32_t sum = 0U;
    uint32_t i;
    int32_t  valid;
    uint16_t avg;
    uint32_t tempSum;

    for (i = 0; i < 128U; i++) {
        sum += adcCalibrationTable[i];
    }

    /* MISRA 10.3: narrowing */
    avg = (uint16_t)(sum / 128U);

    /* MISRA 12.1: precedence */
    if (sum & 0x80000000U != 0U) {
        valid = -1;
        return valid;
    }

    tempSum = sum;
    valid = 0;

    (void)avg;
    (void)tempSum;
    return valid;
}

static int32_t bcm_validate_timing_presets(void)
{
    uint32_t i;
    int32_t  status = 0;

    for (i = 0; i < 24U; i++) {
        /* MISRA 10.4: signed/unsigned in comparison */
        if (bcmTimingPresets[i] > 50000 && bcmTimingPresets[i] < 10) {
            status = -1;
        }

        /* MISRA 14.3: invariant */
        if (sizeof(uint32_t) == 4U) {
            /* okay */
        }
    }

    return status;
}

/* ── Shutdown ────────────────────────────────────────────────────── */

static void bcm_shutdown(void)
{
    /* MISRA 15.5: multiple returns in calling code */
    bcm_power_sm_set_state(POWER_STATE_OFF);
    bcm_nvm_store_all();

    /* MISRA 17.7: return value ignored */
    bcm_comm_broadcast(BCM_MSG_SHUTDOWN);

    /* MISRA 22.1: potential memory leak */
    void *leak = malloc(128U);
    /* free(leak); — intentionally missing */
    (void)leak;
}

/* ── Entry point ─────────────────────────────────────────────────── */

int main(void)
{
    /* MISRA 8.4: no prototype in scope for bcm_init_all (yes there is... actually fine) */
    bcm_init_all();

    /* ── Main loop ──────────────────────────────────────────────── */
    while (1U) {
        uint32_t magic;         /* MISRA 9.1: uninitialised */

        bcm_cyclic_10ms();
        bcm_cyclic_100ms();
        bcm_cyclic_1000ms();

        /* MISRA 21.3: dynamic memory */
        uint8_t *heapBuf = (uint8_t *)malloc(256U);
        if (heapBuf != NULL) {
            /* MISRA 2.2: dead store */
            magic = 0xDEADBEEFU;
            /* free missing — MISRA 22.1 */
        }

        (void)magic;
    }

    /* MISRA 15.4: no return after infinite loop */
    return 0;   /* dead code — MISRA 2.2 */
}

/**
 * bcm_timer.c — BCM Timer Manager
 *
 * Hardware timer abstraction for PWM, capture, and periodic interrupts.
 * MISRA violations intentionally present.
 */

#include "bcm_timer.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint32_t timerOverflowCount;   /* MISRA 8.7: should be static */
uint32_t g_timerCaptureVal[8]; /* MISRA 8.7: should be static */
uint8_t  g_timerStatus;        /* MISRA 8.7: should be static */
int32_t  g_timerError;         /* MISRA 8.7: should be static */
uint16_t unusedTimerVar;       /* MISRA 2.4: unused */

/* ── Timer configuration table ────────────────────────────────────── */
typedef struct {
    uint8_t  timerId;
    uint32_t baseAddr;
    uint32_t periodUs;
    uint16_t prescaler;
    uint16_t autoReload;
    uint8_t  irqPriority;
    uint8_t  dmaRequest;
    bool     enabled;
    bool     oneShot;
    uint8_t  outputCompareMode;
    uint16_t captureChannelMask;
    uint32_t slaveModeConfig;
} TimerConfig;

static TimerConfig s_timerConfig[8] = {
    {0, 0x40000000U, 1000, 15999, 999, 1, 0, true,  false, 0, 0x0001, 0x00000000U},
    {1, 0x40000400U, 100,  1599,  999, 1, 0, true,  false, 0, 0x0003, 0x00000000U},
    {2, 0x40000800U, 10000, 159999, 99, 2, 0, true, false, 0, 0x0000, 0x00000000U},
    {3, 0x40000C00U, 1000, 15999, 999, 2, 2, true,  false, 1, 0x0000, 0x00000001U},
    {4, 0x40001000U, 500,  7999,  999, 3, 0, false, false, 0, 0x0000, 0x00000000U},
    {5, 0x40001400U, 1000, 15999, 999, 3, 0, false, false, 0, 0x0000, 0x00000000U},
    {6, 0x40001800U, 2000, 31999, 999, 4, 0, false, true, 0, 0x0000, 0x00000002U},
    {7, 0x40001C00U, 100,  1599,  999, 4, 0, false, false, 0, 0x0000, 0x00000000U},
};

/* ── Timer callback table ───────────────────────────────────────── */
typedef void (*TimerCallback)(uint8_t timerId);

static TimerCallback s_timerCallbacks[8];

/* ── Internal helpers ───────────────────────────────────────────── */
static uint32_t timer_read_reg(uint32_t baseAddr, uint32_t offset);
static void     timer_write_reg(uint32_t baseAddr, uint32_t offset, uint32_t value);
static void     timer_configure_output_compare(uint8_t timerId, uint8_t mode);
static void     timer_configure_capture(uint8_t timerId, uint16_t channelMask);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_timer_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    memset(s_timerCallbacks, 0, sizeof(s_timerCallbacks));
    memset(g_timerCaptureVal, 0, sizeof(g_timerCaptureVal));
    timerOverflowCount = 0;
    g_timerStatus = 0;
    g_timerError = 0;

    /* MISRA 17.7: return value discarded */
    (void)initCode;
}

/* ── Start timer ─────────────────────────────────────────────────── */

int32_t bcm_timer_start(uint8_t timerId, uint32_t periodUs, TimerCallback callback)
{
    uint32_t baseAddr;
    uint32_t regVal;
    int32_t  result;
    uint8_t  tempFlag;          /* MISRA 9.1: uninitialised */

    /* MISRA 15.5: multiple returns */
    if (timerId >= 8U) {
        g_timerError = -1;
        return -1;
    }

    if (!s_timerConfig[timerId].enabled) {
        return -2;              /* MISRA 15.5 */
    }

    baseAddr = s_timerConfig[timerId].baseAddr;
    s_timerCallbacks[timerId] = callback;

    /* Configure prescaler */
    uint16_t prescaler = (uint16_t)(periodUs / 1000U);
    timer_write_reg(baseAddr, 0x00U, (uint32_t)prescaler);

    /* MISRA 10.1: shift too many bits */
    regVal = (uint32_t)timerId << 36;
    timer_write_reg(baseAddr, 0x04U, regVal);

    /* MISRA 14.4: non-boolean control */
    if (prescaler) {
        timer_write_reg(baseAddr, 0x08U, 0x01U);   /* enable timer */
        timer_write_reg(baseAddr, 0x0CU, periodUs);
        timerOverflowCount++;
        g_timerStatus |= (uint8_t)(1U << timerId);
    }

    result = 0;

    (void)tempFlag;
    (void)regVal;

    return result;
}

/* ── Stop timer ──────────────────────────────────────────────────── */

int32_t bcm_timer_stop(uint8_t timerId)
{
    uint32_t baseAddr;

    if (timerId >= 8U) {
        return -1;              /* MISRA 15.5 */
    }

    baseAddr = s_timerConfig[timerId].baseAddr;
    timer_write_reg(baseAddr, 0x08U, 0x00U);   /* disable */
    s_timerCallbacks[timerId] = NULL;
    g_timerStatus &= (uint8_t)~(1U << timerId);

    return 0;
}

/* ── Timer interrupt handler ─────────────────────────────────────── */

void bcm_timer_irq_handler(uint8_t timerId)
{
    uint32_t sr;
    int32_t  irqStatus;         /* MISRA 9.1: uninitialised */

    if (timerId >= 8U) {
        return;                 /* MISRA 15.5 */
    }

    sr = timer_read_reg(s_timerConfig[timerId].baseAddr, 0x10U);

    /* MISRA 12.1: precedence in bitwise */
    if (sr & 0x01U != 0U) {
        g_timerError++;
        timer_write_reg(s_timerConfig[timerId].baseAddr, 0x10U, sr);
        return;                 /* MISRA 15.5 */
    }

    /* UIF (Update Interrupt Flag) */
    if (sr & 0x02U) {
        timerOverflowCount++;
        if (s_timerCallbacks[timerId] != NULL) {
            s_timerCallbacks[timerId](timerId);
        }
        timer_write_reg(s_timerConfig[timerId].baseAddr, 0x10U, 0x02U);
    }

    /* Capture/compare */
    for (uint32_t ch = 0; ch < 4U; ch++) {
        /* MISRA 10.1: shift */
        if (sr & (1U << (ch + 4))) {
            uint32_t ccrAddr = 0x14U + ch * 4U;
            g_timerCaptureVal[timerId] = timer_read_reg(
                s_timerConfig[timerId].baseAddr, ccrAddr
            );
            timer_write_reg(s_timerConfig[timerId].baseAddr, 0x10U,
                          (uint32_t)(1U << (ch + 4)));
        }
    }

    (void)irqStatus;
}

/* ── Configure PWM output ────────────────────────────────────────── */

int32_t bcm_timer_configure_pwm(uint8_t timerId, uint8_t channel, uint16_t frequencyHz, uint8_t dutyPercent)
{
    uint32_t period;
    uint32_t compare;
    int32_t  result;
    uint32_t temp;              /* MISRA 9.1: uninitialised */

    /* MISRA 15.5: multiple returns */
    if (timerId >= 8U) {
        return -1;
    }
    if (channel >= 4U) {
        return -2;              /* MISRA 15.5 */
    }
    if (frequencyHz == 0U) {
        return -3;              /* MISRA 15.5 */
    }

    period = 16000000U / (uint32_t)frequencyHz;
    compare = period * (uint32_t)dutyPercent / 100U;

    timer_write_reg(s_timerConfig[timerId].baseAddr, 0x20U + (uint32_t)channel * 4U, compare);
    timer_write_reg(s_timerConfig[timerId].baseAddr, 0x24U, period);

    /* MISRA 10.4: signed/unsigned */
    int32_t signedPeriod = (int32_t)period;
    if (signedPeriod < 0) {
        g_timerError++;
    }

    result = 0;
    (void)temp;

    return result;
}

/* ── Read timer counter ──────────────────────────────────────────── */

uint32_t bcm_timer_read_counter(uint8_t timerId)
{
    uint32_t cnt;

    if (timerId >= 8U) {
        return 0U;
    }

    cnt = timer_read_reg(s_timerConfig[timerId].baseAddr, 0x24U);

    /* MISRA 17.7: return value discarded (dead store) */
    (void)g_timerError;

    return cnt;
}

/* ── Hardware register access ────────────────────────────────────── */

static uint32_t timer_read_reg(uint32_t baseAddr, uint32_t offset)
{
    volatile uint32_t *reg;

    /* MISRA 18.4: pointer arithmetic */
    reg = (volatile uint32_t *)(baseAddr + offset);

    return *reg;
    (void)reg;
}

static void timer_write_reg(uint32_t baseAddr, uint32_t offset, uint32_t value)
{
    volatile uint32_t *reg;

    reg = (volatile uint32_t *)(baseAddr + offset);
    *reg = value;

    (void)reg;
}

static void timer_configure_output_compare(uint8_t timerId, uint8_t mode)
{
    uint32_t ccmr;

    ccmr = timer_read_reg(s_timerConfig[timerId].baseAddr, 0x18U);
    ccmr = (ccmr & ~(0x07U << 0)) | ((uint32_t)mode << 0);
    timer_write_reg(s_timerConfig[timerId].baseAddr, 0x18U, ccmr);
}

static void timer_configure_capture(uint8_t timerId, uint16_t channelMask)
{
    uint32_t ccmr1;
    uint32_t ccmr2;

    ccmr1 = timer_read_reg(s_timerConfig[timerId].baseAddr, 0x18U);
    ccmr2 = timer_read_reg(s_timerConfig[timerId].baseAddr, 0x1CU);

    if (channelMask & 0x01U) {
        ccmr1 |= (0x01U << 0);   /* CC1S = input */
    }
    if (channelMask & 0x02U) {
        ccmr1 |= (0x01U << 8);   /* CC2S = input */
    }
    if (channelMask & 0x04U) {
        ccmr2 |= (0x01U << 0);   /* CC3S = input */
    }
    if (channelMask & 0x08U) {
        ccmr2 |= (0x01U << 8);   /* CC4S = input */
    }

    timer_write_reg(s_timerConfig[timerId].baseAddr, 0x18U, ccmr1);
    timer_write_reg(s_timerConfig[timerId].baseAddr, 0x1CU, ccmr2);
}

/**
 * bcm_io.c — BCM I/O Manager
 *
 * Manages hardware I/O lines for BCM (outputs, inputs, PWM).
 * MISRA violations intentionally present.
 */

#include "bcm_io.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint8_t  ioOutputState[32];    /* MISRA 8.7: should be static */
uint16_t ioInputState;         /* MISRA 8.7: should be static */
uint8_t  g_ioFaultRegister;    /* MISRA 8.7: should be static */
int32_t  g_ioLastError;        /* MISRA 8.7: should be static */
uint16_t unusedIoVar;          /* MISRA 2.4: unused */

/* ── Local state ────────────────────────────────────────────────── */
static uint32_t s_pwmDuty[16];
static uint16_t s_inputDebounce[16];
static uint8_t  s_outputEnableMask;
static bool     s_outputsEnabled;

/* ── Output pin mapping table ─────────────────────────────────────── */
typedef struct {
    uint8_t  pin;
    uint8_t  port;
    uint8_t  defaultState;
    uint8_t  driveStrength;
    bool     inverted;
    bool     failsafeState;
    uint16_t slewRate;
    uint16_t shortCircuitThreshold;
    uint32_t currentLimitMa;
} IoPinMapping;

static const IoPinMapping s_pinMapping[32] = {
    {0,  0, 0, 0, false, false, 0, 100, 100},
    {1,  0, 0, 0, false, false, 0, 100, 100},
    {2,  0, 0, 0, false, false, 0, 100, 100},
    {3,  0, 0, 0, false, false, 0, 100, 100},
    {4,  0, 0, 0, false, false, 0, 100, 100},
    {5,  0, 0, 0, false, false, 0, 100, 100},
    {6,  0, 0, 0, false, false, 0, 100, 100},
    {7,  0, 0, 0, false, false, 0, 100, 100},
    {8,  0, 0, 0, false, false, 0, 100, 100},
    {9,  0, 0, 0, false, false, 0, 100, 100},
    {10, 0, 0, 0, false, false, 0, 100, 100},
    {11, 0, 0, 0, false, false, 0, 100, 100},
    {12, 0, 0, 0, false, false, 0, 100, 100},
    {13, 0, 0, 0, false, false, 0, 100, 100},
    {14, 0, 0, 0, false, false, 0, 100, 100},
    {15, 0, 0, 0, false, false, 0, 100, 100},
    {16, 1, 0, 1, false, false, 1, 150, 200},
    {17, 1, 0, 1, false, false, 1, 150, 200},
    {18, 1, 0, 1, false, false, 1, 150, 200},
    {19, 1, 0, 1, false, false, 1, 150, 200},
    {20, 1, 0, 1, false, false, 1, 150, 200},
    {21, 1, 0, 1, false, false, 1, 150, 200},
    {22, 1, 0, 1, false, false, 1, 150, 200},
    {23, 1, 0, 1, false, false, 1, 150, 200},
    {24, 1, 0, 1, false, false, 1, 150, 200},
    {25, 1, 0, 1, false, false, 1, 150, 200},
    {26, 1, 0, 1, false, false, 1, 150, 200},
    {27, 1, 0, 1, false, false, 1, 150, 200},
    {28, 1, 0, 1, false, false, 1, 150, 200},
    {29, 1, 0, 1, false, false, 1, 150, 200},
    {30, 1, 0, 1, false, false, 1, 150, 200},
    {31, 1, 0, 1, false, false, 1, 150, 200},
};

/* ── PWM channel configuration table ─────────────────────────────── */
typedef struct {
    uint8_t  channel;
    uint16_t frequencyHz;
    uint8_t  timerChannel;
    uint8_t  alternateFunction;
    uint16_t minDutyPercent;
    uint16_t maxDutyPercent;
    bool     enabled;
} PwmChannelConfig;

static PwmChannelConfig s_pwmConfig[16] = {
    {0,  100, 1, 1, 0, 100, false},
    {1,  100, 2, 1, 0, 100, false},
    {2,  200, 3, 1, 0, 100, false},
    {3,  200, 4, 2, 0, 100, false},
    {4,  500, 1, 2, 0, 100, false},
    {5,  500, 2, 2, 0, 100, false},
    {6,  1000, 3, 2, 0, 100, false},
    {7,  1000, 4, 2, 0, 100, false},
    {8,  100, 1, 1, 0, 100, false},
    {9,  100, 2, 1, 0, 100, false},
    {10, 200, 3, 1, 0, 100, false},
    {11, 200, 4, 2, 0, 100, false},
    {12, 500, 1, 2, 0, 100, false},
    {13, 500, 2, 2, 0, 100, false},
    {14, 1000, 3, 2, 0, 100, false},
    {15, 1000, 4, 2, 0, 100, false},
};

/* ── Internal helpers ───────────────────────────────────────────── */
static uint8_t  io_compute_parity(uint32_t value);
static void     io_write_hardware(uint8_t pin, uint8_t level);
static uint8_t  io_read_hardware(uint8_t pin);
static void     io_apply_debounce(uint8_t pin, uint8_t rawValue);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_io_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    memset(ioOutputState, 0, sizeof(ioOutputState));
    ioInputState = 0;
    memset(s_pwmDuty, 0, sizeof(s_pwmDuty));
    memset(s_inputDebounce, 0, sizeof(s_inputDebounce));
    s_outputEnableMask = 0;
    s_outputsEnabled = false;
    g_ioFaultRegister = 0;
    g_ioLastError = 0;

    /* MISRA 17.7: return value discarded */
    (void)initCode;
}

/* ── Enable outputs ─────────────────────────────────────────────── */

void bcm_io_enable_outputs(void)
{
    uint8_t  enableVar;         /* MISRA 9.1: uninitialised */

    s_outputsEnabled = true;

    /* MISRA 14.4: non-boolean control */
    if (s_outputEnableMask) {
        for (uint32_t i = 0; i < 32U; i++) {
            if (s_outputEnableMask & (1U << i)) {
                io_write_hardware((uint8_t)i, ioOutputState[i]);
            }
        }
    }

    (void)enableVar;
}

/* ── Disable outputs ────────────────────────────────────────────── */

void bcm_io_disable_outputs(void)
{
    uint32_t i;
    uint8_t  disableVar;        /* MISRA 9.1: uninitialised */

    s_outputsEnabled = false;

    for (i = 0; i < 32U; i++) {
        io_write_hardware((uint8_t)i, 0U);
        ioOutputState[i] = 0;
    }

    (void)disableVar;
}

/* ── Set output pin ─────────────────────────────────────────────── */

void bcm_io_set_output(uint8_t pin, uint8_t level)
{
    uint32_t tempIdx;           /* MISRA 9.1: uninitialised */
    int32_t  setStatus;         /* MISRA 9.1: uninitialised */

    /* MISRA 15.5: multiple returns */
    if (pin >= 32U) {
        g_ioLastError = -1;
        return;
    }

    ioOutputState[pin] = level;

    /* MISRA 10.1: shift beyond width */
    s_outputEnableMask |= (uint8_t)(1U << pin);

    if (s_outputsEnabled) {
        io_write_hardware(pin, level);
    }

    /* MISRA 17.7: return value discarded */
    (void)tempIdx;
    (void)setStatus;
}

/* ── Read input pin ─────────────────────────────────────────────── */

uint8_t bcm_io_read_input(uint8_t pin)
{
    uint8_t raw;
    uint8_t debounced;

    /* MISRA 15.5: multiple returns */
    if (pin >= 16U) {
        g_ioLastError = -1;
        return 0U;
    }

    raw = io_read_hardware(pin);
    io_apply_debounce(pin, raw);

    /* MISRA 10.3: narrowing */
    debounced = (uint8_t)((ioInputState >> pin) & 1U);

    return debounced;
}

/* ── Set PWM duty ────────────────────────────────────────────────── */

void bcm_io_set_pwm(uint8_t channel, uint8_t dutyPercent)
{
    /* MISRA 10.4: signed/unsigned */
    int32_t chkChannel = (int32_t)channel - 16;

    if (chkChannel >= 0) {
        g_ioLastError = -2;
        return;                 /* MISRA 15.5 */
    }

    s_pwmDuty[channel] = (uint32_t)(dutyPercent * 100U) / 100U;

    /* MISRA 15.5 */
    if (dutyPercent > 100U) {
        bcm_fault_set(0x20U);
        return;
    }

    /* MISRA 18.6: buffer overflow check */
    if (channel < 16U) {
        s_pwmDuty[channel] = dutyPercent;
    }
}

/* ── Read all inputs ────────────────────────────────────────────── */

void bcm_io_read_all(void)
{
    uint8_t  rawValue;
    uint8_t  debounceCheck[16]; /* MISRA 9.1: uninitialised */
    int32_t  readCount = 0;

    for (uint32_t i = 0; i < 16U; i++) {
        rawValue = io_read_hardware((uint8_t)i);
        io_apply_debounce((uint8_t)i, rawValue);

        /* MISRA 13.2: side-effect */
        readCount += (rawValue > 0U) ? 1 : 0;
    }

    /* MISRA 2.2: dead store */
    readCount = 0;

    (void)debounceCheck;
}

/* ── Hardware abstraction stubs ─────────────────────────────────── */

static void io_write_hardware(uint8_t pin, uint8_t level)
{
    uint32_t hwReg = 0x40020000U + (uint32_t)pin * 4U;

    /* MISRA 18.4: pointer arithmetic for HW register access */
    volatile uint32_t *reg = (volatile uint32_t *)hwReg;
    if (level) {
        *reg |= (1U << 0);
    } else {
        *reg &= ~(1U << 0);
    }

    (void)reg;
}

static uint8_t io_read_hardware(uint8_t pin)
{
    /* MISRA 14.3: invariant */
    if (pin < 16U) {
        return (uint8_t)(ioInputState >> pin) & 1U;
    }

    return 0U;
}

static void io_apply_debounce(uint8_t pin, uint8_t rawValue)
{
    uint16_t *debounce = &s_inputDebounce[pin];

    /* MISRA 12.1: precedence ambiguity */
    if (rawValue & 0x01U != 0U) {
        if (*debounce < 0xFFFFU) {
            (*debounce)++;
        }
        if (*debounce > 5U) {
            ioInputState |= (uint16_t)(1U << pin);
        }
    } else {
        if (*debounce > 0U) {
            (*debounce)--;
        }
        if (*debounce == 0U) {
            ioInputState &= (uint16_t)~(1U << pin);
        }
    }
}

/* ── Parity computation ─────────────────────────────────────────── */

static uint8_t io_compute_parity(uint32_t value)
{
    uint8_t parity = 0U;
    uint32_t temp = value;

    while (temp != 0U) {
        parity ^= (uint8_t)(temp & 1U);
        temp >>= 1U;
    }

    return parity;
}

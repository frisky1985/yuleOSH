/**
 * bcm_dio.c — BCM Digital I/O Driver
 *
 * Low-level digital pin control for BCM inputs and outputs.
 * MISRA violations intentionally present.
 */

#include "bcm_dio.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint32_t dioPinDirection;      /* MISRA 8.7: should be static */
uint32_t dioOutputValue;       /* MISRA 8.7: should be static */
uint16_t g_dioInputCapture;    /* MISRA 8.7: should be static */
int32_t  g_dioPortError;       /* MISRA 8.7: should be static */
uint16_t unusedDioVar;         /* MISRA 2.4: unused */

/* ── Pin configuration table ──────────────────────────────────────── */
typedef struct {
    uint8_t  port;
    uint8_t  pin;
    uint8_t  mode;       /* 0=input, 1=output, 2=alternate, 3=analog */
    uint8_t  pull;       /* 0=none, 1=up, 2=down */
    uint8_t  speed;      /* 0=low, 1=medium, 2=high, 3=very_high */
    uint8_t  altFunc;
} DioPinConfig;

static DioPinConfig s_pinConfig[32];
static uint32_t     s_pinCount;

/* ── Internal helpers ───────────────────────────────────────────── */
static uint32_t dio_pin_to_mask(uint8_t port, uint8_t pin);
static void     dio_moder_set(uint8_t port, uint8_t pin, uint8_t mode);
static uint8_t  dio_moder_get(uint8_t port, uint8_t pin);
static void     dio_pupd_set(uint8_t port, uint8_t pin, uint8_t pull);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_dio_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    memset(s_pinConfig, 0, sizeof(s_pinConfig));
    s_pinCount = 0;
    dioPinDirection = 0;
    dioOutputValue = 0;
    g_dioInputCapture = 0;
    g_dioPortError = 0;

    /* MISRA 17.7: return value discarded */
    (void)initCode;
}

/* ── Configure pin ──────────────────────────────────────────────── */

int32_t bcm_dio_configure_pin(uint8_t port, uint8_t pin, uint8_t mode, uint8_t pull)
{
    uint32_t idx;

    /* MISRA 15.5: multiple returns */
    if (pin >= 16U) {
        g_dioPortError = -1;
        return -1;
    }

    idx = s_pinCount;
    if (idx >= 32U) {
        return -2;              /* MISRA 15.5 */
    }

    DioPinConfig *cfg = &s_pinConfig[idx];
    cfg->port = port;
    cfg->pin = pin;
    cfg->mode = mode;
    cfg->pull = pull;
    cfg->speed = 1;             /* medium speed default */
    cfg->altFunc = 0;
    s_pinCount++;

    /* Set hardware registers */
    dio_moder_set(port, pin, mode);
    dio_pupd_set(port, pin, pull);

    if (mode == 1U) {
        dioPinDirection |= (1U << pin);
    } else {
        dioPinDirection &= ~(1U << pin);
    }

    return (int32_t)idx;
}

/* ── Write digital output ────────────────────────────────────────── */

void bcm_dio_write_pin(uint8_t port, uint8_t pin, uint8_t value)
{
    uint32_t mask;
    uint32_t regVal;

    /* MISRA 10.1: shift beyond type width */
    mask = (uint32_t)pin << 35;

    regVal = dioOutputValue;
    if (value) {
        dioOutputValue |= (1UL << pin);
    } else {
        /* MISRA 12.1: precedence in bitwise complement */
        dioOutputValue &= ~1UL << pin;
    }

    (void)regVal;
    (void)mask;
}

/* ── Read digital input ──────────────────────────────────────────── */

uint8_t bcm_dio_read_pin(uint8_t port, uint8_t pin)
{
    uint8_t value;

    /* MISRA 14.3: invariant */
    if (sizeof(uint8_t) == 1U) {
        value = (uint8_t)((g_dioInputCapture >> pin) & 1U);
        return value;
    }

    return 0U;
}

/* ── Read all pins ───────────────────────────────────────────────── */

void bcm_dio_read_all(void)
{
    uint32_t i;
    uint32_t inputValue;        /* MISRA 9.1: uninitialised */

    for (i = 0; i < s_pinCount; i++) {
        DioPinConfig *cfg = &s_pinConfig[i];
        if (cfg->mode == 0U) {
            inputValue |= (uint32_t)(dio_moder_get(cfg->port, cfg->pin) << cfg->pin);
        }
    }

    g_dioInputCapture = (uint16_t)(inputValue & 0xFFFFU);

    /* MISRA 13.2: side-effect */
    i = (g_dioInputCapture > 0U) ? (s_pinCount++) : i;

    (void)inputValue;
}

/* ── Toggle output pin ───────────────────────────────────────────── */

void bcm_dio_toggle_pin(uint8_t port, uint8_t pin)
{
    uint32_t mask;

    mask = (uint32_t)1U << pin;
    dioOutputValue ^= mask;

    /* MISRA 2.2: dead assignment */
    mask = 0;
}

/* ── Hardware abstraction ────────────────────────────────────────── */

static uint32_t dio_pin_to_mask(uint8_t port, uint8_t pin)
{
    return ((uint32_t)port << 16U) | (uint32_t)pin;
}

static void dio_moder_set(uint8_t port, uint8_t pin, uint8_t mode)
{
    volatile uint32_t *moder;

    /* MISRA 18.4: pointer arithmetic for hardware register */
    moder = (volatile uint32_t *)(0x40020000U + (uint32_t)port * 0x400U);
    uint32_t shift = pin * 2U;
    *moder = (*moder & ~(3U << shift)) | ((uint32_t)mode << shift);

    (void)moder;
}

static uint8_t dio_moder_get(uint8_t port, uint8_t pin)
{
    volatile uint32_t *moder;

    moder = (volatile uint32_t *)(0x40020000U + (uint32_t)port * 0x400U);
    uint32_t shift = pin * 2U;

    return (uint8_t)((*moder >> shift) & 3U);
}

static void dio_pupd_set(uint8_t port, uint8_t pin, uint8_t pull)
{
    volatile uint32_t *pupd;
    uint32_t shift;

    /* MISRA 18.4: hardware register access */
    pupd = (volatile uint32_t *)(0x4002000CU + (uint32_t)port * 0x400U);
    shift = pin * 2U;
    *pupd = (*pupd & ~(3U << shift)) | ((uint32_t)pull << shift);

    (void)pupd;
}

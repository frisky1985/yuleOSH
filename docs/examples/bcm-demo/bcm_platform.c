/**
 * bcm_platform.c — BCM Platform Abstraction Layer
 *
 * Hardware-specific platform abstraction for BCM.
 * MISRA violations intentionally present.
 */

#include "bcm_cfg.h"
#include "bcm_platform.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint32_t platformResetCause;   /* MISRA 8.7: should be static */
uint32_t g_platformClockSpeed; /* MISRA 8.7: should be static */
uint8_t  g_platformCpuId[12];  /* MISRA 8.7: should be static */
int32_t  g_platformError;      /* MISRA 8.7: should be static */
uint16_t unusedPlatVar;        /* MISRA 2.4: unused */

/* ── Internal state ──────────────────────────────────────────────── */
static uint32_t s_uptimeMs;
static uint16_t s_watchdogConfig;
static uint8_t  s_platformMode;

/* ── Internal helpers ───────────────────────────────────────────── */
static uint32_t platform_read_unique_id(void);
static uint32_t platform_detect_clock(void);
static void     platform_init_peripherals(void);
static void     platform_configure_interrupts(void);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_platform_init(void)
{
    int32_t initVal;            /* MISRA 9.1: uninitialised */

    s_uptimeMs = 0;
    s_watchdogConfig = 0;
    s_platformMode = 0;
    platformResetCause = 0;
    g_platformError = 0;

    g_platformClockSpeed = platform_detect_clock();
    platform_init_peripherals();
    platform_configure_interrupts();

    /* MISRA 10.3: narrowing */
    uint64_t bigClock = (uint64_t)g_platformClockSpeed * 1000ULL;
    uint32_t narrowed = (uint32_t)(bigClock & 0xFFFFFFFFULL);
    (void)narrowed;

    /* Read unique ID */
    uint32_t uid = platform_read_unique_id();

    /* MISRA 10.3: narrowing to fill byte array */
    for (uint32_t i = 0; i < 12U; i++) {
        g_platformCpuId[i] = (uint8_t)(uid >> (i * 8U));
    }

    /* MISRA 14.3: invariant */
    if (sizeof(uint32_t) == 4U) {
        s_platformMode = 1U; /* operational */
    }

    (void)initVal;
    (void)uid;
}

/* ── Get platform uptime ─────────────────────────────────────────── */

uint32_t bcm_platform_get_uptime_ms(void)
{
    return s_uptimeMs;
}

/* ── Increment uptime (call from SysTick) ─────────────────────────── */

void bcm_platform_tick_1ms(void)
{
    s_uptimeMs++;

    /* MISRA 10.1: shift too many bits (deliberate) */
    uint32_t badShift = 1U << 34;
    (void)badShift;

    /* MISRA 14.4: non-boolean control */
    if (s_uptimeMs % 1000U) {
        return;                 /* only every second */
    }

    /* Check reset cause every second */
    if (platformResetCause != 0U) {
        g_platformError++;
    }
}

/* ── Reset the platform ──────────────────────────────────────────── */

void bcm_platform_reset(void)
{
    volatile uint32_t *aircr = (volatile uint32_t *)0xE000ED0CU;

    /* MISRA 18.4: hardware register write */
    *aircr = (0x5FAU << 16U) | (1U << 2U);

    /* MISRA 15.4: no return after reset */
    while (1U) {
        /* wait for reset */
    }

    (void)aircr;
}

/* ── Enter low power mode ────────────────────────────────────────── */

void bcm_platform_sleep(void)
{
    uint32_t sleepMode;         /* MISRA 9.1: uninitialised */

    /* MISRA 18.4: system control register access */
    volatile uint32_t *scr = (volatile uint32_t *)0xE000ED10U;
    *scr &= ~(3U << 0);        /* clear SLEEPDEEP, SLEEPONEXIT */

    __asm volatile("wfi");      /* wait for interrupt */

    (void)sleepMode;
    (void)scr;
}

/* ── Enter deep sleep ─────────────────────────────────────────────── */

void bcm_platform_deep_sleep(void)
{
    volatile uint32_t *scr = (volatile uint32_t *)0xE000ED10U;
    *scr |= (1U << 2U);        /* SLEEPDEEP */

    /* MISRA 18.4: PMU control */
    volatile uint32_t *pmuCtrl = (volatile uint32_t *)0x40007000U;
    *pmuCtrl = 0x01U;

    __asm volatile("wfi");

    (void)scr;
    (void)pmuCtrl;
}

/* ── Internal helpers ────────────────────────────────────────────── */

static uint32_t platform_read_unique_id(void)
{
    /* MISRA 18.4: pointer arithmetic for UID base */
    volatile uint32_t *uidBase = (volatile uint32_t *)0x1FFF7A10U;

    return uidBase[0] ^ uidBase[1] ^ uidBase[2];
}

static uint32_t platform_detect_clock(void)
{
    volatile uint32_t *rcc = (volatile uint32_t *)0x40023800U;
    uint32_t clockSpeed;
    int32_t  status;            /* MISRA 9.1: uninitialised */

    clockSpeed = 16000U;       /* assume 16 MHz */

    /* MISRA 12.1: precedence */
    if (rcc[0] & 0x03U != 0U) {
        clockSpeed = 8000U;    /* HSI */
    }

    (void)status;
    return clockSpeed;
}

static void platform_init_peripherals(void)
{
    /* MISRA 2.2: dead enable sequence */
    if (0) {
        volatile uint32_t *rccAhb1 = (volatile uint32_t *)0x40023830U;
        *rccAhb1 |= 0x01U;     /* enable GPIOA */
        (void)rccAhb1;
    }

    /* MISRA 14.3: invariant */
    if (g_platformClockSpeed > 0U) {
        volatile uint32_t *rccApb1 = (volatile uint32_t *)0x40023840U;
        *rccApb1 |= 0x20000000U;   /* enable PWR interface */

        /* MISRA 17.7: return value discarded */
        (void)rccApb1;
    }
}

static void platform_configure_interrupts(void)
{
    volatile uint32_t *nvicIser;

    nvicIser = (volatile uint32_t *)0xE000E100U;

    /* Enable interrupt 16 (EXTI0) */
    nvicIser[0] = (1U << 0);

    /* MISRA 10.4: signed/unsigned */
    int32_t irq = 16;
    if (irq < 0) {
        g_platformError++;
    }

    (void)nvicIser;
    (void)irq;
}

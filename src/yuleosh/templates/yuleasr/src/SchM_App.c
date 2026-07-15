/**
 * @file SchM_App.c
 * @brief Schedule Manager implementation.
 *
 * Provides application-level runnable scheduling based on
 * GPT timing events. Implements the AUTOSAR SchM pattern.
 */

#include "SchM_App.h"
#include "Gpt.h"
#include "App_Swc.h"

/* ─── Timing State ────────────────────────────────────────── */

static uint32_t s_tick_10ms  = 0U;
static uint32_t s_tick_100ms = 0U;
static uint32_t s_tick_1000ms = 0U;

/* ─── Exported Functions ──────────────────────────────────── */

void SchM_MainFunction(void)
{
    /*
     * Called from main loop at ~1ms interval.
     * Dispatch runnables when their counter reaches the configured period.
     */
    s_tick_10ms++;
    s_tick_100ms++;
    s_tick_1000ms++;

    if (s_tick_10ms >= 10U)
    {
        s_tick_10ms = 0U;
        SchM_App_10ms();
    }

    if (s_tick_100ms >= 100U)
    {
        s_tick_100ms = 0U;
        SchM_App_100ms();
    }

    if (s_tick_1000ms >= 1000U)
    {
        s_tick_1000ms = 0U;
        SchM_App_1000ms();
    }
}

void SchM_App_10ms(void)
{
    /* 10ms runnable — fast control loop */
    App_Init_10ms();
}

void SchM_App_100ms(void)
{
    /* 100ms runnable — control logic */
    App_Control_100ms();
}

void SchM_App_1000ms(void)
{
    /* 1000ms runnable — diagnostics / health reporting */
    App_Diag_1000ms();
}

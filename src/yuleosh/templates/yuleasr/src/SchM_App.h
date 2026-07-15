/**
 * @file SchM_App.h
 * @brief Schedule Manager header — application-level scheduling.
 *
 * Coordinates runnable entity execution timing.
 * In production, this would be generated from AUTOSAR timing
 * events (TimingEvent in SW-C ARXML).
 */

#ifndef SCHM_APP_H
#define SCHM_APP_H

#include "Std_Types.h"

/* ─── SchM API ────────────────────────────────────────────── */

/**
 * @brief Initialize the schedule manager.
 */
void SchM_Init(void);

/**
 * @brief Main function — called from the OS tick or main loop.
 *
 * Dispatches runnable entities according to their configured
 * timing events (1ms, 10ms, 100ms, 1000ms base cycles).
 */
void SchM_MainFunction(void);

/**
 * @brief 10ms schedule group.
 */
void SchM_App_10ms(void);

/**
 * @brief 100ms schedule group.
 */
void SchM_App_100ms(void);

/**
 * @brief 1000ms schedule group.
 */
void SchM_App_1000ms(void);

/* ─── Inline Helper ───────────────────────────────────────── */

static inline void SchM_Init(void)
{
    /* Initialize scheduling state */
}

#endif /* SCHM_APP_H */

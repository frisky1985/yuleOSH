/**
 * @file timer_mock.h
 * @brief STM32 HAL Timer mock — records calls, simulates time.
 *
 * Implements: HAL_TIM_Base_Start, HAL_TIM_Base_Stop, HAL_GetTick,
 *             HAL_TIM_PeriodElapsedCallback (weak default)
 *
 * License: MIT
 */

#ifndef HAL_MOCK_TIMER_H
#define HAL_MOCK_TIMER_H

#include "mock_core.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

extern uint64_t _mock_timer_ticks;   /* monotonic ms counter   */
extern bool     _mock_timer_running; /* is the timer started?  */

/* ------------------------------------------------------------------ */
/*  STM32 HAL type stubs                                               */
/* ------------------------------------------------------------------ */

typedef struct {
    uint32_t Instance;
} TIM_TypeDefiant;

typedef struct {
    TIM_TypeDefiant *Instance;
    uint32_t         Prescaler;
    uint32_t         Period;
} TIM_HandleTypeDef;

/* ------------------------------------------------------------------ */
/*  STM32 HAL API — mock implementations                               */
/* ------------------------------------------------------------------ */

#undef  HAL_TIM_Base_Start
#define HAL_TIM_Base_start(htim)                        _hal_tim_base_start_mock(htim)
#undef  HAL_TIM_Base_Stop
#define HAL_TIM_Base_Stop(htim)                         _hal_tim_base_stop_mock(htim)
#undef  HAL_GetTick
#define HAL_GetTick()                                   _mock_timer_ticks

static inline void _hal_tim_base_start_mock(TIM_HandleTypeDef *htim) {
    (void)htim;
    _mock_timer_running = true;
    mock_record("HAL_TIM_Base_Start", "");
}

static inline void _hal_tim_base_stop_mock(TIM_HandleTypeDef *htim) {
    (void)htim;
    _mock_timer_running = false;
    mock_record("HAL_TIM_Base_Stop", "");
}

/* Simulate time passage for testing delay / timeout logic */
static inline void mock_timer_elapse(uint32_t ms) {
    _mock_timer_ticks += ms;
}

#ifdef __cplusplus
}
#endif

#endif /* HAL_MOCK_TIMER_H */

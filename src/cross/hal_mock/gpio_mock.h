/**
 * @file gpio_mock.h
 * @brief STM32 HAL GPIO mock — records pin-state for host-side testing.
 *
 * Implements: HAL_GPIO_WritePin, HAL_GPIO_ReadPin, HAL_GPIO_TogglePin,
 *             HAL_GPIO_Init, HAL_GPIO_DeInit
 *
 * License: MIT
 */

#ifndef HAL_MOCK_GPIO_H
#define HAL_MOCK_GPIO_H

#include "mock_core.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

#define MOCK_GPIO_PIN_COUNT 16
extern uint8_t _mock_gpio_pins[MOCK_GPIO_PIN_COUNT]; /* 0=low, 1=high */

/* ------------------------------------------------------------------ */
/*  STM32 HAL type stubs                                               */
/* ------------------------------------------------------------------ */

typedef struct { uint32_t Reserved; } GPIO_TypeDef;
typedef enum   { GPIO_PIN_RESET = 0, GPIO_PIN_SET = 1 } GPIO_PinState;
typedef uint32_t GPIO_Pin; /* Bitmask: GPIO_PIN_0 .. GPIO_PIN_15 */

/* ------------------------------------------------------------------ */
/*  STM32 HAL API — mock implementations                               */
/* ------------------------------------------------------------------ */

#undef  HAL_GPIO_WritePin
#define HAL_GPIO_WritePin(GPIOx, GPIO_Pin, PinState)    \
    _hal_gpio_writepin_mock(GPIOx, GPIO_Pin, PinState)

#undef  HAL_GPIO_ReadPin
#define HAL_GPIO_ReadPin(GPIOx, GPIO_Pin)               \
    _hal_gpio_readpin_mock(GPIOx, GPIO_Pin)

#undef  HAL_GPIO_TogglePin
#define HAL_GPIO_TogglePin(GPIOx, GPIO_Pin)             \
    _hal_gpio_togglepin_mock(GPIOx, GPIO_Pin)

static inline void
_hal_gpio_writepin_mock(GPIO_TypeDef *GPIOx, uint16_t pin_mask, GPIO_PinState state) {
    (void)GPIOx;
    for (int i = 0; i < MOCK_GPIO_PIN_COUNT; i++) {
        if (pin_mask & (1u << i)) _mock_gpio_pins[i] = (uint8_t)state;
    }
    char args[64];
    snprintf(args, sizeof(args), "GPIOx=%p, Pin=0x%04x, State=%s",
             (void*)GPIOx, pin_mask, state == GPIO_PIN_SET ? "SET" : "RESET");
    mock_record("HAL_GPIO_WritePin", "%s", args);
}

static inline GPIO_PinState
_hal_gpio_readpin_mock(GPIO_TypeDef *GPIOx, uint16_t pin_mask) {
    (void)GPIOx;
    GPIO_PinState result = GPIO_PIN_RESET;
    for (int i = 0; i < MOCK_GPIO_PIN_COUNT; i++) {
        if (pin_mask & (1u << i) && _mock_gpio_pins[i]) result = GPIO_PIN_SET;
    }
    char args[48];
    snprintf(args, sizeof(args), "GPIOx=%p, Pin=0x%04x", (void*)GPIOx, pin_mask);
    mock_record("HAL_GPIO_ReadPin", "%s", args);
    return result;
}

static inline void
_hal_gpio_togglepin_mock(GPIO_TypeDef *GPIOx, uint16_t pin_mask) {
    (void)GPIOx;
    for (int i = 0; i < MOCK_GPIO_PIN_COUNT; i++) {
        if (pin_mask & (1u << i)) _mock_gpio_pins[i] = !_mock_gpio_pins[i];
    }
    char args[48];
    snprintf(args, sizeof(args), "GPIOx=%p, Pin=0x%04x", (void*)GPIOx, pin_mask);
    mock_record("HAL_GPIO_TogglePin", "%s", args);
}

#ifdef __cplusplus
}
#endif

#endif /* HAL_MOCK_GPIO_H */

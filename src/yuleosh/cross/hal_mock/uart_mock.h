/**
 * @file uart_mock.h
 * @brief STM32 HAL UART mock — records calls for host-side testing.
 *
 * Implements: HAL_UART_Transmit, HAL_UART_Receive, HAL_UART_Abort
 *
 * License: MIT
 */

#ifndef HAL_MOCK_UART_H
#define HAL_MOCK_UART_H

#include "mock_core.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

/* Ring buffer of received bytes (firmware → mock via HAL_UART_Receive) */
#define MOCK_UART_RX_BUF 1024
extern uint8_t  _mock_uart_rx_data[MOCK_UART_RX_BUF];
extern uint32_t _mock_uart_rx_len;

/* Pre-loaded TX data the test provides so HAL_UART_Transmit reads match */
#define MOCK_UART_TX_BUF 1024
extern uint8_t  _mock_uart_tx_data[MOCK_UART_TX_BUF];
extern uint32_t _mock_uart_tx_len;

/* ------------------------------------------------------------------ */
/*  STM32 HAL type stubs                                               */
/* ------------------------------------------------------------------ */

typedef enum { UART_OK = 0, UART_ERROR = 1, UART_BUSY = 2, UART_TIMEOUT = 3 } HAL_UART_StatusTypeDef;
typedef struct { uint32_t Instance; } USART_TypeDefiant;
typedef struct {
    USART_TypeDefiant *Instance;
    uint32_t          BaudRate;
    uint8_t           WordLength;
    uint8_t           StopBits;
    uint8_t           Parity;
} UART_HandleTypeDef;

/* ------------------------------------------------------------------ */
/*  Mock wrappers (call these in test code)                            */
/* ------------------------------------------------------------------ */

static inline void mock_uart_set_rx_data(const uint8_t *data, uint32_t len) {
    if (len > MOCK_UART_RX_BUF) len = MOCK_UART_RX_BUF;
    memcpy(_mock_uart_rx_data, data, len);
    _mock_uart_rx_len = len;
}

static inline int mock_assert_uart_transmit(const char *expected) {
    for (uint32_t i = 0; i < _mock_call_count; i++) {
        if (strcmp(_mock_call_log[i].name, "HAL_UART_Transmit") == 0) {
            if (strstr(_mock_call_log[i].args, expected)) return 0;
        }
    }
    fprintf(stderr, "[MOCK FAIL] UART_Transmit: expected output containing '%s' not found\n", expected);
    return 1;
}

/* ------------------------------------------------------------------ */
/*  STM32 HAL API implementations (link these in host test builds)     */
/* ------------------------------------------------------------------ */

#undef  HAL_UART_Transmit
#define HAL_UART_Transmit(huart, pData, Size, Timeout)  \
    _hal_uart_transmit_mock(huart, pData, Size, Timeout)

#undef  HAL_UART_Receive
#define HAL_UART_Receive(huart, pData, Size, Timeout)   \
    _hal_uart_receive_mock(huart, pData, Size, Timeout)

#undef  HAL_UART_Abort
#define HAL_UART_Abort(huart)                           \
    _hal_uart_abort_mock(huart)

/* These are defined in the .c companion or inline below */
static inline HAL_UART_StatusTypeDef
_hal_uart_transmit_mock(UART_HandleTypeDef *huart, const uint8_t *pData, uint16_t Size, uint32_t Timeout) {
    (void)huart; (void)Timeout;
    char args[128];
    snprintf(args, sizeof(args), "pData=\"%.*s\", Size=%u", (int)Size, (const char*)pData, Size);
    mock_record("HAL_UART_Transmit", "%s", args);
    return UART_OK;
}

static inline HAL_UART_StatusTypeDef
_hal_uart_receive_mock(UART_HandleTypeDef *huart, uint8_t *pData, uint16_t Size, uint32_t Timeout) {
    (void)huart; (void)Timeout;
    uint32_t copy = Size < _mock_uart_rx_len ? Size : _mock_uart_rx_len;
    memcpy(pData, _mock_uart_rx_data, copy);
    if (copy < Size) memset(pData + copy, 0, Size - copy);
    char args[64];
    snprintf(args, sizeof(args), "Size=%u", Size);
    mock_record("HAL_UART_Receive", "%s", args);
    return UART_OK;
}

static inline HAL_UART_StatusTypeDef
_hal_uart_abort_mock(UART_HandleTypeDef *huart) {
    (void)huart;
    mock_record("HAL_UART_Abort", "");
    return UART_OK;
}

#ifdef __cplusplus
}
#endif

#endif /* HAL_MOCK_UART_H */

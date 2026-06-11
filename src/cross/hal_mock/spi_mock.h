/**
 * @file spi_mock.h
 * @brief STM32 HAL SPI mock — records transactions for host-side testing.
 *
 * Implements: HAL_SPI_Transmit, HAL_SPI_Receive, HAL_SPI_TransmitReceive
 *
 * License: MIT
 */

#ifndef HAL_MOCK_SPI_H
#define HAL_MOCK_SPI_H

#include "mock_core.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

#define MOCK_SPI_RX_BUF 256
extern uint8_t  _mock_spi_rx_data[MOCK_SPI_RX_BUF];
extern uint32_t _mock_spi_rx_len;

/* ------------------------------------------------------------------ */
/*  STM32 HAL type stubs                                               */
/* ------------------------------------------------------------------ */

typedef enum { SPI_OK = 0, SPI_ERROR = 1, SPI_BUSY = 2, SPI_TIMEOUT = 3 } HAL_SPI_StatusTypeDef;
typedef struct { uint32_t Instance; } SPI_TypeDefiant;
typedef struct {
    SPI_TypeDefiant *Instance;
    uint32_t         InitMode;
    uint32_t         InitDirection;
    uint32_t         InitDataSize;
} SPI_HandleTypeDef;

/* ------------------------------------------------------------------ */
/*  Test helpers                                                       */
/* ------------------------------------------------------------------ */

static inline void mock_spi_set_rx_data(const uint8_t *data, uint32_t len) {
    if (len > MOCK_SPI_RX_BUF) len = MOCK_SPI_RX_BUF;
    memcpy(_mock_spi_rx_data, data, len);
    _mock_spi_rx_len = len;
}

/* ------------------------------------------------------------------ */
/*  STM32 HAL API — mock implementations                               */
/* ------------------------------------------------------------------ */

#undef  HAL_SPI_Transmit
#define HAL_SPI_Transmit(hspi, pData, Size, Timeout)       \
    _hal_spi_transmit_mock(hspi, pData, Size, Timeout)

#undef  HAL_SPI_Receive
#define HAL_SPI_Receive(hspi, pData, Size, Timeout)        \
    _hal_spi_receive_mock(hspi, pData, Size, Timeout)

#undef  HAL_SPI_TransmitReceive
#define HAL_SPI_TransmitReceive(hspi, pTxData, pRxData, Size, Timeout) \
    _hal_spi_transmitreceive_mock(hspi, pTxData, pRxData, Size, Timeout)

static inline HAL_SPI_StatusTypeDef
_hal_spi_transmit_mock(SPI_HandleTypeDef *hspi, const uint8_t *pData, uint16_t Size, uint32_t Timeout) {
    (void)hspi; (void)Timeout;
    char args[128];
    snprintf(args, sizeof(args), "Size=%u, Data=\"%.*s\"", Size, (int)Size, (const char*)pData);
    mock_record("HAL_SPI_Transmit", "%s", args);
    return SPI_OK;
}

static inline HAL_SPI_StatusTypeDef
_hal_spi_receive_mock(SPI_HandleTypeDef *hspi, uint8_t *pData, uint16_t Size, uint32_t Timeout) {
    (void)hspi; (void)Timeout;
    uint32_t copy = Size < _mock_spi_rx_len ? Size : _mock_spi_rx_len;
    memcpy(pData, _mock_spi_rx_data, copy);
    char args[48];
    snprintf(args, sizeof(args), "Size=%u", Size);
    mock_record("HAL_SPI_Receive", "%s", args);
    return SPI_OK;
}

static inline HAL_SPI_StatusTypeDef
_hal_spi_transmitreceive_mock(SPI_HandleTypeDef *hspi, const uint8_t *pTxData,
                               uint8_t *pRxData, uint16_t Size, uint32_t Timeout) {
    (void)hspi; (void)Timeout;
    uint32_t copy = Size < _mock_spi_rx_len ? Size : _mock_spi_rx_len;
    if (pRxData) memcpy(pRxData, _mock_spi_rx_data, copy);
    char args[96];
    snprintf(args, sizeof(args), "Size=%u, TX=\"%.*s\"", Size, (int)Size, (const char*)pTxData);
    mock_record("HAL_SPI_TransmitReceive", "%s", args);
    return SPI_OK;
}

#ifdef __cplusplus
}
#endif

#endif /* HAL_MOCK_SPI_H */

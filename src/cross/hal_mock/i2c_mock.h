/**
 * @file i2c_mock.h
 * @brief STM32 HAL I2C mock — records transactions for host-side testing.
 *
 * Implements: HAL_I2C_Master_Transmit, HAL_I2C_Master_Receive,
 *             HAL_I2C_Mem_Write, HAL_I2C_Mem_Read
 *
 * License: MIT
 */

#ifndef HAL_MOCK_I2C_H
#define HAL_MOCK_I2C_H

#include "mock_core.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/*  Mock state                                                         */
/* ------------------------------------------------------------------ */

#define MOCK_I2C_RX_BUF 256
extern uint8_t  _mock_i2c_rx_data[MOCK_I2C_RX_BUF];
extern uint32_t _mock_i2c_rx_len;

/* ------------------------------------------------------------------ */
/*  STM32 HAL type stubs                                               */
/* ------------------------------------------------------------------ */

typedef enum { I2C_OK = 0, I2C_ERROR = 1, I2C_BUSY = 2, I2C_TIMEOUT = 3 } HAL_I2C_StatusTypeDef;
typedef struct { uint32_t Instance; } I2C_TypeDefiant;
typedef struct {
    I2C_TypeDefiant *Instance;
    uint32_t         Timing;
} I2C_HandleTypeDef;

/* ------------------------------------------------------------------ */
/*  Test helpers                                                       */
/* ------------------------------------------------------------------ */

static inline void mock_i2c_set_rx_data(uint16_t dev_addr, const uint8_t *data, uint32_t len) {
    (void)dev_addr;
    if (len > MOCK_I2C_RX_BUF) len = MOCK_I2C_RX_BUF;
    memcpy(_mock_i2c_rx_data, data, len);
    _mock_i2c_rx_len = len;
}

/* ------------------------------------------------------------------ */
/*  STM32 HAL API — mock implementations                               */
/* ------------------------------------------------------------------ */

#undef  HAL_I2C_Master_Transmit
#define HAL_I2C_Master_Transmit(hi2c, DevAddress, pData, Size, Timeout)  \
    _hal_i2c_master_transmit_mock(hi2c, DevAddress, pData, Size, Timeout)

#undef  HAL_I2C_Master_Receive
#define HAL_I2C_Master_Receive(hi2c, DevAddress, pData, Size, Timeout)   \
    _hal_i2c_master_receive_mock(hi2c, DevAddress, pData, Size, Timeout)

#undef  HAL_I2C_Mem_Write
#define HAL_I2C_Mem_Write(hi2c, DevAddress, MemAddress, MemAddSize, pData, Size, Timeout) \
    _hal_i2c_mem_write_mock(hi2c, DevAddress, MemAddress, MemAddSize, pData, Size, Timeout)

#undef  HAL_I2C_Mem_Read
#define HAL_I2C_Mem_Read(hi2c, DevAddress, MemAddress, MemAddSize, pData, Size, Timeout)  \
    _hal_i2c_mem_read_mock(hi2c, DevAddress, MemAddress, MemAddSize, pData, Size, Timeout)

static inline HAL_I2C_StatusTypeDef
_hal_i2c_master_transmit_mock(I2C_HandleTypeDef *hi2c, uint16_t DevAddress,
                               const uint8_t *pData, uint16_t Size, uint32_t Timeout) {
    (void)hi2c; (void)Timeout;
    char args[128];
    snprintf(args, sizeof(args), "DevAddr=0x%02x, Size=%u, Data=\"%.*s\"",
             DevAddress, Size, (int)Size, (const char*)pData);
    mock_record("HAL_I2C_Master_Transmit", "%s", args);
    return I2C_OK;
}

static inline HAL_I2C_StatusTypeDef
_hal_i2c_master_receive_mock(I2C_HandleTypeDef *hi2c, uint16_t DevAddress,
                              uint8_t *pData, uint16_t Size, uint32_t Timeout) {
    (void)hi2c; (void)Timeout;
    uint32_t copy = Size < _mock_i2c_rx_len ? Size : _mock_i2c_rx_len;
    memcpy(pData, _mock_i2c_rx_data, copy);
    char args[64];
    snprintf(args, sizeof(args), "DevAddr=0x%02x, Size=%u", DevAddress, Size);
    mock_record("HAL_I2C_Master_Receive", "%s", args);
    return I2C_OK;
}

static inline HAL_I2C_StatusTypeDef
_hal_i2c_mem_write_mock(I2C_HandleTypeDef *hi2c, uint16_t DevAddress,
                         uint16_t MemAddress, uint16_t MemAddSize,
                         const uint8_t *pData, uint16_t Size, uint32_t Timeout) {
    (void)hi2c; (void)Timeout;
    char args[128];
    snprintf(args, sizeof(args), "DevAddr=0x%02x, MemAddr=0x%04x, Size=%u",
             DevAddress, MemAddress, Size);
    mock_record("HAL_I2C_Mem_Write", "%s", args);
    return I2C_OK;
}

static inline HAL_I2C_StatusTypeDef
_hal_i2c_mem_read_mock(I2C_HandleTypeDef *hi2c, uint16_t DevAddress,
                        uint16_t MemAddress, uint16_t MemAddSize,
                        uint8_t *pData, uint16_t Size, uint32_t Timeout) {
    (void)hi2c; (void)Timeout;
    uint32_t copy = Size < _mock_i2c_rx_len ? Size : _mock_i2c_rx_len;
    memcpy(pData, _mock_i2c_rx_data, copy);
    char args[64];
    snprintf(args, sizeof(args), "DevAddr=0x%02x, MemAddr=0x%04x, Size=%u",
             DevAddress, MemAddress, Size);
    mock_record("HAL_I2C_Mem_Read", "%s", args);
    return I2C_OK;
}

#ifdef __cplusplus
}
#endif

#endif /* HAL_MOCK_I2C_H */

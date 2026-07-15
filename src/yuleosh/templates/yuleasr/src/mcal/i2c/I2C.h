/**
 * @file I2C.h
 * @brief I2C Driver — Master/slave synchronous serial
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full I2C driver is integrated.
 */

#ifndef I2C_H
#define I2C_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief I2C configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} I2C_ConfigType;

typedef uint8_t I2c_ChannelType;

typedef uint8_t I2c_StatusType;
#define I2C_IDLE  0x00U
#define I2C_BUSY  0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType I2c_Init(const I2c_ConfigType *ConfigPtr);

extern Std_ReturnType I2c_DeInit(void);

extern void I2c_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType I2c_MasterTransmit(I2c_ChannelType Channel, uint16_t SlaveAddr, const uint8_t *TxData, uint16_t Length);

extern Std_ReturnType I2c_MasterReceive(I2c_ChannelType Channel, uint16_t SlaveAddr, uint8_t *RxData, uint16_t Length);

extern Std_ReturnType I2c_SlaveTransmit(I2c_ChannelType Channel, const uint8_t *TxData, uint16_t Length);

extern Std_ReturnType I2c_SlaveReceive(I2c_ChannelType Channel, uint8_t *RxData, uint16_t Length);

extern I2c_StatusType I2c_GetStatus(I2c_ChannelType Channel);

#ifdef __cplusplus
}
#endif

#endif /* I2C_H */

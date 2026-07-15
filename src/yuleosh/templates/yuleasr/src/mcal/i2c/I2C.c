/**
 * @file I2C.c
 * @brief I2C Driver — Master/slave synchronous serial
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "I2C.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t I2C_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief I2c_Init — stub implementation */
Std_ReturnType I2c_Init(const I2c_ConfigType *ConfigPtr)
{
    I2C_Initialized = 1U;
    return E_OK;
}

/** @brief I2c_DeInit — stub implementation */
Std_ReturnType I2c_DeInit(void)
{
    I2C_Initialized = 0U;
    return E_OK;
}

/** @brief I2c_GetVersionInfo — stub implementation */
void I2c_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
{
    /* Stub — no operation */
}

/** @brief I2c_MasterTransmit — stub implementation */
Std_ReturnType I2c_MasterTransmit(I2c_ChannelType Channel, uint16_t SlaveAddr, const uint8_t *TxData, uint16_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief I2c_MasterReceive — stub implementation */
Std_ReturnType I2c_MasterReceive(I2c_ChannelType Channel, uint16_t SlaveAddr, uint8_t *RxData, uint16_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief I2c_SlaveTransmit — stub implementation */
Std_ReturnType I2c_SlaveTransmit(I2c_ChannelType Channel, const uint8_t *TxData, uint16_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief I2c_SlaveReceive — stub implementation */
Std_ReturnType I2c_SlaveReceive(I2c_ChannelType Channel, uint8_t *RxData, uint16_t Length)
{
    /* Stub — returning default */
    return E_NOT_OK;
}

/** @brief I2c_GetStatus — stub implementation */
I2c_StatusType I2c_GetStatus(I2c_ChannelType Channel)
{
    /* Stub — returning default */
    return I2C_IDLE;
}

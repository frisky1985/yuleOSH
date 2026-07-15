/**
 * @file Uart.c
 * @brief UART Driver — Asynchronous serial (SCI/LIN-capable)
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Uart.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t UART_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Uart_Init — stub implementation */
Std_ReturnType Uart_Init(const Uart_ConfigType *ConfigPtr)
{
    UART_Initialized = 1U;
    return E_OK;
}

/** @brief Uart_DeInit — stub implementation */
Std_ReturnType Uart_DeInit(void)
{
    UART_Initialized = 0U;
    return E_OK;
}

/** @brief Uart_GetVersionInfo — stub implementation */
void Uart_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
{
    /* Stub — no version info available */
    if (VersionInfoPtr != NULL_PTR)
    {
        VersionInfoPtr->vendorID = 0U;
        VersionInfoPtr->moduleID = 0U;
        VersionInfoPtr->sw_major_version = 0U;
        VersionInfoPtr->sw_minor_version = 0U;
        VersionInfoPtr->sw_patch_version = 0U;
    }
}

/** @brief Uart_Write — stub implementation */
Std_ReturnType Uart_Write(Uart_ChannelType Channel, const uint8_t *TxData, uint16_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Uart_Read — stub implementation */
Std_ReturnType Uart_Read(Uart_ChannelType Channel, uint8_t *RxData, uint16_t Length)
{
    /* Stub — returning default */
    return E_NOT_OK;
}

/** @brief Uart_SetBaudrate — stub implementation */
Std_ReturnType Uart_SetBaudrate(Uart_ChannelType Channel, uint32_t Baudrate)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Uart_GetStatus — stub implementation */
Uart_StatusType Uart_GetStatus(Uart_ChannelType Channel)
{
    /* Stub — returning default */
    return UART_IDLE;
}

/** @brief Uart_EnableInterrupt — stub implementation */
Std_ReturnType Uart_EnableInterrupt(Uart_ChannelType Channel, Uart_InterruptType Interrupt)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Uart_DisableInterrupt — stub implementation */
Std_ReturnType Uart_DisableInterrupt(Uart_ChannelType Channel, Uart_InterruptType Interrupt)
{
    /* Stub — returning default */
    return E_OK;
}

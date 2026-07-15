/**
 * @file Uart.h
 * @brief UART Driver — Asynchronous serial (SCI/LIN-capable)
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Uart driver is integrated.
 */

#ifndef UART_H
#define UART_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Uart configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Uart_ConfigType;

typedef uint8_t Uart_ChannelType;

typedef uint8_t Uart_StatusType;
#define UART_IDLE  0x00U
#define UART_BUSY  0x01U

typedef uint8_t Uart_InterruptType;
#define UART_INT_TX  0x01U
#define UART_INT_RX  0x02U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Uart_Init(const Uart_ConfigType *ConfigPtr);

extern Std_ReturnType Uart_DeInit(void);

extern void Uart_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Uart_Write(Uart_ChannelType Channel, const uint8_t *TxData, uint16_t Length);

extern Std_ReturnType Uart_Read(Uart_ChannelType Channel, uint8_t *RxData, uint16_t Length);

extern Std_ReturnType Uart_SetBaudrate(Uart_ChannelType Channel, uint32_t Baudrate);

extern Uart_StatusType Uart_GetStatus(Uart_ChannelType Channel);

extern Std_ReturnType Uart_EnableInterrupt(Uart_ChannelType Channel, Uart_InterruptType Interrupt);

extern Std_ReturnType Uart_DisableInterrupt(Uart_ChannelType Channel, Uart_InterruptType Interrupt);

#ifdef __cplusplus
}
#endif

#endif /* UART_H */

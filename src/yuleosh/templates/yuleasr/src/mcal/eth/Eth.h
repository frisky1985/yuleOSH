/**
 * @file Eth.h
 * @brief Ethernet Driver — SGMII/RMII 100Mbps/1Gbps
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Eth driver is integrated.
 */

#ifndef ETH_H
#define ETH_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Eth configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Eth_ConfigType;

typedef struct { uint8_t *data; uint16_t length; uint16_t reserved; } Eth_FrameType;

typedef uint8_t Eth_ModeType;
#define ETH_MODE_DOWN    0x00U
#define ETH_MODE_ACTIVE  0x01U

typedef uint16_t Eth_BufIdxType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Eth_Init(const Eth_ConfigType *ConfigPtr);

extern Std_ReturnType Eth_DeInit(void);

extern void Eth_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Eth_Write(uint32_t Controller, const Eth_FrameType *FramePtr);

extern Std_ReturnType Eth_Read(uint32_t Controller, Eth_FrameType *FramePtr);

extern Std_ReturnType Eth_SetControllerMode(uint32_t Controller, Eth_ModeType Mode);

extern Eth_ModeType Eth_GetControllerMode(uint32_t Controller);

extern Std_ReturnType Eth_ProvideTxBuffer(uint32_t Controller, Eth_BufIdxType BufIdx, uint8_t **BufferPtr, Eth_FrameType *FramePtr);

extern uint16_t Eth_GetTxErrorCounter(uint32_t Controller);

#ifdef __cplusplus
}
#endif

#endif /* ETH_H */

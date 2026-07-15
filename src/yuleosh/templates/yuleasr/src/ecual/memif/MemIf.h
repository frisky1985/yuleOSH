/**
 * @file MemIf.h
 * @brief Memory Abstraction Interface — NvM abstraction over Fee/Ea
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full MemIf driver is integrated.
 */

#ifndef MEMIF_H
#define MEMIF_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief MemIf configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} MemIf_ConfigType;

typedef uint16_t MemIf_BlockIdType;

typedef uint8_t MemIf_StatusType;
#define MEMIF_IDLE  0x00U
#define MEMIF_BUSY  0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType MemIf_Init(void);

extern Std_ReturnType MemIf_DeInit(void);

extern void MemIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType MemIf_Read(MemIf_BlockIdType BlockId, uint16_t BlockOffset, uint8_t *DataBufferPtr, uint16_t Length);

extern Std_ReturnType MemIf_Write(MemIf_BlockIdType BlockId, const uint8_t *DataBufferPtr);

extern Std_ReturnType MemIf_EraseImmediate(MemIf_BlockIdType BlockId);

extern MemIf_StatusType MemIf_GetStatus(void);

extern void MemIf_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* MEMIF_H */

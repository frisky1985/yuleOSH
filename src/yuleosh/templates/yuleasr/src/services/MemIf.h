/**
 * @file MemIf.h
 * @brief Memory Abstraction Interface — Unified memory service abstraction (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef MEMIF_SV_H
#define MEMIF_SV_H

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

typedef uint8_t MemIf_StatusType;
#define MEMIF_IDLE       0x00U
#define MEMIF_BUSY       0x01U
#define MEMIF_BUSY_INTERNAL 0x02U

typedef uint8_t MemIf_JobResultType;
#define MEMIF_JOB_OK        0x00U
#define MEMIF_JOB_FAILED    0x01U
#define MEMIF_JOB_PENDING   0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType MemIf_Init(void);
extern Std_ReturnType MemIf_DeInit(void);
extern void MemIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType MemIf_Read(uint8_t ModuleRef, uint8_t BlockNum, uint16_t BlockOffset, uint8_t *DataBufferPtr, uint16_t Length);
extern Std_ReturnType MemIf_Write(uint8_t ModuleRef, uint8_t BlockNum, const uint8_t *DataBufferPtr);
extern MemIf_StatusType MemIf_GetStatus(uint8_t ModuleRef);
extern void MemIf_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* MEMIF_SV_H */

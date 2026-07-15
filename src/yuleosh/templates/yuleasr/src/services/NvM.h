/**
 * @file NvM.h
 * @brief NVRAM Manager — Non-volatile data block management
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef NVM_H
#define NVM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief NvM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} NvM_ConfigType;

typedef uint16_t NvM_BlockIdType;
typedef uint8_t NvM_RequestResultType;
#define NVM_REQ_OK        0x00U
#define NVM_REQ_NOT_OK    0x01U
#define NVM_REQ_PENDING   0x02U

typedef uint8_t NvM_OpStatusType;
#define NVM_OP_IDLE    0x00U
#define NVM_OP_WRITE   0x01U
#define NVM_OP_READ    0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType NvM_Init(void);
extern Std_ReturnType NvM_DeInit(void);
extern void NvM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType NvM_ReadBlock(NvM_BlockIdType BlockId, uint8_t *DataBufferPtr);
extern Std_ReturnType NvM_WriteBlock(NvM_BlockIdType BlockId, const uint8_t *DataBufferPtr);
extern Std_ReturnType NvM_CancelWriteJob(NvM_BlockIdType BlockId);
extern void NvM_MainFunction(void);
extern void NvM_JobEndNotification(NvM_BlockIdType BlockId);
extern void NvM_JobErrorNotification(NvM_BlockIdType BlockId);
#ifdef __cplusplus
}
#endif

#endif /* NVM_H */

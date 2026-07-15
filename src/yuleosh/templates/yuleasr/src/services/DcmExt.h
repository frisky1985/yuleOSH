/**
 * @file DcmExt.h
 * @brief DCM Extension — Extended diagnostic request processing
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef DCMEXT_H
#define DCMEXT_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief DcmExt configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} DcmExt_ConfigType;

typedef uint8_t DcmExt_ExtSessionType;
#define DCMEXT_EXT_DEFAULT     0x01U
#define DCMEXT_EXT_EXTENDED    0x02U
#define DCMEXT_EXT_PROGRAMMING 0x03U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType DcmExt_Init(void);
extern Std_ReturnType DcmExt_DeInit(void);
extern void DcmExt_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType DcmExt_ProcessExtRequest(const uint8_t *ReqData, uint16_t ReqLen, uint8_t *RespData, uint16_t *RespLen);
extern Std_ReturnType DcmExt_ControlExtSession(DcmExt_ExtSessionType Session);
extern void DcmExt_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* DCMEXT_H */

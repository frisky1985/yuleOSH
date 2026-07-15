/**
 * @file ObdDcm.h
 * @brief OBD Diagnostic Manager — On-Board Diagnostics II (OBD-II) service handler
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef OBDDCM_H
#define OBDDCM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief ObdDcm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} ObdDcm_ConfigType;

typedef uint8_t ObdDcm_MIDType;
#define OBDDCM_MID_0  0x00U
#define OBDDCM_MID_1  0x01U

typedef uint8_t ObdDcm_ServiceType;
#define OBDDCM_SVC_MONITOR   0x01U
#define OBDDCM_SVC_DATA      0x02U
#define OBDDCM_SVC_FREEZE    0x03U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType ObdDcm_Init(void);
extern Std_ReturnType ObdDcm_DeInit(void);
extern void ObdDcm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType ObdDcm_ProcessOBDRequest(uint8_t ServiceId, const uint8_t *Data, uint16_t Len, uint8_t *Resp, uint16_t *RespLen);
extern void ObdDcm_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* OBDDCM_H */

/**
 * @file J1939Rm.h
 * @brief J1939 Request Manager — J1939 request/response protocol handling
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef J1939RM_H
#define J1939RM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief J1939Rm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} J1939Rm_ConfigType;

typedef uint8_t J1939Rm_StateType;
#define J1939RM_STATE_IDLE  0x00U
#define J1939RM_STATE_BUSY  0x01U

typedef uint16_t J1939Rm_PGNType;
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType J1939Rm_Init(void);
extern Std_ReturnType J1939Rm_DeInit(void);
extern void J1939Rm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType J1939Rm_Request(J1939Rm_PGNType PGN, uint8_t SourceAddr);
extern Std_ReturnType J1939Rm_SendResponse(J1939Rm_PGNType PGN, const uint8_t *Data, uint16_t Length);
extern void J1939Rm_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* J1939RM_H */

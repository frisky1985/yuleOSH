/**
 * @file ComM.h
 * @brief Communication Manager — Channel and bus state coordination
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef COMM_H
#define COMM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief ComM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} ComM_ConfigType;

typedef uint8_t ComM_StateType;
#define COMM_NO_COMMUNICATION     0x00U
#define COMM_SILENT_COMMUNICATION 0x01U
#define COMM_FULL_COMMUNICATION   0x02U

typedef uint8_t ComM_UserHandleType;
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType ComM_Init(void);
extern Std_ReturnType ComM_DeInit(void);
extern void ComM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType ComM_RequestComMode(ComM_UserHandleType User, ComM_StateType RequestedMode);
extern ComM_StateType ComM_GetCurrentComMode(uint8_t ChannelId);
extern void ComM_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* COMM_H */

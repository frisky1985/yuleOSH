/**
 * @file BswM.h
 * @brief BSW Mode Manager — Mode arbitration and mode request aggregation
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef BSWM_H
#define BSWM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief BswM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} BswM_ConfigType;

typedef uint8_t BswM_StateType;
#define BSWM_STATE_INIT    0x00U
#define BSWM_STATE_RUNNING 0x01U

typedef uint8_t BswM_ModeType;
#define BSWM_MODE_STARTUP    0x00U
#define BSWM_MODE_RUN        0x01U
#define BSWM_MODE_POST_RUN   0x02U
#define BSWM_MODE_SLEEP      0x03U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType BswM_Init(void);
extern Std_ReturnType BswM_DeInit(void);
extern void BswM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType BswM_RequestMode(BswM_ModeType Mode);
extern BswM_ModeType BswM_GetCurrentMode(void);
extern void BswM_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* BSWM_H */

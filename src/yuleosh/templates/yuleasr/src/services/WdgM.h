/**
 * @file WdgM.h
 * @brief Watchdog Manager — Supervised entity deadline monitoring
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef WDGM_H
#define WDGM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief WdgM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} WdgM_ConfigType;

typedef uint16_t WdgM_SupervisedEntityIdType;
typedef uint8_t WdgM_ModeType;
#define WDGM_MODE_OFF     0x00U
#define WDGM_MODE_SLOW    0x01U
#define WDGM_MODE_FAST    0x02U

typedef uint8_t WdgM_AlarmNotificationType;
#define WDGM_ALARM_DEADLINE_MISSED 0x01U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType WdgM_Init(void);
extern Std_ReturnType WdgM_DeInit(void);
extern void WdgM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType WdgM_SetMode(WdgM_ModeType Mode);
extern Std_ReturnType WdgM_PerformReset(void);
extern void WdgM_AlarmNotification(uint8_t seId);
#ifdef __cplusplus
}
#endif

#endif /* WDGM_H */

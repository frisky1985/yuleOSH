/**
 * @file WdgIf.h
 * @brief Watchdog Interface — Abstraction layer for hardware watchdog drivers (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef WDGIF_SV_H
#define WDGIF_SV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief WdgIf configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} WdgIf_ConfigType;

typedef uint8_t WdgIf_ModeType;
#define WDGIF_OFF_MODE  0x00U
#define WDGIF_SLOW_MODE 0x01U
#define WDGIF_FAST_MODE 0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType WdgIf_Init(void);
extern Std_ReturnType WdgIf_DeInit(void);
extern void WdgIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType WdgIf_SetMode(uint8_t DeviceIndex, WdgIf_ModeType Mode);
extern Std_ReturnType WdgIf_Trigger(uint8_t DeviceIndex);
#ifdef __cplusplus
}
#endif

#endif /* WDGIF_SV_H */

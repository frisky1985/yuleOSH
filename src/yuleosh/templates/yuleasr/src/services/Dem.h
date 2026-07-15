/**
 * @file Dem.h
 * @brief Diagnostic Event Manager — Event storage and fault memory
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef DEM_H
#define DEM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Dem configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Dem_ConfigType;

typedef uint16_t Dem_EventIdType;
typedef uint8_t  Dem_EventStatusType;
#define DEM_EVENT_STATUS_PASSED  0x00U
#define DEM_EVENT_STATUS_FAILED  0x01U

typedef uint8_t Dem_DTCKindType;
#define DEM_DTC_KIND_ALL_DTCS  0x00U
#define DEM_DTC_KIND_EMISSION  0x01U

typedef uint32_t Dem_DTCType;
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Dem_Init(void);
extern Std_ReturnType Dem_DeInit(void);
extern void Dem_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Dem_ReportErrorStatus(Dem_EventIdType EventId, Dem_EventStatusType EventStatus);
extern Dem_EventStatusType Dem_GetEventStatus(Dem_EventIdType EventId);
extern void Dem_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* DEM_H */

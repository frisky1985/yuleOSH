/**
 * @file DemExt.h
 * @brief DEM Extension — Extended event and DTC management
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef DEMEXT_H
#define DEMEXT_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief DemExt configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} DemExt_ConfigType;

typedef uint8_t DemExt_ExtStatusType;
#define DEMEXT_EXT_PASSED       0x00U
#define DEMEXT_EXT_FAILED       0x01U
#define DEMEXT_EXT_PREFAILED    0x02U
#define DEMEXT_EXT_CONFIRMED    0x03U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType DemExt_Init(void);
extern Std_ReturnType DemExt_DeInit(void);
extern void DemExt_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType DemExt_ClearDTC(uint8_t DTCGroup);
extern Std_ReturnType DemExt_GetExtendedStatus(Dem_EventIdType EventId, uint8_t *ExtStatus);
extern void DemExt_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* DEMEXT_H */

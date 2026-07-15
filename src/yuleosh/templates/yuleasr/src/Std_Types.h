/**
 * @file Std_Types.h
 * @brief AUTOSAR Standard Types.
 *
 * Minimal stub for build purposes.
 * In production usage, this is provided by yuleASR.
 */

#ifndef STD_TYPES_H
#define STD_TYPES_H

#include <stdint.h>

/* Boolean */
#ifndef TRUE
#define TRUE  1U
#endif
#ifndef FALSE
#define FALSE 0U
#endif

/* Standard Return Type */
typedef uint8_t Std_ReturnType;
#define E_OK    0U
#define E_NOT_OK  1U

/* Standard Level */
#define STD_HIGH  1U
#define STD_LOW   0U

/* Standard On/Off */
#define STD_ON    1U
#define STD_OFF   0U

/* NULL pointer */
#define NULL_PTR  ((void *)0)

/* AUTOSAR base types */
typedef uint8_t  PduIdType;
typedef uint16_t PduLengthType;

/* NvM types */
typedef uint16_t NvM_BlockIdType;

/* Dem types */
typedef uint8_t  Dem_EventIdType;
#define DEM_EVENT_STATUS_FAILED  0x01U
#define DEM_EVENT_STATUS_PASSED  0x00U

/* Dem_EventStatusType (simplified) */
typedef uint8_t Dem_EventStatusType;

Std_ReturnType Dem_ReportErrorStatus(Dem_EventIdType eventId,
                                     Dem_EventStatusType eventStatus);

/* Dcm types */
typedef uint8_t Dcm_OpStatusType;

/* MCU Mode */
#define MCU_MODE_NORMAL  0x01U

/* OS Application Mode */
#define OSDEFAULTAPPMODE  0x01U

/* WdgM */
#define WDGIF_INSTANCE_ID  0x00U

#endif /* STD_TYPES_H */

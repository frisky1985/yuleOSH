/**
 * @file Adc.h
 * @brief ADC Driver — 12-bit SAR ADC with HW trigger
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Adc driver is integrated.
 */

#ifndef ADC_H
#define ADC_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Adc configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Adc_ConfigType;

typedef uint8_t Adc_GroupType;

typedef uint16_t Adc_ValueGroupType;

typedef uint8_t Adc_GroupStatusType;
#define ADC_NOT_INIT      0x00U
#define ADC_IDLE          0x01U
#define ADC_BUSY          0x02U
#define ADC_COMPLETE      0x03U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Adc_Init(const Adc_ConfigType *ConfigPtr);

extern Std_ReturnType Adc_DeInit(void);

extern void Adc_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Adc_StartGroupConversion(Adc_GroupType Group);

extern Std_ReturnType Adc_StopGroupConversion(Adc_GroupType Group);

extern Std_ReturnType Adc_ReadGroup(Adc_GroupType Group, Adc_ValueGroupType *DataBufferPtr);

extern Adc_GroupStatusType Adc_GetGroupStatus(Adc_GroupType Group);

#ifdef __cplusplus
}
#endif

#endif /* ADC_H */

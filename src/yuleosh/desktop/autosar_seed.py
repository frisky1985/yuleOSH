# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: Elastic-2.0

"""Deterministic AUTOSAR Classic starter code for desktop projects.

The generated example is intentionally small, but keeps the production dependency
rule visible: Application SWC -> RTE -> BSW (Services / ECU Abstraction / MCAL).
Business logic never appears in ``main.c`` and hardware access never leaves MCAL.
"""

from pathlib import Path


_FILES: dict[str, str] = {
    "code/src/common/Std_Types.h": """/* AUTOSAR standard types — shared definitions only. */
#ifndef STD_TYPES_H
#define STD_TYPES_H

#include <stdint.h>

typedef uint8_t uint8;
typedef uint16_t uint16;
typedef uint8_t boolean;
typedef uint8_t Std_ReturnType;

#define TRUE       ((boolean)1U)
#define FALSE      ((boolean)0U)
#define E_OK       ((Std_ReturnType)0U)
#define E_NOT_OK   ((Std_ReturnType)1U)
#define NULL_PTR   ((void *)0)

#endif
""",
    "code/src/rte/Rte_Type.h": """/* AUTOSAR RTE data types shared through ports. */
#ifndef RTE_TYPE_H
#define RTE_TYPE_H

typedef enum {
    HEADLIGHT_OFF = 0U,
    HEADLIGHT_LOW_BEAM = 1U,
    HEADLIGHT_HIGH_BEAM = 2U
} HeadlightBeamMode;

#endif
""",
    "code/src/application/HeadlightSwc.h": """/* @req REQ-001, REQ-002 */
#ifndef HEADLIGHT_SWC_H
#define HEADLIGHT_SWC_H

void HeadlightSwc_Init(void);
void HeadlightSwc_Run(void);

#endif
""",
    "code/src/application/HeadlightSwc.c": """/* @req REQ-001, REQ-002 */
#include "HeadlightSwc.h"
#include "Rte_HeadlightSwc.h"

static HeadlightBeamMode s_beam = HEADLIGHT_LOW_BEAM;

void HeadlightSwc_Init(void)
{
    s_beam = HEADLIGHT_LOW_BEAM;
}

void HeadlightSwc_Run(void)
{
    if (Rte_Read_LightSensor_IsNight() == TRUE) {
        s_beam = (s_beam == HEADLIGHT_LOW_BEAM)
            ? HEADLIGHT_HIGH_BEAM : HEADLIGHT_LOW_BEAM;
        (void)Rte_Write_Headlight_Beam(s_beam);
    } else {
        s_beam = HEADLIGHT_LOW_BEAM;
        (void)Rte_Write_Headlight_Beam(HEADLIGHT_OFF);
    }
}
""",
    "code/src/rte/Rte_HeadlightSwc.h": """/* RTE generated port interface for HeadlightSwc. */
#ifndef RTE_HEADLIGHT_SWC_H
#define RTE_HEADLIGHT_SWC_H

#include "Std_Types.h"
#include "Rte_Type.h"

boolean Rte_Read_LightSensor_IsNight(void);
Std_ReturnType Rte_Write_Headlight_Beam(HeadlightBeamMode mode);

#endif
""",
    "code/src/rte/Rte.h": """/* RTE public entry header — no application business logic. */
#ifndef RTE_H
#define RTE_H

#include "Rte_HeadlightSwc.h"

#endif
""",
    "code/src/rte/Rte.c": """/* RTE port glue: SWC ports are mapped to ECU abstraction APIs. */
#include "Rte.h"
#include "IoHwAb.h"

boolean Rte_Read_LightSensor_IsNight(void)
{
    return IoHwAb_ReadLightSensorIsNight();
}

Std_ReturnType Rte_Write_Headlight_Beam(HeadlightBeamMode mode)
{
    return IoHwAb_WriteHeadlight((uint8)mode);
}
""",
    "code/src/bsw/services/EcuM.h": """/* AUTOSAR service layer: ECU state/startup management. */
#ifndef ECUM_H
#define ECUM_H

void EcuM_Init(void);

#endif
""",
    "code/src/bsw/services/EcuM.c": """/* Service layer delegates board details to ECU abstraction. */
#include "EcuM.h"
#include "IoHwAb.h"

void EcuM_Init(void)
{
    IoHwAb_Init();
}
""",
    "code/src/bsw/ecu_abstraction/IoHwAb.h": """/* ECU abstraction: hides channels and board routing from RTE/services. */
#ifndef IO_HW_AB_H
#define IO_HW_AB_H

#include "Std_Types.h"

void IoHwAb_Init(void);
boolean IoHwAb_ReadLightSensorIsNight(void);
Std_ReturnType IoHwAb_WriteHeadlight(uint8 mode);

#endif
""",
    "code/src/bsw/ecu_abstraction/IoHwAb.c": """/* ECU abstraction accesses hardware only through MCAL APIs. */
#include "IoHwAb.h"
#include "Adc.h"
#include "Dio.h"

#define IOHWAB_LIGHT_CHANNEL        ((uint8)0U)
#define IOHWAB_LOW_BEAM_CHANNEL     ((uint8)0U)
#define IOHWAB_HIGH_BEAM_CHANNEL    ((uint8)1U)
#define IOHWAB_NIGHT_THRESHOLD      ((uint16)100U)

void IoHwAb_Init(void)
{
    Adc_Init();
    Dio_Init();
}

boolean IoHwAb_ReadLightSensorIsNight(void)
{
    uint16 level = 0U;
    if (Adc_ReadChannel(IOHWAB_LIGHT_CHANNEL, &level) != E_OK) {
        return FALSE;
    }
    return (level < IOHWAB_NIGHT_THRESHOLD) ? TRUE : FALSE;
}

Std_ReturnType IoHwAb_WriteHeadlight(uint8 mode)
{
    const uint8 low = (mode == (uint8)1U) ? (uint8)1U : (uint8)0U;
    const uint8 high = (mode == (uint8)2U) ? (uint8)1U : (uint8)0U;

    if (Dio_WriteChannel(IOHWAB_LOW_BEAM_CHANNEL, low) != E_OK) {
        return E_NOT_OK;
    }
    return Dio_WriteChannel(IOHWAB_HIGH_BEAM_CHANNEL, high);
}
""",
    "code/src/bsw/mcal/Adc.h": """/* MCAL ADC driver API — hardware details stay below this interface. */
#ifndef ADC_H
#define ADC_H

#include "Std_Types.h"

void Adc_Init(void);
Std_ReturnType Adc_ReadChannel(uint8 channel, uint16 *value);

#endif
""",
    "code/src/bsw/mcal/Adc.c": """/* MCAL demo stub. Replace the stub with target register access here only. */
#include "Adc.h"

#define ADC_LIGHT_CHANNEL ((uint8)0U)
static uint16 s_light_level = 0U;

void Adc_Init(void)
{
    s_light_level = 0U;
}

Std_ReturnType Adc_ReadChannel(uint8 channel, uint16 *value)
{
    if ((value == NULL_PTR) || (channel != ADC_LIGHT_CHANNEL)) {
        return E_NOT_OK;
    }
    *value = s_light_level;
    return E_OK;
}
""",
    "code/src/bsw/mcal/Dio.h": """/* MCAL DIO driver API. */
#ifndef DIO_H
#define DIO_H

#include "Std_Types.h"

void Dio_Init(void);
Std_ReturnType Dio_WriteChannel(uint8 channel, uint8 level);
uint8 Dio_ReadChannel(uint8 channel);

#endif
""",
    "code/src/bsw/mcal/Dio.c": """/* MCAL demo stub. Target DIO registers must not leak to upper layers. */
#include "Dio.h"

#define DIO_CHANNEL_COUNT ((uint8)2U)
static uint8 s_levels[DIO_CHANNEL_COUNT];

void Dio_Init(void)
{
    s_levels[0] = 0U;
    s_levels[1] = 0U;
}

Std_ReturnType Dio_WriteChannel(uint8 channel, uint8 level)
{
    if (channel >= DIO_CHANNEL_COUNT) {
        return E_NOT_OK;
    }
    s_levels[channel] = level;
    return E_OK;
}

uint8 Dio_ReadChannel(uint8 channel)
{
    if (channel >= DIO_CHANNEL_COUNT) {
        return 0U;
    }
    return s_levels[channel];
}
""",
    "code/src/main.c": """/* AUTOSAR composition root: startup and runnable dispatch only. */
#include "EcuM.h"
#include "HeadlightSwc.h"

int main(void)
{
    EcuM_Init();
    HeadlightSwc_Init();
    HeadlightSwc_Run();
    return 0;
}
""",
    "tests/test_headlight_swc.c": """// @req REQ-001, REQ-002
#include <assert.h>
#include "EcuM.h"
#include "HeadlightSwc.h"
#include "Dio.h"

void test_night_switches_headlight_on(void)
{
    EcuM_Init();
    HeadlightSwc_Init();
    HeadlightSwc_Run();
    assert((Dio_ReadChannel(0U) + Dio_ReadChannel(1U)) > 0U);
}

void test_beam_toggles_between_low_and_high(void)
{
    EcuM_Init();
    HeadlightSwc_Init();
    HeadlightSwc_Run();
    assert(Dio_ReadChannel(0U) == 0U);
    assert(Dio_ReadChannel(1U) == 1U);
    HeadlightSwc_Run();
    assert(Dio_ReadChannel(0U) == 1U);
    assert(Dio_ReadChannel(1U) == 0U);
}

int main(void)
{
    test_night_switches_headlight_on();
    test_beam_toggles_between_low_and_high();
    return 0;
}
""",
}


def seed_autosar_artifacts(project_dir: str | Path) -> list[str]:
    """Write missing AUTOSAR starter files and return their relative paths.

    Existing files are never overwritten: real pipeline output always wins over
    this deterministic baseline.
    """
    root = Path(project_dir)
    for rel_path, content in _FILES.items():
        target = root / rel_path
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return sorted(_FILES)

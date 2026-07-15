/**
 * @file main.c
 * @brief AUTOSAR BSW Application — yuleASR on S32K312
 *
 * Full BSW stack initialization and main loop.
 *
 * Layer structure:
 *   MCAL  → 21 modules (Mcu, Dio, Port, Gpt, Can, ...)
 *   ECUAL → 29 modules (CanIf, CanTp, LinIf, MemIf, ...)
 *   SVC   → 44 modules (Com, Dcm, Dem, NvM, EcuM, BswM, ...)
 *   RTE   → SW-C scheduling
 *   App   → Application SW-Cs
 *
 * Build with:
 *   export YULEASR_HOME=/path/to/yuleASR
 *   make
 */

#include <stdint.h>
#include "Mcu.h"
#include "Port.h"
#include "Dio.h"
#include "Gpt.h"
#include "Can.h"
#include "EcuM.h"
#include "BswM.h"
#include "SchM.h"
#include "Com.h"
#include "ComM.h"
#include "Dem.h"
#include "Dcm.h"
#include "NvM.h"
#include "Det.h"
#include "PduR.h"
#include "CanIf.h"
#include "CanTp.h"
#include "Fee.h"
#include "MemIf.h"
#include "Wdg.h"
#include "WdgM.h"

/* ─── Forward declarations for configuration sets ─────────── */
extern const Mcu_ConfigType  McuConfig;
extern const Port_ConfigType PortConfig;
extern const Dio_ConfigType  DioConfig;
extern const Gpt_ConfigType  GptConfig;
extern const Can_ConfigType  CanConfig;

/* ─── BSW Module Initialization ───────────────────────────── */

static void Bsw_Init(void)
{
    /* Phase 1: Core MCAL — hardware bring-up */
    Mcu_Init(&McuConfig);
    Mcu_SetMode(MCU_MODE_NORMAL);
    Port_Init(&PortConfig);
    Dio_Init(&DioConfig);
    Gpt_Init(&GptConfig);

    /* Phase 2: Communication MCAL */
    Can_Init(&CanConfig);

    /* Phase 3: ECUAL layer */
    CanIf_Init();
    CanTp_Init();
    MemIf_Init();

    /* Phase 4: Services — mode management */
    EcuM_Init();
    BswM_Init();
    ComM_Init();
    Com_Init();
    PduR_Init();

    /* Phase 5: Diagnostics and memory */
    Dem_Init();
    Dcm_Init();
    NvM_Init();
    Fee_Init();

    /* Phase 6: Safety */
    WdgM_Init();
    Det_Init();
}

/* ─── Main Entry Point ────────────────────────────────────── */

int main(void)
{
    Bsw_Init();
    SchM_Init();

    while (1)
    {
        /* Base tick */
        SchM_MainFunction();

        /* Communication stack */
        Can_MainFunction_Read();
        Can_MainFunction_Write();
        CanIf_MainFunction();
        CanTp_MainFunction();
        Com_MainFunction();
        PduR_MainFunction();

        /* Diagnostics */
        Dcm_MainFunction();
        Dem_MainFunction();

        /* Memory */
        NvM_MainFunction();
        Fee_MainFunction();

        /* Watchdog */
        WdgM_PerformReset();
    }

    return 0;
}

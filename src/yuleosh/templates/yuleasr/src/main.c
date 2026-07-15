/**
 * @file main.c
 * @brief yuleASR AUTOSAR BSW Application — S32K312
 *
 * This file demonstrates the initialization sequence and main loop
 * for an AUTOSAR BSW project built on the yuleASR platform.
 *
 * Layer stack (bottom-up):
 *   MCAL  (21 modules)  →  hardware abstraction
 *   ECUAL (29 modules)  →  communication & memory abstraction
 *   Services (44 modules) →  diagnostics, COM, NVM, mode mgmt
 *   RTE   →  SW-C scheduling
 *   App   →  application software components
 */

#include "Mcu.h"
#include "Port.h"
#include "Dio.h"
#include "Gpt.h"
#include "Can.h"
#include "Adc.h"
#include "Spi.h"
#include "Lin.h"
#include "Pwm.h"
#include "Icu.h"
#include "Wdg.h"

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
#include "E2E.h"
#include "Csm.h"
#include "CanIf.h"
#include "CanTp.h"
#include "LinIf.h"
#include "LinTp.h"
#include "MemIf.h"
#include "Fee.h"
#include "WdgM.h"

/* OS (if using AUTOSAR OS */
#include "Os.h"

/* SW-C headers */
#include "App_Swc.h"
#include "Rte_App.h"
#include "SchM_App.h"

/* ─── Static configuration forward declarations ───────────────────── */

extern const Mcu_ConfigType   Mcu_Config;
extern const Port_ConfigType  Port_Config;
extern const Dio_ConfigType   Dio_Config;
extern const Gpt_ConfigType   Gpt_Config;
extern const Can_ConfigType   Can_Config;
extern const Adc_ConfigType   Adc_Config;
extern const Spi_ConfigType   Spi_Config;
extern const Lin_ConfigType   Lin_Config;
extern const Wdg_ConfigType   Wdg_Config;

/* ─── BSW Module Initialization Sequence ──────────────────── */

static void Bsw_InitAll(void)
{
    /*
     * Phase 1: MCU and Port — lowest-level hardware initialization.
     * Order matches AUTOSAR specification: MCU → Port → remaining MCAL.
     */
    Mcu_Init(&Mcu_Config);
    Mcu_SetMode(MCU_MODE_NORMAL);
    Port_Init(&Port_Config);

    /*
     * Phase 2: Core MCAL drivers.
     * GPT must be early for timing services; DIO for basic I/O.
     */
    Gpt_Init(&Gpt_Config);
    Dio_Init(&Dio_Config);

    /*
     * Phase 3: Communication MCAL.
     * SPI, LIN, CAN initialization order follows bus dependency.
     */
    Spi_Init(&Spi_Config);
    Lin_Init(&Lin_Config);
    Can_Init(&Can_Config);

    /*
     * Phase 4: Analog and PWM MCAL.
     */
    Adc_Init(&Adc_Config);
    Pwm_Init(&Pwm_Config);

    /*
     * Phase 5: ECUAL layer.
     * Interface modules (CanIf, LinIf) depend on their respective MCAL drivers.
     */
    CanIf_Init();
    CanTp_Init();
    LinIf_Init();
    LinTp_Init();
    MemIf_Init();

    /*
     * Phase 6: Services layer — mode and communication management.
     */
    EcuM_Init();
    BswM_Init();
    ComM_Init();
    Com_Init();
    PduR_Init();

    /*
     * Phase 7: Diagnostic and memory services.
     */
    Dem_Init();
    Dcm_Init();
    NvM_Init();
    Fee_Init();

    /*
     * Phase 8: Safety and crypto services.
     */
    E2E_Init();
    Csm_Init();

    /*
     * Phase 9: Watchdog Management — must be started last
     * after all modules are initialized.
     */
    WdgM_Init();
    Det_Init();
}

/* ─── Main Entry Point ────────────────────────────────────── */

int main(void)
{
    /* Initialize the full BSW stack */
    Bsw_InitAll();

    /* Start AUTOSAR OS (if using) or enter scheduled main loop */
#if defined(USE_AUTOSAR_OS)
    StartOS(OSDEFAULTAPPMODE);
    /* Never returns */
#else
    SchM_Init();

    /* Main scheduling loop */
    while (1)
    {
        /* 1ms base tick — SchM manages runnable scheduling */
        SchM_MainFunction();

        /* Communication stack main functions */
        Can_MainFunction_Read();
        Can_MainFunction_Write();
        CanIf_MainFunction();
        CanTp_MainFunction();
        Com_MainFunction();
        PduR_MainFunction();

        /* Diagnostic main functions */
        Dcm_MainFunction();
        Dem_MainFunction();

        /* Memory management */
        NvM_MainFunction();
        Fee_MainFunction();

        /* Watchdog trigger */
        WdgM_PerformReset();
    }
#endif

    return 0;
}

/* ─── AUTOSAR Callbacks ───────────────────────────────────── */

/**
 * @brief CanIf TX confirmation callback.
 */
void CanIf_TxConfirmation(PduIdType pduId)
{
    (void)pduId;
    /* Forward to upper layer (Com) */
    Com_TxConfirmation(pduId);
}

/**
 * @brief CanIf RX indication callback.
 */
void CanIf_RxIndication(PduIdType pduId)
{
    (void)pduId;
    /* Forward to upper layer (Com) */
    Com_RxIndication(pduId);
}

/**
 * @brief NvM block write completed callback.
 */
void NvM_JobEndNotification(NvM_BlockIdType blockId)
{
    (void)blockId;
}

/**
 * @brief NvM block write error callback.
 */
void NvM_JobErrorNotification(NvM_BlockIdType blockId)
{
    (void)blockId;
}

/**
 * @brief DCM request processing callback.
 */
void Dcm_RequestProcess(Dcm_OpStatusType opStatus)
{
    (void)opStatus;
}

/**
 * @brief Det error report handler.
 * Called when a development error is detected by any BSW module.
 */
void Det_ReportError(uint16_t moduleId,
                     uint8_t instanceId,
                     uint8_t apiId,
                     uint8_t errorId)
{
    /* Log the error (can be redirected to DLT, serial, or stored in DEM) */
    (void)moduleId;
    (void)instanceId;
    (void)apiId;
    (void)errorId;
}

/**
 * @brief WdgM notification callback — triggered on
 * deadline violation for a supervised entity.
 */
void WdgM_AlarmNotification(uint8_t seId)
{
    (void)seId;
    /* Critical failure — trigger safe-state or shutdown */
}

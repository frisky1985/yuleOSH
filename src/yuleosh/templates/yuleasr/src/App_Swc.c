/**
 * @file App_Swc.c
 * @brief Application Software Component implementation.
 *
 * Demonstrates AUTOSAR SW-C runnable pattern with
 * RTE-based signal routing and diagnostic integration.
 */

#include "App_Swc.h"
#include "SchM_App.h"
#include "Dem.h"
#include "Rte_App.h"

/* ─── Local State ─────────────────────────────────────────── */

static App_InputCommandType  s_input  = 0U;
static App_OutputStateType   s_output = 0U;

/* ─── Runnable Implementations ────────────────────────────── */

void App_Init_10ms(void)
{
    /* Read input command from RTE */
#if defined(USE_RTE)
    (void)Rte_Read_AppInput_Command(&s_input);
#else
    /* Direct read for non-RTE mode */
    s_input = 0U;
#endif

    s_output = 0U;
}

void App_Control_100ms(void)
{
    /* Process input → output transformation */
    s_output = (App_OutputStateType)(s_input * 2U);

    /* Write output via RTE */
#if defined(USE_RTE)
    (void)Rte_Write_AppOutput_State(s_output);
#endif

    /* Report diagnostic event if output overflow detected */
    if (s_output > 0xFF00U)
    {
        Dem_ReportErrorStatus(
            1U,                         /* EventId: AppOverflow */
            DEM_EVENT_STATUS_FAILED
        );
    }
    else
    {
        Dem_ReportErrorStatus(
            1U,
            DEM_EVENT_STATUS_PASSED
        );
    }
}

void App_Diag_1000ms(void)
{
    Std_ReturnType rv;
    uint8_t healthData[8] = {0U};

    /* Pack health status */
    healthData[0] = (uint8_t)((s_output >> 8) & 0xFFU);
    healthData[1] = (uint8_t)(s_output & 0xFFU);

    /* Invoke diagnostic service via RTE (Client-Server) */
#if defined(USE_RTE)
    (void)Rte_Call_AppDiag_App_DiagnosticService(
        0x22U,                          /* UDS SID: ReadDataByIdentifier */
        healthData,
        sizeof(healthData)
    );
#else
    (void)App_DiagnosticService(
        0x22U,
        healthData,
        sizeof(healthData)
    );
#endif
}

/* ─── Client-Server Operation ─────────────────────────────── */

Std_ReturnType App_DiagnosticService(uint8_t serviceId,
                                     const uint8_t *data,
                                     uint16_t length)
{
    Std_ReturnType result = RTE_E_OK;

    switch (serviceId)
    {
    case 0x22U:     /* ReadDataByIdentifier */
    case 0x2EU:     /* WriteDataByIdentifier */
    case 0x31U:     /* RoutineControl */
        result = RTE_E_OK;
        break;

    default:
        result = RTE_E_NOT_OK;
        break;
    }

    return result;
}

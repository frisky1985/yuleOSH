/**
 * @file App_Swc.h
 * @brief Application Software Component header.
 *
 * Demonstrates AUTOSAR SW-C interface definition with
 * Sender-Receiver and Client-Server ports.
 */

#ifndef APP_SWC_H
#define APP_SWC_H

#include "Std_Types.h"
#include "Rte_App.h"

/*
 * ── Port Interface Definitions ─────────────────────────────
 *
 * SR-Port: AppData_SR      (Sender-Receiver)
 *   Send:  App_OutputState
 *   Recv:  App_InputCommand
 *
 * CS-Port: AppDiag_CS      (Client-Server)
 *   Oper.: App_DiagnosticService
 */

typedef uint8_t  App_InputCommandType;
typedef uint16_t App_OutputStateType;

/*
 * Run Result codes
 */
#define APP_E_OK      0U
#define APP_E_NOT_OK  1U

/*
 * ── Runnable Prototypes ────────────────────────────────────
 */

/**
 * @brief 10ms init runnable — reads input state from RTE.
 */
void App_Init_10ms(void);

/**
 * @brief 100ms control runnable — processes inputs and updates outputs.
 */
void App_Control_100ms(void);

/**
 * @brief 1000ms diagnostic runnable — reports health status.
 */
void App_Diag_1000ms(void);

/*
 * ── Client-Server Operation Implementation ──────────────────
 */

/**
 * @brief Diagnostic service operation exposed via RTE.
 * @param serviceId UDS service identifier
 * @param data      request data buffer
 * @param length    data length
 * @return          Std_ReturnType (E_OK / E_NOT_OK)
 */
Std_ReturnType App_DiagnosticService(uint8_t serviceId,
                                     const uint8_t *data,
                                     uint16_t length);

#endif /* APP_SWC_H */

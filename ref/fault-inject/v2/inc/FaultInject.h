/*******************************************************************************
 * Copyright (C) 2024 Ingeek, Inc. or its affiliates.  All Rights Reserved.
 *
 * @file    FaultInject.h
 * @brief   A66-T HardFault Exception Injection Test Framework API
 *
 * @details Provides functions to inject CPU exceptions (HardFault, BusFault,
 *          UsageFault, MemManage, StackOverflow) for testing the A66-T fault
 *          handling chain on Z20K148M (ARM Cortex-M4F).
 *
 *          Chain: handler invocation → NoInit fault record save (.share_ram
 *          @0x1FFE0000) → Mcu_PerformReset → post-reset fault report.
 *
 *          Test results are stored in NoInit_DataType_St.faultInjectResult
 *          (union member, no separate address needed).
 *
 * @note    Only compiled when A66T_FAULT_INJECTION_TEST_ENABLE is STD_ON.
 ******************************************************************************/

#ifndef A66T_FAULTINJECT_H_
#define A66T_FAULTINJECT_H_

#ifdef __cplusplus
extern "C" {
#endif

/*===========================================================================
 *  Includes
 *=========================================================================*/
#include "Std_Types.h"
#include "FaultInject_Cfg.h"

/*===========================================================================
 *  Type Definitions
 *=========================================================================*/

/** @brief Fault injection test type identifiers */
typedef enum
{
    FAULT_INJECT_NONE = 0,           /**< No test                        */
    FAULT_INJECT_NULL_POINTER = 1,   /**< TC-01: Null pointer write      */
    FAULT_INJECT_INVALID_FUNC = 2,   /**< TC-02: Invalid function call   */
    FAULT_INJECT_DIV_BY_ZERO = 3,    /**< TC-03: Division by zero        */
    FAULT_INJECT_UNALIGNED = 4,      /**< TC-04: Unaligned access        */
    FAULT_INJECT_STACK_OVERFLOW = 5, /**< TC-05: Stack overflow          */
    FAULT_INJECT_MPU_VIOLATION = 6,  /**< TC-06: MPU violation           */
    FAULT_INJECT_UNDEF_INSTR = 7,    /**< TC-07: Undefined instruction   */
    FAULT_INJECT_DIRECT_SCB = 8,     /**< TC-08: Direct SCB injection    */
    FAULT_INJECT_BUS_ACCESS = 9,     /**< TC-09: Bus access fault        */
    FAULT_INJECT_MAX                /**< Sentinel                       */
} FaultInject_Type_E;

/** @brief Test result status */
typedef enum
{
    FAULT_INJECT_STATUS_PENDING = 0, /**< Test injected, awaiting reset  */
    FAULT_INJECT_STATUS_PASSED  = 1, /**< Fault captured and verified    */
    FAULT_INJECT_STATUS_FAILED  = 2, /**< Fault not captured or mismatch */
    FAULT_INJECT_STATUS_ERROR   = 3  /**< Unexpected error               */
} FaultInject_Status_E;

/** @brief Test result stored in NoInit_DataType_St.faultInjectResult */
typedef struct
{
    uint32_t magic;           /**< 0xF175F175 = valid record            */
    uint32_t testId;          /**< FaultInject_Type_E value             */
    uint32_t faultTypeSeen;   /**< faultType from NoInit_FaultRecord_St */
    uint32_t pcSeen;          /**< PC from fault record                 */
    uint32_t cfsrSeen;        /**< CFSR from fault record               */
    uint32_t hfsrSeen;        /**< HFSR from fault record               */
    uint32_t status;          /**< FaultInject_Status_E                 */
} A66T_FaultInject_TestResult_St;

/*===========================================================================
 *  Public API
 *=========================================================================*/

#if (A66T_FAULT_INJECTION_TEST_ENABLE == STD_ON)

/**
 * @brief   Initialize the A66-T fault injection test framework.
 * @details Enables MemManage, BusFault, UsageFault handlers in SCB->SHCSR.
 *          Call once during system init, after NoInit_Init().
 */
void FaultInject_Init(void);

/**
 * @brief   Run a specific fault injection test.
 * @details Stores test metadata in NoInit RAM, then triggers a CPU exception.
 *          This function does NOT return — the system will reset.
 *          After reboot, call FaultInject_CheckResult() to verify.
 * @param   testType: Which fault to inject (see FaultInject_Type_E)
 * @warning This function causes a system reset. Do not call in production.
 */
void FaultInject_Run(FaultInject_Type_E testType);

/**
 * @brief   Check and verify test result after reset.
 * @details Call during startup, after NoInit_ReportFaultRecord().
 * @return  TRUE if a pending test result was found and processed.
 */
boolean FaultInject_CheckResult(void);

/**
 * @brief   Get pointer to the test result structure.
 * @return  Pointer to A66T_FaultInject_TestResult_St in NoInit RAM.
 */
const A66T_FaultInject_TestResult_St* FaultInject_GetResult(void);

/**
 * @brief   Get human-readable name for a test type.
 */
const char* FaultInject_GetTestName(FaultInject_Type_E testType);

#else /* A66T_FAULT_INJECTION_TEST_ENABLE == STD_OFF */

/* Stub implementations for production builds — all no-ops */
static inline void FaultInject_Init(void) {}
static inline void FaultInject_Run(FaultInject_Type_E testType) { (void)testType; }
static inline boolean FaultInject_CheckResult(void) { return FALSE; }
static inline const A66T_FaultInject_TestResult_St* FaultInject_GetResult(void) { return NULL; }
static inline const char* FaultInject_GetTestName(FaultInject_Type_E testType) { (void)testType; return "Disabled"; }

#endif /* A66T_FAULT_INJECTION_TEST_ENABLE */

#ifdef __cplusplus
}
#endif

#endif /* A66T_FAULTINJECT_H_ */

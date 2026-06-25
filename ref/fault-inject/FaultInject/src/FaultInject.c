/*******************************************************************************
 * Copyright (C) 2024 Ingeek, Inc. or its affiliates.  All Rights Reserved.
 *
 * @file    FaultInject.c
 * @brief   A66-T HardFault Exception Injection Test Framework Implementation
 *
 * @details Implements 9 fault injection methods for testing the A66-T MCU's
 *          exception handling chain on Z20K148M (ARM Cortex-M4F).
 *
 *          Target: A66-T SBM MCU
 *          MCU:   Z20K148M (ZhiXin Semiconductor)
 *          Core:  ARM Cortex-M4F
 *          SRAM:  .share_ram @ 0x1FFE0000 (1KB, NoInit, SRAML=SRAM0, ECC)
 *          EIRU:  0x4000B000 (SRAM ECC control)
 *
 *          Each injection triggers a real CPU exception:
 *            - Exception handler (Exception.c) saves context to NoInit
 *            - Mcu_PerformReset() resets the system
 *            - After reboot, FaultInject_CheckResult() verifies the record
 *
 * @warning NEVER compile with A66T_FAULT_INJECTION_TEST_ENABLE=STD_ON
 *          in production. This code intentionally triggers CPU faults.
 *
 * @note    Prerequisites (from A66-T safety reports):
 *          1. RTCtime: pointer → embedded struct (null pointer fix)
 *          2. memset → 32-bit word writes (ECC read-modify-write fix)
 *          3. EIRU_CR ECC disable at Exception_SaveFaultRecord entry
 *          4. Startup.s BEQ→BNE fix (POR Share RAM clear)
 *          5. Add faultInjectResult member to NoInit_DataType_St union
 ******************************************************************************/

#ifdef __cplusplus
extern "C" {
#endif

/*===========================================================================
 *  Includes
 *=========================================================================*/
#include "FaultInject.h"

#if (A66T_FAULT_INJECTION_TEST_ENABLE == STD_ON)

#include "NoInit.h"
#include "McalLib.h"
#include <string.h>

/*===========================================================================
 *  Z20K148M Register Definitions
 *=========================================================================*/

/* SCB (System Control Block) — Cortex-M4F core */
#define SCB_CCR_ADDR            (0xE000ED14U)  /* Configuration & Control   */
#define SCB_SHCSR_ADDR          (0xE000ED24U)  /* System Handler Ctrl & State*/
#define SCB_CFSR_ADDR           (0xE000ED28U)  /* Configurable Fault Status  */
#define SCB_HFSR_ADDR           (0xE000ED2CU)  /* HardFault Status Register  */
#define SCB_MMFAR_ADDR          (0xE000ED34U)  /* MemManage Fault Address    */
#define SCB_BFAR_ADDR           (0xE000ED38U)  /* BusFault Address Register  */

/* SHCSR enable bits */
#define SCB_SHCSR_MEMFAULTENA   (1U << 16)
#define SCB_SHCSR_BUSFAULTENA   (1U << 17)
#define SCB_SHCSR_USGFAULTENA   (1U << 18)

/* CCR trap enable bits */
#define SCB_CCR_UNALIGN_TRP     (1U << 3)
#define SCB_CCR_DIV_0_TRP       (1U << 4)

/* HFSR bits */
#define SCB_HFSR_FORCED         (1U << 30)

/* EIRU (ECC/Interrupt Control Unit) — Z20K148M specific */
/* EIRU base = PERIPHERAL_BASE_ADDR(0x40000000) + 0xB000 = 0x4000B000 */
#define EIRU_CR_ADDR            (0x4000B000U)
/* SRAM0 = SRAML = .share_ram region. Disable all ECC error responses. */
#define EIRU_CR_SRAM0_DISABLE_ALL (0x0FU)  /* ER_DIS|EW_DIS|ESB_DIS|EMB_DIS */

/*===========================================================================
 *  External References
 *=========================================================================*/
/* Defined in Exception.c — Z20K148M platform startup */
extern void HardFault_Handler(void);

/* Defined in Mcu module */
extern void Mcu_PerformReset(void);

/*===========================================================================
 *  Private Helper: Disable SRAM0 ECC response
 *  Prevents recursive BusFault when accessing .share_ram (0x1FFE0000)
 *  during fault handler. Mirrors fix from A66-T_Share_RAM_Safety_Report.
 *=========================================================================*/
static void FaultInject_DisableEccResponse(void)
{
    volatile uint32_t *eiruCr = (volatile uint32_t *)EIRU_CR_ADDR;
    *eiruCr |= EIRU_CR_SRAM0_DISABLE_ALL;
}

/*===========================================================================
 *  Private Helper: Enable all configurable fault handlers
 *=========================================================================*/
static void FaultInject_EnableFaultHandlers(void)
{
    volatile uint32_t *shcsr = (volatile uint32_t *)SCB_SHCSR_ADDR;
    *shcsr |= (SCB_SHCSR_MEMFAULTENA |
               SCB_SHCSR_BUSFAULTENA |
               SCB_SHCSR_USGFAULTENA);
    __DSB();
    __ISB();
}

/*===========================================================================
 *  Injection Functions
 *  Each triggers a real CPU exception and does NOT return.
 *=========================================================================*/

#if (A66T_FAULT_INJECT_NULL_POINTER == STD_ON)
/**
 * TC-01: Null pointer write → BusFault → HardFault
 * CFSR: BFSR.PRECISERR (0x200) or BFSR.IMPRECISERR (0x400)
 * BFAR: 0x00000000 (if PRECISERR)
 */
static void FaultInject_DoNullPointer(void)
{
    volatile uint32_t *null_ptr = (volatile uint32_t *)0x00000000U;
    *null_ptr = 0xDEADBEEFU;
}
#endif

#if (A66T_FAULT_INJECT_INVALID_FUNC == STD_ON)
/**
 * TC-02: Invalid function call (T-bit=0) → UsageFault: INVSTATE
 * CFSR: UFSR.INVSTATE (0x00020000)
 */
static void FaultInject_DoInvalidFunc(void)
{
    typedef void (*func_ptr_t)(void);
    func_ptr_t bad_func = (func_ptr_t)0x00000001U;
    bad_func();
}
#endif

#if (A66T_FAULT_INJECT_DIV_BY_ZERO == STD_ON)
/**
 * TC-03: Division by zero → UsageFault: DIVBYZERO
 * CFSR: UFSR.DIVBYZERO (0x02000000)
 */
static void FaultInject_DoDivByZero(void)
{
    volatile uint32_t *ccr = (volatile uint32_t *)SCB_CCR_ADDR;
    volatile uint32_t numerator = 100U;
    volatile uint32_t denominator = 0U;
    volatile uint32_t result;

    *ccr |= SCB_CCR_DIV_0_TRP;
    __DSB();

    result = numerator / denominator;
    (void)result;
}
#endif

#if (A66T_FAULT_INJECT_UNALIGNED == STD_ON)
/**
 * TC-04: Unaligned access → UsageFault: UNALIGNED
 * CFSR: UFSR.UNALIGNED (0x01000000)
 */
static void FaultInject_DoUnaligned(void)
{
    volatile uint32_t *ccr = (volatile uint32_t *)SCB_CCR_ADDR;
    volatile uint8_t buf[8] = {0U, 0U, 0U, 0U, 0U, 0U, 0U, 0U};
    volatile uint32_t *misaligned;

    *ccr |= SCB_CCR_UNALIGN_TRP;
    __DSB();

    misaligned = (volatile uint32_t *)&buf[1];
    *misaligned = 0xCAFEF00DU;
}
#endif

#if (A66T_FAULT_INJECT_STACK_OVERFLOW == STD_ON)
/**
 * TC-05: Stack overflow via infinite recursion
 * FreeRTOS calls vApplicationStackOverflowHook() → faultType=5
 */
__attribute__((noinline))
static void FaultInject_RecursiveNop(uint32_t depth)
{
    volatile uint8_t canary[128];
    volatile uint32_t i;
    for (i = 0U; i < sizeof(canary); i++)
    {
        canary[i] = (uint8_t)(depth + i);
    }
    FaultInject_RecursiveNop(depth + 1U);
}

static void FaultInject_DoStackOverflow(void)
{
    FaultInject_RecursiveNop(0U);
}
#endif

#if (A66T_FAULT_INJECT_MPU_VIOLATION == STD_ON)
/**
 * TC-06: MPU violation → MemManage: DACCVIOL
 * Requires configENABLE_MPU=1 (currently 0 on A66-T)
 * CFSR: MMFSR.DACCVIOL (0x02) or IACCVIOL (0x01)
 */
static void FaultInject_DoMPUViolation(void)
{
    volatile uint32_t *restricted = (volatile uint32_t *)0xE000ED00U;
    volatile uint32_t val = *restricted;
    (void)val;
}
#endif

#if (A66T_FAULT_INJECT_UNDEF_INSTR == STD_ON)
/**
 * TC-07: Undefined instruction → UsageFault: UNDEFINSTR
 * CFSR: UFSR.UNDEFINSTR (0x00010000)
 */
static void FaultInject_DoUndefinedInstr(void)
{
    __asm volatile(".hword 0xDE00");  /* UDF #0 — permanently undefined */
}
#endif

#if (A66T_FAULT_INJECT_DIRECT_SCB == STD_ON)
/**
 * TC-08: Direct SCB injection — tests handler save+reset path
 * Sets HFSR.FORCED, calls HardFault_Handler() directly.
 * No real exception context is stacked.
 */
static void FaultInject_DoDirectSCB(void)
{
    volatile uint32_t *hfsr = (volatile uint32_t *)SCB_HFSR_ADDR;
    *hfsr = SCB_HFSR_FORCED;
    __DSB();
    HardFault_Handler();
}
#endif

#if (A66T_FAULT_INJECT_BUS_ACCESS == STD_ON)
/**
 * TC-09: Bus access to unmapped address → BusFault
 * 0x40080000 is unmapped peripheral space on Z20K148M
 * CFSR: BFSR.IBUSERR (0x100) or PRECISERR (0x200)
 */
static void FaultInject_DoBusAccess(void)
{
    volatile uint32_t *bad_addr = (volatile uint32_t *)0x40080000U;
    volatile uint32_t val = *bad_addr;
    (void)val;
}
#endif

/*===========================================================================
 *  Test Name Lookup
 *=========================================================================*/
const char* FaultInject_GetTestName(FaultInject_Type_E testType)
{
    switch (testType)
    {
        case FAULT_INJECT_NULL_POINTER:   return "NullPointer";
        case FAULT_INJECT_INVALID_FUNC:   return "InvalidFunc";
        case FAULT_INJECT_DIV_BY_ZERO:    return "DivByZero";
        case FAULT_INJECT_UNALIGNED:      return "Unaligned";
        case FAULT_INJECT_STACK_OVERFLOW: return "StackOverflow";
        case FAULT_INJECT_MPU_VIOLATION:  return "MPUViolation";
        case FAULT_INJECT_UNDEF_INSTR:    return "UndefInstr";
        case FAULT_INJECT_DIRECT_SCB:     return "DirectSCB";
        case FAULT_INJECT_BUS_ACCESS:     return "BusAccess";
        default:                          return "Unknown";
    }
}

/*===========================================================================
 *  Public API Implementation
 *=========================================================================*/

void FaultInject_Init(void)
{
    FaultInject_EnableFaultHandlers();
}

void FaultInject_Run(FaultInject_Type_E testType)
{
    /* Access test result via NoInit union member (in .share_ram @ 0x1FFE0000) */
    volatile A66T_FaultInject_TestResult_St *result = NoInit_FaultInjectResultPtrGet();

    /* --- Phase 1: Save test metadata to NoInit RAM --- */

    /* Disable SRAM0 ECC to protect NoInit write from recursive fault */
    FaultInject_DisableEccResponse();

    result->testId        = (uint32_t)testType;
    result->magic         = A66T_FAULT_INJECT_RESULT_MAGIC;
    result->status        = (uint32_t)FAULT_INJECT_STATUS_PENDING;
    result->faultTypeSeen = 0U;
    result->pcSeen        = 0U;
    result->cfsrSeen      = 0U;
    result->hfsrSeen      = 0U;

    __DSB();
    __ISB();

    /* --- Phase 2: Enable fault handlers --- */
    FaultInject_EnableFaultHandlers();

    /* --- Phase 3: Execute injection (none of these return) --- */
    switch (testType)
    {
#if (A66T_FAULT_INJECT_NULL_POINTER == STD_ON)
        case FAULT_INJECT_NULL_POINTER:   FaultInject_DoNullPointer();   break;
#endif
#if (A66T_FAULT_INJECT_INVALID_FUNC == STD_ON)
        case FAULT_INJECT_INVALID_FUNC:   FaultInject_DoInvalidFunc();   break;
#endif
#if (A66T_FAULT_INJECT_DIV_BY_ZERO == STD_ON)
        case FAULT_INJECT_DIV_BY_ZERO:    FaultInject_DoDivByZero();     break;
#endif
#if (A66T_FAULT_INJECT_UNALIGNED == STD_ON)
        case FAULT_INJECT_UNALIGNED:      FaultInject_DoUnaligned();     break;
#endif
#if (A66T_FAULT_INJECT_STACK_OVERFLOW == STD_ON)
        case FAULT_INJECT_STACK_OVERFLOW: FaultInject_DoStackOverflow(); break;
#endif
#if (A66T_FAULT_INJECT_MPU_VIOLATION == STD_ON)
        case FAULT_INJECT_MPU_VIOLATION:  FaultInject_DoMPUViolation();  break;
#endif
#if (A66T_FAULT_INJECT_UNDEF_INSTR == STD_ON)
        case FAULT_INJECT_UNDEF_INSTR:    FaultInject_DoUndefinedInstr(); break;
#endif
#if (A66T_FAULT_INJECT_DIRECT_SCB == STD_ON)
        case FAULT_INJECT_DIRECT_SCB:     FaultInject_DoDirectSCB();     break;
#endif
#if (A66T_FAULT_INJECT_BUS_ACCESS == STD_ON)
        case FAULT_INJECT_BUS_ACCESS:     FaultInject_DoBusAccess();     break;
#endif
        case FAULT_INJECT_NONE:
        case FAULT_INJECT_MAX:
        default:
            result->status = (uint32_t)FAULT_INJECT_STATUS_ERROR;
            break;
    }

    /* If we reach here, injection didn't trigger a fault (shouldn't happen) */
    if (result->status == (uint32_t)FAULT_INJECT_STATUS_PENDING)
    {
        result->status = (uint32_t)FAULT_INJECT_STATUS_FAILED;
    }
}

boolean FaultInject_CheckResult(void)
{
    volatile A66T_FaultInject_TestResult_St *result = NoInit_FaultInjectResultPtrGet();
    volatile NoInit_FaultRecord_St *rec = NoInit_FaultRecordPtrGet();

    /* Check for pending test result from before reset */
    if (result->magic != A66T_FAULT_INJECT_RESULT_MAGIC)
    {
        return FALSE;
    }
    if (result->status != (uint32_t)FAULT_INJECT_STATUS_PENDING)
    {
        return FALSE;
    }

    /* Disable ECC for safe NoInit access */
    FaultInject_DisableEccResponse();

    /* Verify fault record was captured */
    if (rec->magic != NOINIT_FAULT_MAGIC)
    {
        result->faultTypeSeen = 0U;
        result->pcSeen        = 0U;
        result->cfsrSeen      = 0U;
        result->hfsrSeen      = 0U;
        result->status        = (uint32_t)FAULT_INJECT_STATUS_FAILED;
        return TRUE;
    }

    /* Capture fault record details */
    result->faultTypeSeen = rec->faultType;
    result->pcSeen        = rec->PC;
    result->cfsrSeen      = rec->CFSR;
    result->hfsrSeen      = rec->HFSR;

    /* Verification: StackOverflow should produce faultType=5 */
    if ((uint32_t)result->testId == FAULT_INJECT_STACK_OVERFLOW)
    {
        result->status = (rec->faultType == 5U)
            ? (uint32_t)FAULT_INJECT_STATUS_PASSED
            : (uint32_t)FAULT_INJECT_STATUS_FAILED;
    }
    else
    {
        /* CPU exceptions should produce faultType 1-4 */
        result->status = (rec->faultType >= 1U && rec->faultType <= 4U)
            ? (uint32_t)FAULT_INJECT_STATUS_PASSED
            : (uint32_t)FAULT_INJECT_STATUS_FAILED;
    }

    return TRUE;
}

const A66T_FaultInject_TestResult_St* FaultInject_GetResult(void)
{
    return (const A66T_FaultInject_TestResult_St *)NoInit_FaultInjectResultPtrGet();
}

#endif /* A66T_FAULT_INJECTION_TEST_ENABLE == STD_ON */

#ifdef __cplusplus
}
#endif

/** @} */

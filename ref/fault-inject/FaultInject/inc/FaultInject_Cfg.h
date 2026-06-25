/*******************************************************************************
 * Copyright (C) 2024 Ingeek, Inc. or its affiliates.  All Rights Reserved.
 *
 * @file    FaultInject_Cfg.h
 * @brief   A66-T HardFault Exception Injection Test Configuration
 *
 * @details Compile-time configuration for the fault injection test framework.
 *          Target: A66-T SBM MCU (Z20K148M, ARM Cortex-M4F, IAR toolchain).
 *          Enable ONLY in test/debug builds. NEVER enable in production.
 *
 * @note    This module is safety-relevant: enabling fault injection in a
 *          production build is a safety violation. Use build configuration
 *          guards to prevent accidental enablement.
 ******************************************************************************/

#ifndef A66T_FAULTINJECT_CFG_H_
#define A66T_FAULTINJECT_CFG_H_

#include "Std_Types.h"

/*===========================================================================
 *  Master Switch
 *  Set to STD_ON only in dedicated A66-T test builds. Production = STD_OFF.
 *=========================================================================*/
#define A66T_FAULT_INJECTION_TEST_ENABLE   (STD_OFF)

/*===========================================================================
 *  Individual Injection Method Enables
 *  Only effective when A66T_FAULT_INJECTION_TEST_ENABLE == STD_ON
 *=========================================================================*/
#if (A66T_FAULT_INJECTION_TEST_ENABLE == STD_ON)

#define A66T_FAULT_INJECT_NULL_POINTER     (STD_ON)   /* TC-01: Null pointer deref  */
#define A66T_FAULT_INJECT_INVALID_FUNC     (STD_ON)   /* TC-02: Invalid func call   */
#define A66T_FAULT_INJECT_DIV_BY_ZERO      (STD_ON)   /* TC-03: Division by zero    */
#define A66T_FAULT_INJECT_UNALIGNED        (STD_ON)   /* TC-04: Unaligned access    */
#define A66T_FAULT_INJECT_STACK_OVERFLOW   (STD_ON)   /* TC-05: Stack overflow      */
#define A66T_FAULT_INJECT_MPU_VIOLATION    (STD_OFF)  /* TC-06: MPU (needs MPU ON)  */
#define A66T_FAULT_INJECT_UNDEF_INSTR      (STD_ON)   /* TC-07: Undefined instruction*/
#define A66T_FAULT_INJECT_DIRECT_SCB       (STD_ON)   /* TC-08: Direct SCB inject   */
#define A66T_FAULT_INJECT_BUS_ACCESS       (STD_ON)   /* TC-09: Bus fault access    */

/*===========================================================================
 *  Test Result Magic
 *  Stored in NoInit_DataType_St.faultInjectResult (union member in .share_ram)
 *  No separate address needed — uses NoInit_FaultInjectResultPtrGet()
 *=========================================================================*/
#define A66T_FAULT_INJECT_RESULT_MAGIC     (0xF175F175U)

/*===========================================================================
 *  UDS Integration
 *  DID for triggering fault injection via UDS $2E WriteDataByIdentifier
 *=========================================================================*/
#define A66T_FAULT_INJECT_UDS_DID          (0xF190U)

/* Security level required to trigger fault injection via UDS */
#define A66T_FAULT_INJECT_UDS_SEC_LEVEL    (0x01U)

#endif /* A66T_FAULT_INJECTION_TEST_ENABLE == STD_ON */

#endif /* A66T_FAULTINJECT_CFG_H_ */

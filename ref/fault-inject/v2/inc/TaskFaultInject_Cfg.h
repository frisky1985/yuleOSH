/*******************************************************************************
 * Copyright (C) 2024 Ingeek, Inc. or its affiliates.  All Rights Reserved.
 *
 * @file    TaskFaultInject_Cfg.h
 * @brief   Per-Task Fault Injection Configuration
 *
 * @details Compile-time configuration for per-task simulated fault injection.
 *          Extends the FaultInject framework with task-level fault injection
 *          that does NOT trigger CPU exceptions — instead uses FreeRTOS
 *          Task Notifications to inject simulated fault conditions.
 *
 *          Target: A66-T SBM MCU (Z20K148M, ARM Cortex-M4F, FreeRTOS)
 *
 * @note    This module is safe to leave enabled in debug/test builds.
 *          In production, set A66T_TASK_FAULT_INJECT_ENABLE = STD_OFF.
 ******************************************************************************/

#ifndef A66T_TASKFAULTINJECT_CFG_H_
#define A66T_TASKFAULTINJECT_CFG_H_

#include "Std_Types.h"

/*===========================================================================
 *  Master Switch
 *  STD_ON  = per-task fault injection enabled (debug/test builds)
 *  STD_OFF = all injection code compiled out (production builds)
 *=========================================================================*/
#define A66T_TASK_FAULT_INJECT_ENABLE    (STD_OFF)

/*===========================================================================
 *  Individual Fault Type Enables
 *  Each can be turned on/off independently to control binary size.
 *=========================================================================*/
#if (A66T_TASK_FAULT_INJECT_ENABLE == STD_ON)

#define A66T_TASK_FAULT_SIM_NULL_HANDLE       (STD_ON)
#define A66T_TASK_FAULT_SIM_INVALID_PARAM     (STD_ON)
#define A66T_TASK_FAULT_SIM_TIMEOUT           (STD_ON)
#define A66T_TASK_FAULT_SIM_QUEUE_FULL        (STD_ON)
#define A66T_TASK_FAULT_SIM_BUFFER_OVF        (STD_ON)
#define A66T_TASK_FAULT_SIM_RESOURCE_LOST     (STD_ON)
#define A66T_TASK_FAULT_SIM_STATE_CORRUPT     (STD_ON)
#define A66T_TASK_FAULT_REAL_STACK_DEPLETE    (STD_OFF)  /* Risky — may cause real overflow */

/*===========================================================================
 *  Result Storage
 *  Maximum number of fault injection results stored in the rolling buffer.
 *=========================================================================*/
#define TASK_FAULT_RESULT_BUFFER_SIZE         (16U)

/*===========================================================================
 *  Injection Timeout
 *  Maximum time (ms) to wait for the target task to consume the injection
 *  notification and report a result back. If the task does not respond
 *  within this timeout, the injection is marked as TIMEOUT.
 *=========================================================================*/
#define TASK_FAULT_INJECT_TIMEOUT_MS          (5000U)

/*===========================================================================
 *  UDS Integration
 *  DID for triggering per-task fault injection via UDS $2E.
 *  Uses a separate DID from the system-level fault inject (0xF190).
 *=========================================================================*/
#define A66T_TASK_FAULT_INJECT_UDS_DID        (0xF193U)
#define A66T_TASK_FAULT_INJECT_UDS_SEC_LEVEL  (0x01U)

#endif /* A66T_TASK_FAULT_INJECT_ENABLE == STD_ON */

#endif /* A66T_TASKFAULTINJECT_CFG_H_ */

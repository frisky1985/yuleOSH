/*******************************************************************************
 * Copyright (C) 2024 Ingeek, Inc. or its affiliates.  All Rights Reserved.
 *
 * @file    TaskFaultInject.h
 * @brief   Per-Task Simulated Fault Injection Framework API
 *
 * @details Provides a mechanism to inject simulated fault conditions into
 *          specific FreeRTOS tasks WITHOUT triggering CPU exceptions or
 *          system resets. Uses FreeRTOS Task Notifications as the injection
 *          channel — the fastest, lowest-overhead IPC in FreeRTOS.
 *
 *          Architecture:
 *          ┌──────────────┐    Task Notification     ┌──────────────────┐
 *          │ Injector Task │ ───────────────────────→ │  Target Task     │
 *          │ (UDS/CAN)    │    (32-bit fault ID)     │  TASK_FAULT_CHECK│
 *          └──────┬───────┘                           └────────┬─────────┘
 *                 │  poll result                              │ handle fault
 *                 ▼                                            ▼
 *          ┌──────────────┐                           ┌──────────────────┐
 *          │ Result Queue │ ←─────────────────────── │ Error-handling   │
 *          │ (ring buffer)│    report PASS/FAIL       │ code exercised   │
 *          └──────────────┘                           └──────────────────┘
 *
 *          Contrast with system-level FaultInject:
 *          - System-level: injects real CPU exceptions → system reset
 *          - Task-level:   injects simulated conditions → task keeps running
 *
 *          Use cases:
 *          - Verify each task's NULL-handle error path
 *          - Verify timeout/deadline-miss fallback behavior
 *          - Verify queue-full backpressure handling
 *          - Verify state-machine corruption recovery
 *
 *          Target: A66-T SBM MCU (Z20K148M, ARM Cortex-M4F, FreeRTOS)
 *
 * @note    Safe for debug/test builds. Compiled out when
 *          A66T_TASK_FAULT_INJECT_ENABLE == STD_OFF (production).
 ******************************************************************************/

#ifndef A66T_TASKFAULTINJECT_H_
#define A66T_TASKFAULTINJECT_H_

#ifdef __cplusplus
extern "C" {
#endif

/*===========================================================================
 *  Includes
 *=========================================================================*/
#include "Std_Types.h"
#include "TaskFaultInject_Cfg.h"

#if (A66T_TASK_FAULT_INJECT_ENABLE == STD_ON)

#include "FreeRTOS.h"
#include "task.h"

/*===========================================================================
 *  Type Definitions
 *=========================================================================*/

/**
 * @brief Per-task simulated fault types.
 *
 * These are DIFFERENT from FaultInject_Type_E (system-level CPU faults).
 * Task-level faults simulate error CONDITIONS that a task should handle
 * gracefully — they do NOT trigger CPU exceptions or system resets.
 */
typedef enum
{
    TASK_FAULT_NONE                = 0x00U, /**< No injection active            */

    /* --- Simulated fault conditions (no CPU exception triggered) --- */
    TASK_FAULT_SIM_NULL_HANDLE     = 0x01U, /**< Simulate: critical handle NULL */
    TASK_FAULT_SIM_INVALID_PARAM   = 0x02U, /**< Simulate: invalid parameter    */
    TASK_FAULT_SIM_TIMEOUT         = 0x03U, /**< Simulate: timeout / dead-miss  */
    TASK_FAULT_SIM_QUEUE_FULL      = 0x04U, /**< Simulate: message queue full   */
    TASK_FAULT_SIM_BUFFER_OVF      = 0x05U, /**< Simulate: buffer overrun cond  */
    TASK_FAULT_SIM_RESOURCE_LOST   = 0x06U, /**< Simulate: peripheral lost      */
    TASK_FAULT_SIM_STATE_CORRUPT   = 0x07U, /**< Simulate: state machine corrupt*/

    /* --- Real resource depletion (use with caution) --- */
    TASK_FAULT_REAL_STACK_DEPLETE  = 0x10U, /**< Real: pre-consume stack space  */

    TASK_FAULT_MAX                           /**< Sentinel                       */
} TaskFault_Type_E;

/**
 * @brief Per-task fault injection result status.
 */
typedef enum
{
    TASK_FAULT_RESULT_PENDING     = 0U, /**< Injection sent, awaiting response  */
    TASK_FAULT_RESULT_PASSED      = 1U, /**< Task handled fault correctly       */
    TASK_FAULT_RESULT_FAILED      = 2U, /**< Task handled fault incorrectly     */
    TASK_FAULT_RESULT_TIMEOUT     = 3U, /**< Task did not respond in time       */
    TASK_FAULT_RESULT_NOT_REGISTERED = 4U, /**< Task not registered for injection */
} TaskFault_Result_E;

/**
 * @brief Single injection result record.
 *
 * Stored in a rolling buffer. When the buffer is full, oldest records
 * are overwritten (circular buffer).
 */
typedef struct
{
    TaskFault_Type_E   faultType;      /**< What was injected                   */
    TaskFault_Result_E result;         /**< PASSED / FAILED / TIMEOUT / ...    */
    TaskHandle_t       taskHandle;     /**< Target task (NULL if not registered)*/
    const char        *taskName;       /**< Target task name (for UDS report)   */
    uint32_t           injectTick;     /**< xTaskGetTickCount() at injection    */
    uint32_t           respondTick;    /**< xTaskGetTickCount() at response     */
} TaskFault_ResultRecord_St;

/*===========================================================================
 *  Public API
 *=========================================================================*/

/**
 * @brief   Initialize the per-task fault injection framework.
 * @details Creates the result buffer. Must be called after the RTOS
 *          scheduler has started (so xTaskGetTickCount is valid).
 *          Safe to call multiple times — subsequent calls are no-ops.
 */
void TaskFault_Init(void);

/**
 * @brief   Register a task as eligible for fault injection.
 * @details A task MUST be registered before faults can be injected into it.
 *          The task must also call TASK_FAULT_CHECK() in its main loop.
 * @param   task      Task handle (from osThreadNew or xTaskCreate)
 * @param   taskName  Human-readable name (static string, not copied)
 * @return  TRUE if registered, FALSE if task list is full.
 */
boolean TaskFault_RegisterTask(TaskHandle_t task, const char *taskName);

/**
 * @brief   Inject a simulated fault into a specific task.
 * @details Sends a FreeRTOS Task Notification to the target task with
 *          the fault type encoded in the notification value. Does NOT
 *          block — returns immediately. The task must call
 *          TASK_FAULT_CHECK() to consume the notification.
 *
 *          After injection, poll TaskFault_GetResult() to check if the
 *          task responded.
 *
 * @param   task       Target task handle (must be registered)
 * @param   faultType  Which fault to inject
 * @return  TRUE if the notification was sent, FALSE if task not registered
 *          or notification queue full.
 */
boolean TaskFault_Inject(TaskHandle_t task, TaskFault_Type_E faultType);

/**
 * @brief   Get the most recent injection result.
 * @details Returns the latest result record from the rolling buffer.
 *          Call after TaskFault_Inject() to check the outcome.
 * @return  Pointer to result record, or NULL if no results yet.
 */
const TaskFault_ResultRecord_St *TaskFault_GetLatestResult(void);

/**
 * @brief   Get all injection results.
 * @param   outCount  [out] Number of valid records returned
 * @return  Pointer to the result buffer array (valid until next injection).
 */
const TaskFault_ResultRecord_St *TaskFault_GetAllResults(uint32_t *outCount);

/**
 * @brief   Clear all results from the buffer.
 */
void TaskFault_ClearResults(void);

/**
 * @brief   Get a human-readable name for a task fault type.
 * @param   faultType  Fault type to look up
 * @return  Static string (e.g., "NullHandle", "Timeout").
 */
const char *TaskFault_GetFaultName(TaskFault_Type_E faultType);

/**
 * @brief   Get a human-readable name for a result status.
 * @param   result  Result to look up
 * @return  Static string (e.g., "PASSED", "FAILED").
 */
const char *TaskFault_GetResultName(TaskFault_Result_E result);

/*===========================================================================
 *  Task-Side Integration
 *=========================================================================*/

/**
 * @brief   Check for and handle an injected fault notification.
 *
 * @details This function MUST be called periodically by every task that
 *          supports fault injection. Typical placement: at the top of
 *          the task's main for(;;) loop, before any business logic.
 *
 *          When a fault notification is received, this function:
 *          1. Reads the fault type from the notification value
 *          2. Sets the task's local "fault mode" flag
 *          3. Records PASSED/FAILED based on whether the task detected
 *             the fault condition and handled it correctly
 *
 *          Usage pattern in a task:
 *          @code
 *          void MyTask(void *pvParams) {
 *              TaskFault_RegisterTask(xTaskGetCurrentTaskHandle(), "MyTask");
 *              for (;;) {
 *                  TASK_FAULT_CHECK();
 *                  // ... normal business logic ...
 *                  TASK_FAULT_END_CHECK();
 *              }
 *          }
 *          @endcode
 *
 * @note    Returns immediately if no notification is pending (fast path).
 *          Only executes the fault-handling logic when a fault is injected.
 */
void TaskFault_CheckNotification(void);

/**
 * @brief   Manually report the result for the current fault injection.
 * @details Called by task code when it has detected and handled (or failed
 *          to handle) an injected fault condition.
 * @param   result  PASSED or FAILED
 */
void TaskFault_ReportResult(TaskFault_Result_E result);

/**
 * @brief   Get the currently active fault type for this task.
 * @return  TASK_FAULT_NONE if no fault is active, otherwise the fault type.
 */
TaskFault_Type_E TaskFault_GetActiveFault(void);

/*===========================================================================
 *  Convenience Macros for Task Integration
 *=========================================================================*/

/**
 * @brief   Check for injected faults at the top of the task loop.
 * @details Call this ONCE at the top of your task's for(;;) loop.
 *          When a fault is injected, subsequent code should check
 *          TASK_FAULT_IS_ACTIVE() and exercise the appropriate error path.
 *
 *          Example:
 *          @code
 *          void RteTask_High(void *pvParams) {
 *              TaskFault_RegisterTask(xTaskGetCurrentTaskHandle(), "RteHigh");
 *              for (;;) {
 *                  TASK_FAULT_CHECK();
 *                  // ... business logic with fault-aware branches ...
 *                  TASK_FAULT_END_CHECK();
 *              }
 *          }
 *          @endcode
 */
#define TASK_FAULT_CHECK()                    TaskFault_CheckNotification()

/**
 * @brief   End-of-iteration fault check.
 * @details Call at the END of the task's main loop iteration. If a fault
 *          was active but no code reported a result, this auto-reports
 *          FAILED (fault not handled).
 */
#define TASK_FAULT_END_CHECK()                TaskFault_EndOfIterationCheck()

/**
 * @brief   Check if a specific fault type is currently active.
 * @param   _fault_type  The TaskFault_Type_E to check for.
 * @return  TRUE if this fault type is the currently injected one.
 *
 *          Usage pattern in task code:
 *          @code
 *          void *handle = getHandle();
 *
 *          if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_NULL_HANDLE)) {
 *              handle = NULL;  // Force NULL to test error path
 *          }
 *
 *          if (handle == NULL) {
 *              TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);
 *              return ERR_PARAM;
 *          }
 *          @endcode
 */
#define TASK_FAULT_IS_ACTIVE(_fault_type)     \
    (TaskFault_GetActiveFault() == (_fault_type))

/**
 * @brief   Report the current fault injection result.
 * @param   _result  TASK_FAULT_RESULT_PASSED or TASK_FAULT_RESULT_FAILED
 *
 *          Call this in the error-handling path that the fault was designed
 *          to exercise. Example:
 *          @code
 *          if (NULL == pvHandle) {
 *              // This is the code path we want to verify works.
 *              TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);
 *              return DKF_RESULT_ERR_PARAM;
 *          }
 *          @endcode
 */
#define TASK_FAULT_REPORT(_result)            TaskFault_ReportResult(_result)

#else /* A66T_TASK_FAULT_INJECT_ENABLE == STD_OFF */

/* Stub implementations — all compile to nothing in production */
static inline void    TaskFault_Init(void) {}
static inline boolean TaskFault_RegisterTask(TaskHandle_t task, const char *name) { (void)task; (void)name; return FALSE; }
static inline boolean TaskFault_Inject(TaskHandle_t task, TaskFault_Type_E type) { (void)task; (void)type; return FALSE; }
static inline const TaskFault_ResultRecord_St *TaskFault_GetLatestResult(void) { return NULL; }
static inline const TaskFault_ResultRecord_St *TaskFault_GetAllResults(uint32_t *c) { *c = 0U; return NULL; }
static inline void    TaskFault_ClearResults(void) {}
static inline const char *TaskFault_GetFaultName(TaskFault_Type_E t) { (void)t; return "Disabled"; }
static inline const char *TaskFault_GetResultName(TaskFault_Result_E r) { (void)r; return "Disabled"; }
static inline void    TaskFault_CheckNotification(void) {}
static inline void    TaskFault_ReportResult(TaskFault_Result_E r) { (void)r; }
static inline TaskFault_Type_E TaskFault_GetActiveFault(void) { return TASK_FAULT_NONE; }

/* Macros become no-ops */
#define TASK_FAULT_CHECK()                    do {} while(0)
#define TASK_FAULT_END_CHECK()                do {} while(0)
#define TASK_FAULT_IS_ACTIVE(_fault_type)     (FALSE)
#define TASK_FAULT_REPORT(_result)            do {} while(0)

#endif /* A66T_TASK_FAULT_INJECT_ENABLE */

#endif /* A66T_TASKFAULTINJECT_H_ */

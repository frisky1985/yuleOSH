/*******************************************************************************
 * Copyright (C) 2024 Ingeek, Inc. or its affiliates.  All Rights Reserved.
 *
 * @file    TaskFaultInject.c
 * @brief   Per-Task Simulated Fault Injection Framework Implementation
 *
 * @details Implements task-level fault injection using FreeRTOS Task
 *          Notifications. This complements the system-level FaultInject
 *          module (which injects real CPU exceptions) by providing a way
 *          to test each task's business-level error handling code.
 *
 *          Key design decisions:
 *          - Uses Task Notifications (fastest FreeRTOS IPC, ~40 cycles)
 *            instead of queues or semaphores to minimize overhead
 *          - Each injection is fire-and-forget: the injector sends a
 *            notification, the target task handles it asynchronously
 *          - Results are stored in a fixed-size rolling buffer (no heap)
 *          - All state is in static arrays — no malloc, no share RAM
 *          - Thread-safe via critical sections on the result buffer
 *
 *          Fault injection flow:
 *          1. Injector calls TaskFault_Inject(task, TASK_FAULT_SIM_NULL_HANDLE)
 *          2. Framework sends xTaskNotify(task, FAULT_NOTIFY_VAL, eSetValueWithOverwrite)
 *          3. Target task calls TASK_FAULT_CHECK() → reads notification
 *          4. Target task sets active fault type, enters "fault mode"
 *          5. Target task's error-handling code detects the fault condition
 *             and calls TASK_FAULT_REPORT(PASSED) or TASK_FAULT_REPORT(FAILED)
 *          6. Injector polls TaskFault_GetLatestResult() to get the outcome
 *
 *          Target: A66-T SBM MCU (Z20K148M, ARM Cortex-M4F, FreeRTOS)
 ******************************************************************************/

#ifdef __cplusplus
extern "C" {
#endif

/*===========================================================================
 *  Includes
 *=========================================================================*/
#include "TaskFaultInject.h"

#if (A66T_TASK_FAULT_INJECT_ENABLE == STD_ON)

#include "task.h"
#include <string.h>

/*===========================================================================
 *  Internal Constants
 *=========================================================================*/

/**
 * @brief   Notification value prefix to distinguish fault injection
 *          notifications from other task notification uses.
 *
 *          Upper 8 bits = 0xFA (fault injection magic).
 *          Lower 24 bits = fault type.
 */
#define TASK_FAULT_NOTIFY_MAGIC        (0xFA000000U)
#define TASK_FAULT_NOTIFY_MASK         (0xFF000000U)
#define TASK_FAULT_NOTIFY_VALUE(_ft)   (TASK_FAULT_NOTIFY_MAGIC | ((uint32_t)(_ft) & 0x00FFFFFFU))

/**
 * @brief   Extract fault type from notification value.
 */
#define TASK_FAULT_FROM_NOTIFY(_v)     ((TaskFault_Type_E)((_v) & 0x00FFFFFFU))

/**
 * @brief   Max registered tasks.
 */
#define TASK_FAULT_MAX_REGISTERED      (8U)

/*===========================================================================
 *  Internal Types
 *=========================================================================*/

/**
 * @brief   Registered task entry.
 */
typedef struct
{
    TaskHandle_t  handle;       /**< FreeRTOS task handle                    */
    const char   *name;         /**< Static task name string                 */
    boolean       registered;   /**< TRUE if this slot is in use             */
} TaskFault_RegisteredTask_St;

/*===========================================================================
 *  Static Variables
 *=========================================================================*/

/** Registered task table. Indexed by slot, not task handle. */
static TaskFault_RegisteredTask_St s_registeredTasks[TASK_FAULT_MAX_REGISTERED];
static uint32_t s_registeredCount = 0U;

/** Rolling result buffer (circular). */
static TaskFault_ResultRecord_St s_resultBuffer[TASK_FAULT_RESULT_BUFFER_SIZE];
static uint32_t s_resultWriteIndex = 0U;
static uint32_t s_resultCount      = 0U;

/** Per-task active fault — stored in task-local via TLS-like mechanism.
 *  Since FreeRTOS doesn't have true TLS, we use a small lookup table
 *  keyed by the registered task slot. */
static TaskFault_Type_E s_activeFaults[TASK_FAULT_MAX_REGISTERED];
static boolean           s_faultEndChecked[TASK_FAULT_MAX_REGISTERED];

/** Init guard. */
static boolean s_initialized = FALSE;

/*===========================================================================
 *  Internal Helper Functions
 *=========================================================================*/

/**
 * @brief   Find the slot index for a registered task handle.
 * @param   task  Task handle to look up.
 * @return  Slot index (0..TASK_FAULT_MAX_REGISTERED-1), or
 *          TASK_FAULT_MAX_REGISTERED if not found.
 */
static uint32_t TaskFault_FindTaskSlot(TaskHandle_t task)
{
    uint32_t i;
    for (i = 0U; i < TASK_FAULT_MAX_REGISTERED; i++)
    {
        if ((s_registeredTasks[i].registered == TRUE) &&
            (s_registeredTasks[i].handle == task))
        {
            return i;
        }
    }
    return TASK_FAULT_MAX_REGISTERED;
}

/**
 * @brief   Push a result record into the rolling buffer.
 * @param   record  Result to push (copied by value).
 */
static void TaskFault_PushResult(const TaskFault_ResultRecord_St *record)
{
    taskENTER_CRITICAL();
    {
        s_resultBuffer[s_resultWriteIndex] = *record;
        s_resultWriteIndex = (s_resultWriteIndex + 1U) % TASK_FAULT_RESULT_BUFFER_SIZE;
        if (s_resultCount < TASK_FAULT_RESULT_BUFFER_SIZE)
        {
            s_resultCount++;
        }
    }
    taskEXIT_CRITICAL();
}

/*===========================================================================
 *  Public API Implementation
 *=========================================================================*/

void TaskFault_Init(void)
{
    if (s_initialized)
    {
        return;
    }

    (void)memset(s_registeredTasks, 0, sizeof(s_registeredTasks));
    (void)memset(s_resultBuffer,    0, sizeof(s_resultBuffer));
    (void)memset(s_activeFaults,    0, sizeof(s_activeFaults));
    s_registeredCount  = 0U;
    s_resultWriteIndex = 0U;
    s_resultCount      = 0U;
    s_initialized      = TRUE;
}

boolean TaskFault_RegisterTask(TaskHandle_t task, const char *taskName)
{
    if ((task == NULL) || (taskName == NULL))
    {
        return FALSE;
    }

    /* Check if already registered */
    if (TaskFault_FindTaskSlot(task) < TASK_FAULT_MAX_REGISTERED)
    {
        return TRUE; /* Already registered */
    }

    if (s_registeredCount >= TASK_FAULT_MAX_REGISTERED)
    {
        return FALSE; /* No free slots */
    }

    /* Find a free slot */
    uint32_t i;
    for (i = 0U; i < TASK_FAULT_MAX_REGISTERED; i++)
    {
        if (s_registeredTasks[i].registered == FALSE)
        {
            s_registeredTasks[i].handle     = task;
            s_registeredTasks[i].name       = taskName;
            s_registeredTasks[i].registered = TRUE;
            s_activeFaults[i]               = TASK_FAULT_NONE;
            s_faultEndChecked[i]            = FALSE;
            s_registeredCount++;
            return TRUE;
        }
    }

    return FALSE; /* Should not reach here */
}

boolean TaskFault_Inject(TaskHandle_t task, TaskFault_Type_E faultType)
{
    uint32_t slot;

    if (faultType == TASK_FAULT_NONE)
    {
        return FALSE;
    }

    slot = TaskFault_FindTaskSlot(task);
    if (slot >= TASK_FAULT_MAX_REGISTERED)
    {
        /* Task not registered — record as NOT_REGISTERED */
        TaskFault_ResultRecord_St record;
        (void)memset(&record, 0, sizeof(record));
        record.faultType   = faultType;
        record.result      = TASK_FAULT_RESULT_NOT_REGISTERED;
        record.taskHandle  = task;
        record.taskName    = "Unknown";
        record.injectTick  = xTaskGetTickCount();
        record.respondTick = 0U;
        TaskFault_PushResult(&record);
        return FALSE;
    }

    /* Prepare result record (pre-fill with PENDING) */
    TaskFault_ResultRecord_St record;
    (void)memset(&record, 0, sizeof(record));
    record.faultType   = faultType;
    record.result      = TASK_FAULT_RESULT_PENDING;
    record.taskHandle  = task;
    record.taskName    = s_registeredTasks[slot].name;
    record.injectTick  = xTaskGetTickCount();
    record.respondTick = 0U;

    /* Reset end-check flag for the new injection */
    s_faultEndChecked[slot] = FALSE;

    /* Push PENDING record immediately */
    TaskFault_PushResult(&record);

    /* Send notification to target task.
     * eSetValueWithOverwrite: if the task hasn't consumed the previous
     * notification, overwrite it. This prevents notification queue
     * overflow (each task has exactly 1 notification slot in FreeRTOS). */
    BaseType_t notifyResult = xTaskNotify(task,
        TASK_FAULT_NOTIFY_VALUE(faultType),
        eSetValueWithOverwrite);

    if (notifyResult != pdPASS)
    {
        /* Should not happen with eSetValueWithOverwrite, but be safe */
        record.result = TASK_FAULT_RESULT_FAILED;
        TaskFault_PushResult(&record);
        return FALSE;
    }

    return TRUE;
}

const TaskFault_ResultRecord_St *TaskFault_GetLatestResult(void)
{
    if (s_resultCount == 0U)
    {
        return NULL;
    }

    /* The write index points to the NEXT slot, so the latest is
     * (writeIndex - 1 + BUFFER_SIZE) % BUFFER_SIZE */
    uint32_t latest = (s_resultWriteIndex + TASK_FAULT_RESULT_BUFFER_SIZE - 1U)
                      % TASK_FAULT_RESULT_BUFFER_SIZE;
    return &s_resultBuffer[latest];
}

const TaskFault_ResultRecord_St *TaskFault_GetAllResults(uint32_t *outCount)
{
    *outCount = s_resultCount;
    return s_resultBuffer;
}

void TaskFault_ClearResults(void)
{
    taskENTER_CRITICAL();
    {
        (void)memset(s_resultBuffer, 0, sizeof(s_resultBuffer));
        s_resultWriteIndex = 0U;
        s_resultCount      = 0U;
    }
    taskEXIT_CRITICAL();
}

/*===========================================================================
 *  Task-Side Functions (called from target task context)
 *=========================================================================*/

void TaskFault_CheckNotification(void)
{
    uint32_t    notifyValue;
    uint32_t    slot;
    TaskHandle_t self = xTaskGetCurrentTaskHandle();

    /* Fast path: if no notification pending, return immediately */
    if (xTaskNotifyWait(0U, 0xFFFFFFFFU, &notifyValue, 0U) != pdTRUE)
    {
        return;
    }

    /* Verify magic prefix — ignore notifications not from us */
    if ((notifyValue & TASK_FAULT_NOTIFY_MASK) != TASK_FAULT_NOTIFY_MAGIC)
    {
        /* Not our notification. Re-post it.
         * Note: this means Task Notifications used by fault injection
         * coexist with other notification uses as long as the other uses
         * don't use the 0xFA prefix. */
        xTaskNotify(self, notifyValue, eSetValueWithOverwrite);
        return;
    }

    slot = TaskFault_FindTaskSlot(self);
    if (slot >= TASK_FAULT_MAX_REGISTERED)
    {
        /* Task not registered — should not happen if RegisterTask was called */
        return;
    }

    /* Set the active fault for this task */
    TaskFault_Type_E faultType = TASK_FAULT_FROM_NOTIFY(notifyValue);
    s_activeFaults[slot]       = faultType;
    s_faultEndChecked[slot]    = FALSE;
}

void TaskFault_ReportResult(TaskFault_Result_E result)
{
    TaskHandle_t self = xTaskGetCurrentTaskHandle();
    uint32_t slot = TaskFault_FindTaskSlot(self);

    if (slot >= TASK_FAULT_MAX_REGISTERED)
    {
        return; /* Not registered */
    }

    if (s_activeFaults[slot] == TASK_FAULT_NONE)
    {
        return; /* No active fault */
    }

    /* Record the result */
    TaskFault_ResultRecord_St record;
    (void)memset(&record, 0, sizeof(record));
    record.faultType    = s_activeFaults[slot];
    record.result       = result;
    record.taskHandle   = self;
    record.taskName     = s_registeredTasks[slot].name;
    record.injectTick   = 0U; /* Unknown at this point — injector fills */
    record.respondTick  = xTaskGetTickCount();
    TaskFault_PushResult(&record);

    /* Reset the active fault */
    s_activeFaults[slot]    = TASK_FAULT_NONE;
    s_faultEndChecked[slot] = TRUE;
}

TaskFault_Type_E TaskFault_GetActiveFault(void)
{
    TaskHandle_t self = xTaskGetCurrentTaskHandle();
    uint32_t slot = TaskFault_FindTaskSlot(self);

    if (slot >= TASK_FAULT_MAX_REGISTERED)
    {
        return TASK_FAULT_NONE;
    }

    return s_activeFaults[slot];
}

/**
 * @brief   End-of-iteration check. Called by TASK_FAULT_END_CHECK().
 * @details If a fault was injected but the task's code did not call
 *          TASK_FAULT_REPORT() during this iteration, auto-report FAILED.
 */
void TaskFault_EndOfIterationCheck(void)
{
    TaskHandle_t self = xTaskGetCurrentTaskHandle();
    uint32_t slot = TaskFault_FindTaskSlot(self);

    if (slot >= TASK_FAULT_MAX_REGISTERED)
    {
        return;
    }

    if (s_activeFaults[slot] != TASK_FAULT_NONE)
    {
        /* Fault was active but no one reported — auto FAIL */
        TaskFault_ReportResult(TASK_FAULT_RESULT_FAILED);
    }
}

/*===========================================================================
 *  Name Lookups
 *=========================================================================*/

const char *TaskFault_GetFaultName(TaskFault_Type_E faultType)
{
    switch (faultType)
    {
        case TASK_FAULT_NONE:              return "None";
#if (A66T_TASK_FAULT_SIM_NULL_HANDLE == STD_ON)
        case TASK_FAULT_SIM_NULL_HANDLE:   return "NullHandle";
#endif
#if (A66T_TASK_FAULT_SIM_INVALID_PARAM == STD_ON)
        case TASK_FAULT_SIM_INVALID_PARAM: return "InvalidParam";
#endif
#if (A66T_TASK_FAULT_SIM_TIMEOUT == STD_ON)
        case TASK_FAULT_SIM_TIMEOUT:       return "Timeout";
#endif
#if (A66T_TASK_FAULT_SIM_QUEUE_FULL == STD_ON)
        case TASK_FAULT_SIM_QUEUE_FULL:    return "QueueFull";
#endif
#if (A66T_TASK_FAULT_SIM_BUFFER_OVF == STD_ON)
        case TASK_FAULT_SIM_BUFFER_OVF:    return "BufferOverflow";
#endif
#if (A66T_TASK_FAULT_SIM_RESOURCE_LOST == STD_ON)
        case TASK_FAULT_SIM_RESOURCE_LOST: return "ResourceLost";
#endif
#if (A66T_TASK_FAULT_SIM_STATE_CORRUPT == STD_ON)
        case TASK_FAULT_SIM_STATE_CORRUPT: return "StateCorrupt";
#endif
#if (A66T_TASK_FAULT_REAL_STACK_DEPLETE == STD_ON)
        case TASK_FAULT_REAL_STACK_DEPLETE:return "StackDeplete";
#endif
        default:                           return "Unknown";
    }
}

const char *TaskFault_GetResultName(TaskFault_Result_E result)
{
    switch (result)
    {
        case TASK_FAULT_RESULT_PENDING:         return "PENDING";
        case TASK_FAULT_RESULT_PASSED:          return "PASSED";
        case TASK_FAULT_RESULT_FAILED:          return "FAILED";
        case TASK_FAULT_RESULT_TIMEOUT:         return "TIMEOUT";
        case TASK_FAULT_RESULT_NOT_REGISTERED:  return "NOT_REGISTERED";
        default:                                return "UNKNOWN";
    }
}

#endif /* A66T_TASK_FAULT_INJECT_ENABLE == STD_ON */

#ifdef __cplusplus
}
#endif

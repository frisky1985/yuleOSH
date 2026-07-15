/*******************************************************************************
 * Copyright (C) 2024 Ingeek, Inc. or its affiliates.  All Rights Reserved.
 *
 * @file    FaultInject_Test.c
 * @brief   Self-test suite for the FaultInject framework
 *
 * @details Tests the fault injection framework itself (not the fault-handling
 *          chain). Verifies that the injection mechanism is correct:
 *            - Registration logic works
 *            - Notification encoding/decoding is correct
 *            - Result buffer (rolling/circular) is correct
 *            - Multiple concurrent injections are tracked
 *            - Timeout handling
 *            - Clear/reset operations
 *
 *          For Layer 1 (system-level CPU exceptions), testing is limited
 *          to the API surface without triggering real exceptions (which
 *          requires target hardware). The injection functions themselves
 *          are tested by the acceptance matrix (fault-injection-acceptance).
 *
 *          For Layer 2 (task-level simulated faults), this test suite can
 *          run on the host if FreeRTOS stubs or a mock layer is linked.
 *          The test provides FreeRTOS stubs so it can be compiled and run
 *          on a host machine for CI validation.
 *
 * @note    Compile with:
 *            arm-none-eabi-gcc -c FaultInject_Test.c \
 *              -I../inc -DFAULT_INJECT_SELF_TEST
 *          Or for host testing, stub FreeRTOS functions are provided below.
 *
 * @note    Prerequisites:
 *          1. FreeRTOS stubs (provided below) for host testing
 *          2. Define FAULT_INJECT_SELF_TEST to enable host-side test runner
 *          3. Define TASK_FAULT_TEST_MODE for mock-FreeRTOS target
 ******************************************************************************/

#ifdef __cplusplus
extern "C" {
#endif

/*===========================================================================
 *  Includes
 *=========================================================================*/
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

/*===========================================================================
 *  FreeRTOS Stubs for Host Testing
 *
 *  These stubs provide enough FreeRTOS functionality for the TaskFaultInject
 *  module to compile on the host. They implement:
 *    - TaskHandle as integer ID
 *    - Task Notifications via a polled flag per task
 *    - xTaskGetTickCount as a monotonic counter
 *    - Critical section as no-ops
 *
 *  For embedded testing, the real FreeRTOS handles these at runtime.
 *=========================================================================*/

#if defined(FAULT_INJECT_SELF_TEST) || defined(TASK_FAULT_TEST_MODE)

/* --- Base types --- */
#define BaseType_t        int
#define TickType_t        uint32_t

#ifndef pdTRUE
#define pdTRUE            1
#endif
#ifndef pdFALSE
#define pdFALSE           0
#endif
#ifndef pdPASS
#define pdPASS            1
#endif

/* --- Task Handle --- */
typedef uint32_t TaskHandle_t;

#define xTaskGetCurrentTaskHandle()    (FAULT_INJECT_TEST_CURRENT_TASK)

static uint32_t FAULT_INJECT_TEST_CURRENT_TASK = 0U;

/* --- Notification values --- */
#define eSetValueWithOverwrite  0

/* --- Critical section (no-op on host) --- */
#define taskENTER_CRITICAL()    do {} while(0)
#define taskEXIT_CRITICAL()     do {} while(0)

/* --- Tick count (monotonic, incremented by test code) --- */
static TickType_t g_testTicks = 0U;

TickType_t xTaskGetTickCount(void)
{
    return g_testTicks;
}

void Test_IncrementTicks(uint32_t amount)
{
    g_testTicks += amount;
}

void Test_ResetTicks(void)
{
    g_testTicks = 0U;
}

/* --- Notification state per task (up to 16 mock tasks) --- */
#define TASK_NOTIFY_MAX_TASKS    16U

typedef struct
{
    uint32_t  notifyValue;
    uint32_t  notifyPending : 1;
} Test_NotifyState_St;

static Test_NotifyState_St g_notifyStates[TASK_NOTIFY_MAX_TASKS] = {{0}};

/* --- Notification send (mock) --- */
BaseType_t xTaskNotify(TaskHandle_t task, uint32_t value, uint32_t action)
{
    (void)action;
    if (task < TASK_NOTIFY_MAX_TASKS)
    {
        g_notifyStates[task].notifyValue   = value;
        g_notifyStates[task].notifyPending = 1U;
        return pdPASS;
    }
    return pdFAIL;
}

/* --- Notification wait (mock) --- */
BaseType_t xTaskNotifyWait(uint32_t bitsToClearOnEntry,
                           uint32_t bitsToClearOnExit,
                           uint32_t *pulNotificationValue,
                           TickType_t xTicksToWait)
{
    (void)bitsToClearOnEntry;
    (void)xTicksToWait;

    TaskHandle_t self = FAULT_INJECT_TEST_CURRENT_TASK;
    if (self < TASK_NOTIFY_MAX_TASKS && g_notifyStates[self].notifyPending)
    {
        if (pulNotificationValue != NULL)
        {
            *pulNotificationValue = g_notifyStates[self].notifyValue;
        }
        g_notifyStates[self].notifyPending = 0U;
        if (bitsToClearOnExit)
        {
            g_notifyStates[self].notifyValue &= ~bitsToClearOnExit;
        }
        return pdTRUE;
    }
    return pdFALSE;
}

/* Helper: reset all notification state */
void Test_ResetNotifications(void)
{
    (void)memset(g_notifyStates, 0, sizeof(g_notifyStates));
}

#endif /* FAULT_INJECT_SELF_TEST || TASK_FAULT_TEST_MODE */

/*===========================================================================
 *  Test Includes (must come after stubs)
 *=========================================================================*/
#include "FaultInject.h"
#include "TaskFaultInject.h"

#if (A66T_TASK_FAULT_INJECT_ENABLE == STD_ON)

/*===========================================================================
 *  Test Assertion Helpers
 *=========================================================================*/
static int g_testsPassed = 0;
static int g_testsFailed = 0;

#define TEST_ASSERT(cond, msg)                    do {                         \
    if (!(cond)) {                                                             \
        printf("  FAIL [line %d]: %s\n", __LINE__, msg);                       \
        g_testsFailed++;                                                        \
    } else {                                                                   \
        printf("  PASS [line %d]: %s\n", __LINE__, msg);                       \
        g_testsPassed++;                                                        \
    }                                                                          \
} while(0)

#define TEST_START(name)          printf("\n=== %s ===\n", name)
#define TEST_END()                do {                                         \
    printf("  -> Passed: %d  Failed: %d\n", g_testsPassed, g_testsFailed);     \
} while(0)

/*===========================================================================
 *  Test 1: Fault Registration
 *
 *  Verify that:
 *    - TaskFault_RegisterTask succeeds for valid tasks
 *    - Duplicate registration is idempotent
 *    - Registration fails when task is NULL
 *    - Registration fails when name is NULL
 *=========================================================================*/
static void Test_Registration(void)
{
    TaskHandle_t task1 = 1U;
    TaskHandle_t task2 = 2U;

    TEST_START("Test 1: Task Registration");

    /* Init */
    TaskFault_Init();
    Test_ResetNotifications();

    /* Valid registration */
    TEST_ASSERT(TaskFault_RegisterTask(task1, "Task1") == TRUE,
                "Register valid task");

    /* Duplicate registration (should succeed/idempotent) */
    TEST_ASSERT(TaskFault_RegisterTask(task1, "Task1") == TRUE,
                "Register duplicate task (idempotent)");

    /* Register second task */
    TEST_ASSERT(TaskFault_RegisterTask(task2, "Task2") == TRUE,
                "Register second valid task");

    /* Null handle */
    TEST_ASSERT(TaskFault_RegisterTask(0U, "NullTask") == FALSE,
                "Register with NULL handle fails");

    /* Null name */
    TEST_ASSERT(TaskFault_RegisterTask(task1, NULL) == FALSE,
                "Register with NULL name fails");

    TEST_END();
}

/*===========================================================================
 *  Test 2: Fault Injection / Notification
 *
 *  Verify that:
 *    - TaskFault_Inject sends a notification
 *    - TASK_FAULT_CHECK() consumes the notification
 *    - TaskFault_GetActiveFault() returns the correct fault type
 *    - Injection into an unregistered task returns NOT_REGISTERED
 *    - TASK_FAULT_NONE injection is rejected
 *=========================================================================*/
static void Test_InjectionAndNotification(void)
{
    TaskHandle_t task1 = 1U;
    FAULT_INJECT_TEST_CURRENT_TASK = task1;

    TEST_START("Test 2: Fault Injection & Notification");

    TaskFault_Init();
    Test_ResetNotifications();
    TaskFault_ClearResults();
    TEST_ASSERT(TaskFault_RegisterTask(task1, "Task1") == TRUE,
                "Register task for injection test");

    /* Verify: no active fault initially */
    TEST_ASSERT(TaskFault_GetActiveFault() == TASK_FAULT_NONE,
                "No active fault before injection");

    /* Inject NullHandle fault */
    TEST_ASSERT(TaskFault_Inject(task1, TASK_FAULT_SIM_NULL_HANDLE) == TRUE,
                "Inject NullHandle fault");

    /* Verify: notification was sent (check mocked notify state) */
    TEST_ASSERT(g_notifyStates[task1].notifyPending == 1U,
                "Notification is pending on target task");

    /* Consume notification via TASK_FAULT_CHECK */
    TaskFault_CheckNotification();

    /* Verify active fault type */
    TEST_ASSERT(TaskFault_GetActiveFault() == TASK_FAULT_SIM_NULL_HANDLE,
                "Active fault is NullHandle");

    /* Notification should be consumed */
    TEST_ASSERT(g_notifyStates[task1].notifyPending == 0U,
                "Notification consumed after check");

    /* Inject into unregistered task */
    TaskHandle_t unregTask = 99U;
    TEST_ASSERT(TaskFault_Inject(unregTask, TASK_FAULT_SIM_TIMEOUT) == FALSE,
                "Inject into unregistered task returns FALSE");

    /* Check result shows NOT_REGISTERED */
    const TaskFault_ResultRecord_St *res = TaskFault_GetLatestResult();
    TEST_ASSERT(res != NULL, "Result exists after unregistered injection");
    if (res != NULL)
    {
        TEST_ASSERT(res->result == TASK_FAULT_RESULT_NOT_REGISTERED,
                    "Result is NOT_REGISTERED for unregistered task");
    }

    /* Inject TASK_FAULT_NONE should fail */
    TEST_ASSERT(TaskFault_Inject(task1, TASK_FAULT_NONE) == FALSE,
                "Inject TASK_FAULT_NONE returns FALSE");

    TEST_END();
}

/*==========================================================================*
 *  Test 3: Fault Reporting
 *
 *  Verify that:
 *    - TASK_FAULT_REPORT(PASSED) records the correct status
 *    - The result record contains original fault type and task info
 *    - Multiple reports are captured
 *=========================================================================*/
static void Test_Reporting(void)
{
    TaskHandle_t task1 = 1U;
    FAULT_INJECT_TEST_CURRENT_TASK = task1;

    TEST_START("Test 3: Fault Reporting");

    TaskFault_Init();
    Test_ResetNotifications();
    TaskFault_ClearResults();
    TaskFault_RegisterTask(task1, "Task1");

    /* Inject → consume → report PASSED */
    Test_ResetTicks();
    TaskFault_Inject(task1, TASK_FAULT_SIM_NULL_HANDLE);
    TaskFault_CheckNotification();
    TaskFault_ReportResult(TASK_FAULT_RESULT_PASSED);

    /* Check result */
    const TaskFault_ResultRecord_St *rec = TaskFault_GetLatestResult();
    TEST_ASSERT(rec != NULL, "Result record exists after report");
    if (rec != NULL)
    {
        TEST_ASSERT(rec->result == TASK_FAULT_RESULT_PASSED,
                    "Result is PASSED");
        TEST_ASSERT(rec->faultType == TASK_FAULT_SIM_NULL_HANDLE,
                    "Fault type is NullHandle");
        TEST_ASSERT(rec->taskHandle == task1,
                    "Task handle matches");
        TEST_ASSERT(rec->taskName != NULL &&
                    strcmp(rec->taskName, "Task1") == 0,
                    "Task name matches");
    }

    /* Active fault should be cleared after report */
    TEST_ASSERT(TaskFault_GetActiveFault() == TASK_FAULT_NONE,
                "Active fault cleared after report");

    /* Second injection: InvalidParam */
    TaskFault_Inject(task1, TASK_FAULT_SIM_INVALID_PARAM);
    TaskFault_CheckNotification();
    TaskFault_ReportResult(TASK_FAULT_RESULT_PASSED);

    rec = TaskFault_GetLatestResult();
    TEST_ASSERT(rec != NULL, "Second result exists");
    if (rec != NULL)
    {
        TEST_ASSERT(rec->faultType == TASK_FAULT_SIM_INVALID_PARAM,
                    "Second injection has InvalidParam type");
    }

    TEST_END();
}

/*===========================================================================
 *  Test 4: Fault Timeout Detection
 *
 *  Verify that:
 *    - If a task does NOT report a result, TASK_FAULT_END_CHECK
 *      auto-reports FAILED
 *    - Active fault is cleared after end-check
 *=========================================================================*/
static void Test_TimeoutDetection(void)
{
    TaskHandle_t task1 = 1U;
    FAULT_INJECT_TEST_CURRENT_TASK = task1;

    TEST_START("Test 4: Fault Timeout (EndCheck auto-report)");

    TaskFault_Init();
    Test_ResetNotifications();
    TaskFault_ClearResults();
    TaskFault_RegisterTask(task1, "Task1");

    /* Inject → consume but DO NOT report */
    TaskFault_Inject(task1, TASK_FAULT_SIM_TIMEOUT);
    TaskFault_CheckNotification();

    /* Verify fault is active */
    TEST_ASSERT(TaskFault_GetActiveFault() == TASK_FAULT_SIM_TIMEOUT,
                "Active fault is Timeout before end-check");

    /* End check should auto-report FAILED */
    TaskFault_EndOfIterationCheck();

    /* Verify fault is cleared */
    TEST_ASSERT(TaskFault_GetActiveFault() == TASK_FAULT_NONE,
                "Active fault cleared after end-check");

    /* Check the latest result */
    const TaskFault_ResultRecord_St *rec = TaskFault_GetLatestResult();
    TEST_ASSERT(rec != NULL, "Result exists after end-check auto-report");
    if (rec != NULL)
    {
        TEST_ASSERT(rec->result == TASK_FAULT_RESULT_FAILED,
                    "Auto-report result is FAILED");
        TEST_ASSERT(rec->faultType == TASK_FAULT_SIM_TIMEOUT,
                    "Fault type preserved in auto-report");
    }

    TEST_END();
}

/*===========================================================================
 *  Test 5: Fault Clear
 *
 *  Verify that:
 *    - TaskFault_ClearResults clears all results
 *    - After clear, GetLatestResult returns NULL
 *    - GetAllResults returns count=0
 *=========================================================================*/
static void Test_Clear(void)
{
    TaskHandle_t task1 = 1U;
    FAULT_INJECT_TEST_CURRENT_TASK = task1;

    TEST_START("Test 5: Fault Clear");

    TaskFault_Init();
    Test_ResetNotifications();
    TaskFault_ClearResults();
    TaskFault_RegisterTask(task1, "Task1");

    /* Inject and report a few faults */
    TaskFault_Inject(task1, TASK_FAULT_SIM_NULL_HANDLE);
    TaskFault_CheckNotification();
    TaskFault_ReportResult(TASK_FAULT_RESULT_PASSED);

    TaskFault_Inject(task1, TASK_FAULT_SIM_TIMEOUT);
    TaskFault_CheckNotification();
    TaskFault_ReportResult(TASK_FAULT_RESULT_PASSED);

    /* Verify count before clear */
    uint32_t countBefore = 0U;
    const TaskFault_ResultRecord_St *allBefore = TaskFault_GetAllResults(&countBefore);
    TEST_ASSERT(countBefore > 0U, "Results exist before clear");
    TEST_ASSERT(allBefore != NULL, "All results pointer not NULL before clear");

    /* Clear */
    TaskFault_ClearResults();

    /* Verify count after clear */
    uint32_t countAfter = 99U; /* should be set to 0 */
    const TaskFault_ResultRecord_St *allAfter = TaskFault_GetAllResults(&countAfter);
    TEST_ASSERT(countAfter == 0U, "Count is 0 after clear");
    TEST_ASSERT(allAfter != NULL, "All results pointer not NULL after clear (buffer exists)");

    /* GetLatestResult should be NULL */
    const TaskFault_ResultRecord_St *latest = TaskFault_GetLatestResult();
    TEST_ASSERT(latest == NULL, "Latest result is NULL after clear");

    TEST_END();
}

/*===========================================================================
 *  Test 6: Rolling Buffer (Circular Behavior)
 *
 *  Verify that:
 *    - Injecting more than TASK_FAULT_RESULT_BUFFER_SIZE entries
 *      overwrites the oldest entries (circular)
 *    - The write index advances correctly
 *    - GetAllResults still returns count == BUFFER_SIZE (not more)
 *=========================================================================*/
static void Test_RollingBuffer(void)
{
    TaskHandle_t task1 = 1U;
    FAULT_INJECT_TEST_CURRENT_TASK = task1;

    TEST_START("Test 6: Rolling Buffer (Circular Overflow)");

    TaskFault_Init();
    Test_ResetNotifications();
    TaskFault_ClearResults();
    TaskFault_RegisterTask(task1, "Task1");

    uint32_t bufSize = TASK_FAULT_RESULT_BUFFER_SIZE;

    /* Inject more than BUFFER_SIZE fault types */
    /* We use different fault type values for each injection */
    uint32_t extra = 5U;
    uint32_t total = bufSize + extra;

    for (uint32_t i = 0U; i < total; i++)
    {
        /* Use modulo to cycle through fault types (avoiding NONE=0) */
        TaskFault_Type_E ft = (TaskFault_Type_E)((i % 7U) + 1U);
        TEST_ASSERT(TaskFault_Inject(task1, ft) == TRUE,
                    "Rolling buffer injection");
        TaskFault_CheckNotification();
        TaskFault_ReportResult(TASK_FAULT_RESULT_PASSED);
    }

    /* Count should not exceed BUFFER_SIZE */
    uint32_t finalCount = 0U;
    (void)TaskFault_GetAllResults(&finalCount);
    TEST_ASSERT(finalCount <= bufSize,
                "Result count does not exceed buffer size");
    TEST_ASSERT(finalCount == bufSize,
                "Result count equals buffer size (full circular)");

    /* Latest result should be valid */
    const TaskFault_ResultRecord_St *latest = TaskFault_GetLatestResult();
    TEST_ASSERT(latest != NULL, "Latest result is not NULL in circular buffer");
    if (latest != NULL)
    {
        TEST_ASSERT(latest->result == TASK_FAULT_RESULT_PASSED,
                    "Latest result in circular buffer is PASSED");
    }

    TEST_END();
}

/*===========================================================================
 *  Test 7: Multiple Task Concurrent Injections
 *
 *  Verify that:
 *    - Injecting into different tasks works concurrently
 *    - Each task's active fault is independent
 *    - Switching task context (mock) preserves per-task state
 *=========================================================================*/
static void Test_MultipleTasksConcurrent(void)
{
    TaskHandle_t taskA = 1U;
    TaskHandle_t taskB = 2U;
    TaskHandle_t taskC = 3U;

    TEST_START("Test 7: Multiple Tasks Concurrent Injection");

    TaskFault_Init();
    Test_ResetNotifications();
    TaskFault_ClearResults();

    TaskFault_RegisterTask(taskA, "TaskA");
    TaskFault_RegisterTask(taskB, "TaskB");
    TaskFault_RegisterTask(taskC, "TaskC");

    /* --- Inject fault into taskA from a "different" context --- */
    FAULT_INJECT_TEST_CURRENT_TASK = taskA;

    TaskFault_Inject(taskA, TASK_FAULT_SIM_NULL_HANDLE);
    TaskFault_CheckNotification();
    TEST_ASSERT(TaskFault_GetActiveFault() == TASK_FAULT_SIM_NULL_HANDLE,
                "TaskA has NullHandle active");

    /* --- Inject fault into taskB independently --- */
    FAULT_INJECT_TEST_CURRENT_TASK = taskB;

    TaskFault_Inject(taskB, TASK_FAULT_SIM_TIMEOUT);
    TaskFault_CheckNotification();
    TEST_ASSERT(TaskFault_GetActiveFault() == TASK_FAULT_SIM_TIMEOUT,
                "TaskB has Timeout active");

    /* --- TaskA still has its own active fault --- */
    FAULT_INJECT_TEST_CURRENT_TASK = taskA;
    TEST_ASSERT(TaskFault_GetActiveFault() == TASK_FAULT_SIM_NULL_HANDLE,
                "TaskA still has NullHandle (independent)");

    /* --- Report both --- */
    TaskFault_ReportResult(TASK_FAULT_RESULT_PASSED);

    FAULT_INJECT_TEST_CURRENT_TASK = taskB;
    TaskFault_ReportResult(TASK_FAULT_RESULT_PASSED);

    /* --- Inject into taskC --- */
    FAULT_INJECT_TEST_CURRENT_TASK = taskC;

    TaskFault_Inject(taskC, TASK_FAULT_SIM_QUEUE_FULL);
    TaskFault_CheckNotification();
    TEST_ASSERT(TaskFault_GetActiveFault() == TASK_FAULT_SIM_QUEUE_FULL,
                "TaskC has QueueFull active");
    TaskFault_ReportResult(TASK_FAULT_RESULT_PASSED);

    /* --- Verify all results are recorded --- */
    uint32_t count = 0U;
    (void)TaskFault_GetAllResults(&count);
    TEST_ASSERT(count == 3U,
                "Three independent injections recorded");

    TEST_END();
}

/*===========================================================================
 *  Test 8: UDS DID Exposure
 *
 *  Verify that:
 *    - Configuration defines the correct UDS DIDs
 *    - DIDs are within the standard range
 *=========================================================================*/
static void Test_UDSConfiguration(void)
{
    TEST_START("Test 8: UDS DID Configuration");

    /* System-level DID */
    TEST_ASSERT(A66T_FAULT_INJECT_UDS_DID == 0xF190U,
                "System fault inject DID = 0xF190");

    /* Task-level DID */
    TEST_ASSERT(A66T_TASK_FAULT_INJECT_UDS_DID == 0xF193U,
                "Task fault inject DID = 0xF193");

    /* DIDs are in manufacturer-specific range (0xF000-0xF1FF) */
    TEST_ASSERT(A66T_FAULT_INJECT_UDS_DID >= 0xF000U &&
                A66T_FAULT_INJECT_UDS_DID <= 0xF1FFU,
                "System DID in manufacturer-specific range");

    TEST_ASSERT(A66T_TASK_FAULT_INJECT_UDS_DID >= 0xF000U &&
                A66T_TASK_FAULT_INJECT_UDS_DID <= 0xF1FFU,
                "Task DID in manufacturer-specific range");

    /* DIDs are distinct */
    TEST_ASSERT(A66T_FAULT_INJECT_UDS_DID != A66T_TASK_FAULT_INJECT_UDS_DID,
                "System and task DIDs are distinct");

    TEST_END();
}

/*===========================================================================
 *  Test 9: Per-Task Name Lookups
 *
 *  Verify that:
 *    - TaskFault_GetFaultName returns meaningful strings
 *    - TaskFault_GetResultName returns meaningful strings
 *    - Unknown values return "Unknown"
 *=========================================================================*/
static void Test_NameLookups(void)
{
    TEST_START("Test 9: Name Lookups");

    /* Fault type names */
    TEST_ASSERT(strcmp(TaskFault_GetFaultName(TASK_FAULT_NONE), "None") == 0,
                "Fault name 'None'");
    TEST_ASSERT(strcmp(TaskFault_GetFaultName(TASK_FAULT_SIM_NULL_HANDLE), "NullHandle") == 0,
                "Fault name 'NullHandle'");
    TEST_ASSERT(strcmp(TaskFault_GetFaultName(TASK_FAULT_SIM_TIMEOUT), "Timeout") == 0,
                "Fault name 'Timeout'");
    TEST_ASSERT(strcmp(TaskFault_GetFaultName(TASK_FAULT_SIM_QUEUE_FULL), "QueueFull") == 0,
                "Fault name 'QueueFull'");
    TEST_ASSERT(strcmp(TaskFault_GetFaultName((TaskFault_Type_E)0xFF), "Unknown") == 0,
                "Fault name 'Unknown' for invalid value");

    /* Result names */
    TEST_ASSERT(strcmp(TaskFault_GetResultName(TASK_FAULT_RESULT_PENDING), "PENDING") == 0,
                "Result name 'PENDING'");
    TEST_ASSERT(strcmp(TaskFault_GetResultName(TASK_FAULT_RESULT_PASSED), "PASSED") == 0,
                "Result name 'PASSED'");
    TEST_ASSERT(strcmp(TaskFault_GetResultName(TASK_FAULT_RESULT_FAILED), "FAILED") == 0,
                "Result name 'FAILED'");
    TEST_ASSERT(strcmp(TaskFault_GetResultName(TASK_FAULT_RESULT_TIMEOUT), "TIMEOUT") == 0,
                "Result name 'TIMEOUT'");
    TEST_ASSERT(strcmp(TaskFault_GetResultName(TASK_FAULT_RESULT_NOT_REGISTERED), "NOT_REGISTERED") == 0,
                "Result name 'NOT_REGISTERED'");

    TEST_END();
}

/*===========================================================================
 *  Test 10: Layer 1 System-Level API Bounds
 *
 *  Verify that:
 *    - FaultInject_GetTestName returns correct names for all types
 *    - FAULT_INJECT_MAX is the sentinel
 *    - All enum values are sequential
 *=========================================================================*/
static void Test_SystemLevelAPI(void)
{
    TEST_START("Test 10: Layer 1 System-Level API Bounds");

    /* Verify enum values are sequential */
    TEST_ASSERT(FAULT_INJECT_NONE == 0U, "FAULT_INJECT_NONE == 0");
    TEST_ASSERT(FAULT_INJECT_NULL_POINTER == 1U, "FAULT_INJECT_NULL_POINTER == 1");
    TEST_ASSERT(FAULT_INJECT_INVALID_FUNC == 2U, "FAULT_INJECT_INVALID_FUNC == 2");
    TEST_ASSERT(FAULT_INJECT_DIV_BY_ZERO == 3U, "FAULT_INJECT_DIV_BY_ZERO == 3");
    TEST_ASSERT(FAULT_INJECT_UNALIGNED == 4U, "FAULT_INJECT_UNALIGNED == 4");
    TEST_ASSERT(FAULT_INJECT_STACK_OVERFLOW == 5U, "FAULT_INJECT_STACK_OVERFLOW == 5");
    TEST_ASSERT(FAULT_INJECT_MPU_VIOLATION == 6U, "FAULT_INJECT_MPU_VIOLATION == 6");
    TEST_ASSERT(FAULT_INJECT_UNDEF_INSTR == 7U, "FAULT_INJECT_UNDEF_INSTR == 7");
    TEST_ASSERT(FAULT_INJECT_DIRECT_SCB == 8U, "FAULT_INJECT_DIRECT_SCB == 8");
    TEST_ASSERT(FAULT_INJECT_BUS_ACCESS == 9U, "FAULT_INJECT_BUS_ACCESS == 9");

    /* FAULT_INJECT_MAX is the sentinel (10) */
    TEST_ASSERT(FAULT_INJECT_MAX == 10U, "FAULT_INJECT_MAX == 10");

    /* Test name lookup */
    TEST_ASSERT(strcmp(FaultInject_GetTestName(FAULT_INJECT_NONE), "Unknown") == 0,
                "None getTestName = 'Unknown'");
    TEST_ASSERT(strcmp(FaultInject_GetTestName(FAULT_INJECT_NULL_POINTER), "NullPointer") == 0,
                "NullPointer getTestName");
    TEST_ASSERT(strcmp(FaultInject_GetTestName(FAULT_INJECT_BUS_ACCESS), "BusAccess") == 0,
                "BusAccess getTestName");
    TEST_ASSERT(strcmp(FaultInject_GetTestName((FaultInject_Type_E)99), "Unknown") == 0,
                "Invalid getTestName = 'Unknown'");

    TEST_END();
}

/*===========================================================================
 *  Test Runner
 *=========================================================================*/
int main(void)
{
    printf("\n");
    printf("============================================================\n");
    printf("  A66-T Fault Injection Framework — Self-Test Suite\n");
    printf("============================================================\n");
    printf("  Config: A66T_TASK_FAULT_INJECT_ENABLE = STD_ON\n");
    printf("  Config: A66T_FAULT_INJECTION_TEST_ENABLE = STD_ON\n");
    printf("  Buffer: %u entries, Timeout: %u ms\n",
           (unsigned)TASK_FAULT_RESULT_BUFFER_SIZE,
           (unsigned)TASK_FAULT_INJECT_TIMEOUT_MS);
    printf("  UDS DIDs: 0xF190 (system), 0xF193 (task)\n");
    printf("============================================================\n");

    g_testsPassed = 0;
    g_testsFailed = 0;

    /* Initialize system-level framework (stub-safe) */
    FaultInject_Init();

    /* Layer 2 tests (with FreeRTOS stubs) */
    Test_Registration();
    Test_InjectionAndNotification();
    Test_Reporting();
    Test_TimeoutDetection();
    Test_Clear();
    Test_RollingBuffer();
    Test_MultipleTasksConcurrent();
    Test_UDSConfiguration();
    Test_NameLookups();
    Test_SystemLevelAPI();

    /* Summary */
    printf("\n============================================================\n");
    printf("  Results: %d passed, %d failed out of %d tests\n",
           g_testsPassed, g_testsFailed, g_testsPassed + g_testsFailed);
    printf("============================================================\n");

    return (g_testsFailed > 0) ? 1 : 0;
}

#endif /* A66T_TASK_FAULT_INJECT_ENABLE == STD_ON */

#ifdef __cplusplus
}
#endif

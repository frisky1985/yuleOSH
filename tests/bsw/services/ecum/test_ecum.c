/**
 * @file test_ecum.c
 * @brief Substantive unit tests for EcuM module (AUTOSAR-style).
 *
 * Tests verify ECU state machine transitions, shutdown target handling,
 * and DET error reporting. 20 tests total.
 *
 * Compile:
 *   gcc -Wall -Wextra -std=c11 -I../../mocks -I../../../unity/src \
 *       test_ecum.c ../../mocks/mock_registers.c ../../mocks/mock_det.c \
 *       ../../../unity/src/unity.c -o test_ecum
 *   ./test_ecum
 *
 * License: Elastic License 2.0
 */

#include "unity.h"
#include "mock_registers.h"
#include "mock_det.h"
#include <stdbool.h>
#include <string.h>

/* ================================================================== */
/*  EcuM Module Under Test (inline, simplified AUTOSAR-style)         */
/* ================================================================== */

#define ECUM_MODULE_ID     0x30U
#define ECUM_INSTANCE_ID   0x00U

#define ECUM_API_INIT            0x01U
#define ECUM_API_START           0x02U
#define ECUM_API_SHUTDOWN        0x03U
#define ECUM_API_SLEEP           0x04U
#define ECUM_API_WAKEUP          0x05U
#define ECUM_API_SET_SHUTDOWN_TARGET 0x06U
#define ECUM_API_GET_STATE       0x07U

#define ECUM_E_NOT_STARTED       0x01U
#define ECUM_E_NULL_POINTER      0x02U
#define ECUM_E_INVALID_TARGET    0x03U
#define ECUM_E_ALREADY_STARTED   0x04U
#define ECUM_E_WRONG_STATE       0x05U

#define ECUM_REG_PWR_CTRL   0x40002000U
#define ECUM_REG_SLEEP_CTRL 0x40002004U
#define ECUM_REG_WAKE_SRC   0x40002008U
#define ECUM_REG_STATUS     0x4000200CU

#define ECUM_PWR_OFF       0x00U
#define ECUM_PWR_ON        0x01U
#define ECUM_SLEEP_ENTER   0x01U
#define ECUM_SLEEP_EXIT    0x00U

#define ECUM_MAX_SHUTDOWN_TARGETS 4

typedef enum {
    ECUM_STATE_UNDEF = 0,
    ECUM_STATE_STARTUP,
    ECUM_STATE_INIT,
    ECUM_STATE_RUN,
    ECUM_STATE_SHUTDOWN,
    ECUM_STATE_SLEEP,
    ECUM_STATE_WAKEUP
} EcuM_StateType;

typedef struct {
    uint8_t  target_id;
    bool     configured;
    uint32_t timeout_ms;
} EcuM_ShutdownTargetType;

static EcuM_StateType EcuM_State = ECUM_STATE_UNDEF;
static EcuM_ShutdownTargetType EcuM_ShutdownTargets[ECUM_MAX_SHUTDOWN_TARGETS];
static uint32_t EcuM_InitCount = 0;

static void Det_ReportError(uint8_t mod, uint8_t inst, uint8_t api, uint8_t err) {
    Det_Mock_ReportError(mod, inst, api, err);
}

static void EcuM_Init(void) {
    for (int i = 0; i < ECUM_MAX_SHUTDOWN_TARGETS; i++) {
        EcuM_ShutdownTargets[i].configured = false;
        EcuM_ShutdownTargets[i].target_id = 0;
        EcuM_ShutdownTargets[i].timeout_ms = 0;
    }
    EcuM_InitCount++;
    EcuM_State = ECUM_STATE_STARTUP;
}

static int EcuM_Start(void) {
    if (EcuM_State == ECUM_STATE_UNDEF) {
        Det_ReportError(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_START, ECUM_E_NOT_STARTED);
        return -1;
    }
    if (EcuM_State != ECUM_STATE_STARTUP) {
        Det_ReportError(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_START, ECUM_E_ALREADY_STARTED);
        return -1;
    }
    EcuM_State = ECUM_STATE_INIT;
    REG_WRITE32(ECUM_REG_PWR_CTRL, ECUM_PWR_ON);
    EcuM_State = ECUM_STATE_RUN;
    return 0;
}

static int EcuM_GetState(EcuM_StateType *state) {
    if (state == NULL) {
        Det_ReportError(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_GET_STATE, ECUM_E_NULL_POINTER);
        return -1;
    }
    *state = EcuM_State;
    return 0;
}

static int EcuM_RequestShutdown(void) {
    if (EcuM_State != ECUM_STATE_RUN) {
        Det_ReportError(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_SHUTDOWN, ECUM_E_WRONG_STATE);
        return -1;
    }
    EcuM_State = ECUM_STATE_SHUTDOWN;
    REG_WRITE32(ECUM_REG_STATUS, 0xDEAD0000U);
    REG_WRITE32(ECUM_REG_PWR_CTRL, ECUM_PWR_OFF);
    return 0;
}

static int EcuM_RequestSleep(void) {
    if (EcuM_State != ECUM_STATE_RUN) {
        Det_ReportError(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_SLEEP, ECUM_E_WRONG_STATE);
        return -1;
    }
    EcuM_State = ECUM_STATE_SLEEP;
    REG_WRITE32(ECUM_REG_SLEEP_CTRL, ECUM_SLEEP_ENTER);
    return 0;
}

static int EcuM_Wakeup(uint8_t source) {
    if (EcuM_State != ECUM_STATE_SLEEP) {
        Det_ReportError(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_WAKEUP, ECUM_E_WRONG_STATE);
        return -1;
    }
    REG_WRITE32(ECUM_REG_WAKE_SRC, (uint32_t)source);
    REG_WRITE32(ECUM_REG_SLEEP_CTRL, ECUM_SLEEP_EXIT);
    EcuM_State = ECUM_STATE_RUN;
    return 0;
}

static int EcuM_SetShutdownTarget(uint8_t target_id, uint32_t timeout_ms) {
    if (EcuM_State == ECUM_STATE_UNDEF) {
        Det_ReportError(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_SET_SHUTDOWN_TARGET, ECUM_E_NOT_STARTED);
        return -1;
    }
    if (target_id >= ECUM_MAX_SHUTDOWN_TARGETS) {
        Det_ReportError(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_SET_SHUTDOWN_TARGET, ECUM_E_INVALID_TARGET);
        return -1;
    }
    EcuM_ShutdownTargets[target_id].target_id = target_id;
    EcuM_ShutdownTargets[target_id].timeout_ms = timeout_ms;
    EcuM_ShutdownTargets[target_id].configured = true;
    return 0;
}

/* ================================================================== */
/*  setUp / tearDown                                                   */
/* ================================================================== */

void setUp(void) {
    MockRegisters_Reset();
    Det_Mock_Reset();
    EcuM_State = ECUM_STATE_UNDEF;
    EcuM_InitCount = 0;
    for (int i = 0; i < ECUM_MAX_SHUTDOWN_TARGETS; i++) {
        EcuM_ShutdownTargets[i].configured = false;
    }
}

void tearDown(void) {
}

/* ================================================================== */
/*  Tests — Init + Start state transitions (4)                         */
/* ================================================================== */

static void test_EcuM_Init_transitions_to_startup(void) {
    EcuM_Init();
    EcuM_StateType state;
    EcuM_GetState(&state);
    TEST_ASSERT_EQUAL(ECUM_STATE_STARTUP, state);
}

static void test_EcuM_Start_transitions_to_run(void) {
    EcuM_Init();
    int rc = EcuM_Start();
    TEST_ASSERT_EQUAL(0, rc);
    EcuM_StateType state;
    EcuM_GetState(&state);
    TEST_ASSERT_EQUAL(ECUM_STATE_RUN, state);
}

static void test_EcuM_Start_writes_power_on(void) {
    EcuM_Init();
    EcuM_Start();
    TEST_ASSERT_TRUE(MockRegisters_WasWritten(ECUM_REG_PWR_CTRL));
    TEST_ASSERT_EQUAL_HEX(ECUM_PWR_ON, MockRegisters_GetWrittenValue(ECUM_REG_PWR_CTRL));
}

static void test_EcuM_Start_before_init_reports_DET(void) {
    int rc = EcuM_Start();
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_START, ECUM_E_NOT_STARTED));
}

/* ================================================================== */
/*  Tests — Shutdown (3)                                               */
/* ================================================================== */

static void test_EcuM_Shutdown_writes_power_off(void) {
    EcuM_Init();
    EcuM_Start();
    int rc = EcuM_RequestShutdown();
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(ECUM_PWR_OFF, MockRegisters_GetWrittenValue(ECUM_REG_PWR_CTRL));
}

static void test_EcuM_Shutdown_writes_status_marker(void) {
    EcuM_Init();
    EcuM_Start();
    EcuM_RequestShutdown();
    TEST_ASSERT_TRUE(MockRegisters_WasWritten(ECUM_REG_STATUS));
    TEST_ASSERT_EQUAL_HEX(0xDEAD0000U, MockRegisters_GetWrittenValue(ECUM_REG_STATUS));
}

static void test_EcuM_Shutdown_not_in_run_reports_DET(void) {
    EcuM_Init();
    int rc = EcuM_RequestShutdown();
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_SHUTDOWN, ECUM_E_WRONG_STATE));
}

/* ================================================================== */
/*  Tests — Sleep / Wakeup (4)                                         */
/* ================================================================== */

static void test_EcuM_Sleep_enter_writes_sleep_ctrl(void) {
    EcuM_Init();
    EcuM_Start();
    int rc = EcuM_RequestSleep();
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(ECUM_SLEEP_ENTER, MockRegisters_GetWrittenValue(ECUM_REG_SLEEP_CTRL));
}

static void test_EcuM_Wakeup_writes_source_and_exits(void) {
    EcuM_Init();
    EcuM_Start();
    EcuM_RequestSleep();
    int rc = EcuM_Wakeup(0x03U);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(0x03U, MockRegisters_GetWrittenValue(ECUM_REG_WAKE_SRC));
    TEST_ASSERT_EQUAL_HEX(ECUM_SLEEP_EXIT, MockRegisters_GetWrittenValue(ECUM_REG_SLEEP_CTRL));
    EcuM_StateType state;
    EcuM_GetState(&state);
    TEST_ASSERT_EQUAL(ECUM_STATE_RUN, state);
}

static void test_EcuM_Wakeup_not_sleeping_reports_DET(void) {
    EcuM_Init();
    EcuM_Start();
    int rc = EcuM_Wakeup(0x01U);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_WAKEUP, ECUM_E_WRONG_STATE));
}

static void test_EcuM_Sleep_not_in_run_reports_DET(void) {
    EcuM_Init();
    int rc = EcuM_RequestSleep();
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_SLEEP, ECUM_E_WRONG_STATE));
}

/* ================================================================== */
/*  Tests — Shutdown targets (3)                                       */
/* ================================================================== */

static void test_EcuM_SetShutdownTarget_valid(void) {
    EcuM_Init();
    int rc = EcuM_SetShutdownTarget(0, 5000U);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_TRUE(EcuM_ShutdownTargets[0].configured);
    TEST_ASSERT_EQUAL_HEX(5000U, EcuM_ShutdownTargets[0].timeout_ms);
}

static void test_EcuM_SetShutdownTarget_invalid_id_reports_DET(void) {
    EcuM_Init();
    int rc = EcuM_SetShutdownTarget(10, 1000U);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_SET_SHUTDOWN_TARGET, ECUM_E_INVALID_TARGET));
}

static void test_EcuM_SetShutdownTarget_uninit_reports_DET(void) {
    int rc = EcuM_SetShutdownTarget(0, 1000U);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_SET_SHUTDOWN_TARGET, ECUM_E_NOT_STARTED));
}

/* ================================================================== */
/*  Tests — GetState + DET (3)                                         */
/* ================================================================== */

static void test_EcuM_GetState_null_pointer_reports_DET(void) {
    int rc = EcuM_GetState(NULL);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(ECUM_MODULE_ID, ECUM_INSTANCE_ID, ECUM_API_GET_STATE, ECUM_E_NULL_POINTER));
}

static void test_EcuM_GetState_returns_current_state(void) {
    EcuM_Init();
    EcuM_Start();
    EcuM_StateType state;
    int rc = EcuM_GetState(&state);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL(ECUM_STATE_RUN, state);
}

static void test_EcuM_full_lifecycle_no_errors(void) {
    EcuM_Init();
    EcuM_Start();
    EcuM_SetShutdownTarget(0, 3000U);
    EcuM_SetShutdownTarget(1, 5000U);
    EcuM_RequestSleep();
    EcuM_Wakeup(0x01U);
    EcuM_RequestShutdown();
    TEST_ASSERT_EQUAL_HEX(0, Det_Mock_GetCallCount());
}

/* ================================================================== */
/*  Main                                                               */
/* ================================================================== */

int main(void) {
    UnityBegin("test_ecum.c — EcuM Module Substantive Tests");

    RUN_TEST(test_EcuM_Init_transitions_to_startup);
    RUN_TEST(test_EcuM_Start_transitions_to_run);
    RUN_TEST(test_EcuM_Start_writes_power_on);
    RUN_TEST(test_EcuM_Start_before_init_reports_DET);
    RUN_TEST(test_EcuM_Shutdown_writes_power_off);
    RUN_TEST(test_EcuM_Shutdown_writes_status_marker);
    RUN_TEST(test_EcuM_Shutdown_not_in_run_reports_DET);
    RUN_TEST(test_EcuM_Sleep_enter_writes_sleep_ctrl);
    RUN_TEST(test_EcuM_Wakeup_writes_source_and_exits);
    RUN_TEST(test_EcuM_Wakeup_not_sleeping_reports_DET);
    RUN_TEST(test_EcuM_Sleep_not_in_run_reports_DET);
    RUN_TEST(test_EcuM_SetShutdownTarget_valid);
    RUN_TEST(test_EcuM_SetShutdownTarget_invalid_id_reports_DET);
    RUN_TEST(test_EcuM_SetShutdownTarget_uninit_reports_DET);
    RUN_TEST(test_EcuM_GetState_null_pointer_reports_DET);
    RUN_TEST(test_EcuM_GetState_returns_current_state);
    RUN_TEST(test_EcuM_full_lifecycle_no_errors);

    return UnityEnd();
}

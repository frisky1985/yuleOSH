/**
 * @file test_wdg.c
 * @brief Substantive unit tests for Wdg module (AUTOSAR-style).
 *
 * Tests verify watchdog state machine transitions, register operations,
 * and DET parameter validation. 16 tests total.
 *
 * Compile:
 *   gcc -Wall -Wextra -std=c11 -I../../mocks -I../../../unity/src \
 *       test_wdg.c ../../mocks/mock_registers.c ../../mocks/mock_det.c \
 *       ../../../unity/src/unity.c -o test_wdg
 *   ./test_wdg
 *
 * License: Elastic License 2.0
 */

#include "unity.h"
#include "mock_registers.h"
#include "mock_det.h"
#include <stdbool.h>
#include <string.h>

/* ================================================================== */
/*  Wdg Module Under Test (inline, simplified AUTOSAR-style)          */
/* ================================================================== */

#define WDG_MODULE_ID     0x20U
#define WDG_INSTANCE_ID   0x00U

#define WDG_API_INIT         0x01U
#define WDG_API_SET_MODE     0x02U
#define WDG_API_ACTIVATE     0x03U
#define WDG_API_DEACTIVATE   0x04U
#define WDG_API_REFRESH      0x05U

#define WDG_E_NOT_INITIALIZED  0x01U
#define WDG_E_MODE_INVALID     0x02U
#define WDG_E_NOT_ACTIVE       0x03U
#define WDG_E_ALREADY_ACTIVE   0x04U

#define WDG_REG_CONTROL   0x40001000U
#define WDG_REG_RELOAD    0x40001004U
#define WDG_REG_COUNTER   0x40001008U
#define WDG_REG_STATUS    0x4000100CU
#define WDG_REG_KEY       0x40001010U

#define WDG_KEY_UNLOCK  0xA5A5A5A5U
#define WDG_CTRL_ENABLE 0x01U
#define WDG_STATUS_OK   0x00U

typedef enum {
    WDG_UNINIT = 0,
    WDG_IDLE,
    WDG_ACTIVE,
    WDG_SLEEP
} Wdg_StateType;

typedef enum {
    WDG_MODE_OFF = 0,
    WDG_MODE_SLOW,
    WDG_MODE_FAST
} Wdg_ModeType;

static Wdg_StateType Wdg_State = WDG_UNINIT;
static Wdg_ModeType Wdg_CurrentMode = WDG_MODE_OFF;
static uint32_t Wdg_RefreshCount = 0;

static void Det_ReportError(uint8_t mod, uint8_t inst, uint8_t api, uint8_t err) {
    Det_Mock_ReportError(mod, inst, api, err);
}

static void Wdg_Init(void) {
    REG_WRITE32(WDG_REG_KEY, WDG_KEY_UNLOCK);
    REG_WRITE32(WDG_REG_CONTROL, 0x00U);
    REG_WRITE32(WDG_REG_COUNTER, 0x00U);
    Wdg_RefreshCount = 0;
    Wdg_CurrentMode = WDG_MODE_OFF;
    Wdg_State = WDG_IDLE;
}

static int Wdg_SetMode(Wdg_ModeType mode) {
    if (Wdg_State == WDG_UNINIT) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_SET_MODE, WDG_E_NOT_INITIALIZED);
        return -1;
    }
    if (mode != WDG_MODE_OFF && mode != WDG_MODE_SLOW && mode != WDG_MODE_FAST) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_SET_MODE, WDG_E_MODE_INVALID);
        return -1;
    }
    if (Wdg_State == WDG_ACTIVE) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_SET_MODE, WDG_E_ALREADY_ACTIVE);
        return -1;
    }
    Wdg_CurrentMode = mode;
    if (mode == WDG_MODE_SLOW) {
        REG_WRITE32(WDG_REG_RELOAD, 1000U);
    } else if (mode == WDG_MODE_FAST) {
        REG_WRITE32(WDG_REG_RELOAD, 100U);
    }
    return 0;
}

static int Wdg_Activate(void) {
    if (Wdg_State == WDG_UNINIT) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_ACTIVATE, WDG_E_NOT_INITIALIZED);
        return -1;
    }
    if (Wdg_CurrentMode == WDG_MODE_OFF) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_ACTIVATE, WDG_E_MODE_INVALID);
        return -1;
    }
    if (Wdg_State == WDG_ACTIVE) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_ACTIVATE, WDG_E_ALREADY_ACTIVE);
        return -1;
    }
    REG_WRITE32(WDG_REG_KEY, WDG_KEY_UNLOCK);
    REG_WRITE32(WDG_REG_CONTROL, WDG_CTRL_ENABLE);
    Wdg_State = WDG_ACTIVE;
    return 0;
}

static int Wdg_Deactivate(void) {
    if (Wdg_State == WDG_UNINIT) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_DEACTIVATE, WDG_E_NOT_INITIALIZED);
        return -1;
    }
    if (Wdg_State != WDG_ACTIVE) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_DEACTIVATE, WDG_E_NOT_ACTIVE);
        return -1;
    }
    REG_WRITE32(WDG_REG_KEY, WDG_KEY_UNLOCK);
    REG_WRITE32(WDG_REG_CONTROL, 0x00U);
    Wdg_State = WDG_IDLE;
    return 0;
}

static int Wdg_Refresh(void) {
    if (Wdg_State == WDG_UNINIT) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_REFRESH, WDG_E_NOT_INITIALIZED);
        return -1;
    }
    if (Wdg_State != WDG_ACTIVE) {
        Det_ReportError(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_REFRESH, WDG_E_NOT_ACTIVE);
        return -1;
    }
    REG_WRITE32(WDG_REG_COUNTER, 0x00U);
    Wdg_RefreshCount++;
    return 0;
}

/* ================================================================== */
/*  setUp / tearDown                                                   */
/* ================================================================== */

void setUp(void) {
    MockRegisters_Reset();
    Det_Mock_Reset();
    Wdg_State = WDG_UNINIT;
    Wdg_CurrentMode = WDG_MODE_OFF;
    Wdg_RefreshCount = 0;
}

void tearDown(void) {
}

/* ================================================================== */
/*  Tests — Init (2)                                                   */
/* ================================================================== */

static void test_Wdg_Init_writes_key_and_control(void) {
    Wdg_Init();
    TEST_ASSERT_TRUE(MockRegisters_WasWritten(WDG_REG_KEY));
    TEST_ASSERT_EQUAL_HEX(WDG_KEY_UNLOCK, MockRegisters_GetWrittenValue(WDG_REG_KEY));
    TEST_ASSERT_TRUE(MockRegisters_WasWritten(WDG_REG_CONTROL));
}

static void test_Wdg_Init_transitions_to_idle(void) {
    Wdg_Init();
    int rc = Wdg_SetMode(WDG_MODE_SLOW);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(0, Det_Mock_GetCallCount());
}

/* ================================================================== */
/*  Tests — SetMode (3)                                                */
/* ================================================================== */

static void test_Wdg_SetMode_slow_writes_reload(void) {
    Wdg_Init();
    int rc = Wdg_SetMode(WDG_MODE_SLOW);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_TRUE(MockRegisters_WasWritten(WDG_REG_RELOAD));
    TEST_ASSERT_EQUAL_HEX(1000U, MockRegisters_GetWrittenValue(WDG_REG_RELOAD));
}

static void test_Wdg_SetMode_fast_writes_shorter_reload(void) {
    Wdg_Init();
    int rc = Wdg_SetMode(WDG_MODE_FAST);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(100U, MockRegisters_GetWrittenValue(WDG_REG_RELOAD));
}

static void test_Wdg_SetMode_invalid_reports_DET(void) {
    Wdg_Init();
    int rc = Wdg_SetMode((Wdg_ModeType)99);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_SET_MODE, WDG_E_MODE_INVALID));
}

/* ================================================================== */
/*  Tests — Activate / Deactivate state machine (4)                    */
/* ================================================================== */

static void test_Wdg_Activate_writes_enable(void) {
    Wdg_Init();
    Wdg_SetMode(WDG_MODE_SLOW);
    int rc = Wdg_Activate();
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(WDG_CTRL_ENABLE, MockRegisters_GetWrittenValue(WDG_REG_CONTROL));
}

static void test_Wdg_Activate_without_mode_reports_DET(void) {
    Wdg_Init();
    int rc = Wdg_Activate();
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_ACTIVATE, WDG_E_MODE_INVALID));
}

static void test_Wdg_Deactivate_clears_control(void) {
    Wdg_Init();
    Wdg_SetMode(WDG_MODE_FAST);
    Wdg_Activate();
    int rc = Wdg_Deactivate();
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(0x00U, MockRegisters_GetWrittenValue(WDG_REG_CONTROL));
}

static void test_Wdg_Deactivate_when_inactive_reports_DET(void) {
    Wdg_Init();
    int rc = Wdg_Deactivate();
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_DEACTIVATE, WDG_E_NOT_ACTIVE));
}

/* ================================================================== */
/*  Tests — Refresh (3)                                                */
/* ================================================================== */

static void test_Wdg_Refresh_clears_counter(void) {
    Wdg_Init();
    Wdg_SetMode(WDG_MODE_SLOW);
    Wdg_Activate();
    int rc = Wdg_Refresh();
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(0x00U, MockRegisters_GetWrittenValue(WDG_REG_COUNTER));
}

static void test_Wdg_Refresh_inactive_reports_DET(void) {
    Wdg_Init();
    int rc = Wdg_Refresh();
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_REFRESH, WDG_E_NOT_ACTIVE));
}

static void test_Wdg_Refresh_uninit_reports_DET(void) {
    int rc = Wdg_Refresh();
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_REFRESH, WDG_E_NOT_INITIALIZED));
}

/* ================================================================== */
/*  Tests — DET parameter validation (4)                               */
/* ================================================================== */

static void test_Wdg_SetMode_uninit_reports_DET(void) {
    int rc = Wdg_SetMode(WDG_MODE_SLOW);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_SET_MODE, WDG_E_NOT_INITIALIZED));
}

static void test_Wdg_Activate_uninit_reports_DET(void) {
    int rc = Wdg_Activate();
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_ACTIVATE, WDG_E_NOT_INITIALIZED));
}

static void test_Wdg_Activate_twice_reports_DET(void) {
    Wdg_Init();
    Wdg_SetMode(WDG_MODE_FAST);
    Wdg_Activate();
    int rc = Wdg_Activate();
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(WDG_MODULE_ID, WDG_INSTANCE_ID, WDG_API_ACTIVATE, WDG_E_ALREADY_ACTIVE));
}

static void test_Wdg_full_lifecycle_no_errors(void) {
    Wdg_Init();
    Wdg_SetMode(WDG_MODE_FAST);
    Wdg_Activate();
    Wdg_Refresh();
    Wdg_Refresh();
    Wdg_Deactivate();
    TEST_ASSERT_EQUAL_HEX(0, Det_Mock_GetCallCount());
    TEST_ASSERT_EQUAL_HEX(2, Wdg_RefreshCount);
}

/* ================================================================== */
/*  Main                                                               */
/* ================================================================== */

int main(void) {
    UnityBegin("test_wdg.c — Wdg Module Substantive Tests");

    RUN_TEST(test_Wdg_Init_writes_key_and_control);
    RUN_TEST(test_Wdg_Init_transitions_to_idle);
    RUN_TEST(test_Wdg_SetMode_slow_writes_reload);
    RUN_TEST(test_Wdg_SetMode_fast_writes_shorter_reload);
    RUN_TEST(test_Wdg_SetMode_invalid_reports_DET);
    RUN_TEST(test_Wdg_Activate_writes_enable);
    RUN_TEST(test_Wdg_Activate_without_mode_reports_DET);
    RUN_TEST(test_Wdg_Deactivate_clears_control);
    RUN_TEST(test_Wdg_Deactivate_when_inactive_reports_DET);
    RUN_TEST(test_Wdg_Refresh_clears_counter);
    RUN_TEST(test_Wdg_Refresh_inactive_reports_DET);
    RUN_TEST(test_Wdg_Refresh_uninit_reports_DET);
    RUN_TEST(test_Wdg_SetMode_uninit_reports_DET);
    RUN_TEST(test_Wdg_Activate_uninit_reports_DET);
    RUN_TEST(test_Wdg_Activate_twice_reports_DET);
    RUN_TEST(test_Wdg_full_lifecycle_no_errors);

    return UnityEnd();
}

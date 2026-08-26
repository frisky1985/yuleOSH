/**
 * @file test_dio.c
 * @brief Substantive unit tests for Dio module (AUTOSAR-style).
 *
 * Tests verify register-level operations via MockRegisters and
 * DET error reporting via MockDet. 15 tests total.
 *
 * Compile:
 *   gcc -Wall -Wextra -std=c11 -I../../mocks -I../../../unity/src \
 *       test_dio.c ../../mocks/mock_registers.c ../../mocks/mock_det.c \
 *       ../../../unity/src/unity.c -o test_dio
 *   ./test_dio
 *
 * License: Elastic License 2.0
 */

#include "unity.h"
#include "mock_registers.h"
#include "mock_det.h"
#include <stdbool.h>
#include <string.h>

/* ================================================================== */
/*  Dio Module Under Test (inline, simplified AUTOSAR-style)          */
/* ================================================================== */

#define DIO_MODULE_ID     0x12U
#define DIO_INSTANCE_ID   0x00U

#define DIO_API_INIT      0x01U
#define DIO_API_READ_CH   0x02U
#define DIO_API_WRITE_CH  0x03U
#define DIO_API_READ_GRP  0x04U
#define DIO_API_WRITE_GRP 0x05U

#define DIO_E_NOT_INITIALIZED  0x01U
#define DIO_E_PARAM_CHANNEL    0x02U
#define DIO_E_PARAM_POINTER    0x03U

#define DIO_MAX_CHANNELS 16

#define DIO_REG_DATA_OUT_BASE  0x40020014U
#define DIO_REG_DATA_IN_BASE   0x40020010U
#define DIO_REG_MODE_BASE      0x40020000U

typedef enum {
    DIO_UNINIT = 0,
    DIO_INITIALIZED
} Dio_StateType;

static Dio_StateType Dio_State = DIO_UNINIT;
static uint8_t Dio_ChannelDirection[DIO_MAX_CHANNELS]; /* 0=in, 1=out */

static void Det_ReportError(uint8_t mod, uint8_t inst, uint8_t api, uint8_t err) {
    Det_Mock_ReportError(mod, inst, api, err);
}

static void Dio_Init(void) {
    for (int i = 0; i < DIO_MAX_CHANNELS; i++) {
        Dio_ChannelDirection[i] = 0;
    }
    REG_WRITE32(DIO_REG_MODE_BASE, 0x00000000U);
    Dio_State = DIO_INITIALIZED;
}

static int Dio_ReadChannel(uint8_t channel, bool *value) {
    if (Dio_State == DIO_UNINIT) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_READ_CH, DIO_E_NOT_INITIALIZED);
        return -1;
    }
    if (channel >= DIO_MAX_CHANNELS) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_READ_CH, DIO_E_PARAM_CHANNEL);
        return -1;
    }
    if (value == NULL) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_READ_CH, DIO_E_PARAM_POINTER);
        return -1;
    }
    uint32_t reg_val = REG_READ32(DIO_REG_DATA_IN_BASE);
    *value = (reg_val & (1U << channel)) != 0;
    return 0;
}

static int Dio_WriteChannel(uint8_t channel, bool value) {
    if (Dio_State == DIO_UNINIT) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_WRITE_CH, DIO_E_NOT_INITIALIZED);
        return -1;
    }
    if (channel >= DIO_MAX_CHANNELS) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_WRITE_CH, DIO_E_PARAM_CHANNEL);
        return -1;
    }
    uint32_t reg_val = REG_READ32(DIO_REG_DATA_OUT_BASE);
    if (value) {
        reg_val |= (1U << channel);
    } else {
        reg_val &= ~(1U << channel);
    }
    REG_WRITE32(DIO_REG_DATA_OUT_BASE, reg_val);
    return 0;
}

static int Dio_ReadGroup(uint8_t start, uint8_t length, uint32_t *value) {
    if (Dio_State == DIO_UNINIT) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_READ_GRP, DIO_E_NOT_INITIALIZED);
        return -1;
    }
    if (start >= DIO_MAX_CHANNELS || (start + length) > DIO_MAX_CHANNELS) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_READ_GRP, DIO_E_PARAM_CHANNEL);
        return -1;
    }
    if (value == NULL) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_READ_GRP, DIO_E_PARAM_POINTER);
        return -1;
    }
    uint32_t reg_val = REG_READ32(DIO_REG_DATA_IN_BASE);
    uint32_t mask = ((1U << length) - 1U) << start;
    *value = (reg_val & mask) >> start;
    return 0;
}

static int Dio_WriteGroup(uint8_t start, uint8_t length, uint32_t value) {
    if (Dio_State == DIO_UNINIT) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_WRITE_GRP, DIO_E_NOT_INITIALIZED);
        return -1;
    }
    if (start >= DIO_MAX_CHANNELS || (start + length) > DIO_MAX_CHANNELS) {
        Det_ReportError(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_WRITE_GRP, DIO_E_PARAM_CHANNEL);
        return -1;
    }
    uint32_t reg_val = REG_READ32(DIO_REG_DATA_OUT_BASE);
    uint32_t mask = ((1U << length) - 1U) << start;
    reg_val = (reg_val & ~mask) | ((value << start) & mask);
    REG_WRITE32(DIO_REG_DATA_OUT_BASE, reg_val);
    return 0;
}

/* ================================================================== */
/*  setUp / tearDown                                                   */
/* ================================================================== */

void setUp(void) {
    MockRegisters_Reset();
    Det_Mock_Reset();
    Dio_State = DIO_UNINIT;
    memset(Dio_ChannelDirection, 0, sizeof(Dio_ChannelDirection));
}

void tearDown(void) {
}

/* ================================================================== */
/*  Tests — Init (2)                                                   */
/* ================================================================== */

static void test_Dio_Init_writes_mode_register(void) {
    Dio_Init();
    TEST_ASSERT_TRUE(MockRegisters_WasWritten(DIO_REG_MODE_BASE));
    TEST_ASSERT_EQUAL_HEX(0x00000000U, MockRegisters_GetWrittenValue(DIO_REG_MODE_BASE));
}

static void test_Dio_Init_sets_initialized_state(void) {
    Dio_Init();
    bool val = false;
    MockRegisters_SetReadValue(DIO_REG_DATA_IN_BASE, 0x01U);
    int rc = Dio_ReadChannel(0, &val);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(0, Det_Mock_GetCallCount());
}

/* ================================================================== */
/*  Tests — ReadChannel (3)                                            */
/* ================================================================== */

static void test_Dio_ReadChannel_bit0_high(void) {
    Dio_Init();
    MockRegisters_SetReadValue(DIO_REG_DATA_IN_BASE, 0x01U);
    bool val = false;
    int rc = Dio_ReadChannel(0, &val);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_TRUE(val);
}

static void test_Dio_ReadChannel_bit7_low(void) {
    Dio_Init();
    MockRegisters_SetReadValue(DIO_REG_DATA_IN_BASE, 0x00U);
    bool val = true;
    int rc = Dio_ReadChannel(7, &val);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_FALSE(val);
}

static void test_Dio_ReadChannel_reads_register(void) {
    Dio_Init();
    MockRegisters_SetReadValue(DIO_REG_DATA_IN_BASE, 0xA5U);
    bool val = false;
    Dio_ReadChannel(5, &val);
    TEST_ASSERT_TRUE(val);
    TEST_ASSERT_TRUE(MockRegisters_GetReadCount() >= 1);
}

/* ================================================================== */
/*  Tests — WriteChannel (3)                                           */
/* ================================================================== */

static void test_Dio_WriteChannel_set_bit(void) {
    Dio_Init();
    MockRegisters_SetReadValue(DIO_REG_DATA_OUT_BASE, 0x00U);
    int rc = Dio_WriteChannel(3, true);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(0x08U, MockRegisters_GetLastWriteValue());
}

static void test_Dio_WriteChannel_clear_bit(void) {
    Dio_Init();
    MockRegisters_SetReadValue(DIO_REG_DATA_OUT_BASE, 0xFFU);
    int rc = Dio_WriteChannel(3, false);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(0xF7U, MockRegisters_GetLastWriteValue());
}

static void test_Dio_WriteChannel_preserves_other_bits(void) {
    Dio_Init();
    MockRegisters_SetReadValue(DIO_REG_DATA_OUT_BASE, 0xAAU);
    Dio_WriteChannel(0, true);
    TEST_ASSERT_EQUAL_HEX(0xABU, MockRegisters_GetLastWriteValue());
}

/* ================================================================== */
/*  Tests — DET errors (4)                                             */
/* ================================================================== */

static void test_Dio_ReadChannel_uninit_reports_DET(void) {
    bool val;
    int rc = Dio_ReadChannel(0, &val);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_READ_CH, DIO_E_NOT_INITIALIZED));
}

static void test_Dio_WriteChannel_invalid_channel_reports_DET(void) {
    Dio_Init();
    int rc = Dio_WriteChannel(20, true);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_WRITE_CH, DIO_E_PARAM_CHANNEL));
}

static void test_Dio_ReadChannel_null_pointer_reports_DET(void) {
    Dio_Init();
    int rc = Dio_ReadChannel(0, NULL);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_READ_CH, DIO_E_PARAM_POINTER));
}

static void test_Dio_WriteChannel_uninit_no_register_access(void) {
    int rc = Dio_WriteChannel(0, true);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_EQUAL_HEX(0, MockRegisters_GetWriteCount());
}

/* ================================================================== */
/*  Tests — Group operations (3)                                       */
/* ================================================================== */

static void test_Dio_ReadGroup_4bits(void) {
    Dio_Init();
    MockRegisters_SetReadValue(DIO_REG_DATA_IN_BASE, 0xF0U);
    uint32_t val = 0;
    int rc = Dio_ReadGroup(4, 4, &val);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(0x0FU, val);
}

static void test_Dio_WriteGroup_preserves_surrounding(void) {
    Dio_Init();
    MockRegisters_SetReadValue(DIO_REG_DATA_OUT_BASE, 0x00U);
    int rc = Dio_WriteGroup(2, 3, 0x05U);
    TEST_ASSERT_EQUAL(0, rc);
    TEST_ASSERT_EQUAL_HEX(0x14U, MockRegisters_GetLastWriteValue());
}

static void test_Dio_WriteGroup_invalid_range_reports_DET(void) {
    Dio_Init();
    int rc = Dio_WriteGroup(14, 4, 0x0FU);
    TEST_ASSERT_EQUAL(-1, rc);
    TEST_ASSERT_TRUE(Det_Mock_WasCalledWith(DIO_MODULE_ID, DIO_INSTANCE_ID, DIO_API_WRITE_GRP, DIO_E_PARAM_CHANNEL));
}

/* ================================================================== */
/*  Main                                                               */
/* ================================================================== */

int main(void) {
    UnityBegin("test_dio.c — Dio Module Substantive Tests");

    RUN_TEST(test_Dio_Init_writes_mode_register);
    RUN_TEST(test_Dio_Init_sets_initialized_state);
    RUN_TEST(test_Dio_ReadChannel_bit0_high);
    RUN_TEST(test_Dio_ReadChannel_bit7_low);
    RUN_TEST(test_Dio_ReadChannel_reads_register);
    RUN_TEST(test_Dio_WriteChannel_set_bit);
    RUN_TEST(test_Dio_WriteChannel_clear_bit);
    RUN_TEST(test_Dio_WriteChannel_preserves_other_bits);
    RUN_TEST(test_Dio_ReadChannel_uninit_reports_DET);
    RUN_TEST(test_Dio_WriteChannel_invalid_channel_reports_DET);
    RUN_TEST(test_Dio_ReadChannel_null_pointer_reports_DET);
    RUN_TEST(test_Dio_WriteChannel_uninit_no_register_access);
    RUN_TEST(test_Dio_ReadGroup_4bits);
    RUN_TEST(test_Dio_WriteGroup_preserves_surrounding);
    RUN_TEST(test_Dio_WriteGroup_invalid_range_reports_DET);

    return UnityEnd();
}

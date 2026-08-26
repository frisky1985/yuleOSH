/**
 * @file mock_det.c
 * @brief Mock DET implementation.
 *
 * License: Elastic License 2.0
 */

#include "mock_det.h"
#include <string.h>

Det_MockData g_det_mock;

void Det_Mock_Init(void) {
    Det_Mock_Reset();
}

void Det_Mock_Reset(void) {
    memset(&g_det_mock, 0, sizeof(g_det_mock));
}

void Det_Mock_ReportError(uint8_t ModuleId, uint8_t InstanceId,
                          uint8_t ApiId, uint8_t ErrorId) {
    if (g_det_mock.CallCount < DET_MOCK_MAX_ERRORS) {
        uint32_t idx = g_det_mock.CallCount;
        g_det_mock.errors[idx].ModuleId = ModuleId;
        g_det_mock.errors[idx].InstanceId = InstanceId;
        g_det_mock.errors[idx].ApiId = ApiId;
        g_det_mock.errors[idx].ErrorId = ErrorId;
    }
    g_det_mock.CallCount++;
    g_det_mock.LastModuleId = ModuleId;
    g_det_mock.LastInstanceId = InstanceId;
    g_det_mock.LastApiId = ApiId;
    g_det_mock.LastErrorId = ErrorId;
}

uint32_t Det_Mock_GetCallCount(void) {
    return g_det_mock.CallCount;
}

bool Det_Mock_WasCalledWith(uint8_t ModuleId, uint8_t InstanceId,
                            uint8_t ApiId, uint8_t ErrorId) {
    for (uint32_t i = 0; i < g_det_mock.CallCount && i < DET_MOCK_MAX_ERRORS; i++) {
        if (g_det_mock.errors[i].ModuleId == ModuleId &&
            g_det_mock.errors[i].InstanceId == InstanceId &&
            g_det_mock.errors[i].ApiId == ApiId &&
            g_det_mock.errors[i].ErrorId == ErrorId) {
            return true;
        }
    }
    return false;
}

uint32_t Det_Mock_GetErrorCount(uint8_t ModuleId, uint8_t ApiId) {
    uint32_t count = 0;
    for (uint32_t i = 0; i < g_det_mock.CallCount && i < DET_MOCK_MAX_ERRORS; i++) {
        if (g_det_mock.errors[i].ModuleId == ModuleId &&
            g_det_mock.errors[i].ApiId == ApiId) {
            count++;
        }
    }
    return count;
}

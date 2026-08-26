/**
 * @file mock_det.h
 * @brief Mock Default Error Tracer (DET) for BSW module host-side testing.
 *
 * Records Det_ReportError calls for verification in unit tests.
 *
 * License: Elastic License 2.0
 */

#ifndef MOCK_DET_H
#define MOCK_DET_H

#include <stdint.h>
#include <stdbool.h>

#define DET_MOCK_MAX_ERRORS 32

typedef struct {
    uint8_t  ModuleId;
    uint8_t  InstanceId;
    uint8_t  ApiId;
    uint8_t  ErrorId;
} DetErrorEntry;

typedef struct {
    DetErrorEntry errors[DET_MOCK_MAX_ERRORS];
    uint32_t      CallCount;
    uint8_t       LastModuleId;
    uint8_t       LastInstanceId;
    uint8_t       LastApiId;
    uint8_t       LastErrorId;
} Det_MockData;

extern Det_MockData g_det_mock;

void Det_Mock_Init(void);
void Det_Mock_Reset(void);
void Det_Mock_ReportError(uint8_t ModuleId, uint8_t InstanceId,
                          uint8_t ApiId, uint8_t ErrorId);
uint32_t Det_Mock_GetCallCount(void);
bool Det_Mock_WasCalledWith(uint8_t ModuleId, uint8_t InstanceId,
                            uint8_t ApiId, uint8_t ErrorId);
uint32_t Det_Mock_GetErrorCount(uint8_t ModuleId, uint8_t ApiId);

#endif /* MOCK_DET_H */

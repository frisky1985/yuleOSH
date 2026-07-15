/**
 * @file Det.h
 * @brief Default Error Tracer — Development error logging and reporting
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef DET_H
#define DET_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Det configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Det_ConfigType;

typedef uint8_t Det_ErrorType;
#define DET_NO_ERROR       0x00U
#define DET_INIT_ERROR     0x01U
#define DET_PARAM_POINTER  0x02U
#define DET_PARAM_VALUE    0x03U
#define DET_API_ERROR      0x04U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Det_Init(void);
extern Std_ReturnType Det_DeInit(void);
extern void Det_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern void Det_ReportError(uint16_t ModuleId, uint8_t InstanceId, uint8_t ApiId, uint8_t ErrorId);
extern void Det_ReportRuntimeError(uint16_t ModuleId, uint8_t InstanceId, uint8_t ApiId, uint8_t ErrorId);
extern void Det_ReportTransientFault(uint16_t ModuleId, uint8_t InstanceId, uint8_t ApiId, uint8_t ErrorId);
extern void Det_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* DET_H */

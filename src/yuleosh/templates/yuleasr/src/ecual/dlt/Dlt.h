/**
 * @file Dlt.h
 * @brief Diagnostic Log and Trace — Runtime logging over CAN/Ethernet
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Dlt driver is integrated.
 */

#ifndef DLT_H
#define DLT_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Dlt configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Dlt_ConfigType;

typedef uint8_t Dlt_LogLevelType;
#define DLT_LOG_FATAL    0x01U
#define DLT_LOG_ERROR    0x02U
#define DLT_LOG_WARN     0x03U
#define DLT_LOG_INFO     0x04U
#define DLT_LOG_DEBUG    0x05U
#define DLT_LOG_VERBOSE  0x06U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Dlt_Init(void);

extern Std_ReturnType Dlt_DeInit(void);

extern void Dlt_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Dlt_SendLog(uint8_t LogLevel, const char *AppId, const char *CtxId, const char *Payload);

extern Std_ReturnType Dlt_SetLogLevel(uint8_t LogLevel);

extern void Dlt_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* DLT_H */

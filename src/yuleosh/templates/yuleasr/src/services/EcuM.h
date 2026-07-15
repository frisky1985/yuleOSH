/**
 * @file EcuM.h
 * @brief ECU State Manager — Startup, shutdown, and sleep state control
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef ECUM_H
#define ECUM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief EcuM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} EcuM_ConfigType;

typedef uint8_t EcuM_StateType;
#define ECUM_STATE_STARTUP      0x00U
#define ECUM_STATE_RUN          0x01U
#define ECUM_STATE_POST_RUN     0x02U
#define ECUM_STATE_SLEEP        0x03U
#define ECUM_STATE_SHUTDOWN     0x04U

typedef uint8_t EcuM_WakeupSourceType;
#define ECUM_WAKEUP_RESET  0x00U
#define ECUM_WAKEUP_CAN    0x01U
#define ECUM_WAKEUP_LIN    0x02U
#define ECUM_WAKEUP_FLEXRAY 0x03U
#define ECUM_WAKEUP_ETHERNET 0x04U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType EcuM_Init(void);
extern Std_ReturnType EcuM_DeInit(void);
extern void EcuM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern void EcuM_SelectShutdownTarget(uint8_t ShutdownTarget);
extern void EcuM_GoSleep(void);
extern void EcuM_GoHalt(void);
extern EcuM_StateType EcuM_GetState(void);
extern void EcuM_StartupTwo(void);
extern void EcuM_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* ECUM_H */

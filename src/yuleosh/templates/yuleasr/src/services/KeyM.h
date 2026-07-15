/**
 * @file KeyM.h
 * @brief Key Manager — Cryptographic key lifecycle management
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef KEYM_H
#define KEYM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief KeyM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} KeyM_ConfigType;

typedef uint8_t KeyM_KeyIdType;
typedef uint8_t KeyM_KeyStateType;
#define KEYM_STATE_INVALID 0x00U
#define KEYM_STATE_VALID   0x01U
#define KEYM_STATE_LOCKED  0x02U

typedef uint8_t KeyM_KeySlotType;
#define KEYM_SLOT_BOOT   0x00U
#define KEYM_SLOT_MAIN   0x01U
#define KEYM_SLOT_UPDATE 0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType KeyM_Init(void);
extern Std_ReturnType KeyM_DeInit(void);
extern void KeyM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType KeyM_KeySetValid(KeyM_KeyIdType KeyId);
extern Std_ReturnType KeyM_KeyInvalidate(KeyM_KeyIdType KeyId);
extern KeyM_KeyStateType KeyM_GetKeyState(KeyM_KeyIdType KeyId);
extern Std_ReturnType KeyM_KeyExchange(KeyM_KeySlotType Slot);
#ifdef __cplusplus
}
#endif

#endif /* KEYM_H */

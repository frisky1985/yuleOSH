/**
 * @file Csm.h
 * @brief Crypto Service Manager — Cryptographic operations abstraction
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef CSM_H
#define CSM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Csm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Csm_ConfigType;

typedef uint8_t Csm_KeyIdType;
typedef uint8_t Csm_AlgorithmType;
#define CSM_ALG_AES128  0x01U
#define CSM_ALG_AES256  0x02U
#define CSM_ALG_CMAC    0x03U
#define CSM_ALG_HMAC    0x04U

typedef uint8_t Csm_OperationModeType;
#define CSM_MODE_ENCRYPT 0x00U
#define CSM_MODE_DECRYPT 0x01U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Csm_Init(void);
extern Std_ReturnType Csm_DeInit(void);
extern void Csm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Csm_Encrypt(Csm_KeyIdType KeyId, const uint8_t *PlainText, uint16_t PlainLen, uint8_t *CipherText, uint16_t *CipherLen);
extern Std_ReturnType Csm_Decrypt(Csm_KeyIdType KeyId, const uint8_t *CipherText, uint16_t CipherLen, uint8_t *PlainText, uint16_t *PlainLen);
extern Std_ReturnType Csm_MACGenerate(Csm_KeyIdType KeyId, const uint8_t *Data, uint16_t DataLen, uint8_t *MAC, uint16_t *MACLen);
extern Std_ReturnType Csm_MACVerify(Csm_KeyIdType KeyId, const uint8_t *Data, uint16_t DataLen, const uint8_t *MAC, uint16_t MACLen);
extern void Csm_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* CSM_H */

/**
 * @file Crypto.h
 * @brief Crypto Driver — Hardware accelerated AES/SHA/RSA/ECC
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Crypto driver is integrated.
 */

#ifndef CRYPTO_H
#define CRYPTO_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Crypto configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Crypto_ConfigType;

typedef struct { uint8_t *input; uint32_t inputLength; uint8_t *output; uint32_t outputLength; uint8_t algoId; uint8_t keyId; } Crypto_JobType;

typedef uint8_t Crypto_KeyElementIdType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Crypto_Init(const Crypto_ConfigType *ConfigPtr);

extern Std_ReturnType Crypto_DeInit(void);

extern void Crypto_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Crypto_ProcessJob(Crypto_JobType *JobPtr);

extern Std_ReturnType Crypto_CancelJob(Crypto_JobType *JobPtr);

extern Std_ReturnType Crypto_GetKeyValid(Crypto_KeyElementIdType KeyId);

extern Std_ReturnType Crypto_Sha256(const uint8_t *Input, uint32_t InputLength, uint8_t *HashOutput);

extern Std_ReturnType Crypto_Aes128CbcEncrypt(const uint8_t *Input, uint32_t InputLength, const uint8_t *Key, const uint8_t *Iv, uint8_t *Output);

extern Std_ReturnType Crypto_Aes128CbcDecrypt(const uint8_t *Input, uint32_t InputLength, const uint8_t *Key, const uint8_t *Iv, uint8_t *Output);

#ifdef __cplusplus
}
#endif

#endif /* CRYPTO_H */

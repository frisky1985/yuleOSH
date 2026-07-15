/**
 * @file Crypto.c
 * @brief Crypto Driver — Hardware accelerated AES/SHA/RSA/ECC
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Crypto.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CRYPTO_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Crypto_Init — stub implementation */
Std_ReturnType Crypto_Init(const Crypto_ConfigType *ConfigPtr)
{
    CRYPTO_Initialized = 1U;
    return E_OK;
}

/** @brief Crypto_DeInit — stub implementation */
Std_ReturnType Crypto_DeInit(void)
{
    CRYPTO_Initialized = 0U;
    return E_OK;
}

/** @brief Crypto_GetVersionInfo — stub implementation */
void Crypto_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
{
    /* Stub — no version info available */
    if (VersionInfoPtr != NULL_PTR)
    {
        VersionInfoPtr->vendorID = 0U;
        VersionInfoPtr->moduleID = 0U;
        VersionInfoPtr->sw_major_version = 0U;
        VersionInfoPtr->sw_minor_version = 0U;
        VersionInfoPtr->sw_patch_version = 0U;
    }
}

/** @brief Crypto_ProcessJob — stub implementation */
Std_ReturnType Crypto_ProcessJob(Crypto_JobType *JobPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Crypto_CancelJob — stub implementation */
Std_ReturnType Crypto_CancelJob(Crypto_JobType *JobPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Crypto_GetKeyValid — stub implementation */
Std_ReturnType Crypto_GetKeyValid(Crypto_KeyElementIdType KeyId)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Crypto_Sha256 — stub implementation */
Std_ReturnType Crypto_Sha256(const uint8_t *Input, uint32_t InputLength, uint8_t *HashOutput)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Crypto_Aes128CbcEncrypt — stub implementation */
Std_ReturnType Crypto_Aes128CbcEncrypt(const uint8_t *Input, uint32_t InputLength, const uint8_t *Key, const uint8_t *Iv, uint8_t *Output)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Crypto_Aes128CbcDecrypt — stub implementation */
Std_ReturnType Crypto_Aes128CbcDecrypt(const uint8_t *Input, uint32_t InputLength, const uint8_t *Key, const uint8_t *Iv, uint8_t *Output)
{
    /* Stub — returning default */
    return E_OK;
}

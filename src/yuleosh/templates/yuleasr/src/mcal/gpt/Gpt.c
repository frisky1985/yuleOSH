/**
 * @file Gpt.c
 * @brief GPT Driver — General-purpose timer channels
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Gpt.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t GPT_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Gpt_Init — stub implementation */
Std_ReturnType Gpt_Init(const Gpt_ConfigType *ConfigPtr)
{
    GPT_Initialized = 1U;
    return E_OK;
}

/** @brief Gpt_DeInit — stub implementation */
Std_ReturnType Gpt_DeInit(void)
{
    GPT_Initialized = 0U;
    return E_OK;
}

/** @brief Gpt_GetVersionInfo — stub implementation */
void Gpt_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Gpt_StartTimer — stub implementation */
Std_ReturnType Gpt_StartTimer(Gpt_ChannelType Channel, Gpt_ValueType Value)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Gpt_StopTimer — stub implementation */
Std_ReturnType Gpt_StopTimer(Gpt_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Gpt_GetTimeElapsed — stub implementation */
Gpt_ValueType Gpt_GetTimeElapsed(Gpt_ChannelType Channel)
{
    /* Stub — returning default */
    return 0U;
}

/** @brief Gpt_GetTimeRemaining — stub implementation */
Gpt_ValueType Gpt_GetTimeRemaining(Gpt_ChannelType Channel)
{
    /* Stub — returning default */
    return 0U;
}

/** @brief Gpt_EnableNotification — stub implementation */
Std_ReturnType Gpt_EnableNotification(Gpt_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Gpt_DisableNotification — stub implementation */
Std_ReturnType Gpt_DisableNotification(Gpt_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}

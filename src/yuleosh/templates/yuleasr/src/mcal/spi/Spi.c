/**
 * @file Spi.c
 * @brief SPI Driver — Master/slave synchronous/asynchronous
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Spi.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t SPI_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Spi_Init — stub implementation */
Std_ReturnType Spi_Init(const Spi_ConfigType *ConfigPtr)
{
    SPI_Initialized = 1U;
    return E_OK;
}

/** @brief Spi_DeInit — stub implementation */
Std_ReturnType Spi_DeInit(void)
{
    SPI_Initialized = 0U;
    return E_OK;
}

/** @brief Spi_GetVersionInfo — stub implementation */
void Spi_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Spi_ReadIB — stub implementation */
Std_ReturnType Spi_ReadIB(Spi_SequenceType Sequence, Spi_DataBufferType *BufferPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Spi_WriteIB — stub implementation */
Std_ReturnType Spi_WriteIB(Spi_SequenceType Sequence, const Spi_DataBufferType *BufferPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Spi_SetupEB — stub implementation */
Std_ReturnType Spi_SetupEB(Spi_SequenceType Sequence, const Spi_DataBufferType *SrcBufPtr, Spi_DataBufferType *DesBufPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Spi_GetStatus — stub implementation */
Spi_StatusType Spi_GetStatus(void)
{
    /* Stub — returning default */
    return SPI_UNINIT;
}

/** @brief Spi_Cancel — stub implementation */
Std_ReturnType Spi_Cancel(Spi_SequenceType Sequence)
{
    /* Stub — returning default */
    return E_OK;
}

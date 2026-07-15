/**
 * @file Spi.h
 * @brief SPI Driver — Master/slave synchronous/asynchronous
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Spi driver is integrated.
 */

#ifndef SPI_H
#define SPI_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Spi configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Spi_ConfigType;

typedef uint8_t Spi_SequenceType;

typedef uint8_t Spi_DataBufferType;

typedef uint8_t Spi_StatusType;
#define SPI_UNINIT  0x00U
#define SPI_IDLE    0x01U
#define SPI_BUSY    0x02U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Spi_Init(const Spi_ConfigType *ConfigPtr);

extern Std_ReturnType Spi_DeInit(void);

extern void Spi_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Spi_ReadIB(Spi_SequenceType Sequence, Spi_DataBufferType *BufferPtr);

extern Std_ReturnType Spi_WriteIB(Spi_SequenceType Sequence, const Spi_DataBufferType *BufferPtr);

extern Std_ReturnType Spi_SetupEB(Spi_SequenceType Sequence, const Spi_DataBufferType *SrcBufPtr, Spi_DataBufferType *DesBufPtr);

extern Spi_StatusType Spi_GetStatus(void);

extern Std_ReturnType Spi_Cancel(Spi_SequenceType Sequence);

#ifdef __cplusplus
}
#endif

#endif /* SPI_H */

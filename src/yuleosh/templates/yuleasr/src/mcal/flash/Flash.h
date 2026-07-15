/**
 * @file Flash.h
 * @brief Flash Low-Level Driver — Sector/program/read operations
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Flash driver is integrated.
 */

#ifndef FLASH_H
#define FLASH_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Flash configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Flash_ConfigType;

typedef uint32_t Flash_AddressType;

typedef uint16_t Flash_SectorType;

typedef uint8_t Flash_StatusType;
#define FLASH_IDLE  0x00U
#define FLASH_BUSY  0x01U

typedef uint8_t Flash_ResultType;
#define FLASH_RESULT_OK      0x00U
#define FLASH_RESULT_FAILED  0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Flash_Init(const Flash_ConfigType *ConfigPtr);

extern Std_ReturnType Flash_DeInit(void);

extern void Flash_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Flash_EraseSector(Flash_SectorType Sector);

extern Std_ReturnType Flash_ProgramWord(Flash_AddressType Address, uint32_t Data);

extern Std_ReturnType Flash_ProgramPage(Flash_AddressType Address, const uint32_t *DataPtr, uint32_t Length);

extern Std_ReturnType Flash_Read(Flash_AddressType Address, uint32_t *DataPtr, uint32_t Length);

extern Flash_StatusType Flash_GetStatus(void);

extern Flash_ResultType Flash_GetResult(void);

#ifdef __cplusplus
}
#endif

#endif /* FLASH_H */

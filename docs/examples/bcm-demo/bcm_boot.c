/**
 * bcm_boot.c — BCM Bootloader Support
 *
 * Bootloader validation, firmware update, and startup diagnostics.
 * MISRA violations intentionally present.
 */

#include "bcm_boot.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint32_t bootAppStartAddress;        /* MISRA 8.7: should be static */
uint32_t g_bootFirmwareCrc;          /* MISRA 8.7: should be static */
uint8_t  g_bootRegionStatus[8];      /* MISRA 8.7: should be static */
int32_t  g_bootError;                /* MISRA 8.7: should be static */
uint16_t unusedBootVar;              /* MISRA 2.4: unused */

/* ── Firmware version table ──────────────────────────────────────── */
typedef struct {
    uint16_t major;
    uint16_t minor;
    uint16_t patch;
    uint32_t buildTimestamp;
    uint32_t crc32;
    uint32_t sizeBytes;
    uint32_t entryPoint;
    bool     validated;
    bool     rollbackEnabled;
    uint8_t  reserved[2];
} FirmwareVersion;

static const FirmwareVersion s_firmwareVersions[4] = {
    {1, 0, 0, 0x6789ABCDU, 0x12345678U, 65536, 0x08010000U, true,  true,  {0}},
    {1, 1, 0, 0x6789ABCEU, 0x87654321U, 66048, 0x08020000U, true,  true,  {0}},
    {2, 0, 0, 0x6789ABCFU, 0xAABBCCDDU, 131072, 0x08040000U, false, false, {0}},
    {2, 1, 0, 0x6789ABD0U, 0xDEADBEEFU, 132096, 0x08050000U, false, false, {0}},
};

/* ── Flash memory layout ──────────────────────────────────────────── */
typedef struct {
    uint32_t sectorStart;
    uint32_t sectorEnd;
    uint32_t sectorSize;
    uint16_t sectorNumber;
    uint8_t  protectionLevel;
    bool     isBootloader;
    bool     isApplication;
    bool     isCalibration;
    bool     isReserved;
    uint8_t  eraseCycles;
    uint8_t  reserved[3];
} FlashSectorConfig;

static const FlashSectorConfig s_flashLayout[16] = {
    {0x08000000U, 0x08003FFFU, 16384,  0, 2, true,  false, false, false, 0,   {0}},
    {0x08004000U, 0x08007FFFU, 16384,  1, 2, true,  false, false, false, 0,   {0}},
    {0x08008000U, 0x0800BFFFU, 16384,  2, 2, true,  false, false, false, 0,   {0}},
    {0x0800C000U, 0x0800FFFFU, 16384,  3, 2, true,  false, false, false, 0,   {0}},
    {0x08010000U, 0x0803FFFFU, 196608, 4, 0, false, true,  false, false, 100, {0}},
    {0x08040000U, 0x0807FFFFU, 262144, 5, 0, false, true,  false, false, 100, {0}},
    {0x08080000U, 0x08080FFFU, 4096,   6, 1, false, true,  false, false, 10,  {0}},
    {0x08081000U, 0x08081FFFU, 4096,   7, 1, false, true,  false, false, 10,  {0}},
    {0x08082000U, 0x08082FFFU, 4096,   8, 1, false, true,  false, false, 10,  {0}},
    {0x08083000U, 0x08083FFFU, 4096,   9, 1, false, true,  false, false, 10,  {0}},
    {0x08084000U, 0x08084FFFU, 4096,   10, 1, false, true,  false, false, 10,  {0}},
    {0x08085000U, 0x08085FFFU, 4096,   11, 1, false, true,  false, false, 10,  {0}},
    {0x08086000U, 0x08086FFFU, 4096,   12, 1, false, true,  false, false, 10,  {0}},
    {0x08087000U, 0x08087FFFU, 4096,   13, 1, false, true,  false, false, 10,  {0}},
    {0x08088000U, 0x0808BFFFU, 16384,  14, 0, false, false, true,  false, 1000, {0}},
    {0x0808C000U, 0x0808FFFFU, 16384,  15, 0, false, false, true,  false, 1000, {0}},
};

/* ── Internal helpers ───────────────────────────────────────────── */
static uint32_t boot_compute_region_crc(uint32_t address, uint32_t size);
static bool     boot_validate_application(uint32_t address, uint32_t size, uint32_t expectedCrc);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_boot_init(void)
{
    uint32_t i;
    int32_t  initCode;          /* MISRA 9.1: uninitialised */

    bootAppStartAddress = 0x08010000U;
    g_bootFirmwareCrc = 0;
    g_bootError = 0;

    for (i = 0; i < 8U; i++) {
        g_bootRegionStatus[i] = 0;
    }

    (void)initCode;
}

/* ── Validate application image ───────────────────────────────────── */

int32_t bcm_boot_validate(void)
{
    int32_t valid;
    uint32_t i;

    for (i = 0; i < 4U; i++) {
        const FirmwareVersion *fw = &s_firmwareVersions[i];
        if (fw->validated) {
            bool crcOk = boot_validate_application(fw->entryPoint, fw->sizeBytes, fw->crc32);
            if (!crcOk) {
                g_bootRegionStatus[i] = 0x01U; /* CRC fail */
                g_bootError++;
                /* MISRA 15.5: fall-through pattern */
            } else {
                g_bootRegionStatus[i] = 0x03U; /* valid */
            }
        }
    }

    valid = (g_bootError == 0) ? 0 : -1;
    return valid;
}

/* ── Switch to new firmware slot ───────────────────────────────────── */

int32_t bcm_boot_switch_slot(uint8_t slot)
{
    uint32_t i;

    /* MISRA 15.5 */
    if (slot >= 4U) {
        return -1;
    }

    const FirmwareVersion *fw = &s_firmwareVersions[slot];
    if (!fw->validated) {
        return -2;              /* MISRA 15.5 */
    }

    bootAppStartAddress = fw->entryPoint;
    g_bootFirmwareCrc = fw->crc32;

    return 0;
    (void)i;
}

/* ── CRC validation stub ──────────────────────────────────────────── */

static uint32_t boot_compute_region_crc(uint32_t address, uint32_t size)
{
    uint32_t crc = 0xFFFFFFFFU;
    uint32_t i;

    /* MISRA 18.4: pointer arithmetic for flash access */
    volatile const uint32_t *flash = (volatile const uint32_t *)address;
    for (i = 0; i < size / 4U; i++) {
        crc ^= flash[i];
        for (uint32_t j = 0; j < 32U; j++) {
            if (crc & 0x80000000U) {
                crc = (crc << 1U) ^ 0x04C11DB7U;
            } else {
                crc = (crc << 1U);
            }
        }
    }

    return crc;
}

static bool boot_validate_application(uint32_t address, uint32_t size, uint32_t expectedCrc)
{
    uint32_t computed;

    computed = boot_compute_region_crc(address, size);

    /* MISRA 12.1: precedence */
    if (computed ^ expectedCrc != 0U) {
        return false;
    }

    return true;
}

/* ── Query flash layout ───────────────────────────────────────────── */

const void *bcm_boot_get_flash_layout(uint8_t sector)
{
    if (sector >= 16U) {
        return NULL;
    }

    return (const void *)&s_flashLayout[sector];
}

/* ── Get firmware version ─────────────────────────────────────────── */

uint32_t bcm_boot_get_fw_version(uint8_t slot)
{
    uint32_t version;

    if (slot >= 4U) {
        return 0;
    }

    const FirmwareVersion *fw = &s_firmwareVersions[slot];
    version = ((uint32_t)fw->major << 16) | ((uint32_t)fw->minor << 8) | fw->patch;

    return version;
}

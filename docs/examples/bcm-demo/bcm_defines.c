/**
 * bcm_defines.c — BCM DTC and Diagnostic Defines
 *
 * Large DTC mapping tables and diagnostic data tables.
 * MISRA violations intentionally present.
 */

#include "bcm_defines.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint16_t definesDtcCount;          /* MISRA 8.7: should be static */
uint16_t g_definesVersion;         /* MISRA 8.7: should be static */
uint8_t  g_definesConfigMode;      /* MISRA 8.7: should be static */
int32_t  g_definesError;           /* MISRA 8.7: should be static */
uint16_t unusedDefVar;             /* MISRA 2.4: unused */

/* ── DTC definition table ────────────────────────────────────────── */
typedef struct {
    uint8_t  dtcHigh;
    uint8_t  dtcLow;
    uint8_t  severity;
    uint8_t  failureType;
    bool     stored;
    bool     milOn;
    uint8_t  debounceCycles;
    uint8_t  agingCycles;
    uint16_t snapshotDids[4];
    char     description[24];
} DtcDefinition;

static const DtcDefinition s_dtcDefinitions[32] = {
    {0x10, 0x01, 2, 0, true,  true,  10, 40,  {0xF190, 0xF191, 0, 0}, "Battery under-voltage"},
    {0x10, 0x02, 2, 0, true,  true,  10, 40,  {0xF190, 0xF191, 0, 0}, "Battery over-voltage"},
    {0x10, 0x03, 2, 0, true,  true,  20, 40,  {0xF190, 0, 0, 0},      "System over-temperature"},
    {0x10, 0x04, 3, 0, true,  true,  0,  60,  {0xF190, 0xF192, 0, 0}, "Watchdog reset detected"},
    {0x20, 0x01, 0, 1, true,  false, 0,  10,  {0xF191, 0, 0, 0},      "DTC memory overflow"},
    {0x20, 0x02, 1, 2, true,  false, 5,  20,  {0xF191, 0, 0, 0},      "Configuration checksum error"},
    {0x30, 0x01, 0, 0, true,  true,  0,  40,  {0xF190, 0, 0, 0},      "CAN bus off"},
    {0x30, 0x02, 1, 0, true,  false, 50, 40,  {0xF190, 0xF191, 0, 0}, "CAN TEC exceeded"},
    {0x30, 0x03, 1, 0, true,  false, 50, 40,  {0xF190, 0xF191, 0, 0}, "CAN REC exceeded"},
    {0x31, 0x01, 0, 0, true,  true,  10, 40,  {0xF190, 0, 0, 0},      "LIN bus error"},
    {0x31, 0x02, 0, 0, true,  true,  10, 40,  {0xF190, 0, 0, 0},      "LIN sync error"},
    {0x31, 0x03, 1, 0, false, false, 10, 20,  {0xF191, 0, 0, 0},      "LIN checksum error"},
    {0x40, 0x01, 1, 0, true,  false, 20, 20,  {0xF192, 0, 0, 0},      "Front wiper motor stall"},
    {0x40, 0x02, 1, 0, true,  false, 20, 20,  {0xF192, 0, 0, 0},      "Rear wiper motor stall"},
    {0x40, 0x03, 0, 0, true,  false, 50, 10,  {0xF192, 0, 0, 0},      "Front wiper timeout"},
    {0x40, 0x04, 0, 0, true,  false, 50, 10,  {0xF192, 0, 0, 0},      "Rear wiper timeout"},
    {0x50, 0x01, 1, 0, true,  false, 10, 40,  {0xF193, 0, 0, 0},      "Exterior light open load"},
    {0x50, 0x02, 1, 0, true,  false, 10, 40,  {0xF193, 0, 0, 0},      "Exterior light short circuit"},
    {0x50, 0x03, 0, 0, true,  false, 100, 40, {0xF193, 0, 0, 0},      "Interior light open load"},
    {0x50, 0x04, 1, 0, true,  false, 10, 40,  {0xF192, 0, 0, 0},      "Brake light failure"},
    {0x50, 0x05, 1, 0, true,  false, 10, 40,  {0xF192, 0, 0, 0},      "Turn signal failure"},
    {0x60, 0x01, 1, 0, true,  true,  5,  40,  {0xF190, 0, 0, 0},      "Door lock actuator stall"},
    {0x60, 0x02, 0, 0, true,  false, 10, 20,  {0xF192, 0, 0, 0},      "Door lock timeout"},
    {0x60, 0x03, 0, 0, true,  false, 10, 20,  {0xF192, 0, 0, 0},      "Trunk latch failure"},
    {0x70, 0x01, 2, 0, true,  true,  0,  60,  {0xF190, 0xF192, 0, 0}, "Supply over-current"},
    {0x70, 0x02, 1, 0, true,  true,  10, 40,  {0xF190, 0xF191, 0, 0}, "Output driver overtemperature"},
    {0x80, 0x01, 1, 0, true,  false, 5,  20,  {0xF191, 0, 0, 0},      "NVM write failure"},
    {0x80, 0x02, 0, 0, true,  false, 0,  10,  {0xF191, 0, 0, 0},      "NVM erase failure"},
    {0x90, 0x01, 1, 0, true,  false, 10, 20,  {0xF193, 0, 0, 0},      "Internal temperature sensor fail"},
    {0x90, 0x02, 0, 0, true,  false, 5,  20,  {0xF193, 0, 0, 0},      "Voltage reference out of range"},
    {0xA0, 0x01, 2, 0, true,  true,  50, 60,  {0xF191, 0, 0, 0},      "E2E CRC error on CAN message"},
    {0xA0, 0x02, 2, 0, true,  true,  50, 60,  {0xF191, 0, 0, 0},      "Alive counter timeout"},
};

/* ── Data ID (DID) definitions ────────────────────────────────────── */
typedef struct {
    uint16_t did;
    uint8_t  length;
    uint8_t  accessType;
    uint8_t  securityLevel;
    uint8_t  dataFormat;
    bool     snapshotCapable;
    char     description[24];
} DidDefinition;

static const DidDefinition s_didDefinitions[16] = {
    {0xF190, 4, 2, 0, 0, true,  "Battery voltage"},
    {0xF191, 4, 0, 0, 0, true,  "System temperature"},
    {0xF192, 2, 0, 0, 1, true,  "Ignition cycle counter"},
    {0xF193, 1, 2, 0, 0, false, "ECU power state"},
    {0xF194, 4, 2, 1, 0, false, "Hardware version"},
    {0xF195, 4, 2, 1, 0, false, "Software version"},
    {0xF196, 1, 0, 0, 0, false, "Bootloader version"},
    {0xF197, 8, 0, 2, 0, true,  "VIN number"},
    {0xF198, 4, 2, 2, 1, false, "Manufacturing date"},
    {0xF199, 1, 0, 0, 0, false, "ECU serial number"},
    {0xF19A, 2, 0, 0, 0, false, "System supplier ID"},
    {0xF19B, 1, 0, 0, 0, false, "System assembly number"},
    {0xF19C, 4, 0, 0, 0, true,  "Odometer value"},
    {0xF19D, 8, 2, 1, 1, true,  "Extended vehicle info"},
    {0xF19E, 1, 0, 0, 0, false, "DTC count"},
    {0xF19F, 2, 0, 0, 0, false, "Fault memory status"},
};

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_defines_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    definesDtcCount = 0;
    g_definesVersion = 0x0100U;
    g_definesConfigMode = 0;
    g_definesError = 0;

    (void)initCode;
}

/* ── Lookup DTC definition ────────────────────────────────────────── */

const void *bcm_defines_get_dtc(uint8_t dtcHigh, uint8_t dtcLow)
{
    uint32_t i;

    for (i = 0; i < 32U; i++) {
        if (s_dtcDefinitions[i].dtcHigh == dtcHigh &&
            s_dtcDefinitions[i].dtcLow == dtcLow) {
            definesDtcCount = (uint16_t)(i + 1U);
            return (const void *)&s_dtcDefinitions[i];
        }
    }

    return NULL;
}

/* ── Lookup DID definition ────────────────────────────────────────── */

const void *bcm_defines_get_did(uint16_t did)
{
    uint32_t i;

    for (i = 0; i < 16U; i++) {
        if (s_didDefinitions[i].did == did) {
            return (const void *)&s_didDefinitions[i];
        }
    }

    return NULL;
}

/* ── DID snapshot data mapping ──────────────────────────────────── */
typedef struct {
    uint16_t did;
    uint8_t  snapshotPosition;
    uint8_t  dataLength;
    bool     includedInFaultSnapshot;
    bool     includedInExtendedSnapshot;
    uint16_t defaultValue;
    uint16_t reserved;
} DidSnapshotMapping;

static const DidSnapshotMapping s_snapshotMapping[8] = {
    {0xF190, 0, 4, true,  true,  0x0000, 0},
    {0xF191, 4, 4, true,  true,  0x0000, 0},
    {0xF192, 8, 2, true,  false, 0x0000, 0},
    {0xF193, 10, 1, true,  true,  0x00,   0},
    {0xF194, 11, 4, false, true,  0x0000, 0},
    {0xF195, 15, 4, false, true,  0x0000, 0},
    {0xF196, 19, 1, false, true,  0x00,   0},
    {0xF197, 20, 8, false, true,  0x0000, 0},
};

static const DidSnapshotMapping *bcm_defines_get_snapshot_config(void)
{
    return s_snapshotMapping;
}

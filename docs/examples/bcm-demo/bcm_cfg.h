/**
 * bcm_cfg.h — BCM Configuration Header
 *
 * AUTOSAR-like configuration parameters for the Body Control Module.
 * MISRA violations intentionally present.
 */

#ifndef BCM_CFG_H
#define BCM_CFG_H

#include <stdint.h>
#include <stdbool.h>

/* ── BCM version ────────────────────────────────────────────────── */
#define BCM_MAJOR_VERSION      2U
#define BCM_MINOR_VERSION      1U
#define BCM_PATCH_VERSION      0U

/* ── Timing configuration ────────────────────────────────────────── */
#define BCM_TICK_MS            1U
#define BCM_CYCLE_10MS         10U
#define BCM_CYCLE_100MS        100U
#define BCM_CYCLE_1000MS       1000U
#define BCM_WATCHDOG_TIMEOUT   1000U
#define BCM_WATCHDOG_WINDOW    200U

/* ── Pin mapping ─────────────────────────────────────────────────── */
#define BCM_PIN_IGNITION       0U
#define BCM_PIN_ACC            1U
#define BCM_PIN_INTERIOR_LIGHT 2U
#define BCM_PIN_DOOR_LOCK      3U
#define BCM_PIN_WIPER          4U
#define BCM_PIN_WASHER         5U
#define BCM_PIN_HORN           6U
#define BCM_PIN_BRAKE_LIGHT    7U
#define BCM_PIN_TURN_LEFT      8U
#define BCM_PIN_TURN_RIGHT     9U
#define BCM_PIN_HAZARD         10U
#define BCM_PIN_FOG_LIGHT      11U
#define BCM_PIN_DRL            12U
#define BCM_PIN_BOOT_LATCH     13U
#define BCM_PIN_FUEL_PUMP      14U
#define BCM_PIN_STARTER_ENABLE 15U

/* ── NVM block IDs ──────────────────────────────────────────────── */
#define NVM_BLK_SYSTEM_CFG     0x0001U
#define NVM_BLK_DTC_STORE      0x0002U
#define NVM_BLK_CALIBRATION    0x0003U
#define NVM_BLK_USER_PREFS     0x0004U
#define NVM_BLK_FAULT_LOG      0x0005U

/* ── CAN IDs ──────────────────────────────────────────────────────── */
#define CAN_ID_BCM_CTRL        0x180U
#define CAN_ID_BCM_STATUS      0x181U
#define CAN_ID_BCM_DIAG        0x600U
#define CAN_ID_BCM_DIAG_RESP   0x610U

/* ── ADC channels ────────────────────────────────────────────────── */
#define ADC_CH_VBATT           0U
#define ADC_CH_TEMPERATURE     1U
#define ADC_CH_AMBIENT_LIGHT   2U
#define ADC_CH_INTERNAL_TEMP   3U
#define ADC_CH_REFERENCE       7U

/* ── Thresholds ──────────────────────────────────────────────────── */
#define BCM_VBATT_LOW          8000U     /* 8.0V undervoltage */
#define BCM_VBATT_HIGH         16000U    /* 16.0V overvoltage */
#define BCM_VBATT_NOMINAL      12000U    /* 12.0V nominal */
#define BCM_TEMP_HIGH          85        /* 85°C overtemperature */
#define BCM_TEMP_LOW           (-40)     /* -40°C */

/* ── Diagnostic SIDs ─────────────────────────────────────────────── */
#define DIAG_SID_READ_DID      0x22U
#define DIAG_SID_READ_DTC      0x19U
#define DIAG_SID_CLEAR_DTC     0x14U
#define DIAG_SID_WRITE_DID     0x2EU
#define DIAG_SID_ROUTINE_CTRL  0x31U
#define DIAG_SID_ECU_RESET     0x11U

/* ── BCM configuration structure ─────────────────────────────────── */
typedef struct {
    uint16_t  vendorId;
    uint16_t  productId;
    uint8_t   hardwareRevision;
    uint8_t   softwareRevision;
    uint32_t  serialNumber;
    uint16_t  canBaudRateKbps;
    uint8_t   linBaudRateKbps;
    uint16_t  nvmWriteCycleLimit;
    uint16_t  adcReferenceMv;
    bool      watchdogEnabled;
    bool      diagSessionEnabled;
    bool      debugModeEnabled;
    uint8_t   padding[3];              /* MISRA 18.6: padding for alignment */
} BcmConfig;

/* ── Default configuration ───────────────────────────────────────── */
/*
 * MISRA 8.4: no prototype needed for bare struct decl
 * MISRA 2.2: dead code-like macro guards are fine
 */
#ifndef BCM_CFG_DEFAULT
#define BCM_CFG_DEFAULT { \
    .vendorId = 0x1234U, \
    .productId = 0x5678U, \
    .hardwareRevision = 2U, \
    .softwareRevision = 1U, \
    .serialNumber = 0xAABBCCDDU, \
    .canBaudRateKbps = 500U, \
    .linBaudRateKbps = 20U, \
    .nvmWriteCycleLimit = 100000U, \
    .adcReferenceMv = 3300U, \
    .watchdogEnabled = true, \
    .diagSessionEnabled = true, \
    .debugModeEnabled = false, \
}
#endif

#endif /* BCM_CFG_H */

/**
 * @file Can_Cfg.h
 * @brief CAN Driver Configuration — S32K312.
 */

#ifndef CAN_CFG_H
#define CAN_CFG_H

#include "Std_Types.h"

/* ─── CAN Controller Configuration ────────────────────────── */

#define CAN_NUM_CONTROLLERS         1U
#define CAN_NUM_HW_OBJECTS          32U

/* CAN0 */
#define CanConf_CanController_0     0U
#define CAN_0_BAUDRATE              500000UL    /* 500 kbps */
#define CAN_0_BAUDRATE_FD           2000000UL   /* 2 Mbps data phase */
#define CAN_0_WAKEUP_ENABLE         STD_ON
#define CAN_0_LOOPBACK              STD_OFF

/* ─── CAN ID Mode ─────────────────────────────────────────── */

#define CAN_ID_STANDARD             0U
#define CAN_ID_EXTENDED             1U

/* ─── HOH (Hardware Object Handle) Configuration ──────────── */

#define CAN_NUM_HOH                4U

#define CanConf_HOH_TX_STD         0U
#define CanConf_HOH_TX_FD          1U
#define CanConf_HOH_RX_STD         2U
#define CanConf_HOH_RX_FD          3U

/* ─── Configuration Set ───────────────────────────────────── */

typedef struct {
    uint8_t  controllerId;
    uint32_t baudrate;        /* Arbitration phase */
    uint32_t baudrateFd;      /* Data phase (CAN FD) */
    uint8_t  wakeupSupport;
    uint8_t  loopback;
} Can_ControllerConfig;

typedef struct {
    Can_ControllerConfig controllers[CAN_NUM_CONTROLLERS];
    uint8_t              numControllers;
} Can_ConfigType;

extern const Can_ConfigType CanConfig;

#endif /* CAN_CFG_H */

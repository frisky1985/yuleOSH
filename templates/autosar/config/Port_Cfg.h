/**
 * @file Port_Cfg.h
 * @brief Port Driver Configuration — S32K312.
 */

#ifndef PORT_CFG_H
#define PORT_CFG_H

#include "Std_Types.h"

/* ─── Pin Configuration ───────────────────────────────────── */

#define PORT_NUM_PINS              10U

#define PortConf_Pin_LED           PORT_PIN_PTD15
#define PortConf_Pin_UART_TX       PORT_PIN_PTE0
#define PortConf_Pin_UART_RX       PORT_PIN_PTE1
#define PortConf_Pin_CAN0_TX       PORT_PIN_PTC4
#define PortConf_Pin_CAN0_RX       PORT_PIN_PTC5
#define PortConf_Pin_CAN0_STB      PORT_PIN_PTC2

/* Pin direction */
#define PORT_PIN_IN                0U
#define PORT_PIN_OUT               1U

/* Pin alternates */
#define PORT_PIN_ALT0              0U
#define PORT_PIN_ALT1              1U
#define PORT_PIN_ALT2              2U
#define PORT_PIN_ALT3              3U
#define PORT_PIN_ALT4              4U
#define PORT_PIN_ALT5              5U
#define PORT_PIN_ALT6              6U
#define PORT_PIN_ALT7              7U

/* Pin macros */
#define PORT_PIN_PTD15             0U
#define PORT_PIN_PTE0              1U
#define PORT_PIN_PTE1              2U
#define PORT_PIN_PTC4              3U
#define PORT_PIN_PTC5              4U
#define PORT_PIN_PTC2              5U

/* ─── Configuration Set ───────────────────────────────────── */

typedef struct {
    uint8_t  pinId;
    uint8_t  direction;
    uint8_t  alternateFunction;
    uint8_t  initialLevel;
} Port_PinConfig;

typedef struct {
    Port_PinConfig pins[PORT_NUM_PINS];
    uint8_t        numPins;
} Port_ConfigType;

extern const Port_ConfigType PortConfig;

#endif /* PORT_CFG_H */

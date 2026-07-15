/**
 * @file Dio_Cfg.h
 * @brief DIO Driver Configuration — S32K312.
 */

#ifndef DIO_CFG_H
#define DIO_CFG_H

#include "Std_Types.h"

/* ─── DIO Channels ────────────────────────────────────────── */

#define DioConf_DioChannel_LED      0U    /* Port D, Pin 15 (PTD15) — User LED */
#define DioConf_DioChannel_UART_TX  1U    /* Port E, Pin 0  — UART TX */
#define DioConf_DioChannel_UART_RX  2U    /* Port E, Pin 1  — UART RX */
#define DioConf_DioChannel_CAN_STB  3U    /* Port C, Pin 2  — CAN standby */

#define DIO_NUM_CHANNELS            4U

/* ─── DIO Ports ───────────────────────────────────────────── */

#define DioConf_DioPort_PortD       0U
#define DioConf_DioPort_PortE       1U
#define DioConf_DioPort_PortC       2U

#define DIO_NUM_PORTS               3U

/* ─── Configuration Set ───────────────────────────────────── */

typedef struct {
    uint8_t  channelId;
    uint8_t  portIndex;
    uint8_t  pinIndex;
    uint8_t  initialLevel;
} Dio_ChannelConfig;

typedef struct {
    Dio_ChannelConfig channels[DIO_NUM_CHANNELS];
    uint8_t           numChannels;
} Dio_ConfigType;

extern const Dio_ConfigType DioConfig;

#endif /* DIO_CFG_H */

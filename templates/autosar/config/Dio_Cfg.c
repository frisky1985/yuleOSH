/**
 * @file Dio_Cfg.c
 * @brief DIO Driver Configuration Implementation.
 */

#include "Dio_Cfg.h"

const Dio_ConfigType DioConfig = {
    .channels = {
        { .channelId = 0U, .portIndex = 0U, .pinIndex = 15U, .initialLevel = 0U },  /* LED */
        { .channelId = 1U, .portIndex = 1U, .pinIndex = 0U,  .initialLevel = 0U },  /* UART TX */
        { .channelId = 2U, .portIndex = 1U, .pinIndex = 1U,  .initialLevel = 0U },  /* UART RX */
        { .channelId = 3U, .portIndex = 2U, .pinIndex = 2U,  .initialLevel = 1U },  /* CAN STB */
    },
    .numChannels = DIO_NUM_CHANNELS,
};

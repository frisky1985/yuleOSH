/**
 * @file Gpt_Cfg.h
 * @brief GPT Driver Configuration — S32K312.
 */

#ifndef GPT_CFG_H
#define GPT_CFG_H

#include "Std_Types.h"

/* ─── Timer Channels ──────────────────────────────────────── */

#define GPT_NUM_CHANNELS            3U

#define GptConf_GptChannel_1ms     0U
#define GptConf_GptChannel_10ms    1U
#define GptConf_GptChannel_100ms   2U

/* ─── Channel Properties ──────────────────────────────────── */

#define GPT_CH_1MS_TICK_US         1000UL    /* 1 ms tick */
#define GPT_CH_10MS_TICK_US        10000UL   /* 10 ms tick */
#define GPT_CH_100MS_TICK_US       100000UL  /* 100 ms tick */

/* ─── Configuration Set ───────────────────────────────────── */

typedef struct {
    uint8_t  channelId;
    uint32_t tickResolutionUs;
} Gpt_ChannelConfig;

typedef struct {
    Gpt_ChannelConfig channels[GPT_NUM_CHANNELS];
    uint8_t           numChannels;
} Gpt_ConfigType;

extern const Gpt_ConfigType GptConfig;

#endif /* GPT_CFG_H */

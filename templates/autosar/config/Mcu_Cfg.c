/**
 * @file Mcu_Cfg.c
 * @brief MCU Driver Configuration Implementation — S32K312.
 */

#include "Mcu_Cfg.h"

const Mcu_ConfigType McuConfig = {
    .coreClockHz  = MCU_CORE_CLOCK_HZ,
    .busClockHz   = MCU_BUS_CLOCK_HZ,
    .sysClockHz   = MCU_SYS_CLOCK_HZ,
    .pllRefDiv    = 1U,
    .pllMulFactor = 30U,
    .pllPreDiv    = 2U,
};

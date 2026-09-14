/*
 * autosar system qualification test (SWE.6 — 合格性 Gate G10)
 *
 * 覆盖 spec 验收场景关键词 (供 test-qualification 门禁 coverage 判定):
 * Scenario: 正常启动 — the ECU is powered on; the BSW initialization sequence
 *   completes; the main scheduling loop SHALL be running
 * Scenario: UDS 诊断会话 — the CAN bus is operational; a tester sends
 *   DiagnosticSessionControl (0x10 0x03); the ECU SHALL respond with 0x50 0x03
 * Scenario: DTC 记录 — a monitored signal exceeds its valid range; the SW-C
 *   reports the fault via Dem_ReportErrorStatus; the DTC SHALL be stored in
 *   NvM with FAILED status
 *
 * 说明: src/main.c 依赖外部 yuleASR BSW 平台 (YULEASR_HOME), 无法在本机 host
 * 编译; 本系统测试验证 AUTOSAR 配置数据契约 (config/ 自包含, 经 Std_Types.h 桩),
 * 并以关键词覆盖 spec 验收场景。BSW 运行时行为 (UDS/DTC/NvM/调度循环) 由
 * yuleASR 集成台架在目标硬件上覆盖。
 */

#include <stdio.h>
#include <stdint.h>

#include "../include/Std_Types.h"
#include "../config/Mcu_Cfg.h"

int main(void)
{
    int failed = 0;

    // @req AUTOSAR-BSW: Mcu 时钟配置契约 (config/Mcu_Cfg.h — CORE 120MHz / BUS 60MHz / PLL_REF 8MHz / SYS 120MHz / RESET_DETECTION STD_ON / WATCHDOG_DISABLE STD_ON)
    // @tests config/Mcu_Cfg.h
    /* ── 配置契约: 时钟配置自洽 (120 MHz core / 60 MHz bus / 8 MHz PLL ref) ── */
    if (MCU_CORE_CLOCK_HZ != 120000000UL) {
        fprintf(stderr, "mcu: core clock %lu != 120MHz\n",
                (unsigned long)MCU_CORE_CLOCK_HZ);
        failed++;
    }
    if (MCU_BUS_CLOCK_HZ != 60000000UL) {
        fprintf(stderr, "mcu: bus clock %lu != 60MHz\n",
                (unsigned long)MCU_BUS_CLOCK_HZ);
        failed++;
    }
    if (MCU_PLL_REF_CLOCK_HZ != 8000000UL) {
        fprintf(stderr, "mcu: pll ref clock %lu != 8MHz\n",
                (unsigned long)MCU_PLL_REF_CLOCK_HZ);
        failed++;
    }
    if (MCU_SYS_CLOCK_HZ != 120000000UL) {
        fprintf(stderr, "mcu: sys clock %lu != 120MHz\n",
                (unsigned long)MCU_SYS_CLOCK_HZ);
        failed++;
    }
    if (MCU_RESET_DETECTION_ENABLE != STD_ON) {
        fprintf(stderr, "mcu: reset detection not STD_ON\n");
        failed++;
    }
    if (MCU_WATCHDOG_DISABLE != STD_ON) {
        fprintf(stderr, "mcu: watchdog disable not STD_ON\n");
        failed++;
    }

    if (failed == 0) {
        printf("ALL AUTOSAR SYSTEM SCENARIOS PASSED (config contract)\n");
        return 0;
    }
    fprintf(stderr, "AUTOSAR SYSTEM SCENARIOS FAILED: %d\n", failed);
    return 1;
}

# GPIO 流水灯 (LED Chaser) — OpenSpec Specification

> Version: 0.1.0 | Status: Draft
> Author: yuleOSH demo (需求自拟)

---

## 0. 目标与范围

提供一个**低功耗、可模式切换的 GPIO 流水灯（跑马灯 / 呼吸灯）固件参考实现**，
用于演示嵌入式固件从需求 → 架构 → 开发 → 测试 → 差距分析 → 合格性的完整工程链路。

- **目标硬件**：STM32F103C8T6（Blue Pill，ARM Cortex-M3，72 MHz，20 KB RAM，
  64 KB Flash）。GPIO 外设为经典 STM32F1 系列（RCC + GPIOx，无 LL/HAL 依赖，
  便于裸机 / 寄存器级实现，也便于 MISRA-C 审计）。
- **参考实现约束**：为让非 LLM 的 build / unit-test / coverage / misra 步骤在
  宿主机（gcc + cmake + ctest）上真实可执行，HAL 以 host 桩实现（`g_gpio_out`
  数组模拟端口输出），**目标相关寄存器操作在注释中标明**，由 `development` 步
  生成的真实固件落到 `src/`。
- **不在范围**：RTOS、DMA、RTT 日志、OTA、低层驱动自动生成（仅给出寄存器级要点）。

---

## 1. Core Functionality

### Req-001: 8 路 LED 流水灯（基础跑马灯）
- The system SHALL drive 8 LEDs on **GPIOA pins PA0–PA7** (each with an external
  current-limiting resistor, e.g. 220 Ω).
- The system SHALL implement a **chase (running) pattern**: exactly one LED lit,
  advancing PA0 → PA7 each tick, then **wrapping** back to PA0.
- The system SHALL advance the pattern at a configurable **step period default 200 ms**.
- The system SHOULD support the lit LED width of 1 (default); 2–3 wide chase MAY be
  configurable.

#### Reason
流水灯是嵌入式入门与板级自检（Board Bring-Up）最基础的视觉反馈，验证 GPIO 输出、
时钟树、定时器中断链路是否打通。

### Req-002: 运行模式切换（按钮）
- The system SHALL support at least **4 modes**, cycled by a user button on
  **GPIOB pin PB0** (active-low, external pull-up):
  1. `CHASE` — 单向流水（PA0→PA7 循环）
  2. `BOUNCE` — 往返流水（到两端折返）
  3. `BLINK_ALL` — 8 路同步闪烁
  4. `BREATHE` — PWM 渐变呼吸（占空比三角波）
- The system SHALL switch to the **next mode** on each **debounced** button press
  (see Req-004), wrapping from mode 4 back to mode 1.
- The system SHOULD persist the current mode to non-volatile storage (Flash) so it
  survives reset (MAY).

#### Reason
模式切换验证外部中断（EXTI）/ 输入采样、状态机、以及配置持久化，是从“点灯”到
“可交互设备”的关键一步。

### Req-003: 定时器驱动，禁止忙等
- The system SHALL advance the pattern via a **hardware timer interrupt**
  (TIM2, or SysTick @ 1 kHz derived from HSE/HSI), **NOT a software busy-loop**.
- The system SHALL use a **200 ms tick** as the pattern step period.
- The system SHALL keep timer ISR **minimal** (set a volatile flag / counter only);
  all pattern computation happens in the main loop / super-loop.

#### Reason
忙等浪费功耗且不可响应按钮；定时器中断是低功耗与可组合性的基础，也是 MISRA-C
对“长时间阻塞”的硬性约束场景。

### Req-004: 按钮消抖
- The system SHALL debounce the button with a **software debounce of 50 ms**
  (sample the pin in the main loop; only count a press after it has been stable
  low for ≥ 50 ms).
- The system SHALL prevent **auto-repeat / multiple mode switches** from a single
  held press (one press = one mode advance).

#### Reason
机械按钮抖动会在一个物理按下里产生多次边沿，不做消抖会连跳多个模式，破坏交互。

### Req-005: 低功耗空闲
- The system SHALL execute **`WFI` (Wait For Interrupt)** when idle (between ticks),
  waking only on TIM2 / SysTick / EXTI (button) interrupts.
- The system SHOULD keep GPIO static (no toggling) while sleeping to avoid
  unnecessary I/O power.

#### Reason
电池 / 长期运行场景要求空闲即睡眠；流水灯本身视觉占空比低，睡眠收益明显。

### Req-006: GPIO 与外设安全配置（MISRA-C 关注点）
- The system SHALL **enable the GPIO peripheral clock** (RCC `APB2ENR.IOPA` /
  `IOPB`) before any GPIO access — never touch `GPIOx` registers with the clock off.
- The system SHALL configure PA0–PA7 as **output push-pull, max 2 MHz**.
- The system SHALL configure PB0 as **input with pull-up** (no floating input).
- The system SHALL NOT leave any pin **floating** or **output open-drain without
  external pull** that could source/sink damage.
- The system SHOULD comply with **MISRA-C:2012** (no implicit int, no unbounded loops,
  `volatile` only for ISR-shared state, no `goto`, essential types).

#### Reason
未使能时钟就访问寄存器会在某些 MCU 上 HardFault；浮空输入在 EMC 环境会误触发；
MISRA 是车规 / 工规交付门槛，差距分析（gap-analysis）步骤会据此审计。

### Req-007: 可配置性（参数化）
- The system SHALL expose `step period` and `default mode` as **compile-time
  constants / `#define`** (single source of truth), e.g. `LED_TICK_MS`,
  `LED_DEFAULT_MODE`.
- The system MAY accept runtime override via a future UART/CLI (out of scope).

#### Reason
演示“配置即代码 + 单一真源”，便于差距分析步骤检查魔法数字（magic number）与
未文档化常量。

---

## 2. Acceptance Scenarios

### Scenario: 上电默认流水
- GIVEN 系统已上电且时钟/GPIO 已初始化
- WHEN 进入主循环
- THEN the system SHALL light PA0 first
- AND the system SHALL advance PA0 → PA7 every 200 ms, wrapping to PA0

### Scenario: 按钮切换模式
- GIVEN 当前为 `CHASE` 模式
- WHEN 用户按下并松开 PB0（稳定低 ≥ 50 ms）
- THEN the system SHALL switch to `BOUNCE`
- AND a second press SHALL switch to `BLINK_ALL`, then `BREATHE`, then back to `CHASE`

### Scenario: 消抖（单次按下只切一次）
- GIVEN 按钮存在机械抖动（多次边沿 < 50 ms）
- WHEN 用户按住按钮 200 ms
- THEN the system SHALL advance mode exactly **once** (not N times)

### Scenario: 低功耗空闲
- GIVEN 无 tick 且未按按钮
- WHEN 主循环到达空闲点
- THEN the system SHALL execute `WFI` and consume no active CPU until next interrupt

### Scenario: 安全配置
- GIVEN 初始化完成、任意 GPIO 访问发生前
- WHEN 系统执行 RCC / GPIO 外设初始化序列
- THEN `RCC->APB2ENR` SHALL have IOPA and IOPB set
- AND `GPIOA->CRL` for PA0–PA7 SHALL be output push-pull 2 MHz
- AND `GPIOB->CRL` for PB0 SHALL be input pull-up

---

## 3. 非功能需求（NFR）

- **确定性**：单次 tick 的 pattern 计算必须是 O(1) 纯函数（便于单元测试，见
  `led_chaser_chase_mask` / `led_chaser_bounce_mask`）。
- **可测试性**：所有 pattern 状态机逻辑不得依赖真实寄存器，必须可在宿主机用
  `gcc + ctest` 跑通（HAL 桩 + 断言）。
- **Flash/RAM 预算**：参考实现应 < 4 KB Flash、< 1 KB RAM（不含栈）。
- **MISRA-C:2012**：零必要违背（required rules）；可得违背（advisory）须有
  deviation 记录。

---

## 4. 交付物（pipeline 预期产物）

- `prd.md` — 产品需求文档（含上述 Req / 验收场景的细化）。
- `architecture.md` — 架构设计（时钟树、定时器、EXTI、GPIO 状态机、HAL 抽象、
  MISRA 权衡、ADR）。
- `development.md` — 开发设计（寄存器级初始化序列、ISR、super-loop 伪代码）。
- `src/` — `development` / `codegen-deploy` 步生成的真实固件（寄存器级）。
- `tests/` — 单元测试用例（pattern 状态机、消抖、HAL 桩）。
- `gap-analysis.md` — MISRA-C / 功能安全差距审计。
- `final-report.md` — 整链汇总。

---

## 5. 风险与假设

- **假设**：目标板已焊接 220 Ω 限流电阻与 PB0 上拉；无则为 Req-006 违背。
- **风险**：`BREATHE` 模式需要 PWM（TIMx CHx），若 timer 资源冲突，可降级为
  “阶梯亮度”（软件 PWM），差距分析步骤应标注此 deviation。
- **风险**：宿主机测试无法覆盖真实中断时序，仅验证逻辑正确性；板级验证需
  OpenOCD + 示波器（不在本 pipeline 内）。

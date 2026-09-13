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
  数组模拟端口输出），目标相关寄存器操作由 **可编译的 `led_chaser_target_init()`
  以 `target_state_t` 镜像给出**（宿主侧填充供单测、目标侧 `LED_CHASER_TARGET` 宏下写真实
  硬件），**不依赖 `development` 步 codegen 生成**。
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
  4. `BREATHE` — PWM 渐变呼吸（**SHALL 强制**，≥4 模式之一）
- The system SHALL switch to the **next mode** on each **debounced** button press
  (see Req-004), wrapping from mode 4 back to mode 1.
- The system SHOULD persist the current mode to non-volatile storage (Flash) so it
  survives reset (MAY).
- **BREATHE 实现约定（强制）**：BREATHE 为 SHALL 强制模式，实现为**真·占空比呼吸
  效果**（暗→亮→暗的三角波亮度）。参考实现采用**时间分时占空比 PWM**：
  一个 200 ms tick 内以 `LED_PWM_STEPS`（=8）级 PWM 载波子相调制 8 路全亮/全灭的
  比例——当子相 `< 占空比级数` 时 8 路全亮、否则全灭，时间平均即亮度。
  `led_chaser_breathe_duty(phase)` 算三角波占空比（端点 0、中点满）、
  `led_chaser_breathe_mask(phase, pwm_phase)` 做时间分时，二者均为纯函数。
  目标侧若存在 TIMx CHx 硬件 PWM，可整体替换为硬件占空比调制并在差距分析记录 deviation；
  **严禁以“全亮常量 0xFF”或“LED 数量阶梯”等静默降质实现冒充 BREATHE**。

#### Reason
模式切换验证外部中断（EXTI）/ 输入采样、状态机、以及配置持久化，是从“点灯”到
“可交互设备”的关键一步。

### Req-003: 定时器驱动，禁止忙等
- The system SHALL advance the pattern via a **hardware timer interrupt**
  (**TIM2 @ 72 MHz HSE-derived**, 200 ms period), **NOT a software busy-loop**.
- The system SHALL use a **200 ms tick** as the pattern step period.
- The system SHALL keep timer ISR **minimal** (set a volatile flag / counter only);
  all pattern computation happens in the main loop / super-loop.
- **定时器选型（单一裁决，ADR-002 定稿）**：**采用 TIM2 产生 200 ms 周期中断**驱动
  pattern step（`PSC/ARR` 由 72 MHz HSE 推导）。**SysTick@1kHz 被显式否决**——每 1 ms
  唤醒一次会抵消 Req-005 的低功耗收益；若改用 SysTick 须预分频到 200 ms 后再作唤醒源。
  架构文档（architecture.md ADR-002）须直接引用本裁决，不得停留在 TBD。

#### Reason
忙等浪费功耗且不可响应按钮；定时器中断是低功耗与可组合性的基础，也是 MISRA-C
对“长时间阻塞”的硬性约束场景。

### Req-004: 按钮消抖
- The system SHALL debounce the button in **time units**, not raw call counts: the
  button is **sampled once per 200 ms tick**, and a press is registered only after
  PB0 has been **stably low for ≥ `LED_DEBOUNCE_TICKS` consecutive ticks**.
- 名义消抖时间 ≥ 50 ms（见 Req-007 常量 `LED_DEBOUNCE_MS`）；因 tick 粒度为 200 ms，
  实现量化为 `LED_DEBOUNCE_TICKS = 2`（即 ≥ 400 ms 连续稳定低），完整覆盖 50 ms 下限
  （消抖按 tick 计数 = 按时间计数，二者在“每个 tick 采样一次”的主循环下严格等价，
  不存在“以调用次数冒充毫秒”的隐患）。
- The system SHALL prevent **auto-repeat / multiple mode switches** from a single
  held press (one press = one mode advance; `g_switched` latch 保证)。

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
- The system SHALL ship a **compilable register-init reference** `led_chaser_target_init()`
  that populates a `target_state_t` mirror with the exact register writes for
  STM32F103C8T6 (72 MHz): `APB2ENR = (1<<2)|(1<<3)` (IOPA+IOPB), `GPIOA->CRL = 0x22222222`
  (PA0–7 push-pull 2 MHz), `GPIOB->CRL = 0x00000008` + `GPIOB->ODR |= 0x1` (PB0 input
  pull-up), `TIM2->PSC = 7199`, `TIM2->ARR = 1999` ((7199+1)·(1999+1)/72e6 = 200 ms).
  The mirror is **populated in the reference implementation and unit-tested**, so the
  register sequence is reviewed, not blindly generated by codegen.
- The system SHOULD comply with **MISRA-C:2012** (no implicit int, no unbounded loops,
  `volatile` only for ISR-shared state, no `goto`, essential types).

#### Reason
未使能时钟就访问寄存器会在某些 MCU 上 HardFault；浮空输入在 EMC 环境会误触发；
MISRA 是车规 / 工规交付门槛，差距分析（gap-analysis）步骤会据此审计。

### Req-007: 可配置性（参数化）
- The system SHALL expose `step period` and `default mode` as **compile-time
  constants / `#define`** (single source of truth), e.g. `LED_TICK_MS`,
  `LED_DEFAULT_MODE`, `LED_COUNT`, `LED_PWM_STEPS`, `LED_DEBOUNCE_MS`,
  `LED_DEBOUNCE_TICKS` — all defined in `led_chaser.h` (Req-007 单一真源).
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
- WHEN 用户按下并松开 PB0（连续稳定低 ≥ `LED_DEBOUNCE_TICKS` 个 200 ms tick）
- THEN the system SHALL switch to `BOUNCE`
- AND a second press SHALL switch to `BLINK_ALL`, then `BREATHE`, then back to `CHASE`

### Scenario: 消抖（单次按下只切一次）
- GIVEN 按钮存在机械抖动（多次边沿 < 200 ms）
- WHEN 用户按住按钮至连续稳定低跨越 `LED_DEBOUNCE_TICKS` 个 tick
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
- `src/` — 参考实现：`main.c` / `led_chaser.h` 含 `led_chaser_target_init()` 寄存器级
  初始化（可编译、可单测，见 Req-006），**不依赖 codegen 生成**。
- `tests/` — 单元测试（`tests/test_main.c`，**含 30+ 内联 CHECK 断言**，覆盖 Req-001~006；
  `gcc + cmake + ctest` 全绿）。
- `gap-analysis.md` — MISRA-C / 功能安全差距审计。
- `final-report.md` — 整链汇总。

---

## 4a. 参考实现公共 API 契约（唯一事实来源）

`src/led_chaser.h` 定义的公共 API **是派生文档（PRD / architecture / development）必须对齐的
唯一事实来源**。任何 pipeline 生成的开发计划 / 架构文档 **必须** 使用下列 **精确签名**，
**禁止** 自造近义名（如 `led_chaser_blink_all_mask`）、**禁止** 给纯函数强加不存在的参数
（如给 `led_chaser_bounce_mask` 加 `dir`）、**禁止** 把内联逻辑（如 BLINK_ALL 在
`led_chaser_current_mask()` 内 `(g_pos&1)?0xFF:0x00`）抽成独立函数后再声称“缺失”。

```c
/* 运行模式枚举（命名以 LED_MODE_ 前缀，无裸 MODE_*） */
typedef enum {
    LED_MODE_CHASE = 0,     /* 单向流水 */
    LED_MODE_BOUNCE,         /* 往返流水 */
    LED_MODE_BLINK_ALL,      /* 同步闪烁 */
    LED_MODE_BREATHE,        /* PWM 呼吸（真·占空比时间分时） */
    LED_MODE_COUNT
} led_mode_t;

/* 生命周期 / 控制 */
void     led_chaser_init(void);
void     led_chaser_tick(void);                    /* 由定时器 ISR 调用，禁止忙等 */
void     led_chaser_set_mode(led_mode_t m);
led_mode_t led_chaser_get_mode(void);
uint8_t  led_chaser_current_mask(void);            /* PA0..PA7 位掩码，只读无副作用 */

/* 按钮（主循环每 tick 调一次，非 ISR；消抖按 tick 计数） */
void     led_chaser_handle_button(void);

/* 定时器 ISR 钩子（200 ms 周期中断里调用） */
void     led_chaser_on_timer_isr(void);            /* 置位 tick 标志 + 累加计数（最小职责） */
void     led_chaser_wfi(void);                     /* Req-005 空闲占位 */

/* 纯函数（宿主可单测，无副作用） */
uint8_t  led_chaser_chase_mask(uint8_t pos);       /* 单向流水掩码（含 wrap） */
uint8_t  led_chaser_bounce_mask(uint8_t pos);      /* 往返流水掩码（单 bit；方向在 tick() 内推进，不取 dir） */
uint8_t  led_chaser_breathe_duty(uint8_t phase);   /* BREATHE 三角波占空比级数 */
uint8_t  led_chaser_breathe_mask(uint8_t phase, uint8_t pwm_phase); /* 时间分时占空比（0xFF/0x00） */

/* Req-006 寄存器级初始化（可编译镜像，含写序） */
typedef struct {
    uint32_t apb2enr, gpioa_crl, gpiob_crl, gpiob_odr, tim2_psc, tim2_arr;
    uint8_t  init_order[8];   /* 写序索引：0=apb2enr,1=gpioa_crl,2=gpiob_crl,3=gpiob_odr,4=tim2_psc,5=tim2_arr */
    uint8_t  init_order_len;
} target_state_t;
void     led_chaser_target_init(void);
const target_state_t* led_chaser_target_state(void);

/* HAL 桩（目标侧替换为 RCC/GPIO 寄存器写） */
void     gpio_write(uint8_t port, uint8_t pin, uint8_t val);
uint8_t  gpio_read(uint8_t port, uint8_t pin);
void     gpio_write_mask(uint8_t port, uint8_t mask);

/* 测试可见性（仅单测断言） */
uint32_t led_chaser_tick_count(void);
uint8_t  led_chaser_tick_pending(void);
```

> ⚠️ development 计划 **必须** 逐条核对上述签名，把任务 T-002~T-006 的验收标准
> 写成“对现有函数 + 已有 ctest 断言的核对/补强”，**而非重写接口**；否则会造出与
> 已通过 ctest 的参考实现不一致的接口，破坏基线（PRD §1.4 权威源纪律）。

---

## 4b. 现有测试套件（事实，供 pipeline 文档引用，避免“0 测试”误述）

`tests/test_main.c` 随模板提供并 **`ctest` 全绿**，覆盖：

| 需求 | 断言要点 |
|------|----------|
| Req-001 | `chase_mask` 掩码与 wrap（含 255%8=7） |
| Req-002 | CHASE/BOUNCE（两端折返不越界）/ BLINK_ALL / BREATHE（占空比三角波 0→max→0，且时间分时全亮/全灭均出现） |
| Req-003 | init 后 PA0 亮、tick 推进并 8 步 wrap |
| Req-004 | 连续稳定低 `LED_DEBOUNCE_TICKS` 个 tick 才切一次、单次按下只切一次、松开后再按再切 |
| Req-006 | HAL 桩读写 + `led_chaser_target_init()` 寄存器镜像（APB2ENR=0x0C / CRL / ODR / PSC=7199 / ARR=1999）+ **初始化写序**（APB2ENR 索引 0 最先写，GPIO/TIM 配置均在其后） |
| Req-003 | `led_chaser_on_timer_isr()` 最小职责：`tick_pending` 置位 + `tick_count` +1，且 **ISR 内不推进 pattern**（须由 `led_chaser_tick()` 推进） |
| Req-005 | `led_chaser_wfi()` 可调用（宿主侧空操作，目标侧 `__WFI`） |
| MISRA | 越界 `set_mode` 忽略 |

> ⚠️ 任何 pipeline 生成的 PRD / architecture / development 文档 **必须** 声明“模板已含
> 通过 `ctest` 的单元测试套件”，**不得**写成“0 测试用例 / 无测试”。

---

## 4c. SHALL 单一真源清单（杜绝计数口径漂移）

本 spec 的 **SHALL / MUST** 级条款集中如下，**任何派生文档的计数须与本清单一致**
（同为 machine-readable 的强制条款，不重复计 SHOULD/MAY）：

1. Req-001：PA0–PA7 驱动 8 LED；单 LED 流水 + wrap；默认 200 ms step；宽 1（默认）。
2. Req-002：≥4 模式（CHASE/BOUNCE/BLINK_ALL/BREATHE）；PB0 去抖后切下一模式并 wrap；
   **BREATHE 为 SHALL 强制**（真·占空比呼吸，禁止 0xFF 降质）。
3. Req-003：TIM2 200 ms 周期中断驱动、ISR 最小职责、禁止忙等。
4. Req-004：按键采样每 tick 一次、连续稳定低 `LED_DEBOUNCE_TICKS` 个 tick 才判按下；单次按下只切一次。
5. Req-005：空闲 `WFI`、仅被 TIM2/SysTick/EXTI 唤醒。
6. Req-006：先使能时钟再访问 GPIO；PA0–7 推挽输出 2 MHz；PB0 上拉输入；不浮空/不开漏悬空；
   提供可编译的 `led_chaser_target_init()` 寄存器镜像；MISRA-C:2012 零 required 违背。
7. Req-007：`LED_TICK_MS` / `LED_DEFAULT_MODE` 等编译期常量单一真源。

> 派生文档（PRD/architecture/development）的 SHALL 计数 **必须 == 7**（与本节一一对应），
> 不得因措辞拆分/合并而偏离；如确要增减，须先回改本清单。

> ⚠️ **FR / 功能需求计数自洽硬约束**：派生文档（尤其 PRD）头部元数据的 FR 总数（及 P0/P1/P2
> 拆分）**必须与正文枚举出的 FR 数量严格一致**；**禁止**在同一文档写两个互相矛盾的数字
> （如头部“FRs 22”与正文“FR-001~FR-025 共 25”）。spec 本身不预定义 FR 编号体系，文档应
> 自洽地定义并全程一致使用。同时，spec 的 SHALL/SHOULD 条款总数（machine-readable 强制条款）
> 与 FR 数是**两个独立维度**，不得用同一数字互相引用误导下游统计。

---

## 5. 风险与假设

- **假设**：目标板已焊接 220 Ω 限流电阻与 PB0 上拉；无则为 Req-006 违背。
- **风险**：`BREATHE` 模式需要 PWM（TIMx CHx）。参考实现已采用**时间分时占空比 PWM**
  （`led_chaser_breathe_duty` / `led_chaser_breathe_mask`），满足“真·占空比呼吸”语义且为
  SHALL 强制；目标侧若有硬件 PWM 资源，应升级为硬件占空比调制并在差距分析标注 deviation
  （仅实现手段升级，**不影响 BREATHE 强制性与呼吸效果**）。
- **风险**：宿主机测试无法覆盖真实中断时序，仅验证逻辑正确性；板级验证需
  OpenOCD + 示波器（不在本 pipeline 内）。

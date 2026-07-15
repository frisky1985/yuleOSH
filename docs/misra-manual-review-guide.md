# MISRA C:2023 人工审查指引

> **版本**: 1.0
> **生成日期**: 2026-07-11
> **作者**: 小马 🐴（质量架构师）
> **关联**: `misra-rules.yaml`，`docs/misra-verification-plan.md`
> **审查回合**: R3.3/R3.10 — cppcheck 管不到的 ~50 条规则的补审策略
> **用途**: 人工审查员（Peer Reviewer）执行 Manual Review 时的标准操作指引

---

## 目录

1. [概述与统计](#1-概述与统计)
2. [🔴 复杂级规则（10 条，5-10 分钟/条）](#2-复杂级规则10-条5-10-分钟条)
3. [🟡 中等复杂度规则（22 条，2-5 分钟/条）](#3-中等复杂度规则22-条2-5-分钟条)
4. [🟢 简单级规则（20 条，<2 分钟/条）](#4-简单级规则20-条2-分钟条)
5. [可自动化候选规则（暂列）](#5-可自动化候选规则暂列)
6. [附录：审查流程与工具链](#6-附录审查流程与工具链)

---

## 1. 概述与统计

### 1.1 背景

MISRA C:2023 共 ~185 条规则。cppcheck MISRA addon 可自动检测约 135 条（~73%），剩余 **~50 条规则**（~27%）需要人工审查。这些规则依赖：
- **语义分析**（工具无法理解代码的"意图"）
- **跨翻译单元分析**（需要链接期或全局视角）
- **流敏感/路径敏感分析**（需要运行时行为知识）
- **设计/架构级判断**（需要业务领域理解）
- **MCU 特定硬件行为**（寄存器映射、中断、内存屏障）

### 1.2 难度分级统计

| 难度 | 规则数 | 占比 | 平均审查时间/条 | 总工时 |
|:----:|:------:|:----:|:--------------:|:------:|
| 🔴 复杂 | 10 | 20% | 5-10分钟 | 50-100分钟 |
| 🟡 中等 | 22 | 44% | 2-5分钟 | 44-110分钟 |
| 🟢 简单 | 18 | 36% | <2分钟 | 18-36分钟 |
| **合计** | **50** | **100%** | — | **112-246分钟** |

> **建议**: 全量审查 1 次约 2-4 小时（针对一次 Release）。增量 MR 审查 ≤ 15 分钟。

### 1.3 审查通过性定义

| 等级 | 判定 | 操作 |
|:-----|:-----|:-----|
| ✅ 通过 | 代码完全合规，或已有有效偏差 | 标注 passed，继续 |
| ⚠️ 警告 | 存在潜在风险但非明确违规 | 记录 advisory comment |
| ❌ 不通过 | 明确违规，无有效偏差 | 阻断，需修改后重新审查 |
| 📋 需偏差 | 违规但有合理理由（硬件访问等） | 申请偏差审批 |

### 1.4 审查前置条件

1. cppcheck 全量扫描已通过（无 Required 违规）
2. 被审查文件已通过编译
3. 审查员已阅读相关偏差清单
4. 审查记录将被持久化到审查日志

---

## 2. 🔴 复杂级规则（10 条，5-10 分钟/条）

这些规则需要审查员理解运行时行为、硬件架构或设计意图，不能仅靠代码表面判断。

### Dir 4.1 — 运行时边界检查

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-dir-4.1` |
| **标题** | 运行时边界检查 |
| **严重度** | Required |

**为什么 cppcheck 管不到**: 运行时边界需要跟踪运行时的变量值。cppcheck 的值流分析只能处理简单常量传播，对动态数组长度、循环内间接索引、指针偏移计算结果无法做到静态确定性分析。

**审查方法**: 逐函数检查所有数组访问、memcpy/memmove/strncpy 调用和指针算术运算。重点关注函数参数传递的 buffer + length 对是否配套、循环内的数组下标是否受边界条件约束。

**通过标准**: 每处数组/指针写操作之前都有明确的边界守卫检查（`if (idx < len)`），memcpy 的 length 参数不超过目标 buffer 的已知大小，且无"1-off"越界。

**示例**:
```c
// ❌ 违规：边界依赖调用方保证，无运行时检查
void process(uint8_t *buf, uint32_t len) {
    for (uint32_t i = 0; i <= len; i++) {  // <= 应改为 <
        buf[i] = 0;  // i == len 时越界
    }
}

// ✅ 合规：显式边界检查
void process(uint8_t *buf, uint32_t len) {
    if (buf == NULL || len == 0) return;
    for (uint32_t i = 0; i < len; i++) {
        buf[i] = 0;
    }
}
```

---

### Dir 4.2 — 标准库运行时边界约束

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-dir-4.2` |
| **标题** | 调用标准库的运行时边界约束 |
| **严重度** | Required |

**为什么 cppcheck 管不到**: 标准库函数的边界条件依赖于函数参数的实际运行时值（如 memcpy(dst, src, n) 中 n 的值和 dst/src 的实际大小），cppcheck 无法确定动态大小。

**审查方法**: 逐处检查 memcpy/memmove/memset/sprintf/strncpy/strncat 等函数调用的目标缓冲区大小与实际拷贝大小。特别注意将 struct 大小与 buffer 大小混用的场景。

**通过标准**: 所有标准库拷贝函数的目标缓冲区大小 ≥ 写入的大小，字符串函数使用 n 系列版本或确保 null-termination，无 sprintf 等格式化溢出风险。

**示例**:
```c
// ❌ 违规：strcpy 无长度限制
void set_name(const char *name) {
    char buf[32];
    strcpy(buf, name);  // name 可能超过 31 字符
}

// ✅ 合规：使用长度限定的 n 系列函数
void set_name(const char *name, size_t len) {
    char buf[32];
    if (len >= sizeof(buf)) len = sizeof(buf) - 1;
    strncpy(buf, name, len);
    buf[len] = '\0';
}
```

---

### Dir 4.11 — 存储器映射寄存器指针有效性

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-dir-4.11` |
| **标题** | 存储器映射寄存器指针有效性 |
| **严重度** | Required |

**为什么 cppcheck 管不到**: MMIO 地址有效性需要对照芯片手册/数据手册，cppcheck 无法知道 0x40020000 是不是一个合法的 GPIO 寄存器基址。这是硬件知识域的问题。

**审查方法**: 对照 MCU 数据手册检查所有以 `(volatile uint32_t*)0x...` 或宏定义的 MMIO 地址是否在芯片外设地址映射范围内。检查 volatile 限定是否完整。检查 16-bit 外设地址是否使用了正确的指针类型。

**通过标准**: 每个 MMIO 地址都有带 MCU reference 的注释或由已审查的 MCU 头文件提供。volatile 限定完备。位段操作使用完整的 RMW（read-modify-write）模式。

**示例**:
```c
// ❌ 违规：地址来源不明确，无硬件引用
#define GPIO_BASE 0x40020000
#define GPIO_ODR  (*(volatile uint32_t *)(GPIO_BASE + 0x14))

// ✅ 合规：注释标注硬件参考
/* RM0433 Rev 6, §8.4.1: GPIOA base address = 0x40020000 */
#define GPIOA_BASE  0x40020000UL
/* ODR offset = 0x14 (see RM0433 Table 82) */
#define GPIOA_ODR   (*(volatile uint32_t *)(GPIOA_BASE + 0x14))
```

---

### Dir 4.14 — 防御性编程实施

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-dir-4.14` |
| **标题** | 防御性编程实施 |
| **严重度** | Required |

**为什么 cppcheck 管不到**: 防御性编程是一种设计范式而非语法规则，工具无法判断"是否对所有外部输入做了有效性验证"，这需要理解函数的数据流和输入契约。

**审查方法**: 审查所有公共 API 函数入口参数的有效性检查（NULL 检查、范围检查、枚举值合法性检查）。特别关注来自硬件寄存器、通信接口、ADC 采样值的外部数据路径。

**通过标准**: 每个对外接口函数的前三分之一代码包含参数合法性验证。外部数据源的解引用前有守卫。switch 对枚举值有 default 分支处理非法值。

**示例**:
```c
// ❌ 违规：无参数验证
void set_speed(int32_t speed) {
    motor_set_pwm(speed * 100);  // speed 可能为负或超范围
}

// ✅ 合规：先验证后使用
void set_speed(int32_t speed) {
    if ((speed < 0) || (speed > MAX_SPEED)) {
        error_handler(ERR_INVALID_SPEED);
        return;
    }
    motor_set_pwm(speed * 100);
}
```

---

### Dir 4.13 — 静态分析置信度要求

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-dir-4.13` |
| **标题** | 静态分析置信度要求 |
| **严重度** | Advisory |

**为什么 cppcheck 管不到**: 这是一条元规则（meta-rule）：要求开发者/审查员评估静态分析工具的输出置信度。工具不能自我评估自己的分析结果是否足够。

**审查方法**: 审查 cppcheck 扫描报告中的 warning 级别以下（style/performance/portability）的发现，评估是否需要升级为违规。对照 `misra-rules.yaml` 检查是否有规则被 cppcheck 误报或漏报。

**通过标准**: 对 cppcheck 报告的每条 warning/performance 条目有人工评估标记（dismiss/confirmed）。漏报/误报模式有记录并纳入下轮自动化改进。

**示例**:
```c
// cppcheck 可能未检出但需人工确认的模式：
void tick(void) {
    static uint32_t counter = 0;
    if (counter < 1000) counter++;
    /* cppcheck 不会抱怨，但有人可能忘记了溢出处理 */
}
```

---

### Dir 4.3 — 汇编代码约束

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-dir-4.3` |
| **标题** | 汇编代码约束 |
| **严重度** | Advisory |

**为什么 cppcheck 管不到**: 内联汇编中的指令、寄存器和参数是编译器相关的文本，cppcheck 不会解析汇编内容，也无法验证汇编是否符合 MISRA 约束。

**审查方法**: 找到所有 `__asm__` / `asm()` / `__ASM` 内联汇编，检查是否封装在专用的汇编函数/模块中，而非散布在普通 C 函数体中。审查 asm 代码中是否有破坏寄存器保存规则的指令。

**通过标准**: 汇编代码全部封装在带 `.s` 后缀的独立汇编文件中，或者封装在 `static inline` 函数内。C 和汇编的接口处有明确的调用约定注释。无 `asm volatile` 意外破坏 C 环境的状态。

**示例**:
```c
// ❌ 违规：汇编散布在 C 函数体中
void delay_us(uint32_t us) {
    __asm volatile("nop");  // 汇编散步在 C 中
    // ...
}

// ✅ 合规：封装在独立函数中
static inline void delay_one_cycle(void) {
    /* 汇编指令：单周期空转，不修改任何寄存器 */
    __asm volatile("nop" ::: "memory");
}
void delay_us(uint32_t us) {
    for (uint32_t i = 0; i < us; i++) {
        delay_one_cycle();
    }
}
```

---

### mcu-arm-1 — 中断优先级分组

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `mcu-arm-1` |
| **标题** | 中断优先级分组 |
| **严重度** | Required |

**为什么 cppcheck 管不到**: NVIC 优先级分组（PRIGROUP）的配置在系统启动代码或 CMSIS 头文件中，是一个软件配置值与硬件设计决策的匹配问题。cppcheck 不感知 ARM Cortex-M 的优先级模型。

**审查方法**: 检查 NVIC_SetPriorityGrouping() 的调用或 SCB->AIRCR 寄存器配置值。对照系统设计文档确认优先级分组策略（抢占优先级位数 vs 子优先级位数）与系统设计中断嵌套策略一致。

**通过标准**: 系统中只有一处优先级分组配置（通常 startup 或 system 初始化），且在系统设计文档中有记录。优先级分组策略与中断响应时间要求一致。

**示例**:
```c
// ❌ 违规：优先级分组不明确
void SystemInit(void) {
    /* 未显式设置优先级分组 */
}

// ✅ 合规：确定的分组策略
/* RM0433 Rev6, §4.3.5: 使用 4-bit 抢占优先级，0-bit 子优先级 */
#define NVIC_PRIORITYGROUP_4  ((uint32_t)0x300)  /* 4 bits preempt */
void SystemInit(void) {
    NVIC_SetPriorityGrouping(NVIC_PRIORITYGROUP_4);
}
```

---

### mcu-arm-2 — 中断嵌套保护

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `mcu-arm-2` |
| **标题** | 中断嵌套保护 |
| **严重度** | Required |

**为什么 cppcheck 管不到**: 中断嵌套保护需要在设计层面对 ISR 的优先级进行整体编排，cppcheck 无法理解"哪个中断能抢占哪个中断"这一系统级设计约束。

**审查方法**: 审查 NVIC_SetPriority() 对所有启用中断的优先级赋值，确保较高优先级的 ISR 确实需要更短的执行时间。检查是否有 ISR 访问被低优先级 ISR 共享的资源而缺少保护。

**通过标准**: 所有中断优先级在启动阶段统一分配，中断优先级与服务函数的关键程度/执行时间匹配。共享资源的 ISR 使用了临界区保护（如 `__disable_irq()` / `__enable_irq()`）。

**示例**:
```c
// ❌ 违规：ISR 访问共享数据无保护
volatile uint32_t shared_tick = 0;
void TIM_IRQHandler(void) { shared_tick++; }   // 可能被 SysTick 抢占
void SysTick_Handler(void)  { shared_tick++; }  // 无保护

// ✅ 合规：使用临界区保护共享数据
volatile uint32_t shared_tick = 0;
void TIM_IRQHandler(void) {
    __disable_irq();
    shared_tick++;
    __enable_irq();
}
void SysTick_Handler(void) {
    __disable_irq();
    shared_tick++;
    __enable_irq();
}
```

---

### mcu-riscv-1 — RISC-V 内存屏障

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `mcu-riscv-1` |
| **标题** | RISC-V 内存屏障 |
| **严重度** | Required |

**为什么 cppcheck 管不到**: 内存屏障（fence）指令的正确使用依赖于多核/多主设备之间共享内存的硬件内存序模型，cppcheck 不感知 RISC-V 的弱内存序。

**审查方法**: 审查多核共享内存（通常是 IPC 缓冲区、共享 SRAM）的访问路径，确认写完成后有 fence 指令、读之前有 fence 指令。检查是否使用 `__atomic` 内建函数自动插入屏障。

**通过标准**: 每个共享内存的写操作后有 `fence w,w`（或等效的 atomic store），读操作前有 `fence r,r`。或统一使用了 C11 atomic 操作。

**示例**:
```c
// ❌ 违规：共享数据无 fence
volatile uint32_t *shared_flag = (uint32_t *)0x80001000;
*shared_flag = 1;  // 无 fence，其他核心可能看不到这个写入

// ✅ 合规：写后插入 fence
volatile uint32_t *shared_flag = (uint32_t *)0x80001000;
__asm volatile("fence w,w" ::: "memory");
*shared_flag = 1;
```

---

### Rule 1.4 — 单元测试充分性审查

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-1.4` |
| **标题** | 单元测试充分性审查 |
| **严重度** | Required |

**为什么 cppcheck 管不到**: 这不是代码分析规则，而是过程审查规则——要求审阅单元测试本身是否充分覆盖了安全需求。cppcheck 是静态分析工具，不执行动态测试，也不评估测试覆盖率。

**审查方法**: 检查每个安全关键函数（spec 中标记为 Required 或 Mandatory 的规则覆盖的函数）是否有对应的单元测试。确认测试用例覆盖正常路径、边界条件和错误路径三个维度。

**通过标准**: 安全关键函数有正向/反向/边界三种测试用例。覆盖率报告显示行覆盖率 ≥ 该文件的门禁要求。无"通过测试但未真正验证"的空测试（如 `TEST_ASSERT_TRUE(1)`）。

**示例**:
```c
// 审查关注点：测试覆盖率不充分
// 被测函数
int32_t clamp(int32_t val, int32_t min, int32_t max) {
    if (val < min) return min;
    if (val > max) return max;
    return val;
}

// ❌ 不充分测试：只测试了正常路径
void test_clamp_normal(void) {
    TEST_ASSERT_EQUAL(5, clamp(5, 0, 10));
}

// ✅ 充分测试：覆盖正常/边界/错误路径
void test_clamp_normal(void)     { TEST_ASSERT_EQUAL( 5, clamp( 5,  0, 10)); }
void test_clamp_below_min(void)  { TEST_ASSERT_EQUAL( 0, clamp(-1,  0, 10)); }
void test_clamp_above_max(void)  { TEST_ASSERT_EQUAL(10, clamp(15,  0, 10)); }
void test_clamp_at_min(void)     { TEST_ASSERT_EQUAL( 0, clamp( 0,  0, 10)); }
void test_clamp_at_max(void)     { TEST_ASSERT_EQUAL(10, clamp(10,  0, 10)); }
```

---

## 3. 🟡 中等复杂度规则（22 条，2-5 分钟/条）

这些规则 cppcheck 可以捕获基本语法违规，但在复杂语义场景（跨文件、条件编译、间接调用）下需要人工确认。

### Rule 1.1 — ISO C 标准合规

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-1.1` |
| **标题** | ISO C standard compliance |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 可以检测部分编译器扩展（如 GCC `__attribute__`），但在实际的嵌入式项目中，许多编译器扩展被滥用而不被 cppcheck 报错（如 `__packed`、`__aligned`、`__interrupt` 等特定于编译器的关键字）。

**审查方法**: 搜索源代码中所有带双下划线或单下划线+大写字母开头的标识符，对照编译器手册判断是否为非标准扩展。重点检查 `__attribute__`、`__asm`、`__builtin_*`、`#pragma` 的使用。

**通过标准**: 所有编译器扩展都有明确的偏差申请（注明扩展名、用途、对应标准中的缺失部分），或已被白名单允许。

**示例**:
```c
// ❌ 违规：未备案的编译器扩展
struct __attribute__((packed)) SensorData {  // GNU 扩展，无偏差
    uint8_t id;
    uint16_t value;
};

// ✅ 合规：备案后使用（有偏差声明）
/* MISRA偏差 R1.1: GCC __attribute__((packed)) 用于硬件协议对齐 */
/* Dev-ID: DEV-MISRA-R1.1-001 */
struct __attribute__((packed)) SensorData {
    uint8_t id;
    uint16_t value;
};
```

---

### Rule 1.2 — 未定义/未指定行为

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-1.2` |
| **标题** | No reliance on undefined or unspecified behavior |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 可以捕获明显的 UB（如除零、空指针），但对隐式 UB 模式（符号整数溢出、有符号移位溢出、restrict 别名冲突）检测不完整，特别是在条件分支中。

**审查方法**: 仔细审查符号整数运算是否可能溢出，移位操作中右操作数是否 ≥ 左操作数的位宽，restrict 指针的使用是否存在别名冲突。特别关注宏展开后的复合表达式。

**通过标准**: 有符号运算的结果在被使用前已确认不会溢出（或已在编译期预算范围内）。移位操作有范围守卫。restrict 指针的所指对象不重叠。

**示例**:
```c
// ❌ 违规：有符号整数溢出（UB）
int32_t inc(int32_t val) {
    return val + 1;  // 当 val == INT32_MAX 时溢出
}

// ✅ 合规：溢出前守卫
int32_t inc(int32_t val) {
    if (val == INT32_MAX) return INT32_MAX;  /* saturate */
    return val + 1;
}
```

---

### Rule 2.2 — 死代码

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-2.2` |
| **标题** | Source code shall not contain dead code |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 可以检测明显的死代码（如 `return` 后语句），但对条件编译导致的死代码、宏展开产生的不可达分支调试代码检测不完全。

**审查方法**: 检查 `#if 0` 保留的旧代码、`ifdef DEBUG` 调试分支、`while(0)` 包裹的禁止代码。注意 MISRA C:2023 允许某些调试宏展开的死代码——确认这些死代码已有标记。

**通过标准**: 没有未标记的 `#if 0` 代码块。调试分支有 `/* DEBUG */` 注释标记。不可达条件（如永远为 false 的 if 条件）已删除或标记为保留死代码。

**示例**:
```c
// ❌ 违规：未标注的条件编译死代码
#if 0
  old_implementation();  // 死代码，无标记
#endif

// ✅ 合规：标记以便未来审计
#if 0  /* MISRA 2.2: 保留以供参考（旧算法 v1.0），计划 Q4 删除 */
  old_implementation();
#endif
```

---

### Rule 8.13 — const 限定（指针参数）

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-8.13` |
| **标题** | const-qualified pointer for read-only parameters |
| **严重度** | Advisory |

**为什么 cppcheck 管不到**: cppcheck 能检测"函数内未修改"但不检查"语义上本应不可修改"——这需要理解函数的设计意图。某些复杂的间接指针（如 `void *` 参数）cppcheck 无法判断是否可加 const。

**审查方法**: 审查函数声明中指针参数，判断其指向的数据在函数内是否只读。如果是，缺少 const 即为 advisory 违规。注意 RTOS 回调函数签名（如 `void *pvParameters`）应加例外。

**通过标准**: 所有不修改目标数据的指针参数都添加了 const。已知的 RTOS/第三方回调例外有偏差记录。

**示例**:
```c
// ❌ 违规：不修改数据但缺失 const
void print_hex(uint8_t *data, uint32_t len) {
    for (uint32_t i = 0; i < len; i++) {
        Log("%02X", data[i]);  // 只读
    }
}

// ✅ 合规：添加 const
void print_hex(const uint8_t *data, uint32_t len) {
    for (uint32_t i = 0; i < len; i++) {
        Log("%02X", data[i]);
    }
}
```

---

### Rule 17.7 — 返回值必须被使用

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-17.7` |
| **标题** | 返回值必须被使用 |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 使用 __attribute__((warn_unused_result)) 或 MISRA 规则捕获部分场景，但对 printf/scanf 等标准库函数、回调返回值、宏展开返回值未覆盖完全。复杂的条件编译也导致漏报。

**审查方法**: 搜索所有存在返回值的函数调用，检查返回值是否被检查或使用。特别注意标准库函数（如 snprintf 返回值指示实际写入大小）的返回值是否被用于后续逻辑判断。

**通过标准**: 每个具有返回值的函数调用结果要么被赋值给变量并使用，要么被显式转换为 void（`(void)func()`），要么在 MISRA 抑制列表中。

**示例**:
```c
// ❌ 违规：忽略 snprintf 返回值
void format_msg(char *buf, size_t sz, uint32_t val) {
    snprintf(buf, sz, "%u", val);  // 未检查写入长度
}

// ✅ 合规：检查返回值
void format_msg(char *buf, size_t sz, uint32_t val) {
    int ret = snprintf(buf, sz, "%u", val);
    if (ret < 0 || (size_t)ret >= sz) {
        buf[sz - 1] = '\0';  /* 截断处理 */
    }
}
```

---

### Rule 9.1 — 未初始化自动变量

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-9.1` |
| **标题** | The value of an object with automatic storage duration shall not be read before it is assigned |
| **严重度** | Mandatory |

**为什么 cppcheck 管不到**: cppcheck 可以检测简单未初始化变量（`int x; use(x)`），但对条件分支中的部分初始化、struct 成员的部分初始化、以及通过指针或 memcpy 间接初始化的场景覆盖率低。

**审查方法**: 检查所有自动变量的声明和初始化路径，确认每个读取前必有写入。特别注意结构体变量——声明后是否所有成员都已初始化。检查通过 memcpy/sprintf/sscanf 间接初始化的变量是否在所有路径上被填充。

**通过标准**: 每个自动变量在声明时/声明后立刻初始化。结构体使用 `= {0}` 或复合字面量初始化。无"条件赋值后使用"但条件不全覆盖的场景。

**示例**:
```c
// ❌ 违规：条件分支未全覆盖
int32_t get_temp(void) {
    int32_t temp;  // 未初始化
    if (sensor_ready()) {
        temp = read_sensor();
    }
    return temp;  // sensor_ready() == false 时返回垃圾值
}

// ✅ 合规：声明时初始化
int32_t get_temp(void) {
    int32_t temp = DEFAULT_TEMP;
    if (sensor_ready()) {
        temp = read_sensor();
    }
    return temp;
}
```

---

### Rule 13.2 — 副作用取决于求值顺序

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-13.2` |
| **标题** | Side effects of called functions shall not depend on evaluation order |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 能检测部分简单 UB 模式（如 `arr[i++] = i`），但对函数参数列表中的求值顺序依赖检测不完整，当函数和宏混合使用时更难检测。

**审查方法**: 检查同一表达式或函数参数列表中，是否有多个出现同一变量的自增/自减/赋值操作。特别关注宏展开后的多参数表达式。

**通过标准**: 同一表达式或函数参数列表中，每个变量最多出现一次赋值/自增/自减。更严格来说，使用临时变量分解复合表达式，让每个表达式只有一个副作用。

**示例**:
```c
// ❌ 违规：参数列表中同一变量出现两次
uint32_t result = process(val++, buffer[val]);  // 未定义顺序

// ✅ 合规：分离副作用
uint32_t idx = val;
val++;
uint32_t result = process(idx, buffer[idx]);
```

---

### Rule 14.3 — 控制表达式不可为不变条件

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-14.3` |
| **标题** | Controlling expressions shall not be invariant conditions |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 可以检测 `if (0)`、`while(1)` 等明显的常量条件，但对宏展开后变为常量的条件、枚举值比较导致的不变条件检测不完全。

**审查方法**: 检查 `#define ENABLED 1` 或 `#define FEATURE_FLAG 0` 后 `if (ENABLED)` 的使用。检查循环条件中是否有宏展开后为常量的表达式。

**通过标准**: 条件编译使用 `#if/#ifdef` 而非 `if (CONSTANT)`。循环使用明确的退出变量而非 `while(1)`。需用无限循环的场景有注释说明。

**示例**:
```c
// ❌ 违规：if (常量)
#define DEBUG_ENABLED 1
void log_msg(const char *msg) {
    if (DEBUG_ENABLED) {  // 永远为真
        printf("%s", msg);
    }
}

// ✅ 合规：使用条件编译
#define DEBUG_ENABLED 1
void log_msg(const char *msg) {
#if DEBUG_ENABLED
    printf("%s", msg);
#endif
}
```

---

### Rule 15.4 — 单一退出点

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-15.4` |
| **标题** | Single point of exit |
| **严重度** | Advisory |

**为什么 cppcheck 管不到**: cppcheck 可以统计函数中 return 的数量，但不能判断"是否应该合并为单一出口"——这需要审查员理解函数的错误处理模式是否适合集中清理。

**审查方法**: 审查多 return 的函数，判断是否可以合并为单一出口（特别是涉及资源分配、锁获取、文件打开需要清理的场景）。

**通过标准**: 非简单函数（有资源分配/锁/文件操作）有单一出口。简单访问器函数可有多个早期 return 但需注释。

**示例**:
```c
// ❌ 违规：资源分配后多处 return
status_t process_data(void) {
    uint8_t *buf = malloc(256);
    if (!buf) return ERR_NOMEM;
    if (check(buf) != OK) {
        free(buf);             // 需要记得释放
        return ERR_CHECK;
    }
    free(buf);
    return OK;
}

// ✅ 合规：单一出口
status_t process_data(void) {
    status_t ret = OK;
    uint8_t *buf = malloc(256);
    if (buf) {
        if (check(buf) != OK) {
            ret = ERR_CHECK;
        }
        free(buf);
    } else {
        ret = ERR_NOMEM;
    }
    return ret;  // 单一出口
}
```

---

### Rule 16.3-16.6 — switch 格式与贯穿

**为什么 cppcheck 管不到**: cppcheck 能检测缺失 `break` 和缺失 `default`。但对 C:2023 允许的"注释标注的贯穿"（intentional fall-through）无法区分是有意还是无意，需要人工确认贯穿注释的规范性。

**审查方法**: 检查每个 fall-through case 结尾是否有规范的贯穿注释（如 `/* fall through */`），且贯穿确实有意义（空 case 合并处理）。检查 default 分支是否包含合理的错误处理逻辑。

**通过标准**: 所有 non-empty 的 fall-through case 都有明确的贯穿注释。default 分支至少包含一个注释说明或错误处理。无嵌套的 switch-within-switch 混淆。

**示例**:
```c
// ❌ 违规：贯穿无注释
switch (cmd) {
    case CMD_IDLE: init();  // 贯穿到 RUN，无注释
    case CMD_RUN:  run(); break;
    default: break;
}

// ✅ 合规：明确标注的贯穿
switch (cmd) {
    case CMD_IDLE:
        init();
        /* fall through */
    case CMD_RUN:
        run();
        break;
    default:
        /* unexpected command — safe ignore */
        break;
}
```

---

### Rule 17.2/17.3 — 递归（直接/间接）

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-17.2` / `misra-c2023-17.3` |
| **标题** | Functions shall not call themselves directly/indirectly |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 可以检测直接递归（A→A），但对间接递归（A→B→C→A）的检测需要构建完整调用图，超过 cppcheck 的 TU 分析范围。

**审查方法**: 审查项目中的函数调用链，确认不存在 A→B→C→A 的间接递归模式。使用静态调用图工具（如 doxygen、calltree）辅助分析。

**通过标准**: 无直接或间接递归。C:2023 允许的 tail-recursion 特例有明确的安全分析报告。

**示例**:
```c
// ❌ 违规：间接递归
void a(void) { b(); }
void b(void) { c(); }
void c(void) { a(); }  // 间接递归：a→b→c→a

// ✅ 合规：改为迭代或消除循环
void a(void) { /* 迭代实现 */ }
void b(void) { /* 独立功能 */ }
void c(void) { /* 独立功能 */ }
```

---

### Rule 18.6 — 数组索引越界

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-18.6` |
| **标题** | Array indexing shall be within bounds |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 能做常量索引检查（`arr[100]` when size 50），但对动态索引（传入函数参数的数组、根据运行时条件计算的索引）的越界检测非常有限。

**审查方法**: 审查所有数组下标表达式，确认下标范围受到守卫条件约束，特别是循环内的索引、复合表达式索引、以及结构体数组成员的索引。

**通过标准**: 每个数组下标使用前有明确的 `if (idx < ARRAY_SIZE)` 或等效检查。函数参数中的数组有对应的长度参数。无"先使用后检查"模式。

**示例**:
```c
// ❌ 违规：无边界检查的数组索引
void set_item(uint32_t idx) {
    buffer[idx] = 0xFF;  // idx 可能 ≥ BUFFER_SIZE
}

// ✅ 合规：索引前守卫
void set_item(uint32_t idx) {
    if (idx >= BUFFER_SIZE) return;
    buffer[idx] = 0xFF;
}
```

---

### Rule 19.1/19.2 — 重叠存储

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-19.1` / `misra-c2023-19.2` |
| **标题** | Object shall not be assigned or copied overlapping / union confusion |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 无法检测运行时 memcpy(dst, src, n) 中 dst 和 src 是否重叠，也无法判断 union 的 type-punning 是否是故意为之的合法使用。

**审查方法**: 检查 memcpy/memmove 调用中 dst 和 src 指针是否可能指向同一对象的重叠区域。检查 union 的不同成员访问场景，判断 type-punning 是否有明确设计意图。

**通过标准**: 重叠拷贝使用 memmove 而非 memcpy。union 的 type-punning 有注释说明且使用偏差。结构体指针别名关系在函数入口有 restrict 声明。

**示例**:
```c
// ❌ 违规：memcpy 涉及重叠内存
uint8_t data[64];
memcpy(&data[4], &data[2], 32);  // 源和目标重叠

// ✅ 合规：使用 memmove
uint8_t data[64];
memmove(&data[4], &data[2], 32);  // memmove 允许重叠
```

---

### Rule 20.5 — #undef 使用

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-20.5` |
| **标题** | #undef should not be used |
| **严重度** | Advisory |

**审查方法**: 搜索所有 `#undef`，确认有注释说明原因。特别注意跨文件的 `#undef` 是否可能影响其他头文件行为。

**通过标准**: 每个 `#undef` 旁边的注释清晰说明为什么需要取消定义。无跨文件的隐式 `#undef` 依赖。

**示例**:
```c
// ❌ 违规：#undef 无注释
#undef DEBUG

// ✅ 合规：注释说明
/* 释放 DEBUG 宏，防止影响后续头文件 */
#undef DEBUG
```

---

### Rule 20.7 — 类函数宏

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-20.7` |
| **标题** | Function-like macro shall not be used |
| **严重度** | Required |

**为什么 cppcheck 管不到**: 类函数宏的展开是纯文本替换，cppcheck 无法评估宏展开后的副作用问题（如参数被多次求值）——特别是宏参数中带有自增/函数调用时。

**审查方法**: 搜索所有类函数宏（带参数的宏），检查宏定义体中的参数是否可能被多次求值（`#define SQUARE(x) ((x)*(x))` 中 x 被使用了两次）。检查宏展开是否可能导致优先级问题。

**通过标准**: 类函数宏的参数在宏体中只出现一次（避免多重求值），或宏的使用处已确保参数无副作用。宏替换整体有括号包裹。优先使用 static inline 函数替代。

**示例**:
```c
// ❌ 违规：宏参数被多次求值
#define MAX(a, b) ((a) > (b) ? (a) : (b))
uint32_t x = MAX(val++, limit);  // val 被自增两次

// ✅ 合规：使用 static inline
static inline uint32_t max_u32(uint32_t a, uint32_t b) {
    return (a > b) ? a : b;
}
uint32_t x = max_u32(val++, limit);  // 正确
```

---

### Rule 21.3 — 动态内存分配

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-21.3` |
| **标题** | Memory allocation functions should not be used |
| **严重度** | Advisory |

**为什么 cppcheck 管不到**: cppcheck 能检测 `malloc`/`free` 的语法存在，但不能判断动态分配的使用场景是否可被静态替代，或是否已通过偏差允许。

**审查方法**: 搜索所有 malloc/calloc/realloc/free 调用，确认嵌入式安全关键代码中没有动态内存分配。对必须动态分配的场景，确认有偏差申请且包含堆大小分析。

**通过标准**: 安全关键（Required/Mandatory）代码中无动态内存分配。非关键代码中的动态分配不超过堆预算且有 OOM 处理。

**示例**:
```c
// ❌ 违规：关键路径使用动态分配
void process_critical(void) {
    uint8_t *buf = malloc(256);  // 安全关键路径用 malloc
    // ...
    free(buf);
}

// ✅ 合规：使用静态缓冲区
#define BUF_SIZE 256
static uint8_t buf[BUF_SIZE];
void process_critical(void) {
    /* 静态分配，已在启动时分配 */
    memset(buf, 0, BUF_SIZE);
    // ...
}
```

---

### Rule 21.4 — 标准库输出函数

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-21.4` |
| **标题** | Standard library output functions should not be used |
| **严重度** | Advisory |

**为什么 cppcheck 管不到**: cppcheck 能检测 printf/puts 的存在，但不能判断在生产代码中的使用是否已通过偏差允许。

**审查方法**: 搜索 printf/sprintf/puts/fputs/fprintf 等输出函数，确认生产代码中不使用（调试日志除外有 `#ifdef DEBUG`）。

**通过标准**: 无裸 printf 调用。日志输出有封装层且通过条件编译控制。格式化字符串不来自外部输入。

**示例**:
```c
// ❌ 违规：生产代码使用 printf
void status_report(void) {
    printf("System OK\n");  // 不可接受
}

// ✅ 合规：通过封装的日志宏（条件编译）
#ifdef DEBUG_ENABLED
    #define LOG(fmt, ...) printf(fmt, ##__VA_ARGS__)
#else
    #define LOG(fmt, ...) ((void)0)
#endif
```

---

### Rule 21.5 — 输入函数

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-21.5` |
| **标题** | Standard library input functions should not be used |
| **严重度** | Advisory |

**审查方法**: 搜索 scanf/gets/fgets/sscanf 等输入函数，gets 是绝对禁止的。sscanf 有安全的替代方案或有长度限界。

**通过标准**: 无 gets 调用。其他输入函数有长度限定和返回值检查。输入数据被验证后才使用。

---

### Rule 22.1 — 资源释放

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-22.1` |
| **标题** | All resources obtained dynamically shall be explicitly released |
| **严重度** | Required |

**为什么 cppcheck 管不到**: cppcheck 的 malloc/free 配对检测只能处理简单场景（同一函数内分配和释放），对跨函数、错误路径的内存释放检测非常有限。

**审查方法**: 审查动态资源（内存、文件句柄、mutex、信号量）的 acquire/release 路径，确保每个 acquire 在正常情况下和所有错误路径上都有对应的 release。

**通过标准**: 每个 acquire 操作有对应的 release 在所有执行路径上。错误路径不泄漏资源。使用 RAII 模式或 goto cleanup 模式保证。

---

### mcu-esp32-1 — ISR 函数属性

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `mcu-esp32-1` |
| **标题** | ISR 函数属性 |
| **严重度** | Required |

**审查方法**: 检查所有 ESP32 ISR 函数是否标记了 `IRAM_ATTR` 属性，确认中断服务程序不在 flash 执行路径上。

**通过标准**: 每个由中断向量表直接调用的 ISR 带有 `IRAM_ATTR`。调用的辅助函数如果也在 ISR 上下文中，也应标记或在 IRAM 中。

---

### mcu-esp32-2 — FreeRTOS 任务栈大小 (auto_checkable=False by YAML, 部分可自动化)

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `mcu-esp32-2` |
| **标题** | FreeRTOS 任务栈大小检查 |
| **严重度** | Advisory |

**审查方法**: 审查 xTaskCreate 调用中的栈大小参数，参考 ESP-IDF 文档推荐的最小栈大小。检查任务函数中是否有大型局部数组（可能栈溢出）。

**通过标准**: 每个任务的栈大小不小于 ESP-IDF 推荐值且有 20% 余量。长期运行时栈高水位（uxTaskGetStackHighWaterMark）在预算内。

---

### Dir 4.4 — Unicode/字符编码约束

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-dir-4.4` |
| **标题** | Unicode/字符编码约束 |
| **严重度** | Advisory |

**审查方法**: 检查源文件的字符编码声明是否一致（如所有 .c/.h 文件编码为 UTF-8 without BOM）。检查字符串字面量中是否混用不同编码。

**通过标准**: 项目的 `.editorconfig` 或 `.clang-format` 统一声明编码。无非 ASCII 字符串字面量在源代码中。

---

### Dir 4.6 — size_t / ptrdiff_t 使用

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-dir-4.6` |
| **标题** | size_t / ptrdiff_t 使用 |
| **严重度** | Advisory |

**审查方法**: 检查数组下标是否使用 size_t 类型而非 int/uint32_t。检查指针差值是否使用 ptrdiff_t。

**通过标准**: 循环索引使用 size_t 遍历数组。指针减法结果赋给 ptrdiff_t 变量。

---

### Dir 4.10 — 诊断信息保留

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-dir-4.10` |
| **标题** | 诊断信息保留 |
| **严重度** | Advisory |

**审查方法**: 检查构建日志的保留策略，确认编译 warning 和 error 在 CI 日志中可检索。检查是否有 `-w` 抑制 warning 的编译选项。

**通过标准**: CI 系统保留完整构建日志。编译选项未使用 `-w` 抑制警告。所有 warning 作为 CI 的 advisory 记录。

---

### Rule 8.7 — 外部链接滥用

| 属性 | 值 |
|:-----|:-----|
| **规则 ID** | `misra-c2023-8.7` |
| **标题** | Functions and objects should not be defined with external linkage if only referenced in one TU |
| **严重度** | Required |

**审查方法**: 检查仅在一个 .c 文件内使用的函数/全局变量是否未加 static。重点审查新添加的函数。

**通过标准**: 单文件使用的所有函数和全局对象有 static 限制。头文件中的声明确保不会与文件内部 static 重名。

---

### Rule 22.5 — 文件资源的释放

**审查方法**: 审查所有文件打开操作（fopen/freopen）有关闭操作（fclose）。特别关注错误路径中的文件句柄泄漏。

**通过标准**: 文件打开的每一条执行路径都有对应的关闭操作。

---

### Rule 22.6 — 互斥锁/信号量资源

**审查方法**: 审查 RTOS mutex/semaphore 的 acquire/release 路径，确认在 ISR 中不使用阻塞的 acquire，确认所有路径都释放。

**通过标准**: acquire/release 成对出现，ISR 中使用 `...FromISR` 版本的释放函数。

---

## 4. 🟢 简单级规则（18 条，<2 分钟/条）

这些规则 check 简单直接，但 cppcheck 在特定场景下可能漏报。

### 规则清单

| # | Rule ID | 标题 | 审查要点 |
|:-:|:--------|:-----|:---------|
| 1 | `misra-c2023-3.1` | 注释嵌套 | 搜索 `/*` 嵌套，确认无嵌套注释 |
| 2 | `misra-c2023-3.2` | 预处理中的注释 | 检查 `#if` 块内是否有 `//` 注释被条件编译意外截断 |
| 3 | `misra-c2023-5.1-5.5` | 标识符命名区分 | 检查长的标识符前 31 字符是否重复 |
| 4 | `misra-c2023-5.7` | 标识符重复声明 | 检查不同作用域内同名标识符是否引发混淆 |
| 5 | `misra-c2023-5.8` | 标识符可见性 | 确认 `file.h` 和 `file.c` 中的标识符声明一致 |
| 6 | `misra-c2023-5.10` | 标识符名称空间 | 检查结构体/联合/枚举标签与普通标识符是否重名 |
| 7 | `misra-c2023-8.1` | 显式声明类型 | 确认无隐式 int 声明（`static count;` 应为 `static int count;`） |
| 8 | `misra-c2023-8.8` | static 外部定义 | 检查 const 变量是否添加了 static |
| 9 | `misra-c2023-8.9` | 符号可见性匹配 | 确认 .h 中的 extern 声明和 .c 中的定义匹配 |
| 10 | `misra-c2023-8.11` | 枚举类型定义 | 检查枚举的底层类型是否显式指定 |
| 11 | `misra-c2023-9.3` | 复合字面量初始化 | 检查复合字面量是否被用于非常量初始化 |
| 12 | `misra-c2023-9.5` | 自定义存储期初始化 | 确认 static/thread_local 变量的初始化器是常量表达式 |
| 13 | `misra-c2023-15.1/15.2` | goto 使用 | 无 goto 或在偏差范围内 |
| 14 | `misra-c2023-15.3` | 标签标记使用 | 确认标签不存在于 switch 语句之外 |
| 15 | `misra-c2023-20.10` | # 和 ## 运算符 | 检查 # 和 ## 的使用，确认不在偏差之外 |
| 16 | `misra-c2023-20.12` | #line 指令 | 检查是否存在 #line（几乎不应使用） |
| 17 | `misra-c2023-20.13` | #error 指令 | 检查是否使用了 #error 进行编译期断言 |
| 18 | `misra-c2023-20.14` | #pragma 指令 | 检查每个 #pragma 是否有偏差说明 |

### 通用审查方法（简单规则）

这些规则的审查关键是一个**模式搜索 + 人工确认**的组合：

```bash
# 一键搜索所有简单规则的常见违规模式
grep -rn "goto" src/ --include="*.c" --include="*.h"
grep -rn "#pragma" src/ --include="*.c" --include="*.h"
grep -rn "##" src/ --include="*.c" --include="*.h"
grep -rn "//\*\|/\*.*/\*" src/ --include="*.c" --include="*.h"
grep -rn "^static;$" src/ --include="*.c" --include="*.h"
```

---

## 5. 可自动化候选规则（暂列）

以下规则在当前 YAML 中标记为 `auto_checkable=True`，但在实际审查中我们发现 cppcheck 的覆盖率不完整。这些规则可作为 LLM Agent 审查或未来 cppcheck 规则扩展的候选。

### 可自动化性评估矩阵

| # | Rule ID | 标题 | cppcheck 覆盖度 | 可否 Agent 自动化 | 优先级 |
|:-:|:--------|:-----|:--------------:|:-----------------:|:------:|
| 1 | 1.2 | 未定义/未指定行为 | ~60% | 🟡 中（需值流分析）| P1 |
| 2 | 2.2 | 死代码 | ~70% | 🟢 高（模式匹配）| P2 |
| 3 | 8.13 | const 参数 | ~50% | 🟡 中（需语义理解）| P1 |
| 4 | 9.1 | 未初始化变量 | ~60% | 🟢 高（路径分析）| P1 |
| 5 | 13.2 | 副作用依赖 | ~40% | 🟡 中 | P2 |
| 6 | 17.7 | 返回值检查 | ~50% | 🟢 高 | P1 |
| 7 | 18.6 | 数组索引越界 | ~30% | 🔴 低（需动态值）| P3 |
| 8 | 20.7 | 类函数宏 | ~60% | 🟢 高（展开分析）| P2 |
| 9 | 21.3 | malloc/free | ~70% | 🟢 高 | P1 |
| 10 | 22.1 | 资源释放配对 | ~40% | 🟡 中 | P2 |

> **说明**: 这些规则"暂列"的意思是：当前仍需要人工审查，但未来改动（如升级 cppcheck、增加 Agent 审查 prompt）后可能转为自动。

---

## 6. 附录：审查流程与工具链

### 6.1 审查工作流

```
[接收 MR/PR] → [运行 cppcheck 全量扫描] → [已通过?]
    ↓ Yes                                    ↓ No
[人工审查 50 条规则]                     [退回修改]
    ↓
[标记通过/不通过] → [不通过?] → [修复/偏差] → [重新审查]
    ↓ Yes (通过)
[审查日志持久化]
```

### 6.2 辅助审查命令

```bash
# 搜索编译器扩展
grep -rn "__attribute__\|__asm\|__builtin\|#pragma" src/ --include="*.c" --include="*.h"

# 搜索动态内存
grep -rn "malloc\|calloc\|realloc\|free" src/ --include="*.c"

# 搜索标准库输出函数
grep -rn "printf\|sprintf\|puts\|fprintf" src/ --include="*.c" --include="*.h"

# 搜索 goto
grep -rn "goto" src/ --include="*.c"

# 搜索类函数宏
grep -rn "^#define [A-Z_][A-Z_0-9]*(" src/ --include="*.h" --include="*.c"

# 搜索 #undef
grep -rn "#undef" src/ --include="*.c" --include="*.h"
```

### 6.3 审查模板

```markdown
## MISRA 人工审查记录

| 审查文件 | 审查员 | 日期 | 耗时 |
|:---------|:-------|:-----|:----|
| src/module/xxx.c | [姓名] | YYYY-MM-DD | XX分钟 |

### 审查结果

| Rule ID | 状态 | 备注 |
|:--------|:----|:-----|
| Dir 4.1 | ✅ 通过 | 所有数组访问有边界守卫 |
| Rule 1.2 | ❌ 不通过 | L42：val++ 在宏参数中出现两次 |
| Rule 1.1 | 📋 偏差 | __packed 用于 SPI 协议对齐，已申请 DEV-MISRA-001 |

### 总评

- ✅ 通过: XX 条
- ❌ 不通过: XX 条（需修改）
- 📋 偏差: XX 条
```

---

*本文档由 yuleOSH MISRA 人工审查指引生成器创建。每次更新请同步评估 cppcheck 新版本的规则覆盖度，将可自动化规则移至自动化管线。*

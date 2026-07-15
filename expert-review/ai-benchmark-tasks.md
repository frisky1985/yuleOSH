# 🐴 AI Benchmark 任务集定义 — yuleOSH Agent 评测

> **编制**: 小马 🐴（质量架构师） | **日期**: 2026-07-05
> **用途**: AI Agent 能力基准评测（Benchmark），公开 Agent 成功率数据
> **参考**: AI 工具专家评审 §5 建议 4
> **总任务数**: 30 个 | **分布**: 简单 10 / 中等 12 / 困难 8

---

## 任务分类概览

| 难度 | 数量 | 占比 | 典型场景 |
|:----:|:----:|:----:|:---------|
| 🟢 简单 | 10 | 33.3% | GPIO/Timer/UART 基础操作 |
| 🟡 中等 | 12 | 40.0% | 状态机/CAN 驱动/数据解析 |
| 🔴 困难 | 8 | 26.7% | 多线程安全/MISRA 违规修复/移植适配 |

### 评测指标

每个任务运行 5 次，统计以下指标：
- **成功率**: 5 次中 pipeline 端到端通过的比例
- **平均耗时**: 从需求输入到 agent 完成的总时间（秒）
- **代码接受率**: 生成的代码经过审查后，接受通过的比例
- **审查通过率**: 代码审查环节一次通过的比例（无驳回 revision）

---

## 🟢 简单任务（10 个）

### T-001: GPIO 输出控制

| 属性 | 值 |
|:-----|:----|
| **名称** | GPIO 输出 — LED 闪烁控制 |
| **分类** | GPIO 基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：实现一个 GPIO 输出功能，控制 STM32F4 板载 LED（PC13），以 1Hz 频率闪烁。使用 HAL 库函数。 |
| **预期输出** | C 源文件，包含 `main()` 和 `HAL_GPIO_TogglePin()` 调用，500ms 延时循环。使用 `HAL_Delay()` 实现定时。 |
| **验收标准** | 1. 代码编译通过（arm-none-eabi-gcc）<br>2. 正确使用 HAL_GPIO_WritePin 或 HAL_GPIO_TogglePin<br>3. 延时准确（500ms ± 50ms）<br>4. 包含主循环结构 |
| **MISRA 检查** | 不强制，但违反 >= 3 条 Required 规则视为失败 |

### T-002: GPIO 输入读取

| 属性 | 值 |
|:-----|:----|
| **名称** | GPIO 输入 — 按键检测 |
| **分类** | GPIO 基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：实现按键 PA0 的输入读取。按键按下（低电平）时点亮板载 LED（PC13），松开时熄灭。需要消抖处理。 |
| **预期输出** | C 源文件，带软件消抖（延时 50ms 后再次读取），HAL_GPIO_ReadPin 读取 PA0，HAL_GPIO_WritePin 控制 PC13。 |
| **验收标准** | 1. 编译通过<br>2. 有软件消抖逻辑（延时 >= 20ms）<br>3. 正确使用 GPIO 输入模式配置<br>4. PA0 配置为输入，PC13 配置为输出 |
| **MISRA 检查** | 不强制 |

### T-003: 定时器延时（阻塞式）

| 属性 | 值 |
|:-----|:----|
| **名称** | 基本定时器 — 阻塞式延时 |
| **分类** | Timer 基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：使用 STM32F4 基本定时器 TIM6 实现 1ms 精度的阻塞式延时函数 `delay_ms(uint32_t ms)`。 |
| **预期输出** | C 函数 `void delay_ms(uint32_t ms)`，配置 TIM6 为 1ms 周期，查询标志位实现阻塞，函数退出前关闭定时器。 |
| **验收标准** | 1. 编译通过<br>2. TIM6 配置正确（PSC=84-1, ARR=1000-1 for 84MHz）<br>3. 使用 TIM 查询标志位而非中断<br>4. 函数可被多次调用 |
| **MISRA 检查** | 不强制 |

### T-004: UART 轮询发送

| 属性 | 值 |
|:-----|:----|
| **名称** | UART 轮询模式 — 发送字符串 |
| **分类** | UART 基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：配置 USART2（PA2=TX, PA3=RX）为 115200 8N1，实现轮询模式发送字符串 "Hello yuleOSH!\r\n"。 |
| **预期输出** | C 源文件，包含 USART2 GPIO 配置、USART2 初始化、字符串发送循环（逐个字符或 HAL_UART_Transmit）。 |
| **验收标准** | 1. 编译通过<br>2. 波特率 115200 配置正确<br>3. PA2/PA3 复用功能配置正确<br>4. 发送正确的字符串 |
| **MISRA 检查** | 不强制 |

### T-005: UART 轮询接收

| 属性 | 值 |
|:-----|:----|
| **名称** | UART 轮询模式 — 接收一个字节 |
| **分类** | UART 基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：在 USART2 上实现轮询接收一个字节。收到字节后将其加 1 并回发（echo + 1）。超时 1000ms。 |
| **预期输出** | C 函数，调用 `HAL_UART_Receive()` 接收一个字节，返回值加 1 后调用 `HAL_UART_Transmit()` 发送。含超时判断。 |
| **验收标准** | 1. 编译通过<br>2. 正确使用 UART 接收超时参数<br>3. 回发逻辑正确（rx_byte + 1）<br>4. 超时后不阻塞 |
| **MISRA 检查** | 不强制 |

### T-006: ADC 单次采样

| 属性 | 值 |
|:-----|:----|
| **名称** | ADC 单次转换 — 读取模拟电压 |
| **分类** | ADC 基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：配置 ADC1 通道 0（PA0）做单次转换，读取模拟电压值。转换结果通过 USART2 以 `"ADC: %d\r\n"` 格式发送。 |
| **预期输出** | C 源文件，ADC1 初始化（单次模式、通道 0、12 位分辨率），循环启动转换→等待完成→读取结果→串口发送。 |
| **验收标准** | 1. 编译通过<br>2. ADC 通道配置正确<br>3. 转换完成后正确读取结果寄存器<br>4. 结果通过 UART 发送 |
| **MISRA 检查** | 不强制 |

### T-007: PWM 输出（基本定时器）

| 属性 | 值 |
|:-----|:----|
| **名称** | PWM 输出 — LED 亮度控制 |
| **分类** | Timer/PWM 基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：使用 TIM3 通道 1（PA6）输出 1kHz PWM，占空比 50%。驱动 LED 显示。 |
| **预期输出** | C 源文件，TIM3 PWM 模式配置（PSC=84-1, ARR=1000-1），通道 1 配置为 PWM1，初始占空比 50%。 |
| **验收标准** | 1. 编译通过<br>2. 频率 1kHz ± 10%（ARR×PSC 计算正确）<br>3. PA6 复用功能配置为 TIM3_CH1<br>4. 占空比初始配置为 500（50% of ARR=1000） |
| **MISRA 检查** | 不强制 |

### T-008: I2C 读取传感器 ID

| 属性 | 值 |
|:-----|:----|
| **名称** | I2C — 读取传感器 ID 寄存器 |
| **分类** | I2C 基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：使用 I2C1（PB6=SCL, PB7=SDA）读取 MPU6050 加速度计 WHO_AM_I 寄存器（0x75），验证返回值是否为 0x68。 |
| **预期输出** | C 源文件，I2C1 初始化（400kHz），MPU6050 地址 0x68（7-bit），发送寄存器地址 0x75，接收 1 字节，比较 0x68。 |
| **验收标准** | 1. 编译通过<br>2. I2C 时序配置合理（400kHz）<br>3. 正确使用 I2C 主设备发送+接收<br>4. 有 WHO_AM_I 返回值检查逻辑 |
| **MISRA 检查** | 不强制 |

### T-009: SPI 读/写寄存器

| 属性 | 值 |
|:-----|:----|
| **名称** | SPI — 读写传感器寄存器 |
| **分类** | SPI 基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：使用 SPI1（PA5=SCK, PA6=MISO, PA7=MOSI, PA4=NSS）读取 LIS3DSH 加速度计的 WHO_AM_I 寄存器（0x0F）。 |
| **预期输出** | C 源文件，SPI1 全双工主机模式（8 位、CPOL=0/CPHA=0），PA4 GPIO 片选控制，发送读命令（0x8F），接收 1 字节。 |
| **验收标准** | 1. 编译通过<br>2. SPI 模式配置合理<br>3. NSS 软件控制（GPIO toggle）<br>4. 读命令格式正确（地址 | 0x80） |
| **MISRA 检查** | 不强制 |

### T-010: 看门狗初始化

| 属性 | 值 |
|:-----|:----|
| **名称** | IWDG 独立看门狗配置 |
| **分类** | 看门狗基础操作 |
| **难度** | 🟢 简单 |
| **输入描述** | 需求：配置 STM32F4 独立看门狗（IWDG），超时时间 4 秒。主循环中每 500ms 喂狗一次，并翻转 LED。 |
| **预期输出** | C 源文件，IWDG 配置（LSI 约 32kHz, PR=6（256 分频）, RLR=0xFFF），超时约 4 秒。循环内 HAL_GPIO_Toggle + HAL_IWDG_Refresh。 |
| **验收标准** | 1. 编译通过<br>2. IWDG 超时计算正确<br>3. 有喂狗操作<br>4. 主循环中喂狗间隔小于超时时间 |
| **MISRA 检查** | 不强制 |

---

## 🟡 中等任务（12 个）

### T-011: 简单状态机 — 交通灯控制

| 属性 | 值 |
|:-----|:----|
| **名称** | 状态机 — 交通灯控制器 |
| **分类** | 状态机设计 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：实现三态交通灯状态机。状态：RED(3s)→GREEN(3s)→YELLOW(1s)→RED。使用枚举类型定义状态。通过三个 GPIO 输出控制红/黄/绿 LED。 |
| **预期输出** | C 源文件，包含状态枚举 `typedef enum {STATE_RED, STATE_GREEN, STATE_YELLOW}`，switch-case 状态机，使用 `HAL_Delay()` 或定时器做状态计时。 |
| **验收标准** | 1. 编译通过<br>2. 状态转换时序符合要求（3s/3s/1s）<br>3. 使用 switch-case 而非 if-else 链<br>4. 枚举类型定义清晰<br>5. 无死锁或状态遗漏 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 16.3（switch 必须有 default） |

### T-012: CAN 报文发送

| 属性 | 值 |
|:-----|:----|
| **名称** | CAN — 标准帧发送 |
| **分类** | CAN 驱动 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：配置 CAN1（PB8=RX, PB9=TX）为 500kbps，发送标准帧（11-bit ID=0x321），数据长度 8 字节，数据为 0x01-0x08 递增序列。 |
| **预期输出** | C 源文件，CAN 过滤器配置（屏蔽位模式，接收所有帧），HAL_CAN_AddTxMessage 发送标准帧。波特率 500kbps（BS1=2tq, BS2=3tq, Prescaler=6 for 42MHz APB1）。 |
| **验收标准** | 1. 编译通过<br>2. CAN 时序配置正确（500kbps ± 2%）<br>3. 标准帧 ID=0x321<br>4. DLC=8，数据正确<br>5. 发送前检查邮箱是否可用 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 10.1（不允许隐式整型转换） |

### T-013: CAN 报文接收与解析

| 属性 | 值 |
|:-----|:----|
| **名称** | CAN — 中断模式接收与数据解析 |
| **分类** | CAN 驱动 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：配置 CAN1 接收中断，接收 ID=0x100 的标准帧，数据长度为 2 字节（车速信号）。byte[0]=速度整数部分，byte[1]=速度小数部分。收到后通过 UART 发送 `"SPEED: %d.%d km/h\r\n"`。 |
| **预期输出** | C 源文件，HAL_CAN_ActivateNotification 开启 RX 中断，回调函数 HAL_CAN_RxFifo0MsgPendingCallback 中解析 CAN 帧。 |
| **验收标准** | 1. 编译通过<br>2. 过滤器设置只通过 ID=0x100<br>3. 中断回调中正确解析数据<br>4. 串口输出格式正确<br>5. 中断服务函数非阻塞 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 8.13（指针参数应加 const） |

### T-014: I2C 温湿度传感器驱动

| 属性 | 值 |
|:-----|:----|
| **名称** | I2C 传感器驱动 — 温湿度读取 |
| **分类** | 传感器驱动 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：为 SHT30 温湿度传感器编写 I2C 驱动。通过 I2C1（400kHz）读取温湿度。SHT30 地址 0x44（7-bit）。发送测量命令 0x2C06，等待 15ms 后读取 6 字节数据。 |
| **预期输出** | C 源文件（`sht30.h` + `sht30.c`），包含：`SHT30_Init()`、`SHT30_ReadTH(float *temp, float *hum)`。CRC 校验可选但加分。 |
| **验收标准** | 1. 编译通过<br>2. 头文件和源文件分离<br>3. 正确计算温湿度（温度 = -45 + 175 * raw/65535, 湿度 = 100 * raw/65535）<br>4. 有错误返回码 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 10.3（赋值不允许隐含窄化转换） |

### T-015: 环形缓冲区实现

| 属性 | 值 |
|:-----|:----|
| **名称** | 数据结构 — 环形缓冲区（lock-free） |
| **分类** | 数据结构/算法 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：实现一个线程安全的环形缓冲区（ring buffer），支持单生产者/单消费者（SPSC）。提供 `rb_init`、`rb_put`、`rb_get`、`rb_is_empty`、`rb_is_full` 接口。缓冲区大小为 256 字节。 |
| **预期输出** | C 源文件（`ringbuf.h` + `ringbuf.c`），struct RingBuf 含 `volatile` head/tail 指针。使用内存屏障或临界区来保证 SPSC 安全。 |
| **验收标准** | 1. 编译通过<br>2. 正确的头尾指针管理<br>3. 支持满/空判断<br>4. SPSC 安全（不使用锁，仅用 volatile + barrier）<br>5. 不溢出、不丢失数据 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 13.2（表达式不得有副作用） |

### T-016: JSON 数据解析（基于 cJSON）

| 属性 | 值 |
|:-----|:----|
| **名称** | 数据解析 — JSON 传感器数据解析 |
| **分类** | 数据处理 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：解析 JSON 传感器数据字符串 `{"sensor":"bme280","temperature":25.3,"humidity":60.1,"pressure":101325}`，提取 temperature、humidity、pressure 值，通过 UART 输出 `"T=25.3 H=60.1 P=101325"`。 |
| **预期输出** | C 函数 `void parse_sensor_json(const char *json_str)`，使用 cJSON 库解析。含错误处理。 |
| **验收标准** | 1. 编译通过<br>2. 正确解析所有三个字段<br>3. 解析结果通过串口格式化输出<br>4. 对非法 JSON 输入有错误处理 |
| **MISRA 检查** | 不强制（cJSON 自身非 MISRA 合规） |

### T-017: FreeRTOS 任务创建

| 属性 | 值 |
|:-----|:----|
| **名称** | FreeRTOS — 多任务创建与调度 |
| **分类** | RTOS 基础 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：创建两个 FreeRTOS 任务。Task1 每 500ms 翻转 LED（PC13），Task2 每 1000ms 通过 UART 发送 `"Task2 alive\r\n"`。使用 vTaskDelay 实现定时。 |
| **预期输出** | C 源文件，两个任务函数 + `main()` 创建任务 + `vTaskStartScheduler()`。堆栈大小各 128 words。 |
| **验收标准** | 1. 编译通过<br>2. 两个任务独立运行<br>3. 定时准确（vTaskDelay 参数正确）<br>4. 使用 xTaskCreate 或 xTaskCreateStatic |
| **MISRA 检查** | 不强制 |

### T-018: 队列通信（FreeRTOS）

| 属性 | 值 |
|:-----|:----|
| **名称** | FreeRTOS — 队列数据通信 |
| **分类** | RTOS 通信 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：生产者任务（每 100ms 发送递增计数值）和消费者任务（接收值并串口输出 `"COUNT: %d\n"`）之间通过 FreeRTOS 队列通信。队列深度 10。 |
| **预期输出** | C 源文件，xQueueHandle，生产者 vTaskDelay(100) 后 xQueueSend，消费者 xQueueReceive（portMAX_DELAY 阻塞）。 |
| **验收标准** | 1. 编译通过<br>2. 队列创建正确<br>3. 生产/消费速率匹配<br>4. 数据不失序 |
| **MISRA 检查** | 不强制 |

### T-019: HAL Mock 测试框架接口

| 属性 | 值 |
|:-----|:----|
| **名称** | HAL Mock — 硬件抽象层 Mock 接口实现 |
| **分类** | 测试框架 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：参考 yuleOSH SWR-008.2，实现一个 HAL Mock 框架。包含 `MockHAL_GPIO_Init()`、`MockHAL_GPIO_WritePin()`、`MockHAL_GPIO_ReadPin()`。支持 call-history 记录。 |
| **预期输出** | C 头文件/源文件，含 mock 实现 + call history 数组 + 断言函数（`ASSERT_GPIO_WRITE(pin, state)`）。 |
| **验收标准** | 1. 编译通过<br>2. 每次调用记录到 call history<br>3. 提供断言接口可查询调用<br>4. 模拟接口签名与真实 API 一致 |
| **MISRA 检查** | 不强制 |

### T-020: MISRA 违规修复（单文件）

| 属性 | 值 |
|:-----|:----|
| **名称** | MISRA 修复 — 单文件违规修正 |
| **分类** | MISRA 合规 |
| **难度** | 🟡 中等 |
| **输入描述** | 输入 C 代码（~50 行）包含以下 MISRA C:2012 违规：Rule 10.1（隐式整型转换）、Rule 8.13（未加 const）、Rule 16.3（缺 default）、Rule 11.3（指针类型强制转换）。修复所有违规。 |
| **预期输出** | 修复后的 C 代码。使用 MISRA 标准方式修复：显式类型转换、加 const、补充 default、避免指针转换。 |
| **验收标准** | 1. 编译通过（编译器 + cppcheck）<br>2. cppcheck --addon=misra 报 0 条违规<br>3. 不影响原始逻辑<br>4. 每处修复加注释说明违反的规则号 |
| **MISRA 检查** | ✅ 此为 MISRA 修复任务，修复后 0 违规 |

### T-021: 位域与端序处理

| 属性 | 值 |
|:-----|:----|
| **名称** | 位域 — CAN ID 解析与端序处理 |
| **分类** | 低阶数据处理 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：解析 CAN 扩展帧（29-bit ID）的标准/扩展标识位 + ID 部分。从 4 字节 ID 字段解包为标准 ID（11-bit）+ 扩展 ID（18-bit）。需考虑大端序输入。 |
| **预期输出** | C 函数 `void parse_can_ext_id(uint8_t id_bytes[4], uint16_t *std_id, uint32_t *ext_id)`，使用位运算正确解码。 |
| **验收标准** | 1. 编译通过<br>2. 正确解码标准 11-bit ID<br>3. 正确解码扩展 18-bit ID<br>4. 正确处理端序 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 10.3、Rule 12.1 |

### T-022: 数据 CRC 校验实现

| 属性 | 值 |
|:-----|:----|
| **名称** | 数据校验 — CRC-8 实现 |
| **分类** | 数据处理 |
| **难度** | 🟡 中等 |
| **输入描述** | 需求：实现 CRC-8-ATM（多项式 0x07）查表算法。函数原型：`uint8_t crc8(const uint8_t *data, uint32_t len)`。生成 256 元素查找表。测试数据 `{0x01,0x02,0x03,0x04}` 的 CRC 应为 0xF4。 |
| **预期输出** | C 源文件（`crc8.h` + `crc8.c`），包含查找表生成（预计算或运行时）和计算函数。 |
| **验收标准** | 1. 编译通过<br>2. 查找表正确（256 元素）<br>3. 测试向量的 CRC 结果正确（0xF4）<br>4. 使用 const 查找表 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 13.2（表达式不得有副作用） |

---

## 🔴 困难任务（8 个）

### T-023: 多线程安全 — 共享资源保护

| 属性 | 值 |
|:-----|:----|
| **名称** | 多线程 — 共享资源的互斥访问 |
| **分类** | 多线程安全 |
| **难度** | 🔴 困难 |
| **输入描述** | 需求：三个 FreeRTOS 任务共享一个系统状态结构体（含 5 个字段：uint32_t 计数值、uint8_t 状态标志、float 采样值、timeout_ms、错误码）。需设计线程安全的读写接口。写者任务独占访问，读者任务允许并发读。使用 FreeRTOS 互斥量 + 读者锁模式实现。 |
| **预期输出** | C 源文件（`shared_state.h` + `shared_state.c`），含 `StateReadLock()`/`StateReadUnlock()`/`StateWriteLock()`/`StateWriteUnlock()` 封装。使用 FreeRTOS 二进制信号量实现写者优先或公平策略。 |
| **验收标准** | 1. 编译通过<br>2. 读者间可并发访问<br>3. 写者排他访问<br>4. 无死锁（通过静态分析或运行时验证）<br>5. 代码注释说明同步策略 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 12.2（右值不得递增加/减操作） |

### T-024: UART DMA 驱动（中断+环形缓冲）

| 属性 | 值 |
|:-----|:----|
| **名称** | UART DMA — 中断驱动接收 + 环形缓冲区 |
| **分类** | 外设驱动 |
| **难度** | 🔴 困难 |
| **输入描述** | 需求：实现 USART2 DMA 接收驱动。DMA 循环模式将接收数据写入环形缓冲区。IDLE 线中断标记帧结束。应用层通过 `uart_read_bytes(uint8_t *buf, uint32_t len, uint32_t timeout)` 读取数据。DMA 缓冲区大小 512 字节，应用环形缓冲区 1024 字节。 |
| **预期输出** | C 源文件（`uart_dma.h` + `uart_dma.c`），含 DMA 初始化、IDLE 中断处理、环形缓冲区管理、应用层读取接口。支持超时返回。 |
| **验收标准** | 1. 编译通过<br>2. DMA 循环模式配置正确<br>3. IDLE 中断标注帧结束<br>4. 环形缓冲区不溢出<br>5. 应用层读取接口支持超时<br>6. 中断优先级配置合理 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 20.9（不得使用 \#undef） |

### T-025: MISRA 大规模违规修复（多文件）

| 属性 | 值 |
|:-----|:----|
| **名称** | MISRA 修复 — 多文件大规模违规修正 |
| **分类** | MISRA 合规 |
| **难度** | 🔴 困难 |
| **输入描述** | 输入 5 个 C 源文件（总计 ~300 行），包含 25+ 条 MISRA C:2012 违规。涵盖：Rule 5.1（名称冲突）、Rule 8.7（外部链接无外部声明）、Rule 10.1/10.3/10.4（类型转换）、Rule 11.3/11.4（指针转换）、Rule 12.1（括号缺失）、Rule 13.2（副作用）、Rule 15.1（非结构化）、Rule 16.3（缺 default）、Rule 17.2（递归）、Rule 18.4（指针运算）等。修复所有违规并保留语义。 |
| **预期输出** | 修复后的 5 个源文件。每处修复加注释标注违反的规则号和修复方式。头文件同步修正。 |
| **验收标准** | 1. 各文件独立编译通过<br>2. 修复后 cppcheck --addon=misra 报 0 违规<br>3. 功能逻辑与原始代码一致<br>4. 注释标注规则号<br>5. 修复后无新增编译警告 |
| **MISRA 检查** | ✅ 此为 MISRA 修复任务，修复后 0 违规 |

### T-026: FreeRTOS 移植适配（新 MCU）

| 属性 | 值 |
|:-----|:----|
| **名称** | RTOS 移植 — FreeRTOS 到新 ARM Cortex-M MCU |
| **分类** | 移植适配 |
| **难度** | 🔴 困难 |
| **输入描述** | 需求：将 FreeRTOS v10.5.1 移植到 RISC-V MCU（GD32VF103）。需适配：portable 层（上下文切换、PendSV 等效异常、SysTick、临界区）、内存堆管理（heap_4.c）、中断管理。提供 `portmacro.h` 定义数据类型和函数原语。 |
| **预期输出** | C/汇编源文件（`portmacro.h`、`port.c`、`portasm.S`），含：上下文切换汇编实现、系统节拍中断处理、临界区（保存/恢复 mstatus）。 |
| **验收标准** | 1. 编译通过（riscv32-unknown-elf-gcc）<br>2. 上下文切换汇编正确保存/恢复寄存器<br>3. SysTick 中断周期配置正确（1ms）<br>4. 临界区实现正确（保存/恢复 mstatus.MIE）<br>5. 堆管理器 heap_4 配置正确 |
| **MISRA 检查** | 汇编文件豁免，C 文件要求 MISRA 合规 |

### T-027: 有限状态机生成器

| 属性 | 值 |
|:-----|:----|
| **名称** | 代码生成 — 有限状态机代码生成器 |
| **分类** | 工具开发 |
| **难度** | 🔴 困难 |
| **输入描述** | 需求：编写一个 Python 脚本，接收 YAML 格式的状态机描述（状态、事件、转换、动作），生成对应的 C 代码（头文件+源文件）。YAML 输入包含：states（状态列表）、events（事件列表）、transitions（状态转换表）、actions（动作函数声明）。 |
| **预期输出** | Python 脚本 `fsm_gen.py` + 生成的 C 文件。YAML 示例输入：3 个状态（IDLE/ACTIVE/ERROR）、4 个事件（START/STOP/FAULT/RESET）、6 条转换。生成的 C 代码包含：状态枚举、事件枚举、状态转换表（二维数组或 switch）、动作函数桩。 |
| **验收标准** | 1. Python 脚本运行无语法错误<br>2. 生成的 C 代码编译通过<br>3. 状态转换逻辑在生成的代码中正确<br>4. 自动生成注释<br>5. 支持自定义动作函数声明 |
| **MISRA 检查** | ✅ 生成的 C 代码需通过 MISRA 检查 |

### T-028: Bootloader 设计（双区 OTA）

| 属性 | 值 |
|:-----|:----|
| **名称** | Bootloader — 双区 OTA 升级框架 |
| **分类** | 系统架构 |
| **难度** | 🔴 困难 |
| **输入描述** | 需求：设计一个 STM32F4 双区 Bootloader 框架。Boot 区（Sector 0, 16KB）+ App A 区（64KB）+ App B 区（64KB）。Boot 区逻辑：上电检查 App A/B 的有效性标志，跳转到有效的最新版本。通过 UART 接收新固件并写入备用分区。固件签名验证（CRC32）。 |
| **预期输出** | C 源文件（`bootloader.c`、`bootloader.h`），含：向量表重映射、分区定义、固件验证、跳转逻辑、UART 固件接收协议（YMODEM 或自定义简单协议）。 |
| **验收标准** | 1. 编译通过<br>2. 分区地址定义正确（不需实际运行）<br>3. 跳转函数正确（设置 MSP + PC）<br>4. 固件 CRC32 验证逻辑正确<br>5. 回退机制（App A 失效则从 App B 启动）<br>6. 注释说明分区布局和启动流程 |
| **MISRA 检查** | ✅ 要求 MISRA 违规 ≤ 3 条（允许跳转相关的 Rule 20.9 豁免） |

### T-029: 驱动层分层架构重构

| 属性 | 值 |
|:-----|:----|
| **名称** | 架构重构 — 将裸机驱动改为分层架构 |
| **分类** | 软件设计 |
| **难度** | 🔴 困难 |
| **输入描述** | 需求：给定的单文件 UART 驱动（~150 行，直接操作寄存器），重构为三层架构：HAL 层（MCU 抽象，使用 STM32 HAL）、驱动层（API 接口封装）、应用层（使用驱动 API 的示例）。HAL 层提供 `uart_init`/`uart_send`/`uart_recv`，驱动层提供 `uart_open`/`uart_write`/`uart_read`/`uart_ioctl`（波特率、奇偶校验配置），应用层展示 UART echo 服务器。 |
| **预期输出** | C 源文件（`hal_uart.c/h`、`drv_uart.c/h`、`app_echo.c/h`），三层清晰分离。 |
| **验收标准** | 1. 各层独立编译通过<br>2. 驱动层不直接操作寄存器（仅调用 HAL 层）<br>3. 应用层不直接调用 HAL 层<br>4. 接口设计合理（错误码、超时、回调）<br>5. 分层注释清晰 |
| **MISRA 检查** | ✅ 要求通过 MISRA Rule 8.7（外部链接必须有外部声明） |

### T-030: 端到端流水线 — 从 Spec 到证据包

| 属性 | 值 |
|:-----|:----|
| **名称** | 端到端流水线 — 完整生命周期验证 |
| **分类** | 系统集成 |
| **难度** | 🔴 困难 |
| **输入描述** | 需求：采用 yuleOSH 全流程，从一个 GPIO LED 闪烁的 OpenSpec 需求文件出发，执行完整的 SDD→DDD→Code→MISRA Check→Unit Test→CI→Evidence Pack 流水线。 |
| **预期输出** | 1. OpenSpec spec 文件 (`spec.md`，含 SHALL 语句)<br>2. SDD 文档输出<br>3. DDD 文档输出<br>4. C 代码（编译通过）<br>5. MISRA 检查通过<br>6. 单元测试编写并通过<br>7. CI 流水线配置<br>8. 证据包可打包 |
| **验收标准** | 1. SDD→DDD→Code→Test→CI 所有步骤自动完成<br>2. 最终证据包 `yuleosh ev check` 返回 `valid: True`<br>3. 全局覆盖率 ≥60%（仅针对本 demo 项目代码）<br>4. MISRA 违规 0 条<br>5. 总耗时 ≤ 3 分钟（基准值，可随环境调整）<br>6. 端到端成功率 ≥ 3/5（5 次运行中至少 3 次成功） |

---

## Benchmark 运行说明

### 环境要求

```
# Benchmark 运行环境
MCU:   STM32F407VGT6 (Cortex-M4)
Board: STM32F4-Discovery
Toolchain: arm-none-eabi-gcc 12.2+
          + cppcheck 2.13+
          + FreeRTOS v10.5.1
RTOS:  FreeRTOS (T-017, T-018, T-023)
Libraries: STM32Cube_FW_F4 V1.28
           cJSON 1.7.17 (T-016)
```

### 运行命令

```bash
# 运行所有 benchmark
python3 -m bench run --all

# 运行指定难度
python3 -m bench run --difficulty easy
python3 -m bench run --difficulty medium
python3 -m bench run --difficulty hard

# 运行单个任务
python3 -m bench run --task T-001

# 输出报告
python3 -m bench report --format markdown --output docs/ai-benchmark-report.md
```

### 结果数据格式 (CSV)

```
task_id,run_id,difficulty,success,duration_seconds,code_accept_rate,review_pass_rate,errors
T-001,1,easy,true,45.2,1.0,1.0,""
T-001,2,easy,true,42.8,1.0,1.0,""
T-001,3,easy,false,120.5,0.0,0.0,"compilation error: undefined reference"
```

---

*小马 🐴 — 30 个 AI Benchmark 任务定义完成*
*任务数量: 30 (简单 10 + 中等 12 + 困难 8)*
*覆盖类型: GPIO/Timer/UART/I2C/SPI/ADC/CAN/PWM/IWDG/FreeRTOS/MISRA/CRC/Bootloader/端到端*

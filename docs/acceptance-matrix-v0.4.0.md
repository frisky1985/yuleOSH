# yuleOSH v0.4.0 — 验收判定矩阵 (Acceptance Matrix)

> **迭代**: v0.4.0 — SIL 仿真测试能力
> **角色**: 小马 🐴 (质量架构师)
> **日期**: 2026-06-09
> **覆盖范围**: RS-008, SWR-008.1, SWR-008.2, SWR-008.3

---

## 矩阵说明

- **方法**: `A`=自动化测试, `C`=代码审查, `R`=人工评审, `M`=手动测试, `I`=CI 集成验证
- **优先级**: P0=必须通过才能发布, P1=建议通过, P2=可选
- **PASS 条件**: 每个验收标准的判定条件，可客观验证

---

## RS-008: 嵌入式 SIL 仿真测试

### RS-008-01: ARM Cortex-M SIL 支持

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| RS-008.1 | 系统支持 ARM Cortex-M 目标的 SIL 测试 | C + A | `qemu-sil-runner --elf test.elf --machine stm32vldiscovery` 在 60s 内返回 SilResult，QEMU 进程正常启动并退出 | P0 |
| RS-008.2 | 交叉编译产物 (.elf) 在 QEMU 下执行 | A | 编译一个最小 ARM 固件 (如 UART 输出 "Hello")，QEMU SIL 运行后 serial log 包含 "Hello" | P0 |
| RS-008.3 | SIL 测试捕获 UART 串口输出 | A | QEMU 启动时通过 `-serial stdio` 或 `-chardev pipe` 连接，测试日志包含目标输出的全部 UART 字符 | P0 |
| RS-008.4 | SIL 测试捕获 semihosting 输出 | A | 使用 semihosting `SVC 0xAB` 输出的固件，serial log 包含 semihosting 输出内容 | P1 |
| RS-008.5 | SIL 测试阻断 CI L2 (失败时) | I | 故意插入一个预期 FAIL 的 SIL 测试，pipeline run 中止且 exit code ≠ 0 | P0 |
| RS-008.6 | SIL 测试报告纳入 evidence 包 | I + C | `sil-test-report.json` 出现在 compliance pack 中；格式包含 per-test passed/failed/log/duration | P0 |
| RS-008.7 | RISC-V QEMU SIL 支持 (SHOULD) | C + A | RISC-V `virt` 机器的 .elf 可通过 `qemu-sil-runner --machine virt --arch riscv64` 运行并输出 | P1 |
| RS-008.8 | Renode 替代平台 (MAY) | C + R | Renode runner 骨架实现存在，接口与 QEMU runner 对齐 (SilResult) | P2 |
| RS-008.9 | ARM Cortex-A/R 系列 (MAY) | C | 目标配置 YAML 支持 cortex-a/cortex-r 机器类型的声明 | P2 |

---

## SWR-008.1: QEMU SIL Runner

### SWR-008.1-01: Runner 核心功能

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| SWR-008.1.1 | `qemu-sil-runner` 组件存在 | C | `src/cross/sil_runner.py` 或等价文件存在，导出的 `QemuSilRunner` 类可实例化 | P0 |
| SWR-008.1.2 | 加载 .elf 到 QEMU | A | 提供一个测试用 .elf，runner 启动后目标正确开始执行 (串口输出启动消息) | P0 |
| SWR-008.1.3 | 串口输出捕获 | A | 目标在 QEMU 中每 100ms 输出一行，runner 捕获全部行直到超时 | P0 |
| SWR-008.1.4 | 超时终止 (默认 30s) | A | 设置 timeout=3，目标持续输出 10s；runner 在 3s ± 1s 内终止 QEMU，返回 duration=3.0s 左右 | P0 |
| SWR-008.1.5 | 超时可配置 | A | `--timeout 5` 使 runner 在 5s 而非 30s 终止 | P0 |
| SWR-008.1.6 | PASS/FAIL 基于串口断言 | A | `expect("FOO")` 匹配到串口输出 → PASS；未匹配到 → FAIL | P0 |
| SWR-008.1.7 | 完整 serial log 返回 | A | 无论 PASS/FAIL，SilResult.log 包含从启动到终止的全部串口内容 | P0 |
| SWR-008.1.8 | ARM Cortex-M3 lm3s6965evb 支持 | A | `--machine lm3s6965evb` 正常启动 QEMU 并执行 .elf | P0 |
| SWR-008.1.9 | ARM Cortex-M4 stm32vldiscovery 支持 | A | `--machine stm32vldiscovery` 正常启动 QEMU 并执行 .elf | P0 |
| SWR-008.1.10 | RISC-V virt 机器支持 (SHOULD) | A | `--machine virt --arch riscv64` 正常启动 QEMU 并执行 RISC-V .elf | P1 |
| SWR-008.1.11 | YAML 配置目标板 (SHOULD) | C + A | 目标板参数可来自 YAML 配置，`qemu-sil-runner --target stm32f4` 读取 `.yuleosh/targets/stm32f4.yaml` | P1 |

### SWR-008.1-02: GIVEN/WHEN/THEN 场景验证

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| SWR-008.1.S1 | GIVEN .elf + machine + timeout → 启动 QEMU + 加载 + 捕获 + 终止 + 返回结果 | A | 执行完整命令后，SilResult 包含 passed(bool)、log(str)、duration_seconds(float) 三个字段 | P0 |
| SWR-008.1.S2 | GIVEN expect 断言 → 匹配则 PASS，不匹配则 FAIL | A | 串口输出 "Hello World" 时 `expect("Hello World")` → PASS；输出 "Goodbye" 时 `expect("Hello")` → FAIL | P0 |

---

## SWR-008.2: HAL Mock 框架

### SWR-008.2-01: Mock 框架功能

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| SWR-008.2.1 | HAL Mock 层存在 | C | `src/cross/hal_mock/` 目录存在，提供 UART/GPIO/Timer/I2C/SPI mock 头文件 | P0 |
| SWR-008.2.2 | UART mock | A | 宿主机构建测试调用 `HAL_UART_Transmit()`，mock 记录调用并可通过 API 查询 | P0 |
| SWR-008.2.3 | GPIO mock | A | 宿主机构建测试调用 `HAL_GPIO_WritePin()` 和 `HAL_GPIO_ReadPin()`，mock 记录调用 | P0 |
| SWR-008.2.4 | Timer mock | A | 宿主机构建测试调用 `HAL_TIM_Base_Start()` / `HAL_TIM_Base_Stop()` / `HAL_GetTick()`，mock 模拟计时 | P0 |
| SWR-008.2.5 | I2C mock | A | 宿主机构建测试调用 `HAL_I2C_Master_Transmit()` / `HAL_I2C_Master_Receive()`，mock 记录调用 | P1 |
| SWR-008.2.6 | SPI mock | A | 宿主机构建测试调用 `HAL_SPI_TransmitReceive()`，mock 记录调用 | P1 |
| SWR-008.2.7 | 调用序列验证 (SHOULD) | A | mock 暴露 `get_call_history()` 返回有序调用列表，支持 `assert_call_order(expected_sequence)` | P1 |
| SWR-008.2.8 | 状态机序列验证 (SHOULD) | A | 测试可断言 `call_history[0] == ("HAL_GPIO_WritePin", "GPIOA", 1)` AND `call_history[1] == ("HAL_UART_Transmit", "USART1", ...)` | P1 |
| SWR-008.2.9 | 自动 mock 生成 (MAY) | C | 提供 HAL 头文件解析脚本骨架，可自动生成 mock C 文件 | P2 |

### SWR-008.2-02: GIVEN/WHEN/THEN 场景验证

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| SWR-008.2.S1 | GIVEN 源码调用 HAL → 宿主机构建 + mock 链接 → 记录调用 | A | 宿主机构建测试程序，链接 mock，运行后 mock 记录了所有 HAL 调用 | P0 |
| SWR-008.2.S2 | GIVEN 状态机(GPIO→UART) → mock 验证序列 | A | 状态机执行后，call_history 中 GPIO 调用在 UART 调用之前 | P1 |

---

## SWR-008.3: SIL 测试规范

### SWR-008.3-01: 测试规范执行

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| SWR-008.3.1 | SIL 测试使用 GIVEN/WHEN/THEN 格式 | C | 所有 SIL 测试定义文件以 GIVEN/WHEN/THEN 结构编写 | P0 |
| SWR-008.3.2 | SIL 作为 CI L2 独立阶段 | I | CI L2 pipeline 配置中包含 `sil-tests` stage，位于 cross-compile 之后、integration-tests 之前 | P0 |
| SWR-008.3.3 | 证据包按测试粒度报告 | I + C | `sil-test-report.json` 包含每条测试的 passed/failed/log/duration | P0 |
| SWR-008.3.4 | SIL 失败阻断 pipeline | I | SIL 测试 FAIL → pipeline exit code ≠ 0 → 后续 stage 不执行 | P0 |
| SWR-008.3.5 | 测试隔离 — 独立 QEMU 进程 | A | 两个 SIL 测试同时运行，各自有独立 QEMU PID，互相不干扰 | P0 |
| SWR-008.3.6 | 参数化多目标 (SHOULD) | I + A | 同一套 SIL 测试可在 ARM M3 和 M4 目标上并行执行，结果分别报告 | P1 |
| SWR-008.3.7 | 并行执行 (MAY) | A | 4 个独立 SIL 测试同时运行时，总耗时 < 单测 × 1.5 (并行比例合理) | P2 |
| SWR-008.3.8 | 测试超时保护 — 每个测试有 timeout | A | 每个 SIL 测试配置 timeout，超时后自动中止并标记 FAIL | P0 |
| SWR-008.3.9 | 证据包包含 SIL 报告 | I + C | SIL 报告位于 `evidence/sil-test-report.json`，作为 evidence pack 的一部分 | P0 |

### SWR-008.3-02: GIVEN/WHEN/THEN 场景验证

| Spec ID | 验收标准 | 方法 | PASS 条件 | 优先级 |
|---------|---------|------|-----------|:------:|
| SWR-008.3.S1 | GIVEN SIL 测试集 → CI L2 执行 → 隔离 QEMU + 证据包 + 阻断 | I | 运行包含一个 FAIL 测试的 SIL 套件，pipeline 在 sil-tests stage 中止，evidence 包含失败记录 | P0 |
| SWR-008.3.S2 | GIVEN 多目标测试 → 各自独立配置 | I | ARM M3 测试使用 `lm3s6965evb` 机器，RISC-V 测试使用 `virt` 机器，证据包分别报告 | P1 |

---

## 总体验收统计

| 分类 | 总数 | P0 | P1 | P2 | 说明 |
|------|:----:|:--:|:--:|:--:|:-----|
| RS-008 | 9 | 6 | 1 | 2 | SIL 仿真测试顶层需求 |
| SWR-008.1 | 13 | 8 | 4 | 1 | QEMU SIL Runner |
| SWR-008.2 | 11 | 5 | 4 | 2 | HAL Mock 框架 |
| SWR-008.3 | 11 | 7 | 3 | 1 | SIL 测试规范 |
| **合计** | **44** | **26** | **12** | **6** | P0 占比 59% |

### P0 门禁清单 (v0.4.0 发布必须通过)

1. RS-008.1 — ARM Cortex-M SIL 支持
2. RS-008.2 — .elf 在 QEMU 下执行
3. RS-008.3 — UART 串口捕获
4. RS-008.5 — SIL 阻断 pipeline
5. RS-008.6 — 报告纳入 evidence
6. SWR-008.1.1 — Runner 组件存在
7. SWR-008.1.2 — .elf 加载
8. SWR-008.1.3 — 串口捕获
9. SWR-008.1.4 — 超时终止 (默认 30s)
10. SWR-008.1.5 — 超时可配置
11. SWR-008.1.6 — PASS/FAIL 基于断言
12. SWR-008.1.7 — 完整 log 返回
13. SWR-008.1.8 — lm3s6965evb 支持
14. SWR-008.1.9 — stm32vldiscovery 支持
15. SWR-008.2.1 — HAL Mock 层存在
16. SWR-008.2.2 — UART mock
17. SWR-008.2.3 — GPIO mock
18. SWR-008.2.4 — Timer mock
19. SWR-008.3.1 — GIVEN/WHEN/THEN 格式
20. SWR-008.3.2 — SIL 作为 CI L2 独立阶段
21. SWR-008.3.3 — 证据包按测试粒度
22. SWR-008.3.4 — 失败阻断
23. SWR-008.3.5 — 测试隔离
24. SWR-008.3.8 — 测试超时保护
25. SWR-008.3.9 — 证据包包含 SIL 报告
26. SWR-008.1.S1 + SWR-008.1.S2 — GIVEN/WHEN/THEN Runner 场景

> 🔴 **26 项 P0 全部通过** = v0.4.0 发布就绪

# Spec Delta — HAL Mock 框架

> **版本**: v0.4.1
> **日期**: 2026-06-11
> **目标**: 补完 SIL 仿真测试最后一环 — HAL Mock C 头文件
> **关联需求**: RS-008 / SWR-008.2

---

## 新增需求

### RS-008.2: HAL Mock 框架（更新）

#### 原需求（不变）
- SWR-008.2.1 ~ SWR-008.2.9: 原有验收标准保持不变

#### 新增细化

| ID | 描述 | SHALL/SHOULD/MAY |
|:---|:-----|:----------------:|
| SWR-008.2.10 | 所有 mock 在 `src/cross/hal_mock/` 目录下 | SHALL |
| SWR-008.2.11 | 提供 `mock_core.h` 核心框架（调用记录、断言、重置） | SHALL |
| SWR-008.2.12 | UART mock 支持 `HAL_UART_Transmit` / `HAL_UART_Receive` / `HAL_UART_Abort` | SHALL |
| SWR-008.2.13 | GPIO mock 支持 `HAL_GPIO_WritePin` / `HAL_GPIO_ReadPin` / `HAL_GPIO_TogglePin` | SHALL |
| SWR-008.2.14 | Timer mock 支持 `HAL_TIM_Base_Start` / `HAL_TIM_Base_Stop` / `HAL_GetTick` | SHALL |
| SWR-008.2.15 | I2C mock 支持 `HAL_I2C_Master_Transmit` / `HAL_I2C_Master_Receive` / `HAL_I2C_Mem_Write` / `HAL_I2C_Mem_Read` | SHOULD |
| SWR-008.2.16 | SPI mock 支持 `HAL_SPI_Transmit` / `HAL_SPI_Receive` / `HAL_SPI_TransmitReceive` | SHOULD |
| SWR-008.2.17 | 提供 `mock_reset_all()` 清空调用历史 | SHALL |
| SWR-008.2.18 | 提供 `mock_assert_call_count(name, expected)` 验证调用次数 | SHALL |
| SWR-008.2.19 | mock 可通过 `hal_mock_impl.c` 编译为宿主机构建测试 | SHALL |
| SWR-008.2.20 | 宿主机构建测试包含 UART+GPIO 序列验证、SPI CS 序列验证、I2C 读取验证 | SHALL |

---

## 验收场景

### GIVEN/WHEN/THEN

**场景 1: UART + GPIO 序列验证**
```
GIVEN 一个调用 HAL_UART_Transmit 和 HAL_GPIO_WritePin 的固件函数
WHEN  在宿主机构建并调用该函数
THEN  mock_assert_call_count("HAL_UART_Transmit", 1) 通过
 AND  mock_assert_call_count("HAL_GPIO_WritePin", 2) 通过
```

**场景 2: SPI CS 序列验证**
```
GIVEN 一个先拉 CS 再 SPI 传输再释放 CS 的固件函数
WHEN  在宿主机构建并调用该函数
THEN  mock_assert_call_count("HAL_GPIO_WritePin", 2) 通过
 AND  mock_assert_call_count("HAL_SPI_TransmitReceive", 1) 通过
```

**场景 3: I2C 读取**
```
GIVEN 一个调用 HAL_I2C_Mem_Read 读取温湿度传感器的固件函数
WHEN  在宿主机构建并调用该函数
THEN  mock_assert_call_count("HAL_I2C_Mem_Read", 1) 通过
```

---

## 影响范围

- 新增 `src/cross/hal_mock/` 目录，6 个文件
- 不影响现有 Python 代码
- 不影响 CI pipeline
- 不影响证据链

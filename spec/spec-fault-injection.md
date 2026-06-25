# yuleOSH Fault Injection Pipeline — 软件需求规格

> **版本**: v1.1.0
> **状态**: 草案
> **作者**: 小马 🐴 (质量架构师)
> **日期**: 2026-06-20
> **规范文体**: RFC 2119 (SHALL/SHALL NOT/SHOULD/MAY)
> **输入源**: A66-T HardFault Exception Injection Automated Test Runner 逆向分析 + 团队讨论
> **参考 MCU**: Z20K148M (ARM Cortex-M4F), FreeRTOS

---

## 目录

1. [核心定位与架构概览](#1-核心定位与架构概览)
2. [行业约束映射](#2-行业约束映射)
3. [Spec 契约层](#3-spec-契约层不可变)
   - 3.1 [Pipeline 集成 (FI-01~05)](#31-pipeline-集成-fi-01fi-05)
   - 3.2 [测试用例定义 (FI-06~10)](#32-测试用例定义-fi-06fi-10)
   - 3.3 [结果与报告 (FI-11~15)](#33-结果与报告-fi-11fi-15)
   - 3.4 [通信层抽象 (FI-16~20)](#34-通信层抽象-fi-16fi-20)
   - 3.5 [任务级注入 (FI-21~31)](#35-任务级注入-fi-21fi-31)
4. [系统架构](#4-系统架构)
5. [实现指引](#5-实现指引可变)

---

## 1. 核心定位与架构概览

### 1.1 定位

Fault Injection Pipeline 是 yuleOSH Pipeline 中的一个**可选 Standard Stage**，注入可控的硬件异常/故障到目标系统，验证错误处理机制的鲁棒性和故障恢复能力。

### 1.2 设计哲学

| 原则 | 说明 |
|------|------|
| **抽象通信层** | 注入方法可插拔（CAN/UDS, Ethernet/DoIP, JTAG/SWD, 模拟器） |
| **用例驱动** | 每个测试用例是 `inject_spec + verify_spec` 元组 |
| **闭环验证** | 注入 → 复位/触发 → 验证 → 报告 |
| **结果可追溯** | 每条用例可关联 FMEA 条目、知识条目、安全目标 |
| **非侵入式** | 可选阶段，默认不启用，用户显式配置 |

### 1.3 与现有模块的关系

| 依赖模块 | 用途 | 契约级别 |
|---------|------|---------|
| pipeline | 新增 `fault_injection` 阶段定义 | 强制 |
| ci | 新增 `fi` 子命令（本地运行、CI 集成） | 强制 |
| evidence | 注入结果进入证据矩阵 | 强制 |
| knowledge | 注入结果与 FMEA 条目/KB 条目关联 | 强制 |
| store | 结构化 JSON 报告持久化 | 强制 |

### 1.4 Pipeline 阶段位置（建议）

```
Build → Unit Test → [Fault Injection] → Integration Test → HIL → Verification
                           ↑
                    可选阶段，默认跳过
```

---

## 2. 行业约束映射

| # | 约束 | 覆盖条目 |
|---|------|---------|
| 1 | ISO 26262 错误处理验证（ASIL 等级门禁） | FI-01, FI-05, FI-14 |
| 2 | UDS / DoIP 诊断协议合规 | FI-02, FI-16 |
| 3 | 多平台 MCU 支持（ARM Cortex-M 全系列） | FI-07, FI-08 |
| 4 | 故障覆盖度度量（Fault Injection Coverage） | FI-11, FI-13, FI-15 |
| 5 | FMEA 闭环验证 | FI-14 |
| 6 | CI/CD 门禁自动化 | FI-04, FI-05 |
| 7 | 通信层安全超时保护 | FI-17, FI-18 |
| 8 | 并发多目标测试（多 ECU 场景） | FI-20 |
| 9 | 代码无侵入 — 不修改被测固件 | FI-06 |
| 10 | 硬件一致性 — 支持 JTAG/SWD 调试口旁路 | FI-02 |

---

## 3. Spec 契约层（不可变）

### 3.1 Pipeline 集成 (FI-01~FI-05)

---

#### FI-01: Pipeline 阶段定义

**SHALL** — yuleOSH pipeline SHALL 支持 `fault_injection` 作为可选的 Standard Stage，命名空间为 `stage.fault_injection`。

**SHALL** — 该阶段 SHALL 与其他 Standard Stage（如 `stage.build`, `stage.unit_test`）遵循相同的生命周期钩子：`pre_run`, `run`, `post_run`, `on_failure`。

**SHALL** — 当 pipeline 配置中未显式声明 `fault_injection` 阶段时，系统 SHALL 跳过该阶段（默认不执行）。

**SHOULD** — `fault_injection` 阶段 SHOULD 在 `unit_test` 之后、`integration_test` 之前执行（默认顺序），但用户可通过配置覆盖该顺序。

---

#### FI-02: 注入目标配置

**SHALL** — 用户 SHALL 通过 YAML 配置注入目标（`injection_target`），支持的枚举值：`can`, `ethernet`, `jtag`, `simulator`。

**SHALL** — 每种注入目标 SHALL 携带连接参数，参数格式由对应的通信适配器定义，但 SHALL 包含以下公共字段：
- `type` (枚举: `can`/`ethernet`/`jtag`/`simulator`)
- `timeout_ms` (整数, 默认 30000)
- `retry_count` (整数, 默认 3)

**SHALL** — 当 `type` 为 `can` 时，SHALL 额外支持以下配置字段：
- `interface` (字符串: `socketcan`/`vector`/`dolp`)
- `channel` (字符串, 如 `can0`)
- `bitrate` (整数, 如 500000)
- `uds_id` (结构体: `{ req_id, res_id }`)

**SHALL** — 当 `type` 为 `ethernet` 时，SHALL 额外支持以下配置字段：
- `interface` (字符串: `doip`/`someip`)
- `ip_address` (字符串)
- `port` (整数)
- `doip_logical_address` (整数, 可选)

**SHALL** — 当 `type` 为 `jtag` 时，SHALL 额外支持以下配置字段：
- `adapter` (字符串: `jlink`/`stlink`/`openocd`/`pyocd`)
- `target_chip` (字符串, 如 `Z20K148M`)
- `interface_speed_khz` (整数, 默认 4000)
- `debug_port` (枚举: `swd`/`jtag`)

**SHALL** — 当 `type` 为 `simulator` 时，SHALL 额外支持以下配置字段：
- `engine` (字符串: `qemu`/`unicorn`/`renode`)
- `machine_model` (字符串)
- `binary_path` (字符串)

**SHALL** — Pipeline 配置中的注入目标 SHALL 以名称（target_name）作为唯一标识，用例集 YAML 中的 `target` 字段 SHALL 引用此名称。

**SHALL** — 同一 target_name 的完整连接参数（含 type 及类型专属字段）SHALL 仅在 pipeline 配置中定义一次，用例集 SHALL NOT 重复定义连接参数。

**MAY** — 系统 MAY 支持混合目标配置（同一阶段中部分用例通过 CAN 执行，部分通过 JTAG）。

---

#### FI-03: 测试用例集配置

**SHALL** — 用户 SHALL 通过 YAML 文件定义故障注入测试用例集，默认路径为 `fault_injection/cases/<suite_name>.yaml`。

**SHALL** — 系统 SHALL 支持通过 `fi.config.test_suites` 配置引用一个或多个用例集文件。

**SHALL** — 用例集 YAML SHALL 经过 schema 校验，校验失败时输出详细的错误报告（文件名 + 行号 + 字段 + 错误类型）。

**SHALL** — 一个用例集 SHALL 包含以下元数据：
- `suite_name` (字符串)
- `description` (Markdown, 可选)
- `fi_version` (字符串, 当前版本 `1.0`)
- `target` (字符串, 引用 FI-02 中定义的注入目标名称 target_name）
- `cases` (数组)

**SHOULD** — 系统 SHOULD 支持从知识管理模块的 FMEA 条目自动生成用例草案（基于 ap_priority 为 H/M 的条目）。

---

#### FI-04: 阶段结果进入 evidence 模块

**SHALL** — `fault_injection` 阶段的执行结果 SHALL 自动写入 evidence 模块，每条测试用例生成一条证据记录。

**SHALL** — 每条证据记录 SHALL 包含：
- `source` (固定值: `fault_injection`)
- `suite_name` (字符串)
- `case_id` (字符串)
- `result` (枚举: `pass`/`fail`/`skip`/`error`)
- `summary` (字符串, 失败时包含故障描述摘要)
- `detail_path` (字符串, 指向结构化 JSON 报告的文件路径)
- `executed_at` (时间戳)
- `duration_ms` (整数)

**SHALL** — 当关联了 FMEA 条目 ID（via FI-14）的用例结果为 `fail` 时，evidence 模块 SHALL 自动通知对应 FMEA 条目的负责人。

---

#### FI-05: 阻断阈值

**SHALL** — 用户 SHALL 通过 `fi.config.block_threshold` 配置阻断阈值，格式为 `{ fail: N, error: M }`。

**SHALL** — 当 `fault_injection` 阶段的 `fail` 计数达到 `block_threshold.fail` 时，系统 SHALL 将阶段状态设为 `blocked` 并终止后续用例执行。

**SHALL** — 当 `block_threshold` 未配置时，系统 SHALL 默认行为为：FAIL > 0 时阻断（即任一用例失败即阻断）。

**SHALL NOT** — 阻断 SHALL NOT 影响其他已完成的 Standard Stage 的执行结果。

---

### 3.2 测试用例定义 (FI-06~FI-10)

---

#### FI-06: 注入 + 验证 双规定义

**SHALL** — 每条测试用例 SHALL 包含 `inject_spec` 和 `verify_spec` 两个强制区块。

**SHALL** — `inject_spec` 定义如何注入故障，`verify_spec` 定义如何验证结果。

**SHALL** — 用例结构体 SHALL 包含以下字段：
- `case_id` (字符串, 用例集内唯一, 如 `FI-NULLPTR-001`)
- `description` (字符串, 用例描述)
- `inject_spec` (对象, 见 FI-07)
- `verify_spec` (对象, 见 FI-08)
- `skip_condition` (对象, 可选, 见 FI-09)
- `cooldown_ms` (整数, 可选, 默认 3000, 见 FI-10)
- `fmea_refs` (字符串数组, 可选, 关联 FMEA 条目 ID)
- `knowledge_refs` (字符串数组, 可选, 关联 KB 条目 ID)
- `safety_goal_refs` (字符串数组, 可选, 关联安全目标 ID)

**SHALL NOT** — 测试用例 SHALL NOT 要求修改被测目标固件代码。

---

#### FI-07: 注入方式（inject_spec）

**SHALL** — `inject_spec` SHALL 支持以下注入方法，由 `method` 字段指定：

1. **`method: did_write`** — 通过诊断 DID（UDS $2E）写入注入指令
   - `did` (十六进制字符串, 如 `F190`)
   - `data` (十六进制字节串, 如 `AABB01`)
   - 适用于 CAN/Ethernet 目标

2. **`method: register_tamper`** — 直接篡改 CPU 寄存器/SCB 寄存器
   - `register` (字符串, 如 `CFSR`, `HFSR`, `MMFSR`, `BFSR`, `UFSR`)
   - `mask` (十六进制掩码, 如 `0x00000600`)
   - `value` (十六进制值, 如 `0x00000600`)
   - 适用于 JTAG/Simulator 目标

3. **`method: memory_overwrite`** — 覆写指定内存地址
   - `address` (十六进制地址)
   - `value` (十六进制字节串)
   - `size` (整数, 字节数, 如 4)
   - 适用于 JTAG/Simulator 目标

4. **`method: stack_overflow`** — 触发栈溢出
   - `target_function` (字符串, 目标函数名)
   - `overflow_bytes` (整数, 溢出字节数)
   - 适用于 Simulator/带符号表 JTAG

**SHALL** — `inject_spec` 中的所有十六进制值 SHALL 为小写字母（如 `0xff`），系统显示和日志输出 SHALL 统一使用大写。

**SHALL** — 每个注入方法 SHALL 支持 `pre_inject_delay_ms` 和 `post_inject_delay_ms` 可选参数（默认 0），用于时序微调。

**MAY** — 系统 MAY 通过插件扩展更多注入方法。

---

#### FI-08: 验证方式（verify_spec）

**SHALL** — `verify_spec` SHALL 支持以下验证维度：

1. **`type: fault_type`** — 验证故障记录中的 faultType
   - `expected_types` (整数数组, 如 `[1, 3]` — 允许一个或多个符合的 faultType)
   - 对应：1=HardFault, 2=MemManage, 3=BusFault, 4=UsageFault, 5=StackOverflow

2. **`type: register_mask`** — 验证 CFSR/其他状态寄存器的特定位
   - `register` (字符串, 如 `CFSR`)
   - `expected_mask` (十六进制掩码, 如 `0x00000600`)
   - `operator` (枚举: `and_nonzero`/`and_zero`/`equal`/`notequal`, 默认 `and_nonzero`)

3. **`type: pc_range`** — 验证故障发生 PC 在预期地址范围
   - `range_start` (十六进制地址)
   - `range_end` (十六进制地址)

4. **`type: behavior`** — 观察目标系统的外部行为
   - `observations` (数组, 枚举: `ecu_reset`/ `dtc_set`/ `nvm_updated`/ `safe_state_enter`)
   - `operator` (枚举: `all`/`any`/`none`)

**SHALL** — 验证通过条件（所有指定验证维度同时满足）：
- fault_type 验证：运行时返回的 `faultType` ∈ `expected_types`
- register_mask 验证：按 `operator` 判断（默认 `and_nonzero` = `(CFSR & expected_mask) != 0`)
- 行为验证：按 `operator` 判断

**SHALL** — 验证前置条件 SHALL 包含 `magic` 完整性校验（A66-T 协议兼容）：`magic == 0xFA017FA0`。

**SHALL** — 当 `magic` 校验失败时，系统 SHALL 将用例结果标记为 `error`（数据损坏），而非 `fail`。

---

#### FI-09: SKIP 条件

**SHALL** — 每条用例 SHALL 支持可选的 `skip_condition` 配置。

**SHALL** — `skip_condition` SHALL 支持以下条件类型：

1. **`type: target_property`** — 基于目标属性
   - `property` (字符串, 如 `mpu_enabled` / `nvm_present` / `debug_enabled`)
   - `expected` (布尔值, 为 `false` 时跳过)

2. **`type: build_config`** — 基于构建配置
   - `config_key` (字符串, 如 `CONFIG_HARD_FAULT_HANDLER`)
   - `expected` (布尔值, 为 `false` 时跳过)

3. **`type: always`** — 无条件跳过（用于标记已废弃或待实现用例）
   - `reason` (字符串, 说明跳过原因)

**SHALL** — 当 `skip_condition` 评估为"应跳过"时，该用例结果 SHALL 记录为 `skip`，不执行注入和验证。

**SHOULD** — 系统 SHOULD 在 summary 报告中说明每条 `skip` 用例的跳过原因。

---

#### FI-10: Cooldown 间隔

**SHALL** — 每条用例 SHALL 支持 `cooldown_ms` 参数，指定用例执行完成（包括验证）后到下一用例开始之间的等待时间。

**SHALL** — 默认 `cooldown_ms` 为 3000（3 秒），对应 A66-T 脚本的测试间间隔。

**SHALL** — `cooldown_ms` 允许最小值为 0（无间隔），但用户 SHALL 显式确认（如配置中写为 0 时，日志输出警告）。

**SHALL** — Cooldown 的等待时间 SHALL 独立于注入超时（inject_timeout_ms）的计算，注入超时计时 SHALL NOT 因 cooldown 而延长。

**SHALL** — Cooldown SHALL 计入用例超时（case_timeout_ms）和 stage 总耗时，计算公式参见 FI-18。

---

### 3.3 结果与报告 (FI-11~FI-15)

---

#### FI-11: 用例结果分类

**SHALL** — 每条测试用例的执行结果 SHALL 属于以下四类之一：
- `pass` — 注入成功、验证通过
- `fail` — 注入成功、验证未通过（magic 校验通过但预期条件不满足）
- `skip` — 因 skip_condition 满足而跳过（见 FI-09）
- `error` — 注入或验证过程中发生非预期异常（通信失败、超时、magic 校验失败、配置错误）

**SHALL** — `pass`/`fail`/`skip`/`error` 四类 SHALL 互斥，一条用例不能同时属于多个分类。

**SHALL** — 当用例结果为 `error` 时，系统 SHALL 记录错误类型（枚举：`timeout`/`connection_lost`/`magic_mismatch`/`config_error`/`internal`）。

---

#### FI-12: 故障详情记录

**SHALL** — 当用例结果为 `pass` 或 `fail` 时，系统 SHALL 记录完整的故障详情，包含：
- `magic` (十六进制, 预期 `0xFA017FA0`)
- `fault_type` (整数, 1–5)
- `pc` (十六进制地址)
- `cfsr` (十六进制, CFSR 寄存器值)
- `hfsr` (十六进制, HFSR 寄存器值, 可选)
- `mmfsr` (十六进制, MemManage Fault Status, 可选)
- `bfsr` (十六进制, BusFault Status, 可选)
- `ufsr` (十六进制, UsageFault Status, 可选)
- `expected_mask` (十六进制, 验证使用)
- `actual_mask_result` (十六进制, 实际相与结果)
- `injected_raw_data` (十六进制, 注入原始数据)

**SHALL** — 当 `fault_type` 的值为 `5` (StackOverflow) 时，故障记录 SHALL 额外包含 `overflow_depth_bytes`（探测到的溢出深度字节数）。

**SHOULD** — 系统 SHOULD 将 `cfsr` / `hfsr` / `mmfsr` / `bfsr` / `ufsr` 解码为可读的位级含义（如 `"CFSR.UNALIGNED: 1"`）。

---

#### FI-13: 结构化 JSON 报告

**SHALL** — `fault_injection` 阶段执行后 SHALL 生成一份结构化 JSON 报告，默认保存路径为 `reports/fault_injection/<timestamp>.json`。

**SHALL** — JSON 报告 SHALL 包含以下顶层字段：
```json
{
  "report_version": "1.0",
  "generated_at": "<ISO 8601 timestamp>",
  "pipeline_run_id": "<UUID>",
  "suite_name": "<suite_name>",
  "injection_target": { "type": "<target_type>", "...": "..." },
  "summary": {
    "total": 0,
    "pass": 0,
    "fail": 0,
    "skip": 0,
    "error": 0,
    "pass_rate_pct": 0.0,
    "duration_ms": 0
  },
  "cases": [ /* 每个用例一条记录 */ ],
  "fmea_trace": { /* FMEA 关联统计 */ }
}
```

**SHALL** — 每一条 `cases[]` 记录 SHALL 包含 FI-11 和 FI-12 定义的所有字段。

**SHALL** — FMEA 追溯统计（`fmea_trace`）SHALL 按 FMEA 条目 ID 聚合：每个 FMEA 条目关联的用例数及各自的结果分布。

**SHOULD** — 系统 SHOULD 输出一份人类可读的 Markdown 摘要报告（与 JSON 报告同级）。

---

#### FI-14: FMEA 条目追溯

**SHALL** — 测试用例的 `fmea_refs` 字段 SHALL 为可选的字符串数组，引用知识管理模块中已注册的 FMEA 条目 ID。

**SHALL** — 当 `fmea_refs` 中引用了不存在的 FMEA 条目时，系统 SHALL 在 schema 校验阶段报错（阻断加载）。

**SHALL** — 当用例结果进入 evidence 模块时，evidence 模块 SHALL 将结果写回关联的 FMEA 条目，更新其 `current_control` 有效性判定（通过 FMEA-08 约定的接口）。

**SHOULD** — 系统 SHOULD 在 JSON 报告中包含 `fmea_trace` 节，展示每个 FMEA 条目的故障注入覆盖情况。

**SHOULD** — 系统 SHOULD 提供查询接口：给定 FMEA 条目 ID，返回所有关联的 fault injection 用例及其历史执行结果。

---

#### FI-15: 汇总统计

**SHALL** — 系统 SHALL 在每个 suite 或阶段结束时生成汇总统计，包含：
- `total` (整数, 总用例数, = pass + fail + skip + error)
- `pass` (整数)
- `fail` (整数)
- `skip` (整数)
- `error` (整数)
- `pass_rate_pct` (浮点, 精确到小数点后两位, `= pass / (pass + fail) * 100`, 不包含 skip 和 error)
- `duration_ms` (整数, 阶段总耗时)

**SHALL** — 汇总统计 SHALL 同时出现在 JSON 报告和 evidence 模块的阶段级记录中。

**SHALL** — 当 `total` 为 0 时，`pass_rate_pct` SHALL 报告为 `N/A`（而非除零错误）。

**SHOULD** — 当有多套用例集时，系统 SHOULD 提供"全局汇总"（所有 suite 的合计数）和"按 suite 分解"两种视图。

---

### 3.4 通信层抽象 (FI-16~FI-20)

---

#### FI-16: 通信适配器插件化

**SHALL** — 通信层 SHALL 采用适配器模式（Adapter Pattern），每种注入目标对应一个适配器实现。

**SHALL** — 系统 SHALL 内置以下适配器（覆盖 FI-02 定义的四类目标）：

| 目标类型 | 内置适配器 |
|---------|-----------|
| CAN | `socketcan`, `vector`, `dolp` |
| Ethernet | `doip` (UDS on IP), `someip` (预留) |
| JTAG | `jlink`, `stlink`, `openocd`, `pyocd` |
| Simulator | `qemu`, `unicorn`, `renode` |

**SHALL** — 每个适配器 SHALL 实现以下接口（以伪代码表述）：
```go
type FaultInjector interface {
    Connect(ctx context.Context, config TargetConfig) error
    Inject(ctx context.Context, spec InjectSpec) (*InjectResult, error)
    WaitForReset(ctx context.Context, timeout time.Duration) error
    Verify(ctx context.Context, spec VerifySpec) (*VerifyResult, error)
    Disconnect(ctx context.Context) error
}
```

**SHALL NOT** — 适配器的实现 SHALL NOT 硬编码任何业务逻辑（如注入策略、验证逻辑）。

**MAY** — 系统 MAY 支持自定义适配器的热加载（通过外部插件接口）。

---

#### FI-17: 连接生命周期管理

**SHALL** — 每个测试用例的执行 SHALL 严格遵循以下生命周期：
```
Connect → Inject → WaitForReset → Verify → Disconnect
```

**SHALL** — `Connect` SHALL 在阶段开始时建立连接，`Disconnect` SHALL 在阶段结束时释放连接。每个 suite 内建一次连接，不反复连接/断开（除非连接丢失）。

**SHALL** — `WaitForReset` 步骤 SHALL 执行以下子步骤：
1. 等待目标 ECU 复位（通过 JTAG 检测或通信超时感知）
2. 轮询检测目标上线（如 CAN TesterPresent, DoIP 路由激活）
3. 可选检测上线后延迟（`post_reset_delay_ms`, 默认 500ms）

**SHALL** — 当 `WaitForReset` 在超时内检测到目标重新上线时，SHALL 进入 `Verify` 步骤。

**SHALL** — 当 `WaitForReset` 超时仍未检测到目标上线时，SHALL 将该用例标记为 `error`（类型：`timeout`）。

**SHALL** — 阶段结束时 SHALL 执行 `Disconnect` 释放资源。如果阶段因阻断而提前终止，SHALL 同样执行 `Disconnect`。

---

#### FI-18: 超时保护机制

**SHALL** — 系统 SHALL 为每个测试用例提供独立超时保护。

**SHALL** — 用例超时计算方式：`case_timeout_ms = inject_timeout_ms + reset_wait_timeout_ms + verify_timeout_ms + cooldown_ms`。

**SHALL** — 每种超时的默认值：
- `inject_timeout_ms` — 5000 (5s)
- `reset_wait_timeout_ms` — 15000 (15s)
- `verify_timeout_ms` — 5000 (5s)

**SHALL** — 用户 SHALL 可通过配置覆盖上述默认超时值。

**SHALL** — 当用例执行超过 `case_timeout_ms` 时，系统 SHALL ：
1. 终止当前用例
2. 将该用例标记为 `error`（类型：`timeout`）
3. 如果连接未丢失，继续下一用例；否则尝试重连（根据 retry_count 配置）

**SHALL NOT** — 超时 SHALL NOT 导致系统整体崩溃或阶段挂起。

---

#### FI-19: 错误重试策略

**SHALL** — 系统 SHALL 支持对 `error` 结果（通信失败、超时、magic 校验失败）的重试。

**SHALL** — 重试行为由 `retry_policy` 配置控制，默认值：
- `max_retries` (整数, 默认 3)
- `retry_delay_ms` (整数, 默认 2000)
- `backoff_factor` (浮点, 默认 1.5, 指每次重试间隔乘以该因子)

**SHALL** — 重试 SHALL 完整执行 Connect → Inject → WaitForReset → Verify 流程（不单独重试某一步）。

**SHALL** — 重试消耗的用例超时 SHALL 独立于主超时之外计算（即重试不计入 `block_threshold` 的 `error` 计数，除非最终结果仍为 error）。

**SHALL NOT** — `fail` 结果（注入成功但验证未通过）SHALL NOT 触发重试。

**SHOULD** — 系统 SHOULD 在日志中记录每次重试的序号和原因。

---

#### FI-20: 多目标并发支持

**SHOULD** — 系统 SHOULD 支持同时管理多个注入目标（多 ECU 或多节点并发测试）。

**SHOULD** — 多并发模式下，每个目标 SHALL 有独立的连接生命周期和超时计数器。

**SHOULD** — 多并发模式 SHALL 由 `fi.config.max_concurrent_targets` 配置控制（整数, 默认 1, 即串行执行）。

**SHALL** — 当 `max_concurrent_targets > 1` 时，系统 SHALL 为每个目标建立独立的通信适配器实例。

**SHALL** — 汇总统计 SHALL 在所有并发目标完成后合并计算。

**SHALL NOT** — 并发 SHALL NOT 产生混淆的报告（每个用例的记录 SHALL 明确标识其执行目标）。

**MAY** — 系统 MAY 支持用例级别的目标映射，即不同用例可指定不同的注入目标（用于跨 ECU 场景测试）。

---

### 3.5 任务级注入 (FI-21~FI-31)

> **层级标识**: Layer 2 — 任务级模拟故障注入
> **注入通道**: FreeRTOS Task Notification（或等价的轻量级 IPC）
> **UDS DID**: 0xF193（写入注入指令），0xF192（读取注入结果）
> **编译开关**: `A66T_TASK_FAULT_INJECT_ENABLE`
> **不触发复位**: 区别于 Layer 1 的系统级复位注入

---

#### FI-21: 任务注册

**SHALL** — 每个支持故障注入的任务 SHALL 通过 `TaskFault_RegisterTask()` 函数注册到故障注入框架。

**SHALL** — `TaskFault_RegisterTask()` SHALL 接收以下参数：
- `task_handle` (FreeRTOS TaskHandle_t) — 目标任务句柄
- `task_name` (字符串) — 人类可读的任务名称（用于日志和报告）

**SHALL** — 同一任务句柄 SHALL NOT 被重复注册，重复注册 SHALL 返回错误码（如 `TASK_FAULT_ERR_ALREADY_REGISTERED`）。

**SHOULD** — 已注册任务的信息（句柄 + 名称）SHOULD 可枚举，支持按任务名查询和注入。

---

#### FI-22: 循环检查

**SHALL** — 每个已注册的任务 SHALL 在其主循环开头调用 `TASK_FAULT_CHECK()` 宏。

**SHALL** — `TASK_FAULT_CHECK()` SHALL 执行以下行为：
1. 读取 FreeRTOS Task Notification 值（通过 `xTaskNotifyWait()` 或等价 API）
2. 如果通知值非零，将其解析为注入故障类型，并设置对应的内部故障标志
3. 复位通知值为 0，准备下一轮注入

**SHALL** — `TASK_FAULT_CHECK()` SHALL 是非阻塞调用：没有挂起的通知时，SHALL 立即返回，不引入调度延迟。

**SHALL** — `TASK_FAULT_CHECK()` 在生产配置（`STD_OFF`）下 SHALL 展开为空（no-op），不产生任何运行时开销。

---

#### FI-23: 循环结束检查

**SHALL** — 每个已注册的任务 SHALL 在其主循环末尾调用 `TASK_FAULT_END_CHECK()` 宏。

**SHALL** — `TASK_FAULT_END_CHECK()` SHALL 执行以下行为：
1. 检查本轮循环中是否存在未处理的激活故障（即设置了故障标志但未调用 `TASK_FAULT_REPORT()`）
2. 如果存在未处理的故障，自动将本轮结果记录为 `FAILED`
3. 清理故障标志，进入正常循环

**SHALL** — `TASK_FAULT_END_CHECK()` 在生产配置（`STD_OFF`）下 SHALL 展开为空（no-op）。

---

#### FI-24: 错误路径报告

**SHALL** — 当已注册任务检测到注入的故障条件并成功执行了对应的错误处理路径后，SHALL 调用 `TASK_FAULT_REPORT(result)` 宏。

**SHALL** — `TASK_FAULT_REPORT()` SHALL 接收一个枚举参数：
- `TASK_FAULT_RESULT_PASSED` — 错误路径正确执行，故障被优雅处理
- `TASK_FAULT_RESULT_FAILED` — 错误路径进入但处理结果不达标（预留）

**SHALL** — `TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED)` SHALL 将当前故障标志结果存入环形缓冲区，标记为 `PASSED`。

**SHALL** — `TASK_FAULT_REPORT()` 在生产配置（`STD_OFF`）下 SHALL 展开为空（no-op）。

---

#### FI-25: 注入通道

**SHALL** — 任务级注入 SHALL 使用 FreeRTOS Task Notification（或等价的轻量级 IPC）作为注入通道。

**SHALL** — 注入过程 SHALL 包含以下步骤：
1. 外部触发方（UDS Handler / Pipeline Runner）调用 `TaskFault_Inject(task, faultType)`
2. `TaskFault_Inject()` SHALL 通过 `xTaskNotify()` 向目标任务发送 32-bit 通知值
3. 目标任务在其下一个主循环 `TASK_FAULT_CHECK()` 中接收通知
4. 通知值被解析为故障类型

**SHALL** — 注入通道 SHALL 是单向的（外部→任务），工作任务 SHALL NOT 通过通知通道直接回复。

**SHALL** — 注入通道 SHALL 引入零调度锁定：不使用全局锁、不关闭调度器、不抢占临界区。

**SHALL** — UDS 通道 `0xF193` SHALL 通过 Yaml 配置映射到任务级注入，格式同 FI-02 的 `did_write` 方法，但 DID 值改为 `F193`。

---

#### FI-26: 注入方式

**SHALL** — 任务级注入 SHALL 支持两种注入方式：

1. **模拟注入（默认）** — 不改变真实硬件或资源状态，仅通过软件标志模拟故障条件
   - 支持类型见 FI-27
   - 安全、快速、可预测

2. **真实资源消耗注入（可选）** — 真正消耗系统资源以触发边界条件
   - 如栈耗尽（`REAL_STACK_DEPLETE`）
   - **默认关闭**，需显式开关启用
   - 可能引发真实 CPU 异常，需配合 Layer 1 的保护机制

**SHOULD** — 真实资源消耗注入 SHOULD 由独立的编译开关或运行时开关控制，不得在常规测试中意外启用。

**SHALL NOT** — 模拟注入 SHALL NOT 引起系统复位、CPU 异常或数据损坏。

---

#### FI-27: 模拟故障类型

**SHALL** — 系统 SHALL 支持至少 4 种模拟故障类型：

| ID | 类型名 | 模拟场景 |
|:--:|:-------|:---------|
| 0x01 | `SIM_NULL_HANDLE` | 关键句柄或指针强制设为 NULL |
| 0x02 | `SIM_INVALID_PARAM` | 参数越界/无效值传入 |
| 0x03 | `SIM_TIMEOUT` | 等待或轮询超时模拟 |
| 0x04 | `SIM_QUEUE_FULL` | 消息队列或资源池满

**SHOULD** — 系统 SHOULD 额外支持以下模拟故障类型（扩展能力）：

| ID | 类型名 | 模拟场景 |
|:--:|:-------|:---------|
| 0x05 | `SIM_BUFFER_OVF` | 缓冲区溢出模拟 |
| 0x06 | `SIM_RESOURCE_LOST` | 外设或资源丢失模拟 |
| 0x07 | `SIM_STATE_CORRUPT` | 状态机状态损坏模拟 |

**SHALL** — 每个模拟故障类型的 ID SHALL 是唯一的 8-bit 枚举值。

**SHALL** — 每个模拟故障类型 SHALL 有对应的独立编译开关（`TASK_FAULT_SIM_NULL_HANDLE_ENABLE` 等），允许按需裁剪。

---

#### FI-28: 结果存储

**SHALL** — 注入结果 SHALL 存储在环形缓冲区（Ring Buffer）中。

**SHALL** — 环形缓冲区 SHALL 至少支持 16 条记录（可配置）。

**SHALL** — 每条结果记录 SHALL 包含以下字段：
- `timestamp` (时间戳, ticks 或 wall clock)
- `task_handle` (TaskHandle_t, 产生结果的任务)
- `fault_type` (整数, 注入的故障类型 ID)
- `result` (枚举: `PASSED`/`FAILED`/`TIMEOUT`)
- `injection_id` (整数, 本次注入的序列号)

**SHALL** — 当环形缓冲区满时，新记录 SHALL 覆盖最旧的记录（FIFO 覆盖）。

**SHALL** — 外部读取方（UDS Handler / Pipeline Runner）SHALL 通过以下方式读取结果：
- 调用 `TaskFault_GetResult(index)` 按索引获取单条记录
- 调用 `TaskFault_GetResultCount()` 获取有效记录数
- 调用 `TaskFault_ClearResults()` 清空缓冲区

---

#### FI-29: 注入超时

**SHALL** — 每次任务级注入 SHALL 有超时机制。

**SHALL** — 默认超时值 SHALL 为 5000 ms（5 秒）。

**SHALL** — 超时计时 SHALL 从 `TaskFault_Inject()` 被调用时开始。

**SHALL** — 当超时到期而目标任务尚未通过 `TASK_FAULT_REPORT()` 上报结果时，系统 SHALL 自动将本次注入记录为 `TIMEOUT` 并写入环形缓冲区。

**SHALL** — 用户 SHALL 可通过配置覆盖默认超时值（`task_inject_timeout_ms`）。

**SHALL NOT** — 超时 SHALL NOT 导致任务本身被挂起或终止。

---

#### FI-30: 项目级逐个任务优先级排序

**SHOULD** — 系统 SHOULD 支持按任务优先级排序执行注入，优先对高风险任务执行故障注入。

**SHOULD** — 任务优先级排序 SHOULD 通过配置声明，用户 SHALL 在用例集 YAML 中指定目标任务优先级顺序：

```yaml
cases:
  - case_id: "FI-TASK-DKI-001"
    description: "DKI 任务 NULL 句柄注入"
    inject_spec:
      method: did_write
      did: "F193"
      data: "0100"  # faultType=0x01, taskIndex=0 (DKI=最高优先级)
    verify_spec:
      - type: task_result
        expected_result: "PASSED"
```

**SHOULD** — 系统 SHOULD 默认按以下优先级顺序执行（参考 AUTOSAR 优先级映射）：
1. DKI（动态核初始化）
2. Vehicle（车辆控制）
3. SE（安全执行环境）
4. EthDrv（以太网驱动）
5. RteHigh/CanDrv/定时器任务 / ...

**MAY** — 系统 MAY 通过知识模块的 FMEA 条目 `ap_priority` 自动推算任务优先级顺序。

---

#### FI-31: 与 Layer 1 的关系

**SHALL NOT** — 任务级注入 SHALL NOT 触发系统复位或 CPU 异常。

**SHALL** — 任务级注入和系统级注入 SHALL 互不干扰：
- 不同的 UDS DID（Layer 1: 0xF190/F191，Layer 2: 0xF192/F193）
- 独立的编译开关（`A66T_FAULT_INJECTION_TEST_ENABLE` vs `A66T_TASK_FAULT_INJECT_ENABLE`）
- 独立的结果存储（Layer 1: NoInit SRAM，Layer 2: 环形缓冲区）
- 独立的生命周期（Layer 1: 注入→复位→验证，Layer 2: 注入→通知→报告）

**SHALL** — 系统 SHALL 支持在同一个 Pipeline 执行中先后运行 Layer 1 和 Layer 2 的测试用例集，执行顺序由用例集配置决定。

**SHALL** — JSON 报告（FI-13）SHALL 为每条用例记录 `layer` 字段（枚举：`"system"` / `"task"`），以区分注入层级。

---

## 4. 系统架构

### 4.1 模块层级

```
┌──────────────────────────────────────────────┐
│                yuleosh CLI                     │
│  ┌──────────────────────────────────────────┐ │
│  │              ci.fi 子命令                  │ │
│  └──────────────────────────────────────────┘ │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│           Fault Injection Engine              │
│  ┌─────────┐  ┌─────────┐  ┌──────────────┐ │
│  │ Loader   │  │ Runner  │  │ Reporter      │ │
│  │ (YAML)   │→ │ (引擎)  │→ │ (JSON+Evid)  │ │
│  └─────────┘  └────┬────┘  └──────────────┘ │
└────────────────────┼─────────────────────────┘
                     │
┌────────────────────▼─────────────────────────┐
│         Communication Adapter Layer           │
│  ┌──────┐ ┌────────┐ ┌──────┐ ┌──────────┐ │
│  │ CAN  │ │Ethernet│ │ JTAG │ │Simulator │ │
│  │ UDS  │ │ DoIP   │ │SWD   │ │QEMU/etc  │ │
│  └──────┘ └────────┘ └──────┘ └──────────┘ │
└──────────────────────────────────────────────┘
                     │
                     ▼
              [ Target System ]
```

### 4.2 YAML 配置参考

#### Pipeline 配置 (`yuleosh-pipeline.yaml`)

```yaml
stages:
  fault_injection:
    enabled: true
    order: 3  # 可选，默认在 unit_test 之后
    config:
      test_suites:
        - fault_injection/cases/hardfault_suite.yaml
        - fault_injection/cases/memory_suite.yaml
      block_threshold:
        fail: 2
        error: 5
      max_concurrent_targets: 1
```

#### 测试用例集定义 (`fault_injection/cases/hardfault_suite.yaml`)

```yaml
suite_name: "ARM-Cortex-M4F-HardFault-Suite"
description: "ARM Cortex-M4F 内核异常注入 — 对标 A66-T 九种注入类型"
fi_version: "1.0"
target: "can_uds"  # 引用 pipeline config 中的 injection_target

cases:
  - case_id: "FI-NULLPTR-001"
    description: "空指针解引用 → BusFault"
    inject_spec:
      method: did_write
      did: "F190"
      data: "01"  # testId = 1
    verify_spec:
      - type: fault_type
        expected_types: [1, 3]
      - type: register_mask
        register: CFSR
        expected_mask: "0x00000600"
    skip_condition: null
    cooldown_ms: 3000
    fmea_refs: ["FMEA-2026-0012"]

  - case_id: "FI-DIVBYZERO-001"
    description: "除零 → UsageFault(DIVBYZERO)"
    inject_spec:
      method: did_write
      did: "F190"
      data: "03"
    verify_spec:
      - type: fault_type
        expected_types: [1, 4]
      - type: register_mask
        register: CFSR
        expected_mask: "0x02000000"
    cooldown_ms: 3000

  - case_id: "FI-MPU-001"
    description: "MPU 违规 → MemManage"
    inject_spec:
      method: did_write
      did: "F190"
      data: "06"
    verify_spec:
      - type: fault_type
        expected_types: [2]
      - type: register_mask
        register: CFSR
        expected_mask: "0x00000003"
    skip_condition:
      type: target_property
      property: mpu_enabled
      expected: false
    cooldown_ms: 3000
    fmea_refs: ["FMEA-2026-0015"]
    knowledge_refs: ["KB-2026-0042"]

  - case_id: "FI-SCB-DIRECT-001"
    description: "直接触发 SCB → HardFault"
    inject_spec:
      method: register_tamper
      register: SCB_SystemControl
      value: "0x00000001"
    verify_spec:
      - type: fault_type
        expected_types: [1]
    cooldown_ms: 3000
```

---

## 5. 实现指引（可变）

以下为开发团队的推荐实施策略，**非契约约束**。

### 5.1 模块划分（建议）

```
yuleosh/fault_injection/
├── engine/
│   ├── loader.py         # YAML 用例集加载 + schema 校验
│   ├── runner.py         # 用例执行引擎（生命周期管理）
│   ├── reporter.py       # JSON/Markdown 报告生成
│   └── retry.py          # 重试策略
├── adapters/
│   ├── base.py           # FaultInjector 接口定义
│   ├── can/
│   │   ├── socketcan.py  # Linux SocketCAN 适配器
│   │   ├── vector.py     # Vector CAN 适配器
│   │   └── dolp.py       # DOLP (Device On Linux PEAK) 适配器
│   ├── ethernet/
│   │   └── doip.py       # DoIP (ISO 13400) 适配器
│   ├── jtag/
│   │   ├── jlink.py      # SEGGER J-Link 适配器
│   │   ├── openocd.py    # OpenOCD 适配器
│   │   └── pyocd.py      # pyOCD 适配器
│   └── simulator/
│       ├── qemu.py       # QEMU GDB stub 适配器
│       └── unicorn.py    # Unicorn 引擎适配器
├── ci/
│   └── fi_cmd.py         # `yuleosh ci fi` 子命令入口
├── models/
│   ├── case.py           # 测试用例数据模型
│   ├── result.py         # 结果数据模型
│   └── target.py         # 目标配置数据模型
└── schemas/
    ├── suite_schema.json     # 用例集 YAML schema
    └── pipeline_config.json  # Pipeline 配置 schema
```

### 5.2 实施优先级（建议）

| 优先级 | 模块 | 说明 |
|-------|------|------|
| P0 | YAML 加载 + schema 校验 | 基础不可减 |
| P0 | Runner 引擎 + 生命周期管理 | 核心执行 |
| P0 | CAN/UDS (socketcan) 适配器 | A66-T 兼容 |
| P0 | JSON 报告 + evidence 集成 | 输出可达 |
| P1 | JTAG/SWD (pyOCD) 适配器 | 多 MCU 兼容 |
| P1 | 阻断阈值 + 重试策略 | 稳定性 |
| P1 | 超时保护 | 防挂死 |
| P2 | Ethernet/DoIP 适配器 | 以太网场景 |
| P2 | Simulator (QEMU) 适配器 | SIL 场景 |
| P2 | FMEA 追溯集成 | 闭环关键 |
| P1 | UDS F193 TaskFault 适配器 | DID 0xF193 任务级注入 |
| P1 | TaskFaultInject.h 移植 | 宏+TASK_FAULT_CHECK/END_CHECK/REPORT |
| P1 | FreeRTOS Notification 注入通道 | 轻量级 IPC 实现 |
| P1 | 环形缓冲区结果存储 | ≥ 16 条，FIFO 覆盖 |
| P2 | 任务优先级排序 | 高风险任务优先注入 |
| P2 | 真实资源消耗注入开关 | 默认 OFF，栈耗尽等 |
| P3 | 多目标并发 | 跨 ECU 场景 |
| P3 | 自动用例生成 (from FMEA) | 提效 |
| P4 | 自定义适配器热加载 | 扩展性 |

### 5.3 A66-T 兼容性对照表

| A66-T 特性 | yuleOSH FI 对应 | 状态 |
|------------|----------------|------|
| UDS $2E/$22 DID F190/F191 | CAN/UDS 适配器 did_write | 内置 |
| 复位后 TesterPresent 轮询 | WaitForReset 步骤 | 内置 |
| Magic 0xFA017FA0 校验 | verify_spec 隐式前置条件 | 内置 |
| faultType + CFSR 掩码验证 | register_mask + fault_type 验证 | 内置 |
| 9 种注入类型（TestID 1–9） | 用例集定义 | P0 |
| 3s Cooldown | cooldown_ms 默认 3000 | 内置 |
| SocketCAN / Vector | can 适配器双实现 | 内置 |
| JSON 报告 | JSON Reporter | 内置 |
| SKIP（MPU 未启用） | skip_condition | 内置 |
| FreeRTOS Task Notification 注入 | 任务级注入适配器 (UDS F193) | P1 |
| TASK_FAULT_CHECK/END_CHECK/REPORT 宏 | C 头文件嵌入（TaskFaultInject.h 移植） | P1 |
| 环形缓冲区 16 条记录 | RingBuffer 结果存储 | P1 |
| 7 种模拟故障 | 用例集定义 | P1 |

### 5.4 数据存储建议

- **JSON 报告**: 存储于 `reports/fault_injection/` 目录，按时间戳命名，纳入 Git 管理
- **evidence 记录**: 通过 evidence 模块持久化到 PostgreSQL（与知识管理共享同一实例）
- **适配器配置**: YAML 配置方式，无需独立数据库存储

---

> **变更记录**
> | 版本 | 日期 | 变更内容 | 作者 |
> |------|------|---------|------|
> | v1.0.0 | 2026-06-20 | 初始正式规约 | 小马 🐴 |
> | v1.1.0 | 2026-06-20 | 追加 Layer 2 任务级注入 §3.5 (FI-21~31) | 小马 🐴 |

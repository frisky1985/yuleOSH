# yuleOSH Fault Injection Pipeline — 验收判定矩阵

> **版本**: v1.0.0
> **状态**: 草案
> **作者**: 小马 🐴 (质量架构师)
> **关联 Spec**: spec-fault-injection.md v1.0.0
> **格式**: ACC (Acceptance Criteria), 每条 SHALL 配 GIVEN/WHEN/THEN

---

## 使用说明

- **ACC-ID**: `FI-ACC-<序号>`，与 Spec FI-<编号> 对应
- **规范等级**: SHALL → ACC 必须验证；SHOULD → ACC 应验证但可豁免
- **覆盖判定**: ✅=全覆盖, ◐=部分覆盖, ❌=未覆盖
- **测试策略**: `unit`=单元测试, `integ`=集成测试, `e2e`=端到端, `review`=代码审查

---

## 3.1 Pipeline 集成

### FI-ACC-01: Pipeline 阶段定义（FI-01 SHALL x3）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | `fault_injection` 阶段存在且命名为 `stage.fault_injection` | ✅ |
| 2 | 阶段钩子 `pre_run`/`run`/`post_run`/`on_failure` 可用 | ✅ |
| 3 | 未配置时默认跳过 | ✅ |

**ACC-01-1: 阶段定义可用**
- **GIVEN** 一个 yuleOSH pipeline 实例
- **WHEN** 查询已注册的阶段列表
- **THEN** `stage.fault_injection` SHALL 存在于列表中

**ACC-01-2: 阶段生命周期钩子**
- **GIVEN** `fault_injection` 阶段已注册
- **WHEN** 执行该阶段
- **THEN** `pre_run` SHALL 在用例执行前触发，`run` SHALL 执行用例，`post_run` SHALL 在用例执行后触发，`on_failure` SHALL 在发生阻断性错误时触发

**ACC-01-3: 默认跳过行为**
- **GIVEN** pipeline 配置中未包含 `fault_injection` 阶段定义
- **WHEN** 执行 pipeline
- **THEN** `fault_injection` 阶段SHALL 被跳过，SHALL NOT 影响其他阶段

---

### FI-ACC-02: 注入目标配置（FI-02 SHALL x6, MAY x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 注入目标枚举 `can`/`ethernet`/`jtag`/`simulator` | ✅ |
| 2 | 公共连接字段 `type`/`timeout_ms`/`retry_count` | ✅ |
| 3 | CAN 额外字段 `interface`/`channel`/`bitrate`/`uds_id` 可选 | ✅ |
| 4 | Ethernet 额外字段 `interface`/`ip_address`/`port` 可选 | ✅ |
| 5 | JTAG 额外字段 `adapter`/`target_chip`/`interface_speed_khz`/`debug_port` | ✅ |
| 6 | Simulator 额外字段 `engine`/`machine_model`/`binary_path` | ✅ |
| 7 | 混合目标配置 | ◐ |

**ACC-02-1: 目标类型枚举**
- **GIVEN** 一个 `injection_target` YAML 配置
- **WHEN** 其 `type` 字段值为 `can`/`ethernet`/`jtag`/`simulator`
- **THEN** schema 校验 SHALL 通过

**ACC-02-2: 非法目标类型拒绝**
- **GIVEN** 一个 `injection_target` YAML 配置
- **WHEN** 其 `type` 字段值为非法值（如 `serial`、`bluetooth`）
- **THEN** schema 校验 SHALL 失败并返回明确的错误消息

**ACC-02-3: CAN 配置有效性**
- **GIVEN** `injection_target.type = "can"`
- **WHEN** 加载配置
- **THEN** `interface` SHALL 为 `socketcan`/`vector`/`dolp` 之一；`uds_id.req_id` 和 `uds_id.res_id` SHALL 为可选

**ACC-02-4: JTAG 配置有效性**
- **GIVEN** `injection_target.type = "jtag"`
- **WHEN** 加载配置
- **THEN** `adapter` SHALL 为 `jlink`/`stlink`/`openocd`/`pyocd` 之一；`debug_port` SHALL 为 `swd`/`jtag`

**ACC-02-5: 配置缺省字段**
- **GIVEN** `injection_target` 未指定 `timeout_ms` 和 `retry_count`
- **WHEN** 加载配置
- **THEN** `timeout_ms` SHALL 默认 30000，`retry_count` SHALL 默认 3

---

### FI-ACC-03: 测试用例集配置（FI-03 SHALL x4 + FI-02 SHALL x2）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | YAML 用例集定义，默认路径 `fault_injection/cases/` | ✅ |
| 2 | 通过 `fi.config.test_suites` 引用用例集 | ✅ |
| 3 | YAML schema 校验，失败时输出详细错误 | ✅ |
| 4 | 用例集包含 `suite_name`/`description`/`fi_version`/`target`/`cases` | ✅ |
| 5 | `target` 引用 pipeline 配置中定义的 target_name | ✅ |
| 6 | 完整的连接参数仅在 pipeline 配置中定义一次 | ✅ |

**ACC-03-1: 用例集加载**
- **GIVEN** 路径 `fault_injection/cases/hardfault_suite.yaml` 存在的有效用例集 YAML
- **WHEN** 通过 `fi.config.test_suites` 加载
- **THEN** 系统 SHALL 成功加载并解析所有用例

**ACC-03-2: Schema 校验失败**
- **GIVEN** 一个格式错误的用例集 YAML（缺少 `case_id` 或 `inject_spec` 字段）
- **WHEN** 加载该 YAML
- **THEN** 系统 SHALL 输出详细错误报告，包含文件名、行号和字段信息

**ACC-03-3: 元数据完整性**
- **GIVEN** 一个加载成功的用例集
- **WHEN** 检查其内容
- **THEN** `suite_name`、`fi_version`、`target`、`cases` SHALL 均存在且非空

**ACC-03-4: target 名称引用**
- **GIVEN** 用例集 YAML 中 `target: "can_uds"`
- **WHEN** 加载阶段
- **THEN** 系统 SHALL 在 pipeline 配置中查找名为 `can_uds` 的注入目标定义（含完整连接参数），若找不到则 schema 校验失败并报错

---

### FI-ACC-04: 阶段结果进入 evidence 模块（FI-04 SHALL x3）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 执行结果写入 evidence 模块 | ✅ |
| 2 | 每条用例一条证据记录，含 source/suite/case/result/summary 等 | ✅ |
| 3 | 关联 FMEA 的 fail 用例通知负责人 | ✅ |

**ACC-04-1: 证据记录生成**
- **GIVEN** `fault_injection` 阶段完成执行
- **WHEN** 查询 evidence 模块中 source=`fault_injection` 的记录
- **THEN** 总记录数 SHALL 等于 `pass + fail + skip + error` 计数

**ACC-04-2: 证据记录字段**
- **GIVEN** 一条 evidence 记录（source=`fault_injection`）
- **WHEN** 检查其字段
- **THEN** `source`、`suite_name`、`case_id`、`result`、`executed_at`、`duration_ms` SHALL 均存在

**ACC-04-3: FMEA 关联通知**
- **GIVEN** 一条测试用例关联了 `fmea_refs: ["FMEA-2026-0012"]`
- **WHEN** 该用例结果为 `fail`
- **THEN** 系统 SHALL 自动通知 FMEA-2026-0012 的负责人

---

### FI-ACC-05: 阻断阈值（FI-05 SHALL x3, SHALL NOT x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 可通过 `block_threshold` 配置 fail/error 阈值 | ✅ |
| 2 | 达到阈值时阶段状态设为 `blocked` 并终止执行 | ✅ |
| 3 | 默认阈值为 FAIL > 0 即阻断 | ✅ |
| 4 | 阻断不影响其他已完成阶段 | ✅ |

**ACC-05-1: 阈值配置生效**
- **GIVEN** `block_threshold: { fail: 3, error: 5 }`
- **WHEN** 连续 3 条用例结果为 `fail`
- **THEN** 阶段状态 SHALL 变为 `blocked`，后续用例 SHALL NOT 执行

**ACC-05-2: 默认阻断行为**
- **GIVEN** 未配置 `block_threshold`
- **WHEN** 任一条用例结果为 `fail`
- **THEN** 阶段状态 SHALL 变为 `blocked`

**ACC-05-3: 不影响其他阶段**
- **GIVEN** `fault_injection` 阶段被阻断
- **WHEN** 检查其他已完成阶段
- **THEN** 其他阶段的结果 SHALL NOT 被此阻断影响

---

## 3.2 测试用例定义

### FI-ACC-06: 注入 + 验证 双规定义（FI-06 SHALL x2, SHALL NOT x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 用例包含 `inject_spec` 和 `verify_spec` | ✅ |
| 2 | 用例字段完整性 | ✅ |
| 3 | 不修改被测目标固件 | ✅ |

**ACC-06-1: 双规范存在**
- **GIVEN** 一个已加载的测试用例
- **WHEN** 检查其键
- **THEN** `inject_spec` 和 `verify_spec` SHALL 同时存在

**ACC-06-2: 字段完整性**
- **GIVEN** 一个已加载的测试用例
- **WHEN** 检查其字段
- **THEN** `case_id` SHALL 为字符串且非空，`description` SHALL 为字符串

**ACC-06-3: 无固件修改**
- **GIVEN** 任何测试用例的执行
- **WHEN** 执行注入流程
- **THEN** 系统 SHALL NOT 修改被测目标的固件二进制或代码段

---

### FI-ACC-07: 注入方式（FI-07 SHALL x3, MAY x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | `did_write` 注入支持 DID + data | ✅ |
| 2 | `register_tamper` 注入支持 register + mask + value | ✅ |
| 3 | `memory_overwrite` 注入支持 address + value + size | ✅ |
| 4 | `stack_overflow` 注入支持 target_function + overflow_bytes | ✅ |
| 5 | 十六进制值统一大小写 | ✅ |
| 6 | pre/post inject delay | ✅ |

**ACC-07-1: did_write 注入**
- **GIVEN** `inject_spec.method = "did_write"`，`did: "F190"`，`data: "01"`
- **WHEN** 执行注入
- **THEN** 系统 SHALL 通过当前通信适配器写入 DID 0xF190 携带数据 0x01

**ACC-07-2: register_tamper 注入**
- **GIVEN** `inject_spec.method = "register_tamper"`，`register: "CFSR"`，`mask: "0x00000600"`，`value: "0x00000600"`
- **WHEN** 执行注入（通过 JTAG/Simulator）
- **THEN** 系统 SHALL 写入目标 CPU 的 CFSR 寄存器

**ACC-07-3: 不支持的方法**
- **GIVEN** `inject_spec.method` 值为未定义方法（如 `"pulse_voltage"`）
- **WHEN** 加载用例
- **THEN** schema 校验 SHALL 失败并指出非法 method

**ACC-07-4: 十六进制统一格式**
- **GIVEN** 配置文件中十六进制值为小写（如 `"0xff"`）
- **WHEN** 执行日志和报告输出
- **THEN** 输出 SHALL 统一使用大写十六进制（如 `0xFF`）

---

### FI-ACC-08: 验证方式（FI-08 SHALL x4）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | fault_type 验证 | ✅ |
| 2 | register_mask 验证 | ✅ |
| 3 | behavior 验证 | ✅ |
| 4 | magic 完整性校验 | ✅ |
| 5 | magic 校验失败标记 error（非 fail） | ✅ |

**ACC-08-1: fault_type 验证通过**
- **GIVEN** 故障记录中 `faultType = 1`
- **WHEN** `verify_spec.expected_types = [1, 3]`
- **THEN** 验证 SHALL 通过（1 ∈ [1,3]）

**ACC-08-2: register_mask 验证通过**
- **GIVEN** 故障记录中 `CFSR = 0x00000600`，`expected_mask = 0x00000600`
- **WHEN** 执行 register_mask 校验（operator = and_nonzero）
- **THEN** `0x00000600 & 0x00000600 = 0x00000600 != 0` → 验证 SHALL 通过

**ACC-08-3: register_mask 验证失败**
- **GIVEN** 故障记录中 `CFSR = 0x00000000`，`expected_mask = 0x00000600`
- **WHEN** 执行 register_mask 校验
- **THEN** `0x00000000 & 0x00000600 = 0` → 验证 SHALL 不通过，结果记录为 `fail`

**ACC-08-4: magic 校验失败 → error**
- **GIVEN** 故障记录中 `magic != 0xFA017FA0`
- **WHEN** 验证阶段
- **THEN** 用例结果 SHALL 记录为 `error`（类型：`magic_mismatch`），而非 `fail`

**ACC-08-5: behavior 验证**
- **GIVEN** `verify_spec.observations = ["ecu_reset", "safe_state_enter"]`，`operator = all`
- **WHEN** 目标系统仅触发了 `ecu_reset` 但未进入 safe state
- **THEN** 验证 SHALL 不通过

---

### FI-ACC-09: SKIP 条件（FI-09 SHALL x3）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | skip_condition 支持 `target_property` | ✅ |
| 2 | skip_condition 支持 `build_config` | ✅ |
| 3 | skip_condition 支持 `always` | ✅ |
| 4 | 跳过时结果记录 `skip` | ✅ |

**ACC-09-1: target_property 跳过**
- **GIVEN** `skip_condition: { type: "target_property", property: "mpu_enabled", expected: false }`
- **WHEN** 目标系统的 MPU 功能未启用
- **THEN** 该用例 SHALL 被跳过，结果记录为 `skip`

**ACC-09-2: target_property 不跳过**
- **GIVEN** 同上配置
- **WHEN** 目标系统的 MPU 功能已启用
- **THEN** 该用例 SHALL 正常执行

**ACC-09-3: build_config 跳过**
- **GIVEN** `skip_condition: { type: "build_config", config_key: "CONFIG_HARD_FAULT_HANDLER", expected: false }`
- **WHEN** 构建配置中 `CONFIG_HARD_FAULT_HANDLER` 未定义或为 `false`
- **THEN** 该用例 SHALL 被跳过

**ACC-09-4: always 跳过**
- **GIVEN** `skip_condition: { type: "always", reason: "尚未实现验证逻辑" }`
- **WHEN** 执行该用例
- **THEN** 该用例 SHALL 被跳过，结果记录为 `skip`，摘要中包含 `"尚未实现验证逻辑"`

---

### FI-ACC-10: Cooldown 间隔（FI-10 SHALL x4）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | `cooldown_ms` 默认 3000 | ✅ |
| 2 | 支持 0 值但输出警告 | ✅ |
| 3 | 独立于注入超时计算 | ✅ |
| 4 | 计入用例超时和 stage 总耗时 | ✅ |

**ACC-10-1: 默认 cooldown**
- **GIVEN** 未指定 `cooldown_ms`
- **WHEN** 用例执行完毕后
- **THEN** 系统 SHALL 等待 3000ms 后执行下一用例

**ACC-10-2: 自定义 cooldown**
- **GIVEN** `cooldown_ms: 5000`
- **WHEN** 用例执行完毕后
- **THEN** 系统 SHALL 等待 5000ms 后执行下一用例

**ACC-10-3: cooldown 计入用例超时**
- **GIVEN** `cooldown_ms: 3000`, `inject_timeout_ms: 5000`
- **WHEN** 用例超时计算
- **THEN** `case_timeout_ms` SHALL 包含 cooldown（=3000），但注入超时（inject_timeout_ms=5000）SHALL NOT 因 cooldown 而延长

**ACC-10-4: cooldown 计入 stage 总耗时**
- **GIVEN** 3 条用例，每条 cooldown=3000ms，总执行计时 18000ms
- **WHEN** 检查 stage duration_ms
- **THEN** duration_ms SHALL ≥ 18000，包含所有 cooldown 等待时间

---

## 3.3 结果与报告

### FI-ACC-11: 用例结果分类（FI-11 SHALL x3）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 四类结果：pass/fail/skip/error | ✅ |
| 2 | 四类互斥 | ✅ |
| 3 | error 时记录错误类型 | ✅ |

**ACC-11-1: pass 判定**
- **GIVEN** 注入成功、magic 校验通过、所有 verify_spec 条件满足
- **WHEN** 结果分类判定
- **THEN** 结果 SHALL 记录为 `pass`

**ACC-11-2: fail 判定**
- **GIVEN** 注入成功、magic 校验通过、至少一条 verify_spec 条件不满足
- **WHEN** 结果分类判定
- **THEN** 结果 SHALL 记录为 `fail`

**ACC-11-3: error 判定**
- **GIVEN** 注入过程中通信断开/magic 校验失败/配置错误
- **WHEN** 结果分类判定
- **THEN** 结果 SHALL 记录为 `error`，且 `error_type` SHALL 存在

**ACC-11-4: 结果互斥**
- **GIVEN** 一条用例的最终结果
- **WHEN** 检查其所属类别
- **THEN** 只 SHALL 属于 `pass`/`fail`/`skip`/`error` 中的唯一一类

---

### FI-ACC-12: 故障详情记录（FI-12 SHALL x3）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | pass/fail 时记录完整故障详情 | ✅ |
| 2 | StackOverflow 时记录溢出深度 | ✅ |
| 3 | 寄存器值解码（可选） | ◐ |

**ACC-12-1: 故障详情字段**
- **GIVEN** 一条结果为 `pass` 或 `fail` 的用例
- **WHEN** 检查其报告记录
- **THEN** `magic`、`fault_type`、`pc`、`cfsr`、`expected_mask`、`actual_mask_result`、`injected_raw_data` SHALL 均存在且非空

**ACC-12-2: StackOverflow 详情**
- **GIVEN** `fault_type = 5`
- **WHEN** 检查报告记录
- **THEN** `overflow_depth_bytes` SHALL 存在

**ACC-12-3: skip/error 无故障详情**
- **GIVEN** 一条结果为 `skip` 的用例
- **WHEN** 检查其报告记录
- **THEN** 故障详情字段 SHALL NOT 被记录（或为 `null`）

---

### FI-ACC-13: 结构化 JSON 报告（FI-13 SHALL x4）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 生成 JSON 报告，路径 `reports/fault_injection/<timestamp>.json` | ✅ |
| 2 | 顶层字段完整 | ✅ |
| 3 | 每条用例包含完整字段 | ✅ |
| 4 | FMEA 追溯统计 | ✅ |

**ACC-13-1: 报告文件生成**
- **GIVEN** `fault_injection` 阶段执行完毕
- **WHEN** 检查 `reports/fault_injection/` 目录
- **THEN** 一个以时间戳命名的 `.json` 文件 SHALL 存在

**ACC-13-2: 报告顶层结构**
- **GIVEN** 生成的 JSON 报告
- **WHEN** 解析 JSON 顶层键
- **THEN** `report_version`、`generated_at`、`pipeline_run_id`、`suite_name`、`injection_target`、`summary`、`cases`、`fmea_trace` SHALL 均存在

**ACC-13-3: 汇总统计正确**
- **GIVEN** 执行了 10 条用例：5 pass, 3 fail, 1 skip, 1 error
- **WHEN** 检查 `summary`
- **THEN** `total=10`、`pass=5`、`fail=3`、`skip=1`、`error=1`、`pass_rate_pct=62.50`

**ACC-13-4: pass_rate_pct 在 total=0 时的行为**
- **GIVEN** 0 条用例被执行（`total=0`）
- **WHEN** 检查 `summary.pass_rate_pct`
- **THEN** 其值 SHALL 为 `"N/A"`（字符串）

---

### FI-ACC-14: FMEA 条目追溯（FI-14 SHALL x3）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | `fmea_refs` 引用不存在的 FMEA 条目时报错 | ✅ |
| 2 | 结果反写关联 FMEA 条目的 current_control 有效性 | ✅ |
| 3 | 报告包含 fmea_trace | ✅ |

**ACC-14-1: 非法 FMEA 引用阻断**
- **GIVEN** `fmea_refs: ["FMEA-2026-9999"]` 且该 FMEA ID 在 knowledge 模块中不存在
- **WHEN** 加载用例集
- **THEN** schema 校验 SHALL 失败，报告 `"FMEA-2026-9999: not found"`

**ACC-14-2: 结果反写 FMEA**
- **GIVEN** 用例关联了 `fmea_refs: ["FMEA-2026-0012"]` 且结果为 `pass`
- **WHEN** 查询 FMEA-2026-0012 的 `current_control` 有效性
- **THEN** 该控制措施的 evidence 记录 SHALL 显示已通过故障注入验证

**ACC-14-3: fmea_trace 格式**
- **GIVEN** JSON 报告
- **WHEN** 检查 `fmea_trace`
- **THEN** 每个 FMEA 条目 ID 对应的用例计数和结果分布 SHALL 正确聚合

---

### FI-ACC-15: 汇总统计（FI-15 SHALL x3）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 汇总统计包含 total/pass/fail/skip/error/pass_rate/duration | ✅ |
| 2 | 统计出现在 JSON 和 evidence 中 | ✅ |
| 3 | 多 suite 时提供全局和按 suite 视图 | ◐ |

**ACC-15-1: 统计字段完整**
- **GIVEN** 阶段执行完毕
- **WHEN** 读取汇总统计
- **THEN** `total`、`pass`、`fail`、`skip`、`error`、`pass_rate_pct`、`duration_ms` SHALL 全部存在且类型正确

**ACC-15-2: 双位置存储**
- **GIVEN** 阶段执行完毕
- **WHEN** 检查 JSON 报告和 evidence 阶段级记录
- **THEN** 汇总统计在两个位置 SHALL 一致

**ACC-15-3: pass_rate 计算**
- **GIVEN** `pass=10`, `fail=5`
- **WHEN** 计算 `pass_rate_pct`
- **THEN** `10 / (10+5) * 100 = 66.67`，保留两位小数

---

## 3.4 通信层抽象

### FI-ACC-16: 通信适配器插件化（FI-16 SHALL x3, SHALL NOT x1, MAY x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 适配器模式，每种目标对应一个适配器 | ✅ |
| 2 | 内置适配器覆盖 CAN/Ethernet/JTAG/Simulator | ✅ |
| 3 | 适配器实现 FaultInjector 接口 | ✅ |
| 4 | 适配器不硬编码业务逻辑 | ✅ |

**ACC-16-1: 接口定义**
- **GIVEN** 系统代码中的通信层
- **WHEN** 检查适配器接口定义
- **THEN** `FaultInjector` 接口 SHALL 包含 `Connect`、`Inject`、`WaitForReset`、`Verify`、`Disconnect` 方法

**ACC-16-2: socketcan 适配器可用**
- **GIVEN** `target.type = "can"`, `can.interface = "socketcan"`
- **WHEN** 创建适配器实例
- **THEN** `socketcan` 适配器 SHALL 被成功实例化

**ACC-16-3: 适配器不硬编码业务**
- **GIVEN** 任意适配器的实现代码
- **WHEN** 代码审查
- **THEN** 适配器 SHALL NOT 包含注入策略或验证逻辑的具体实现（仅传递命令和返回结果）

---

### FI-ACC-17: 连接生命周期管理（FI-17 SHALL x6）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 执行生命周期：Connect→Inject→WaitForReset→Verify→Disconnect | ✅ |
| 2 | suite 内建一次连接 | ✅ |
| 3 | WaitForReset: 等待复位 + 轮询上线 | ✅ |
| 4 | 超时未上线 → error(timeout) | ✅ |
| 5 | 阶段结束强制 Disconnect | ✅ |
| 6 | 阻断终止时强制 Disconnect | ✅ |

**ACC-17-1: 生命周期执行顺序**
- **GIVEN** 一个包含 3 条用例的 suite
- **WHEN** 执行
- **THEN** 调用顺序 SHALL 为：`Connect`(1次) → `Inject`→`WaitForReset`→`Verify`(3轮) → `Disconnect`(1次)

**ACC-17-2: 单连接**
- **GIVEN** 一个 suite
- **WHEN** 执行过程中
- **THEN** `Connect` SHALL 仅被调用 1 次，`Disconnect` SHALL 仅被调用 1 次

**ACC-17-3: WaitForReset 超时**
- **GIVEN** 目标 ECU 在 `reset_wait_timeout_ms`（默认 15000ms）内未上线
- **WHEN** WaitForReset 步骤
- **THEN** 该用例 SHALL 标记为 `error`（`error_type: "timeout"`）

**ACC-17-4: 阶段终止时释放**
- **GIVEN** 阶段因阻断阈值而被终止
- **WHEN** `on_failure` 钩子触发
- **THEN** `Disconnect` SHALL 被执行，释放连接资源

---

### FI-ACC-18: 超时保护机制（FI-18 SHALL x5, SHALL NOT x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 每条用例独立超时 | ✅ |
| 2 | 超时组成：inject + reset_wait + verify + cooldown | ✅ |
| 3 | 默认值：5000/15000/5000ms | ✅ |
| 4 | 用户可覆盖超时值 | ✅ |
| 5 | 超时后标记 error 并继续 | ✅ |
| 6 | 超时不导致整体挂起 | ✅ |

**ACC-18-1: 用例超时执行**
- **GIVEN** 用例配置未覆盖超时
- **WHEN** 用例开始执行
- **THEN** `inject_timeout_ms=5000`, `reset_wait_timeout_ms=15000`, `verify_timeout_ms=5000`, `cooldown_ms=3000` SHALL 为默认值

**ACC-18-2: 超时终止**
- **GIVEN** 一条用例执行超过 `case_timeout_ms`
- **WHEN** 监视超时
- **THEN** 该用例 SHALL 被终止，结果记录为 `error(timeout)`，系统 SHALL 继续下一用例

**ACC-18-3: 超时不死锁**
- **GIVEN** 任一阶段卡住超过超时
- **WHEN** 超时触发
- **THEN** 系统 SHALL NOT 死锁或挂起，SHALL 在 `case_timeout_ms + 安全余量` 内进入下一个用例

**ACC-18-4: 自定义超时**
- **GIVEN** `inject_timeout_ms: 10000`, `reset_wait_timeout_ms: 60000`
- **WHEN** 加载配置
- **THEN** 用例的超时计算 SHALL 使用自定义值

---

### FI-ACC-19: 错误重试策略（FI-19 SHALL x4, SHALL NOT x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | error 结果可重试 | ✅ |
| 2 | 默认 max_retries=3, retry_delay=2000, backoff=1.5 | ✅ |
| 3 | 重试执行完整流程 | ✅ |
| 4 | fail 结果不重试 | ✅ |
| 5 | 重试不计入阻断阈值计数（除非最终仍 error） | ◐ |

**ACC-19-1: 重试触发**
- **GIVEN** 一条用例因通信超时而结果为 `error`
- **WHEN** `retry_policy.max_retries = 3`
- **THEN** 系统 SHALL 自动重试该用例，间隔 `2000ms`，间隔随 backoff 递增

**ACC-19-2: 重试次数耗尽**
- **GIVEN** 一条用例在 3 次重试后仍为 `error`
- **WHEN** 计算阻断阈值
- **THEN** 该用例的最终 `error` SHALL 计入阶段阻断计数

**ACC-19-3: fail 不重试**
- **GIVEN** 一条用例结果为 `fail`（验证条件不满足）
- **WHEN** 检查重试逻辑
- **THEN** 该用例 SHALL NOT 被重试

**ACC-19-4: backoff 计算**
- **GIVEN** `retry_delay_ms=2000`, `backoff_factor=1.5`
- **WHEN** 第 1、2、3 次重试
- **THEN** 间隔 SHALL 为 2000ms, 3000ms, 4500ms（四舍五入到毫秒）

---

### FI-ACC-20: 多目标并发支持（FI-20 SHOULD x2, SHALL x2, SHALL NOT x1, MAY x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 多目标并发支持（SHOULD） | ◐ |
| 2 | 每个目标独立生命周期（SHOULD） | ◐ |
| 3 | `max_concurrent_targets` 配置（SHALL） | ✅ |
| 4 | 并发目标建立独立适配器实例（SHALL） | ✅ |
| 5 | 汇总统计合并计算（SHALL） | ◐ |
| 6 | 报告不混淆，每条记录标识执行目标（SHALL NOT） | ✅ |

**ACC-20-1: 并发配置**
- **GIVEN** `fi.config.max_concurrent_targets = 2`
- **WHEN** 阶段启动
- **THEN** 最多 2 个目标可同时执行用例

**ACC-20-2: 独立适配器**
- **GIVEN** 两个并发目标 A 和 B
- **WHEN** 同时执行
- **THEN** 目标 A 和目标 B SHALL 拥有各自的 `FaultInjector` 适配器实例，互不干扰

**ACC-20-3: 报告无混淆**
- **GIVEN** 多并发执行
- **WHEN** 检查每条用例记录
- **THEN** 每条记录 SHALL 标识其执行的 `target`（与注入目标一致）

---

## 3.5 任务级注入

### FI-ACC-21: 任务注册（FI-21 SHALL x2, SHOULD x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 支持故障注入的任务通过 `TaskFault_RegisterTask()` 注册 | ✅ |
| 2 | 重复注册返回错误码 | ✅ |
| 3 | 已注册任务可枚举查询 | ◐ |

**ACC-21-1: 任务注册成功**
- **GIVEN** 一个有效的任务句柄和任务名
- **WHEN** 调用 `TaskFault_RegisterTask(handle, "RteHigh")`
- **THEN** 该任务 SHALL 成功注册到故障注入框架，返回 `TASK_FAULT_OK`

**ACC-21-2: 重复注册拒绝**
- **GIVEN** 同一任务句柄已注册
- **WHEN** 再次调用 `TaskFault_RegisterTask()`
- **THEN** 注册 SHALL 失败，返回 `TASK_FAULT_ERR_ALREADY_REGISTERED`

**ACC-21-3: 任务枚举**
- **GIVEN** 已注册 3 个任务（DKI, Vehicle, SE）
- **WHEN** 查询已注册任务列表
- **THEN** 返回列表 SHALL 包含 3 条记录，每条含 `task_handle` 和 `task_name`

---

### FI-ACC-22: 循环检查（FI-22 SHALL x4）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 主循环开头调用 `TASK_FAULT_CHECK()` | ✅ |
| 2 | 非零通知值 → 解析为故障类型 → 设置故障标志 | ✅ |
| 3 | 无通知时非阻塞立即返回 | ✅ |
| 4 | 生产配置下全 no-op | ✅ |

**ACC-22-1: 注入接收**
- **GIVEN** 目标任务已注册，外部已调用 `TaskFault_Inject(task, 0x01)`
- **WHEN** 目标任务的下一个主循环执行到 `TASK_FAULT_CHECK()`
- **THEN** 内部故障标志 SHALL 被设置为 `SIM_NULL_HANDLE`，通知值 SHALL 复位

**ACC-22-2: 无注入时非阻塞**
- **GIVEN** 未发送任何通知
- **WHEN** 执行 `TASK_FAULT_CHECK()`
- **THEN** 函数 SHALL 立即返回，不阻塞、不给其他任务引入调度延迟

**ACC-22-3: 生产环境 no-op**
- **GIVEN** 生产配置已启用 `STD_OFF`
- **WHEN** 编译后的二进制
- **THEN** `TASK_FAULT_CHECK()` 宏 SHALL 展开为空，不产生任何机器码

---

### FI-ACC-23: 循环结束检查（FI-23 SHALL x3）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 主循环末尾调用 `TASK_FAULT_END_CHECK()` | ✅ |
| 2 | 未处理的故障自动记录为 FAILED | ✅ |
| 3 | 生产配置下全 no-op | ✅ |

**ACC-23-1: 未报告故障自动 FAILED**
- **GIVEN** 任务中已通过 `TASK_FAULT_CHECK()` 激活了故障标志
- **WHEN** 未调用 `TASK_FAULT_REPORT()` 且执行到 `TASK_FAULT_END_CHECK()`
- **THEN** 本次注入结果 SHALL 被自动记录为 `FAILED`，故障标志 SHALL 被清除

---

### FI-ACC-24: 错误路径报告（FI-24 SHALL x4）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 成功处理注入故障后调用 `TASK_FAULT_REPORT(PASSED)` | ✅ |
| 2 | 结果 PASSED 存入环形缓冲区 | ✅ |
| 3 | 生产配置下全 no-op | ✅ |

**ACC-24-1: 错误路径正确报告**
- **GIVEN** 任务中激活了 `SIM_NULL_HANDLE`，且对应 NULL 检查分支被执行
- **WHEN** 分支内调用 `TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED)`
- **THEN** 环形缓冲区中该条注入的结果 SHALL 记录为 `PASSED`

**ACC-24-2: 报告后不触发 END_CHECK  FAILED**
- **GIVEN** 已调用 `TASK_FAULT_REPORT(PASSED)`
- **WHEN** 执行 `TASK_FAULT_END_CHECK()`
- **THEN** SHALL NOT 产生重复的 FAILED 记录

---

### FI-ACC-25: 注入通道（FI-25 SHALL x4）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 使用 FreeRTOS Task Notification 作为注入通道 | ✅ |
| 2 | 注入流程完整：Inject→notify→CHECK→解析 | ✅ |
| 3 | 单向通道，任务不回复 | ✅ |
| 4 | UDS DID 0xF193 可配置为任务级注入通道 | ✅ |

**ACC-25-1: FreeRTOS Notification 发送**
- **GIVEN** 已注册任务 DKI
- **WHEN** 调用 `TaskFault_Inject(dkiTaskHandle, 0x01)`
- **THEN** `xTaskNotify(dkiTaskHandle, 0x01, eSetBits)` SHALL 被调用一次

**ACC-25-2: UDS DID 映射**
- **GIVEN** UDS 0xF193 写入数据 `0x0100`（faultType=0x01, taskIndex=0）
- **WHEN** UDS Handler 接收并解析
- **THEN** SHALL 调用 `TaskFault_Inject(taskAtIndex0, 0x01)`

---

### FI-ACC-26: 注入方式（FI-26 SHALL x1, SHOULD x1, SHALL NOT x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 默认使用模拟注入方式 | ✅ |
| 2 | 真实资源消耗注入有独立开关保护 | ✅ |
| 3 | 模拟注入不引起复位或 CPU 异常 | ✅ |

**ACC-26-1: 模拟注入默认**
- **GIVEN** 未启用真实资源消耗开关
- **WHEN** 执行任务级注入
- **THEN** 系统 SHALL 使用模拟注入方式，不修改任何真实硬件或内存状态

**ACC-26-2: 真实注入开关隔离**
- **GIVEN** `REAL_STACK_DEPLETE` 类型
- **WHEN** 检查其编译开关
- **THEN** 该类型 SHALL 默认关闭（`STD_OFF`），需显式启用

**ACC-26-3: 模拟注入无副作用**
- **GIVEN** 任意模拟注入执行
- **WHEN** 观察系统状态
- **THEN** SHALL NOT 产生复位、CPU 异常、内存损坏或数据丢失

---

### FI-ACC-27: 模拟故障类型（FI-27 SHALL x3, SHOULD x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 至少支持 4 种模拟故障类型 | ✅ |
| 2 | 类型 ID 唯一 8-bit 枚举 | ✅ |
| 3 | 每种类型有独立编译开关 | ✅ |

**ACC-27-1: 最少类型存在**
- **GIVEN** 系统源码
- **WHEN** 检查 `TASK_FAULT_SIM_NULL_HANDLE`、`TASK_FAULT_SIM_INVALID_PARAM`、`TASK_FAULT_SIM_TIMEOUT`、`TASK_FAULT_SIM_QUEUE_FULL` 定义
- **THEN** 这 4 种类型 SHALL 全部存在且 ID 唯一

**ACC-27-2: 类型 ID 唯一性**
- **GIVEN** 所有定义的模拟故障类型
- **WHEN** 检查各类型 ID
- **THEN** 每个 ID SHALL 是唯一的 8-bit 值

**ACC-27-3: 独立编译开关**
- **GIVEN** `TASK_FAULT_SIM_NULL_HANDLE_ENABLE` 设为 `STD_OFF`
- **WHEN** 编译并执行注入
- **THEN** `SIM_NULL_HANDLE` 注入 SHALL 不可用或返回错误

---

### FI-ACC-28: 结果存储（FI-28 SHALL x4）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 结果存储在环形缓冲区中 | ✅ |
| 2 | 至少支持 16 条记录 | ✅ |
| 3 | 每条记录含 timestamp/task_handle/fault_type/result/injection_id | ✅ |
| 4 | 缓冲区满时 FIFO 覆盖 | ✅ |

**ACC-28-1: 环形缓冲区容量**
- **GIVEN** 环形缓冲区配置
- **WHEN** 检查其容量
- **THEN** 容量 SHALL ≥ 16 条

**ACC-28-2: 记录字段完整性**
- **GIVEN** 一条存储的结果记录
- **WHEN** 检查其内容
- **THEN** `timestamp`、`task_handle`、`fault_type`、`result`、`injection_id` SHALL 均存在

**ACC-28-3: FIFO 覆盖**
- **GIVEN** 连续注入超过缓冲区容量（如 20 次）
- **WHEN** 读取索引 0 的最旧记录
- **THEN** 最旧的记录 SHALL 已被覆盖（索引 0 为最新的第 5 条旧记录或新记录）

**ACC-28-4: 结果读取 API**
- **GIVEN** 环形缓冲区中有 5 条记录
- **WHEN** 调用 `TaskFault_GetResultCount()`
- **THEN** 返回 SHALL 为 5

---

### FI-ACC-29: 注入超时（FI-29 SHALL x5, SHALL NOT x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 每次注入有超时机制 | ✅ |
| 2 | 默认超时 5000ms | ✅ |
| 3 | 超时从 `TaskFault_Inject()` 开始计时 | ✅ |
| 4 | 超时后自动记录 TIMEOUT | ✅ |
| 5 | 超时可配置 | ✅ |
| 6 | 超时不挂起目标任务 | ✅ |

**ACC-29-1: 默认超时生效**
- **GIVEN** `task_inject_timeout_ms` 未配置
- **WHEN** 调用 `TaskFault_Inject()`
- **THEN** 超时计时 SHALL 使用 5000ms 默认值

**ACC-29-2: 超时自动标记**
- **GIVEN** 目标任务因阻塞等原因未在 5000ms 内调用 `TASK_FAULT_REPORT()`
- **WHEN** 超时到期
- **THEN** 系统 SHALL 自动将本次注入结果写入环形缓冲区，标记为 `TIMEOUT`

**ACC-29-3: 超时不挂起任务**
- **GIVEN** 一次注入超时
- **WHEN** 检查目标任务状态
- **THEN** 目标任务 SHALL NOT 被挂起或终止，SHALL 继续正常运行

---

### FI-ACC-30: 项目级逐个任务优先级排序（FI-30 SHOULD x2, MAY x1）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 支持按任务优先级排序执行（SHOULD） | ◐ |
| 2 | 支持 YAML 配置指定优先级顺序（SHOULD） | ◐ |
| 3 | 可通过 FMEA ap_priority 自动推算（MAY） | — |

**ACC-30-1: 配置优先级顺序**
- **GIVEN** 用例集 YAML 中配置 `task_priority_order: ["DKI", "Vehicle", "SE"]`
- **WHEN** 执行任务级注入
- **THEN** DKI 任务 SHALL 优先执行注入，其次 Vehicle，最后 SE

---

### FI-ACC-31: 与 Layer 1 的关系（FI-31 SHALL NOT x1, SHALL x3）

| # | 准则 | 覆盖 |
|---|------|:----:|
| 1 | 任务级注入不触发复位或 CPU 异常 | ✅ |
| 2 | 两层互不干扰（独立 DID、独立编译开关、独立存储、独立生命周期） | ✅ |
| 3 | 同一 Pipeline 可先后运行 Layer 1 和 Layer 2 | ✅ |
| 4 | JSON 报告中每条用例记录 layer 字段 | ✅ |

**ACC-31-1: 无复位触发**
- **GIVEN** 执行任意任务级注入
- **WHEN** 监测系统复位状态
- **THEN** SHALL NOT 触发模式复位、CPU 异常或 Watchdog 复位

**ACC-31-2: DID 隔离**
- **GIVEN** Layer 1 DID 为 0xF190/F191，Layer 2 DID 为 0xF192/F193
- **WHEN** UDS $2E 写入 0xF193
- **THEN** Layer 1 的故障注入框架 SHALL NOT 被触发

**ACC-31-3: 报告 layer 标识**
- **GIVEN** 同时执行了 Layer 1 和 Layer 2 的测试用例
- **WHEN** 检查 JSON 报告中每条用例记录
- **THEN** 记录中 SHALL 包含 `layer` 字段（`"system"` 或 `"task"`）

---

## 附录 A: 验证策略概览

| ACC 分类 | 条目数 | 单元测试 | 集成测试 | E2E | 代码审查 |
|----------|:------:|:--------:|:--------:|:---:|:--------:|
| A. Pipeline 集成 | 5 | ✅  | ✅ | —  | —  |
| B. 测试用例定义 | 5 | ✅  | ✅  | ✅ | —  |
| C. 结果与报告 | 5 | ✅  | —  | ✅ | —  |
| D. 通信层抽象 | 5 | ✅  | ✅  | ✅ | ✅ |
| E. 任务级注入 | 11 | ✅  | ✅  | ✅ | ✅ |
| **合计** | **31** | **31** | **17** | **17** | **10** |

---

> **变更记录**
> | 版本 | 日期 | 变更内容 | 作者 |
> |------|------|---------|------|
> | v1.0.0 | 2026-06-20 | 初始验收矩阵（20 个 ACC 条目） | 小马 🐴 |
> | v1.1.0 | 2026-06-20 | 追加 Layer 2 任务级注入（ACC-FI-21~31，共 11 个 ACC 条目） | 小马 🐴 |

# 模块设计速写：sil（Software-In-the-Loop 仿真）

> ⚠️ **状态：未接入 Pipeline（保留为参考库 / ORPHAN）**——`src/yuleosh/` 无任何 `import yuleosh.sil`，仅 tests 引用；真实 SIL 已由 `cross/` 取代投产。

> 包：`src/yuleosh/sil/` ｜ 规模：2 .py ≈ 571 行
> 定位：**未被任何生产代码调用的孤儿 mock**——真实 SIL 在 `cross/`

## 职责（名义 vs 实际）
名义：Vector SIL Kit Digital Twin 集成（创建参与者、运行仿真、收集结果）。**实际是未接线的 MOCK/STUB，不驱动任何真实仿真器。**

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `sil/__init__.py` (225) | 数据类型 + 门面 | `SimStatus` `:23`；`Participant` `:34`；`SimResult` `:47`；`ModelConfig` `:58`；`SILKitIntegration` `:81`（connect `:116`/run_simulation `:161`/get_report `:191`） |
| `sil/adapter.py` (346) | 适配器（桥接 Pipeline ↔ SIL Kit） | `ParticipantState` `:25`；`SimulationState` `:36`；`SilTestConfig` `:49`；`SimReport` `:67`；`SILKitAdapter` `:93`（connect `:113`/run_simulation `:173`/generate_report `:293`） |

## 公共 API / 入口点
- `SILKitIntegration`：`connect()` / `run_simulation()` / `get_report()`
- `SILKitAdapter`：`connect()` / `run_simulation()` / `generate_report()` / `parse_results()` / `convert_testcases()`
- 数据类型：`SimStatus` / `Participant` / `SimResult` / `ModelConfig` / `ParticipantState` / `SimulationState` / `SilTestConfig` / `SimReport`

## 生产接线
- **ORPHAN**：`grep yuleosh.sil` 仅命中 `tests/`，`src/yuleosh/` 无任何 `import yuleosh.sil`。对运行时是死代码。
- 对比：真正投产 SIL 在 `cross/` 并经 CI 接线：`ci/stages/test.py:243 run_sil_tests()` → `:274 from cross.sil_runner import sil_test` → `layer_executor.py:576` → `engine/ci_checkpoint.py:147`。

## 运行时触发方式
- **不被调用**：无注册路由、无 pipeline step 引用 `yuleosh.sil`。

## 它驱动什么仿真器（QEMU? docker? subprocess?）
- **NONE**：全部模拟。
- `SILKitAdapter.connect()`（`adapter.py:113-126`）：注释 `:123-124` 承认"*In production this opens a VAsio connection via SIL Kit C API. In stub/mock mode we simulate success.*"——函数体仅设 `self._state=SimulationState.IDLE` 并打日志。
- `run_simulation()`（`:173-221`）：`time.sleep(0.05)`（`:203`）模拟；`SimResult` 状态硬编码 `COMPLETED`（`:211`），`simulation_time_ns=int(config.timeout_s*1e9)`（`:212`）假指标，从不加载/运行固件。
- 无 `subprocess|QEMU|docker` 引用（`sil/` 下 grep 无匹配）。

## 与 cross 关系
- **两套独立实现，互不导入**（`sil/` 不 import `cross`，`cross/` 也不 import `yuleosh.sil`）。
- 真正投产的 QEMU SIL 在 `cross/sil_runner.py`（`QemuSilRunner` `:125`、`sil_test` `:423`，`subprocess.Popen` 启 QEMU `:285`，`MIN_QEMU_VERSION=(8,2,0)` `:48`）。`yuleosh.sil` 与之一脱节。

## 环境变量 / 配置
- **包内不读环境变量**。硬编码 `registry_uri="silkit://localhost:8500"`（`adapter.py:62`、`__init__.py:72`）、`timeout_s=30.0`（`adapter.py:63`）。

## 偏差 / 死代码（设计文档必记）
- **D1：ORPHAN 模块**——运行时无调用方，仅测试引用。应标注为「当前未启用 / 被 cross 取代或待实现」。
- **D2：名义能力与实际不符**——文档称"SIL Kit Digital Twin integration"，实为 stub（`adapter.py:123-124` 注释承认）。
- `generate_report()` 输出 `step:"sil_kit_simulation"`（`adapter.py:337`）引用不存在的 pipeline step（真实用 `cross.run_sil_tests`）。

## 规模
2 .py ≈ 571 行。

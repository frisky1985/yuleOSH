# `adapter` 模块设计速写

> 本篇为「模块设计速写」（speed-write），基于 2026-10-07 实读 `src/yuleosh/adapter/`。
> 与代码冲突时以代码为准。定位：输出格式化库，非详设。

## 0. 与直觉相悖处（先说结论）
- `adapter` 是**纯 XML / CAPL 文本生成器**，对接 dSPACE AutomationDesk 与 Vector CANoe，
  **不调用任何真实硬件 / 驱动 / CAN 接口**（无串口、无 CAN SDK、无探针通信）。它产出
  `.autoxml` / `.can` / `.xml` + CAPL 脚本 + DBC 映射文本，由人工或 CI 导入硬件平台执行。
- **当前 `src/` 中无任何生产代码 `import yuleosh.adapter`**（仅被 tests 引用）。它是一个
  尚未接入 Pipeline 的输出格式化库。设计文档若称其「直连 HIL 硬件」需加「生成格式、非直连」限定。

## 1. 文件清单
| 文件 | 行数 |
|---|---|
| `adapter/__init__.py` | 126 |
| `adapter/dspace_adapter.py` | 611 |
| `adapter/vector_adapter.py` | 347 |

## 2. 核心职责
Adapter Pattern：将 Pipeline 产出的测试用例（`TestCase` dict）转换为各 HIL 平台可执行格式。
- `VectorCANoeAdapter` → Vector CANoe XML Test Feature（`*.can`/`*.xml`）+ CAPL + DBC 信号映射
  （`vector_adapter.py:6-16`、`__init__.py:84`）。
- `DSAPCEAutomationDeskAdapter` → dSPACE AutomationDesk XML（`*.autoxml`），含 Simulink/MiL/SiL 模型引用
  （`dspace_adapter.py:6-20`、`__init__.py:84`）。
- 命名空间常量：`_AUTODESK_NS`（dspace `:36`）、`_CANOE_NS`（vector `:32`）。

## 3. 关键类与函数（文件:行号）
- `get_adapter(name, **kwargs)` 工厂 → `VectorCANoeAdapter | DSAPCEAutomationDeskAdapter`（`__init__.py:78`）。
- `DSAPCEAutomationDeskAdapter.convert(test_cases, output_dir)`（`:75`）、`generate_test_set`（`:138`）、
  `generate_test_step`（`:225`）、`generate_parameter_set`（`:384`）。
- `VectorCANoeAdapter.convert`（`:62`）、`generate_capl`（`:176`）、`generate_dbc_map`（`:238`）、
  `generate_test_module`（`:109`）。
- 共享类型：`TestCase = Dict[str, Any]`（`__init__.py:55-71`），结构含
  `id/title/group/group_id/type/description/steps/signals/capl/parameters/model`。

## 4. 数据模型
无 dataclass；`TestCase` 为 dict 别名。两适配器均仅依赖标准库（`xml.etree.ElementTree` 等）。

## 5. 集成点
- 仅相对 import，不依赖任何 `yuleosh.*` 其它子包。
- 被 import：仅 tests（`test_adapter_smoke.py`、`test_dspace_adapter.py`、`test_vector_adapter.py`、
  `test_max_import.py`、`test_phase0_coverage_boost.py`）。**无 src 生产调用方**。

## 6. 配置
无环境变量 / 配置文件读取；行为由函数参数控制（`namespace`、`output_dir`）。

## 7. 测试
见第 5 节清单。

## 8. 待决（留给评审）
- 是否接入 Pipeline（目前是孤岛库）？若保留，建议在设计文档明确其「格式生成器」定位，
  并补充与 `pipeline/step_handlers` 的接线计划。

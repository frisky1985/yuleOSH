# `autosar` 模块设计速写

> 本篇为「模块设计速写」（speed-write），基于 2026-10-07 实读 `src/yuleosh/autosar/`。
> 与代码冲突时以代码为准。

## 0. 与直觉相悖处（先说结论）
- `autosar` = **ARXML 读取（Phase 1）+ RTE Stub/Mock C 代码生成（Phase 2）**，处理
  AUTOSAR CP R20-11 的 SWC / Port / Runnable / Internal Behavior。**未含完整 BSW 栈生成**。
- **悬空依赖**：`src/yuleosh/pipeline/async_runner.py:277` 引用不存在的
  `yuleosh.autosar.rte_generator`（全仓 `find` 无此文件，`rte_generator.generate(...)` 在
  该分支会 `ModuleNotFoundError`）。属已知坏引用，建议移除或补实现。
- **CLI 接线缺口**：`autosar/cli.py` 的 `import arxml` 子命令未被 `cli/main.py` 注册，
  仅 `autosar gen-stub` 已接线（`main.py:492-495, 901-903`）。

## 1. 文件清单
| 文件 | 行数 |
|---|---|
| `autosar/__init__.py` | 43 |
| `autosar/cli.py` | 210 |
| `autosar/models.py` | 242 |
| `autosar/parser.py` | 611 |
| `autosar/stubgen.py` | 804 |

## 2. 核心职责
- ARXML 解析：`ARXMLParser` 解析 SWC 描述符（`parser.py:120`，`no lxml dependency`，用标准库
  `xml.etree.ElementTree`，`parser.py:6-7`）。
- RTE Stub 生成：`StubGenerator` 依据 SWC 生成 RTE 桩/ Mock C 代码（`.c`/`.h`）用于 SWE.5 集成
  测试双（`stubgen.py:4-29`）。
- 无 async / 无 HTTP。

## 3. 关键类与函数（文件:行号）
- `ARXMLParser`（`parser.py:120`）：`parse_file` `:148`、`parse_swc` `:157`、`parse_packages` `:185`、
  `to_markdown` `:530`；便捷函数 `parse_arxml_file` `:585`、`parse_arxml_packages` `:602`。
- `StubGenerator`（`stubgen.py:163`）：`generate` `:192`、`generate_all` `:217`；便捷函数
  `generate_stubs` `:696`。
- 数据模型（`models.py`，全部 dataclass）：`ComSpec` `:19`、`PortPrototype` `:46`、
  `RunnableEntity` `:75`、`SwcInternalBehavior` `:119`、`SWCComponent` `:141`、`AutoSarPackage` `:193`。
- CLI：`register_cli`（`cli.py:26` 注册 `import arxml`；`stubgen.py:741` 注册 `gen-stub`）、
  `_handle_arxml_command` `:71`、`import_arxml_to_spec` `:185`。

## 4. 数据模型
见第 3 节 `models.py` 六类 dataclass；Stub 专用 `StubFunction`（`stubgen.py:100`）、
`StubModule`（`stubgen.py:129`）。均为 `dataclasses.dataclass`，非 pydantic。

## 5. 集成点
- `autosar` 仅依赖自身子模块（相对 import），无对其它 `yuleosh.*` 业务模块的硬依赖。
- 被 import：
  - `cli/main.py:494, 903` → `yuleosh.autosar.stubgen`（CLI 接线 `gen-stub`）。
  - `ci/stages/autosar.py:787` → `yuleosh.autosar.parser.ARXMLParser`（CI 阶段解析）。
  - `pipeline/async_runner.py:277` → `yuleosh.autosar.rte_generator`（**悬空，见第 0 节**）。

## 6. 配置
无环境变量 / 配置文件读取；`schema_version` 默认 `"4.2"`（`parser.py:127`）、
`stubgen` 的 `project_dir`/`rte_header`/`emit_call_counters`/`emit_mock_returns` 均有默认值
（`stubgen.py:173-183`）。命名空间常量 `AUTOSAR_NS="http://autosar.org/schema/r4.0"`（`parser.py:51`）。

## 7. 测试
`test_autosar_parser.py`、`test_autosar_cli_ext.py`、`test_autosar_stubgen_unit.py`、
`test_ci_stages_autosar_unit.py`、`test_coverage_phase10_engine.py`、`test_cli.py:690`、
`test_cli_main_adv_unit.py:817`。**无 `test_autosar_rte_generator.py`**（与悬空引用互相印证）。

## 8. 待决（留给评审）
- 修 `async_runner.py:277` 的 `rte_generator` 悬空引用（删或补）。
- 是否接线 `import arxml` 子命令（`cli/main.py` 未注册）。

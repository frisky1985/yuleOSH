# AUTOSAR API 参考
> 代码根:`src/yuleosh/autosar/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述
本子系统提供 AUTOSAR CP ARXML 文件的轻量级解析(Phase 1)与 RTE C stub/mock 代码生成(Phase 2)。
职责证据:`src/yuleosh/autosar/__init__.py:4-16`(模块 docstring 声明解析 SWC 描述符与 stub 生成);
`src/yuleosh/autosar/parser.py:120`(`ARXMLParser`)、`src/yuleosh/autosar/stubgen.py:163`(`StubGenerator`)。
对外无 REST 端点,仅通过 Python API 与 CLI 子命令暴露能力。CLI 入口注册于
`src/yuleosh/cli/main.py:492-495`(`autosar` → `gen-stub`)。

> ⚠️ 注意:`autosar/cli.py` 定义的 `import arxml` 子命令(`register_cli`,`src/yuleosh/autosar/cli.py:26-68`)
> 从未在 `cli/main.py` 中注册(全仓库 Grep `add_parser("import"` 无匹配),当前实际仅注册了 `gen-stub`。见 §6。

## 2. HTTP 端点
无。本子系统不对外暴露 REST 端点。

## 3. Python 公共 API

### 3.1 模块级函数
| 函数 | 签名 | 用途 | 文件:行 |
|------|------|------|---------|
| `parse_arxml_file` | `(filepath: str) -> List[SWCComponent]` | 便捷解析 ARXML 返回所有 SWC 组件(内部使用默认 parser 实例) | `src/yuleosh/autosar/parser.py:585-599` |
| `parse_arxml_packages` | `(filepath: str) -> List[AutoSarPackage]` | 便捷解析 ARXML 返回 AR-PACKAGE 层级 | `src/yuleosh/autosar/parser.py:602-611` |
| `generate_stubs` | `(arxml_path: str, output_dir: str = "generated/stubs", swc_filter: str = "") -> Dict[str, StubModule]` | 从 ARXML 生成 RTE stub/mock C 代码;CLI `gen-stub` 的底层入口 | `src/yuleosh/autosar/stubgen.py:696-738` |
| `register_cli` (stubgen) | `(subparsers) -> None` | 注册 `autosar gen-stub` 子命令 | `src/yuleosh/autosar/stubgen.py:741-780` |
| `register_cli` (cli) | `(subparsers) -> None` | 注册 `import arxml` 子命令(**当前未被 main.py 调用**) | `src/yuleosh/autosar/cli.py:26-68` |
| `import_arxml_to_spec` | `(filepath: str, output_dir: str) -> Dict[str, str]` | 将 ARXML 转为项目 spec markdown 文件(docstring 称被 import 流水线调用,但全仓库无调用方) | `src/yuleosh/autosar/cli.py:185-210` |

### 3.2 公共类
| 类 | 关键方法(签名) | 用途 | 文件:行 |
|----|----------------|------|---------|
| `ARXMLParser` | `__init__(self, schema_version: str = "4.2")` | 构造解析器 | `src/yuleosh/autosar/parser.py:127-128` |
| | `parse_file(self, filepath: str) -> List[SWCComponent]` | 解析并返回全部 SWC(带日志的 `parse_swc` 包装) | `src/yuleosh/autosar/parser.py:148-155` |
| | `parse_swc(self, filepath: str) -> List[SWCComponent]` | 解析 ARXML 提取全部 SWC 组件 | `src/yuleosh/autosar/parser.py:157-183` |
| | `parse_packages(self, filepath: str) -> List[AutoSarPackage]` | 解析并返回 AR-PACKAGE 层级 | `src/yuleosh/autosar/parser.py:185-202` |
| | `to_markdown(self, swcs: List[SWCComponent]) -> str` | 将 SWC 组件格式化为 Markdown | `src/yuleosh/autosar/parser.py:530-575` |
| `StubGenerator` | `__init__(self, project_dir: str = "generated/stubs", rte_header: str = '"Rte_Type.h"', emit_call_counters: bool = True, emit_mock_returns: bool = True)` | 构造 RTE stub 生成器 | `src/yuleosh/autosar/stubgen.py:173-186` |
| | `generate(self, swc: SWCComponent) -> StubModule` | 为单个 SWC 生成 stub 文件 | `src/yuleosh/autosar/stubgen.py:192-215` |
| | `generate_all(self, swcs: List[SWCComponent]) -> Dict[str, StubModule]` | 为多个 SWC 批量生成 | `src/yuleosh/autosar/stubgen.py:217-230` |
| | `clear(self) -> None` | 重置已生成集合 | `src/yuleosh/autosar/stubgen.py:232-234` |
| `SWCComponent` | `port_by_name(name)`, `runnable_by_name(name)` | SWC 顶层描述符,含端口/Runnable 查找 | `src/yuleosh/autosar/models.py:141-190` |
| `AutoSarPackage` | `find_component(name)`, `all_components()`, `print_tree(indent=0)` | AR-PACKAGE 容器,递归查找组件/打印树 | `src/yuleosh/autosar/models.py:193-242` |

### 3.3 关键数据结构
- `@dataclass ComSpec` — 端口通信规格(`src/yuleosh/autosar/models.py:19-43`)
- `@dataclass PortPrototype` — R-PORT / P-PORT 端口原型(`src/yuleosh/autosar/models.py:46-72`)
- `@dataclass RunnableEntity` — Runnable 实体(符号/C 函数名、周期、数据读写访问等)(`src/yuleosh/autosar/models.py:75-116`)
- `@dataclass SwcInternalBehavior` — SWC 内部行为容器(`src/yuleosh/autosar/models.py:119-138`)
- `@dataclass SWCComponent` — SWC 顶层描述符(`src/yuleosh/autosar/models.py:141-190`)
- `@dataclass AutoSarPackage` — AR-PACKAGE 容器(`src/yuleosh/autosar/models.py:193-242`)
- `@dataclass StubFunction` — 生成的 stub 函数描述符(`src/yuleosh/autosar/stubgen.py:100-126`)
- `@dataclass StubModule` — 单个 SWC 的 stub 模块描述符(`src/yuleosh/autosar/stubgen.py:129-155`)

常量(stubgen 模块级,`src/yuleosh/autosar/stubgen.py`):
- `RTE_PREFIX = "Rte_"` (`:53`)
- `RTE_READ_MACRO = "Rte_Read"` (`:61`)、`RTE_WRITE_MACRO = "Rte_Write"` (`:62`)、`RTE_INVOKE_MACRO = "Rte_Call"` (`:63`)
- `RTE_HEADER = '"Rte_Type.h"'` (`:66`)
- `INIT_VALUE_MAP: dict` — 数据类型的默认初始化值映射(uint8/uint16/.../boolean)(`:80-92`)

> `ARXMLParser` 私有辅助 `_AUTOSAR_NS = "http://autosar.org/schema/r4.0"` 用于命名空间处理(`src/yuleosh/autosar/parser.py:51`)。

## 4. 配置 / 环境变量
本子系统不读取环境变量;无配置项。行为通过 CLI 参数 / 函数参数控制:
- `gen-stub`:位置参数 `arxml`、`--output/-o`(默认 `generated/stubs`)、`--swc`、`--verbose/-v`(`src/yuleosh/autosar/stubgen.py:752-779`)
- `import arxml`(未注册):`file`、`--output/-o`、`--format/-f`(markdown/json/tree)、`--swc`、`--verbose/-v`(`src/yuleosh/autosar/cli.py:39-66`)

## 5. 调用示例

示例 1 — 解析 ARXML 并打印 SWC 结构(markdown):
```python
# 依据 src/yuleosh/autosar/parser.py:585-599, :530-575
from yuleosh.autosar import parse_arxml_file, to_markdown  # to_markdown 需经 parser 实例
from yuleosh.autosar.parser import ARXMLParser

swcs = parse_arxml_file("path/to/swc.arxml")
print(ARXMLParser().to_markdown(swcs))
```

示例 2 — 从 ARXML 生成 RTE stub/mock C 代码:
```python
# 依据 src/yuleosh/autosar/stubgen.py:696-738
from yuleosh.autosar import generate_stubs

results = generate_stubs("path/to/swc.arxml", output_dir="out/stubs")
for name, module in results.items():
    print(name, "→", module.header_path, module.source_path)
```

## 6. 偏差 / 备注

### 6.1 悬空引用:`yuleosh.autosar.rte_generator` 不存在
`src/yuleosh/pipeline/async_runner.py:277` 在函数体内执行
`from yuleosh.autosar import rte_generator` 并在 `:280` 调用 `rte_generator.generate(...)`。
但 `src/yuleosh/autosar/` 目录仅有 `__init__.py`、`cli.py`、`models.py`、`parser.py`、`stubgen.py`
(Glob `src/yuleosh/autosar/**/*.py` 佐证),**不存在 `rte_generator.py` 模块**。
该 import 为函数内惰性导入,仅当对应代码路径执行时才会触发 `ImportError` / `ModuleNotFoundError`。
属于悬空引用(死代码路径),建议删除或补实现。

### 6.2 `import arxml` 子命令未注册(死代码)
`src/yuleosh/autosar/cli.py:26` 的 `register_cli` 旨在注册 `import arxml` 子命令,
但全仓库 Grep `add_parser("import"` 无匹配;`cli/main.py` 仅在 `:492-495` 注册了 `autosar` → `gen-stub`
(对应 `stubgen.register_cli`)。因此 `autosar/cli.py` 中的 `register_cli`、`_handle_arxml_command`、
`_format_json`、`_format_tree`、`import_arxml_to_spec` 均为**不可达死代码**(无生产调用方)。

### 6.3 非 ORPHAN,但调用面有限
本子系统模块被 `ci/stages/autosar.py:787`(`from yuleosh.autosar.parser import ARXMLParser`)
及 `cli/main.py`(`gen-stub` 子命令)引用,故 `autosar` 包本身**不是** ORPHAN;
但 `cli.py`(import arxml 分支)与 `import_arxml_to_spec` 确属死代码。

### 6.4 与直觉相悖
- `parser.py:7` 注释称「using xml.etree.ElementTree(标准库,无 lxml 依赖)」,与 `__init__.py:14`
  文档「lxml / xml.etree.ElementTree」表述不一致——实际未使用 lxml。
- `stubgen.py` 生成的 RTE stub 为**纯 mock 文本**(`:282-287` 直接写 `*value = _xxx_mock_value; return RTE_E_OK;`),
  端口数据类型靠 `_port_data_type` 的**启发式字符串匹配**(`stubgen.py:660-680`,默认 `uint8`),并非来自真实 RTE 配置。

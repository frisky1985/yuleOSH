# ADAPTER API 参考
> 代码根:`src/yuleosh/adapter/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述
本子系统是适配器工厂,将 yuleOSH Pipeline 产出的测试用例(dict 列表)转换为各 HIL/测试平台的格式:
Vector CANoe(CAPL/XML Test Feature)与 dSPACE AutomationDesk(AutoDesk XML)。
职责证据:`src/yuleosh/adapter/__init__.py:4-15`(模块 docstring 声明 Adapter Pattern、与核心 Pipeline 解耦)、
`src/yuleosh/adapter/vector_adapter.py:43`(`VectorCANoeAdapter`)、
`src/yuleosh/adapter/dspace_adapter.py:53`(`DSAPCEAutomationDeskAdapter`)。
全部依赖标准库 `xml.etree.ElementTree`,**不调用任何真实硬件 / 外部工具**,仅生成 XML / CAPL 文本文件。

## 2. HTTP 端点
无。本子系统不对外暴露 REST 端点。

## 3. Python 公共 API

### 3.1 模块级函数
| 函数 | 签名 | 用途 | 文件:行 |
|------|------|------|---------|
| `get_adapter` | `(name: str, **kwargs: Any)` | 工厂:根据 `name` 创建适配器(`"canoe"` → `VectorCANoeAdapter`,`"automationdesk"` → `DSAPCEAutomationDeskAdapter`;未知抛 `ValueError`) | `src/yuleosh/adapter/__init__.py:78-109` |
| `_indent` | `(elem: ET.Element, level: int = 0) -> None` | 就地格式化 ElementTree 缩进(私有但导出) | `src/yuleosh/adapter/__init__.py:33-48` |

### 3.2 公共类
| 类 | 关键方法(签名) | 用途 | 文件:行 |
|----|----------------|------|---------|
| `VectorCANoeAdapter` | `__init__(self, namespace: str = _CANOE_NS, prefix: str = _CANOE_PREFIX)` | 构造 CANoe 适配器 | `src/yuleosh/adapter/vector_adapter.py:56-58` |
| | `convert(self, test_cases: List[TestCase], output_dir: str) -> str` | 生成 test_module.can / simulation_setup.xml / 独立 CAPL 文件,返回路径列表(换行分隔) | `src/yuleosh/adapter/vector_adapter.py:62-107` |
| | `generate_test_module(self, test_cases: List[TestCase]) -> str` | 生成 CANoe Test Module XML(含 testgroup/testcase) | `src/yuleosh/adapter/vector_adapter.py:109-174` |
| | `generate_capl(self, test_case: TestCase) -> str` | 生成 CAPL 脚本(有自定义 `capl` 字段则原样返回,否则自动生成框架) | `src/yuleosh/adapter/vector_adapter.py:176-236` |
| | `generate_dbc_map(self, signals: List[Dict[str, Any]]) -> str` | 生成 CAN DBC 信号映射 XML | `src/yuleosh/adapter/vector_adapter.py:238-274` |
| `DSAPCEAutomationDeskAdapter` | `__init__(self, namespace: str = _AUTODESK_NS)` | 构造 dSPACE 适配器 | `src/yuleosh/adapter/dspace_adapter.py:70-71` |
| | `convert(self, test_cases: List[TestCase], output_dir: str) -> str` | 生成 project.autoxml / 分组 testset_*.autoxml / simulink_params.xml / model_*.xml | `src/yuleosh/adapter/dspace_adapter.py:75-136` |
| | `generate_test_set(self, test_cases: List[TestCase], name: str = "yuleOSH_Generated") -> str` | 生成 AutoDesk TestSet XML | `src/yuleosh/adapter/dspace_adapter.py:138-223` |
| | `generate_test_step(self, test_case: TestCase) -> ET.Element` | 生成单个 TestStep 元素 | `src/yuleosh/adapter/dspace_adapter.py:225-382` |
| | `generate_parameter_set(self, test_case: TestCase) -> str` | 生成 dSPACE ParameterSet XML | `src/yuleosh/adapter/dspace_adapter.py:384-422` |
| | `generate_model_ref(self, model_name: str) -> str` | 生成 Simulink 模型引用配置 XML | `src/yuleosh/adapter/dspace_adapter.py:424-487` |

### 3.3 关键数据结构
- 类型别名 `TestCase = Dict[str, Any]` — 测试用例 dict 结构(id/title/group/type/description/steps/signals/capl/parameters/model)(`src/yuleosh/adapter/__init__.py:55-71`)
- 常量 `_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'`(`src/yuleosh/adapter/__init__.py:26`)
- `vector_adapter._CANOE_NS = "http://vector.com/canoe/testfeature"`,`_CANOE_PREFIX = "canoe"`(`src/yuleosh/adapter/vector_adapter.py:32-33`)
- `dspace_adapter._AUTODESK_NS = "http://www.dspace.com/automationdesk"`(`src/yuleosh/adapter/dspace_adapter.py:36`)
- `dspace_adapter.CONDITION_TYPES` / `CRITERION_TYPES` 集合(`src/yuleosh/adapter/dspace_adapter.py:45-46`)

## 4. 配置 / 环境变量
本子系统不读取环境变量,无配置项。`namespace` 可作为构造参数覆盖(`__init__.py:70` / `dspace_adapter.py:70`)。
输出目录由 `convert()` 的 `output_dir` 参数指定(`__init__.py:62` / `dspace_adapter.py:75`)。

## 5. 调用示例
```python
# 依据 src/yuleosh/adapter/__init__.py:78-109, :62-107
from yuleosh.adapter import get_adapter

test_cases = [{
    "id": "TC_001",
    "title": "CAN Bus Communication",
    "group": "Smoke Tests", "group_id": "TG_001",
    "type": "PASS",
    "description": "Verify CAN TX",
    "signals": [{"name": "EngineSpeed", "expected_value": 1500, "condition": "EqualTo"}],
}]

adapter = get_adapter("canoe")
print(adapter.convert(test_cases, output_dir="/tmp/canoe_out"))

adapter2 = get_adapter("automationdesk")
print(adapter2.convert(test_cases, output_dir="/tmp/adk_out"))
```

## 6. 偏差 / 备注

### 6.1 ORPHAN(无生产调用方)— 已 Grep 验证
全仓库 Grep `yuleosh.adapter` / `yuleosh.sil`(两个包一起查,以覆盖潜在调用)/
`get_adapter` / `VectorCANoeAdapter` / `DSAPCEAutomationDeskAdapter`(排除 `adapter/` 包自身)
**无任何匹配**。即 `adapter` 包未被 `pipeline`、`cli`、`ci`、`ui` 等任何模块 import,属 **ORPHAN** 代码。

### 6.2 纯 XML/CAPL 文本生成器,不调真实硬件
尽管 docstring 宣称「将 Pipeline 产出的测试用例转化为各平台可执行格式」
(`__init__.py:7-8`),实际实现仅用 `xml.etree.ElementTree` 写出 `.xml`/`.can` 文本文件
(`vector_adapter.py:62-107`、`dspace_adapter.py:75-136`),**不调用 CANoe / AutomationDesk / 任何硬件**。
与 `sil` 包不同,此处没有 mock 运行层,也没有被 Pipeline 实际驱动的输入来源(无生产调用方)。

### 6.3 与文档「与核心 Pipeline 完全解耦」一致但未被使用
`__init__.py:8` 称「与核心 Pipeline 完全解耦,可独立使用和扩展」,这与 §6.1 的 ORPHAN 结论相互印证:
该适配器确为可独立使用的生成器,但目前**无任何生产代码实例化它**(`get_adapter` 无调用方)。

### 6.4 拼写注意
dSPACE 适配器类名拼写为 `DSAPCEAutomationDeskAdapter`(`dspace_adapter.py:53`,`__init__.py:104/117/121`),
中间为 `DSAPCE`(非 `DSpace`)。属既有命名,调用时须严格按此拼写。

# SIL API 参考
> 代码根:`src/yuleosh/sil/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述
本子系统自称「SIL Kit Digital Twin Integration」,提供基于 Vector SIL Kit 的软件在环(SIL)仿真高层 API:
创建 participant、运行仿真、收集结果并生成 Pipeline 报告。
职责证据:`src/yuleosh/sil/__init__.py:1-8`(模块 docstring)、`src/yuleosh/sil/adapter.py:93-102`
(`SILKitAdapter` 职责说明)。

> ⚠️ 与直觉相悖:`sil` 包内 `connect()` 注释明确写道「In stub/mock mode we simulate success」
(`adapter.py:123-126`),`run_simulation()` 内部仅 `time.sleep(0.05)` 模拟计算(`adapter.py:201-203`),
并不真正启动 Vector SIL Kit 运行时。本仓库**真实的 SIL 实现位于 `src/yuleosh/cross/sil_runner.py`**,
通过 `subprocess.Popen` 启动 QEMU 系统仿真(`cross/sil_runner.py:285`),与 `sil` 包无任何代码关联。见 §6。

## 2. HTTP 端点
无。本子系统不对外暴露 REST 端点。

## 3. Python 公共 API

### 3.1 模块级函数
无独立模块级函数。公共入口为 `SILKitIntegration` 类与 `SILKitAdapter` 类(见 3.2)。
(注:`sil/__init__.py` 与 `sil/adapter.py` 之间仅互相 import,无顶层函数导出。)

### 3.2 公共类
| 类 | 关键方法(签名) | 用途 | 文件:行 |
|----|----------------|------|---------|
| `SILKitIntegration` | `__init__(self) -> None` | 构造集成门面,内部持有 `SILKitAdapter` 实例 | `src/yuleosh/sil/__init__.py:105-110` |
| | `connect(self, registry_uri: str) -> None` | 连接 SIL Kit Registry(实际为 mock,直接置 `_connected=True`) | `src/yuleosh/sil/__init__.py:116-126` |
| | `disconnect(self) -> None` | 断开并清理 participants | `src/yuleosh/sil/__init__.py:128-133` |
| | `create_participant(self, name: str, *, simulation_name: str = "default") -> Participant` | 创建并注册一个 participant | `src/yuleosh/sil/__init__.py:139-155` |
| | `run_simulation(self, model_config: ModelConfig | Dict[str, Any]) -> SimResult` | 运行仿真(未 connect 时抛 `RuntimeError`) | `src/yuleosh/sil/__init__.py:161-185` |
| | `get_report(self, results: List[SimResult]) -> dict` | 生成 Pipeline 报告 dict | `src/yuleosh/sil/__init__.py:191-200` |
| | 属性 `connected` / `participants` | 连接状态 / 已注册 participants | `src/yuleosh/sil/__init__.py:206-214` |
| `SILKitAdapter` | `__init__(self) -> None` | 构造桥接器,`_state=IDLE`,`_participant_handles={}` | `src/yuleosh/sil/adapter.py:104-108` |
| | `connect(self, registry_uri: str) -> None` | 连接 Registry(mock,仅置状态) | `src/yuleosh/sil/adapter.py:113-126` |
| | `shutdown(self) -> None` | 关闭并停止参与者 | `src/yuleosh/sil/adapter.py:128-133` |
| | `convert_testcases(self, cases: List[Dict[str, Any]]) -> List[SilTestConfig]` | yuleOSH 测试用例 → SilTestConfig 列表 | `src/yuleosh/sil/adapter.py:144-167` |
| | `run_simulation(self, config: SilTestConfig) -> "SimResult"` | 执行一次仿真(mock,`time.sleep(0.05)`) | `src/yuleosh/sil/adapter.py:173-221` |
| | `parse_results(self, raw: bytes) -> SimReport` | 解析原始输出字节为 SimReport(占位启发式解析) | `src/yuleosh/sil/adapter.py:250-287` |
| | `generate_report(self, results: List["SimResult"]) -> dict` | 聚合结果为 Pipeline 报告 dict | `src/yuleosh/sil/adapter.py:293-346` |

### 3.3 关键数据结构
枚举(`src/yuleosh/sil/adapter.py`):
- `ParticipantState` — DISCONNECTED/CONNECTING/CONNECTED/RUNNING/STOPPED/CRASHED/RESTARTED(`:25-33`)
- `SimulationState` — IDLE/BOOTING/RUNNING/TEARDOWN/ERROR(`:36-42`)

枚举与 dataclass(`src/yuleosh/sil/__init__.py`):
- `SimStatus` — PENDING/RUNNING/PAUSED/COMPLETED/FAILED/TIMED_OUT/PARTIAL(`:23-31`)
- `@dataclass Participant` — name/simulation_name/firmware_path/status/logs/signal_traces/errors(`:34-44`)
- `@dataclass SimResult` — status/simulation_time_ns/participants/raw_report/metadata(`:47-55`)
- `@dataclass ModelConfig` — simulation_name/participants/registry_uri/timeout_s/signal_map(`:58-74`)
- `@dataclass SilTestConfig`(`adapter.py:49-64`)、`@dataclass SimReport`(`adapter.py:67-86`)

## 4. 配置 / 环境变量
本子系统不读取环境变量。默认值硬编码在 dataclass 字段:
- `SilTestConfig.registry_uri = "silkit://localhost:8500"`,`timeout_s = 30.0`(`src/yuleosh/sil/adapter.py:62-63`)
- `ModelConfig.registry_uri = "silkit://localhost:8500"`,`timeout_s = 30.0`(`src/yuleosh/sil/__init__.py:72-73`)

## 5. 调用示例
(注意:以下为基于源码签名的示例,但该包目前**无生产调用方**,见 §6。)
```python
# 依据 src/yuleosh/sil/__init__.py:81-103, :116-185
from yuleosh.sil import SILKitIntegration, ModelConfig

integration = SILKitIntegration()
integration.connect("silkit://localhost:8500")

result = integration.run_simulation({
    "simulation_name": "brake-system-test",
    "participants": {"ECU_01": "build/firmware.elf"},
    "registry_uri": "silkit://localhost:8500",
    "timeout_s": 45.0,
})
print(result.status)  # SimStatus.COMPLETED
```

## 6. 偏差 / 备注

### 6.1 ORPHAN(无生产调用方)— 已 Grep 验证
全仓库 Grep `yuleosh.sil` / `yuleosh.adapter` / `SILKit` / `SILKitIntegration`(排除 `sil/` 包自身)
**无任何匹配**(`src/yuleosh/sil/__init__.py` 与 `sil/adapter.py` 之间仅互相 import)。
即 `sil` 包未被 `pipeline`、`cli`、`ci`、`ui`、`cross` 等任何其他模块 import,属 **ORPHAN** 代码。

### 6.2 真实 SIL 在 `cross/`(QEMU subprocess),与 `sil` 包无关
`src/yuleosh/cross/sil_runner.py` 的 `QemuSilRunner` 才是真实 SIL 实现:
通过 `subprocess.Popen` 启动 QEMU 仿真并捕获串口输出(`cross/sil_runner.py:285`),
全文件围绕 QEMU 版本检查、`build_qemu_cmd()`、`run_expect_script` 等真实执行逻辑。
`sil` 包的 `SILKitAdapter.connect/run_simulation` 仅是 mock(`:123-126`, `:201-203`),
且**未被 `cross/sil_runner.py` 引用**。二者命名都含 "SIL" 但实现路径完全不同,易误导。

### 6.3 疑似全 mock,与文档声明相悖
- `SILKitAdapter.connect` docstring 声明「opens a VAsio connection via SIL Kit C API」,
  但实现仅为 `logger.info` + 置状态(`adapter.py:113-126`)。
- `run_simulation` 用 `time.sleep(0.05)` 模拟计算,`simulation_time_ns` 直接由 `timeout_s * 1e9` 算出
  (`adapter.py:201-221`),未运行任何固件。
- `parse_results` 为占位实现,自带注释「Placeholder: in production this deserializes protobuf / JSON」
  (`adapter.py:250-259`)。
结论:`sil` 包是 SIL Kit 集成的**桩/mock 骨架**,无真实 SIL 能力。

### 6.4 内部张力
`SILKitIntegration` docstring 称「within the yuleOSH Pipeline」(`__init__.py:7`),但 pipeline 实际
调用的是 `cross` 的 QEMU runner,而非本包(`sil`)。该文档声明与代码事实不符。

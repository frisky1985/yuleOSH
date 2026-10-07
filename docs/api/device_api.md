# device API 参考

> 代码根:`src/yuleosh/device/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

设备管理层(Device Management Layer),平台级资源层:管理 HIL 目标板/测试设备池的注册、状态、锁、调度、健康看门狗与并行执行。位于单板操作层(`hardware.HardwareDeployer`)之上,pipeline hil-test step 之下。`src/yuleosh/device/__init__.py:5-21`

核心职责由 `DeviceManager` 门面统一暴露:组合 `DeviceRegistry`(SQLite 持久化)与 `Allocator`(资源分配状态机),并可按需装配 `DevicePool`(并行执行)与 `DeviceWatchdog`(健康探测)。`src/yuleosh/device/__init__.py:51-82`

> ⚠️ **非 ORPHAN**:本子系统有真实生产调用方,见 §6。

## 2. HTTP 端点

本子系统(`src/yuleosh/device/`)**不对外暴露 REST 端点**——它只通过 CLI 与 Python API 提供能力,所有公共符号均为进程内 Python 接口。

> 备注:对外 REST 包装由独立模块 `src/yuleosh/api/device_ui.py` 提供(它复用本包 `Device` / `DeviceRegistry`,见 `src/yuleosh/api/device_ui.py:33-34`)。该 REST 层属于 `api` 子系统范畴,不在此文档展开。

CLI 入口:`src/yuleosh/device/cli.py`(`yuleosh device list|add|remove|check|events|acquire|release`),由 `src/yuleosh/cli/main.py:387,987` 挂载。

## 3. Python 公共 API

### 3.1 模块级函数

本子系统无独立模块级业务函数;公共能力经类方法暴露。以下列出各模块构造/便捷入口:

| 函数/入口 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `DeviceManager.list_devices` | `list_devices(self) -> list[Device]` | 列出所有设备 | `src/yuleosh/device/__init__.py:64` |
| `DeviceManager.add_device` | `add_device(self, *args, **kwargs) -> Device` | 注册设备(转发至 registry) | `src/yuleosh/device/__init__.py:67` |
| `DeviceManager.remove_device` | `remove_device(self, device_id: str) -> bool` | 移除设备 | `src/yuleosh/device/__init__.py:70` |
| `DeviceManager.get_device` | `get_device(self, device_id: str) -> Device \| None` | 按 id 查设备 | `src/yuleosh/device/__init__.py:73` |
| `DeviceManager.check` | `check(self, device_id: str) -> Device \| None` | 单设备健康检查(转发 registry.get_device) | `src/yuleosh/device/__init__.py:76` |
| `DeviceManager.list_events` | `list_events(self, device_id: str \| None = None, limit: int = 100)` | 事件日志 | `src/yuleosh/device/__init__.py:80` |
| `Allocator.acquire` | `acquire(self, platform=None, job_id="adhoc", timeout=120.0, ttl_seconds=None, preferred_device=None) -> Optional[Device]` | 获取可用设备(超时返回 None) | `src/yuleosh/device/allocator.py:57` |
| `Allocator.release` | `release(self, device_id: str, job_id: str \| None = None) -> bool` | 释放设备(可选校验 job 归属) | `src/yuleosh/device/allocator.py:145` |
| `Allocator.expire_stale` | `expire_stale(self, now_iso: str \| None = None) -> int` | 回收超 TTL 的分配,返回回收数 | `src/yuleosh/device/allocator.py:191` |
| `DeviceRegistry.add_device` | `add_device(self, name, platform, flasher="openocd", flasher_config=None, port=None, serial=None, device_id=None) -> Device` | 写入设备记录 + 注册事件 | `src/yuleosh/device/registry.py:133` |
| `DeviceRegistry.get_device` | `get_device(self, device_id: str) -> Optional[Device]` | 按 id 查 | `src/yuleosh/device/registry.py:173` |
| `DeviceRegistry.get_device_by_name` | `get_device_by_name(self, name: str) -> Optional[Device]` | 按 name 查 | `src/yuleosh/device/registry.py:179` |
| `DeviceRegistry.list_devices` | `list_devices(self) -> list[Device]` | 列出全部(按 name 排序) | `src/yuleosh/device/registry.py:185` |
| `DeviceRegistry.remove_device` | `remove_device(self, device_id: str) -> bool` | 有活跃分配时拒绝移除 | `src/yuleosh/device/registry.py:189` |
| `DeviceRegistry.update_device_state` | `update_device_state(self, device_id, state: DeviceState, current_job=None, firmware_version=None, last_seen=None) -> Optional[Device]` | 更新设备状态 | `src/yuleosh/device/registry.py:206` |
| `DeviceRegistry.create_allocation` | `create_allocation(self, device_id, job_id, ttl_seconds=1800) -> Allocation` | 写分配记录 | `src/yuleosh/device/registry.py:244` |
| `DeviceRegistry.get_active_allocations` | `get_active_allocations(self) -> list[Allocation]` | 活跃分配列表 | `src/yuleosh/device/registry.py:273` |
| `DeviceRegistry.get_allocation_for_device` | `get_allocation_for_device(self, device_id) -> Optional[Allocation]` | 设备当前活跃分配 | `src/yuleosh/device/registry.py:279` |
| `DeviceRegistry.release_allocation` | `release_allocation(self, alloc_id, job_id=None) -> bool` | 释放分配(可校验 job) | `src/yuleosh/device/registry.py:288` |
| `DeviceRegistry.expire_allocation` | `expire_allocation(self, alloc_id) -> bool` | 标记分配过期 | `src/yuleosh/device/registry.py:305` |
| `DeviceRegistry.record_event` | `record_event(self, device_id, event_type: DeviceEventType, detail="") -> DeviceEvent` | 记录事件 | `src/yuleosh/device/registry.py:314` |
| `DeviceRegistry.list_events` | `list_events(self, device_id=None, limit=100) -> list[DeviceEvent]` | 事件日志 | `src/yuleosh/device/registry.py:335` |
| `DevicePool.run` | `run(self, tasks: list[dict]) -> list[dict]` | 并发执行任务列表 | `src/yuleosh/device/pool.py:67` |
| `DeviceWatchdog.start` | `start(self) -> None` | 启动后台探测线程 | `src/yuleosh/device/watchdog.py:76` |
| `DeviceWatchdog.stop` | `stop(self) -> None` | 停止探测线程 | `src/yuleosh/device/watchdog.py:87` |
| `DeviceWatchdog.scan_once` | `scan_once(self) -> dict` | 单轮探测,返回 `{device_id: state}` 变更表 | `src/yuleosh/device/watchdog.py:102` |
| `DeviceWatchdog.recover` | `recover(self, device_id: str) -> bool` | 人工确认设备恢复 → ONLINE | `src/yuleosh/device/watchdog.py:189` |

### 3.2 公共类

| 类 | 关键方法(签名) | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `DeviceManager` | `__init__(self, db_path=None, default_ttl: int = 1800)`;见 3.1 便捷方法 | 设备层门面,组合 Registry+Allocator | `src/yuleosh/device/__init__.py:51,58` |
| `DeviceRegistry` | `__init__(self, db_path: Optional[str\|Path] = None)` | SQLite 持久化的设备/分配/事件存储 | `src/yuleosh/device/registry.py:84,91` |
| `Allocator` | `__init__(self, registry: DeviceRegistry, default_ttl: int = 1800)` | 设备分配器(acquire/release/排队/超时/过期回收) | `src/yuleosh/device/allocator.py:37,48` |
| `DevicePool` | `__init__(self, allocator: Allocator, max_workers: int = 4, acquire_timeout: float = 120.0)` | 多设备并行执行器 | `src/yuleosh/device/pool.py:42,55` |
| `DeviceWatchdog` | `__init__(self, registry: DeviceRegistry, probe=None, interval=60.0, fail_threshold=2, fault_threshold=3, auto_release=True)` | 健康看门狗(定期探测,掉线/故障状态迁移) | `src/yuleosh/device/watchdog.py:34,53` |

**异常类:**

| 异常 | 用途 | 文件:行 |
| --- | --- | --- |
| `AllocationError(Exception)` | 分配/释放非法操作 | `src/yuleosh/device/allocator.py:29` |
| `DeviceUnavailableError(AllocationError)` | acquire 超时,无可用设备 | `src/yuleosh/device/allocator.py:33` |

### 3.3 关键数据结构

| 结构 | 说明 | 文件:行 |
| --- | --- | --- |
| `DeviceState(str, Enum)` | `UNKNOWN/ONLINE/BUSY/OFFLINE/FAULT` | `src/yuleosh/device/models.py:23` |
| `AllocationStatus(str, Enum)` | `ACTIVE/RELEASED/EXPIRED` | `src/yuleosh/device/models.py:33` |
| `DeviceEventType(str, Enum)` | `REGISTERED/REMOVED/ONLINE/OFFLINE/BUSY/RELEASED/FAULT/RECOVERED` | `src/yuleosh/device/models.py:41` |
| `@dataclass Device` | 一块 HIL 目标板:`id,name,platform,flasher,flasher_config,port,serial,state,current_job,firmware_version,last_seen,created_at,updated_at`;含 `to_dict()/from_dict()/is_available()` | `src/yuleosh/device/models.py:54`-`115` |
| `@dataclass Allocation` | 一次设备占用:`id,device_id,job_id,acquired_at,released_at,ttl_seconds,status`;含 `to_dict()/from_dict()/is_expired()` | `src/yuleosh/device/models.py:118`-`165` |
| `@dataclass DeviceEvent` | 事件日志:`id,device_id,event_type,detail,created_at`;含 `to_dict()` | `src/yuleosh/device/models.py:168`-`185` |

## 4. 配置 / 环境变量

| 变量 | 用途 | 文件:行 |
| --- | --- | --- |
| `YULEOSH_DEVICE_DB` | 覆盖默认设备 DB 路径(默认 `~/.yuleosh/device.db`),用于测试/多租户 | `src/yuleosh/device/registry.py:73-77` |

## 5. 调用示例

以下示例基于真实公共 API(`DeviceManager` / `Allocator` / `DeviceRegistry`),见 `src/yuleosh/device/__init__.py:13-21`。

**示例 1:注册设备并分配/释放(进程内)**

```python
from yuleosh.device import DeviceManager

mgr = DeviceManager(db_path="~/.yuleosh/device.db")          # __init__.py:58
dev = mgr.add_device(                                        # __init__.py:67
    name="board-01", platform="s32k",
    flasher="openocd",
    flasher_config={"interface": "stlink", "target": "s32k344"},
)
try:
    acquired = mgr.allocator.acquire(platform="s32k", job_id="run-123")  # allocator.py:57
    # ... 通过 hardware.HardwareDeployer 刷写/测试 ...
finally:
    mgr.allocator.release(acquired.id, job_id="run-123")     # allocator.py:145
```

**示例 2:并行执行多设备任务(DevicePool)**

```python
from yuleosh.device import DeviceManager
from yuleosh.device.pool import DevicePool                    # pool.py:42

mgr = DeviceManager()
pool = DevicePool(mgr.allocator)                              # pool.py:55

def run_test(dev):
    return {"ok": True, "device": dev.name}

results = pool.run([                                          # pool.py:67
    {"platform": "s32k", "job_id": "t1", "fn": run_test},
    {"platform": "s32k", "job_id": "t2", "fn": run_test},
])
```

**示例 3:健康看门狗(依赖注入探测函数)**

```python
from yuleosh.device import DeviceManager
from yuleosh.device.watchdog import DeviceWatchdog            # watchdog.py:34

mgr = DeviceManager()
probe = lambda dev: True   # 真实场景接入 flasher 探测
wd = DeviceWatchdog(mgr.registry, probe=probe, interval=30.0)  # watchdog.py:53
wd.start()                  # watchdog.py:76
# ... wd.scan_once() / wd.stop() ...
```

## 6. 偏差 / 备注

- **非 ORPHAN(实证)**:在 `src/yuleosh/` 范围内 Grep `yuleosh.device` 命中多个生产调用方:
  - `src/yuleosh/cli/main.py:387`(`from yuleosh.device.cli import build_device_parser`)
  - `src/yuleosh/cli/main.py:987`(`from yuleosh.device.cli import handle_device_command`)
  - `src/yuleosh/api/dashboard_v2.py:342`(`from yuleosh.device.registry import DeviceRegistry`)
  - `src/yuleosh/api/device_ui.py:33-34`(`from yuleosh.device.models import ...`、`from yuleosh.device.registry import DeviceRegistry`)
  → 本子系统为活跃使用代码,**非 ORPHAN**。

- **REST 边界**:本包无 REST 端点;对外 REST 由 `api/device_ui.py` 提供(属于 `api` 子系统)。文档 §2 因此标 N/A。

- **`DevicePool.TaskFn` / `Watchdog.ProbeFn` 类型别名**:`TaskFn = Callable[[Device], object]`(`pool.py:39`)、`ProbeFn = Callable[[Device], bool]`(`watchdog.py:31`),供调用方注入任务/探测逻辑。

- **`DeviceWatchdog` 探测默认恒 True**:`probe` 默认 `lambda dev: True`(`watchdog.py:65`),即不接入真实 flasher 探测时不会标记掉线;真实探测需由调用方注入。

- **`DeviceManager.check` 未接看门狗**:当前仅转发 `registry.get_device`(`__init__.py:76-78`),注释说明"未来接 watchdog 探测逻辑",属预留接口。

- **死代码/未接线**:`Allocator` 与 `DeviceWatchdog` 在仓库内**未见**由 pipeline hil-test step 实际驱动(仅被 `cli`/`api`/单测引用);`DevicePool` 亦未发现生产调用方(可能仅用于设计/测试)。如需确认,建议进一步 Grep 调用 `DevicePool` / `DeviceWatchdog` 的具体消费点。

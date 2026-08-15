# yuleOSH 设备管理层（Device Management Layer）设计

> **版本**: v0.1 · 2026-08-15
> **状态**: 设计草案（老板已拍板方案 B：设备注册表+调度）
> **关联**: 产品说明书 Phase 1 HIL 主线 · `src/yuleosh/hardware/`（单板操作层）

---

## 1. 为什么需要这一层

现有 `hardware/` 模块是**单板操作层**（HardwareDeployer：flash → monitor → analyze），解决"怎么操作一块板"。设备管理层解决的是**资源问题**：

- 有多少板、什么状态（在线/忙/离线/故障）
- 这块板现在给谁用（锁），用完释放
- 多块板并行跑测试（多任务不互踩）
- 板子掉线了怎么办（看门狗/自动释放）

没有这一层，HIL 在真实使用（多人共享、多板并行、长时间跑）时会互相踩设备、无法诊断掉线、串行低效。

## 2. 架构定位

```
┌────────────────────────────────────────────────────┐
│ pipeline step: hil-test                             │
│    "需要 1 块 S32K，30 分钟"                        │
└──────────────────────┬─────────────────────────────┘
                       ▼
┌────────────────────────────────────────────────────┐
│ 设备管理层（新增，src/yuleosh/device/）             │
│  registry → allocator → watchdog → pool            │
│  职责：资源注册/状态/锁/调度/健康                    │
└──────────────────────┬─────────────────────────────┘
                       ▼ 分配到的设备
┌────────────────────────────────────────────────────┐
│ 单板操作层（现有，src/yuleosh/hardware/）           │
│  HardwareDeployer: flash → monitor → analyze       │
│  职责：对一块板的实际操作                           │
└────────────────────────────────────────────────────┘
```

**分层原则**：
- 设备管理层不知道"怎么刷写"，只管理"设备资源"
- 单板操作层不知道"谁在用板"，只执行操作
- 边界：设备层通过 `hardware.HardwareDeployer` 做健康探测；操作层通过设备层拿设备句柄

## 3. 模块结构（src/yuleosh/device/）

| 文件 | 职责 | 依赖 |
|---|---|---|
| `__init__.py` | 公开 API（DeviceManager 门面） | — |
| `models.py` | 数据模型（Device/Allocation/DeviceEvent） | dataclasses |
| `registry.py` | 设备注册表（SQLite 持久化，增删查/状态更新） | models, store |
| `allocator.py` | 资源分配（acquire/release/排队/超时/过期回收） | registry, models |
| `watchdog.py` | 健康看门狗（心跳探测、掉线标记、自动释放） | registry, hardware |
| `pool.py` | 并行执行器（多设备并发跑任务） | allocator, hardware |
| `cli.py` | CLI 命令（yuleosh device ...） | registry, allocator |

**命名**：按领域职责命名（registry/allocator/watchdog/pool），不用 utils/helpers/common（老板铁律）。

## 4. 数据模型

### 4.1 Device（设备）

```python
class DeviceState(str, enum.Enum):
    UNKNOWN  = "unknown"    # 未探测
    ONLINE   = "online"     # 在线可用
    BUSY     = "busy"       # 被任务占用
    OFFLINE  = "offline"    # 掉线
    FAULT    = "fault"      # 多次探测失败，需人工

@dataclass
class Device:
    id: str                 # UUID
    name: str               # 显示名 "s32k-lab-01"
    platform: str           # "s32k" / "stm32" / "esp32"（决定探测/测试适配）
    flasher: str            # "openocd" / "jlink" / "esptool"
    flasher_config: dict    # 具体刷写配置（interface/target 等）
    port: str | None        # 串口路径 /dev/ttyUSB0
    serial: str | None      # USB 序列号（自动发现标识）
    state: DeviceState      # 当前状态
    current_job: str | None # 占用中的 job_id
    firmware_version: str | None
    last_seen: datetime | None   # 看门狗心跳时间
    created_at: datetime
    updated_at: datetime
```

### 4.2 Allocation（分配记录）

```python
@dataclass
class Allocation:
    id: str
    device_id: str
    job_id: str            # 哪个 pipeline run / 任务占用
    acquired_at: datetime
    released_at: datetime | None
    ttl_seconds: int       # 默认 1800，防任务崩溃后板子卡死
    status: str            # "active" / "released" / "expired"
```

### 4.3 DeviceEvent（事件日志）

```python
@dataclass
class DeviceEvent:
    id: str
    device_id: str
    event_type: str        # "registered" / "online" / "offline" / "busy" /
                           #  "released" / "fault" / "recovered"
    detail: str
    created_at: datetime
```

**存储**：SQLite 表 `devices` / `allocations` / `device_events`，复用 yuleOSH 的 store 后端（本地 SQLite，生产 PostgreSQL 兼容）。

## 5. 核心流程

### 5.1 注册与发现

```
yuleosh device add --name lab-01 --platform s32k --flasher jlink --serial <sn>
yuleosh device add --config devices.yaml      # 批量导入（方案 A 种子）
yuleosh device discover                       # 自动探测（可选，Phase 2）
```

### 5.2 分配（acquire）

```
请求: acquire(platform="s32k", timeout=120)
  → 查 ONLINE 且空闲的设备（FIFO 排序）
  → 标记 BUSY + current_job
  → 写 allocation（status=active, ttl=1800）
  → 返回设备句柄
超时无可用 → 返回 None（调用方排队或失败）
```

### 5.3 释放（release）

```
release(device_id, job_id)
  → 校验 job 匹配（防误释放他人板子）
  → 状态回 ONLINE，current_job 清空
  → allocation status=released
```

### 5.4 过期回收（防卡死）

后台线程每分钟扫描 active allocation：
- `now - acquired_at > ttl` → 强制释放 + 设备回 ONLINE + 记事件
- 防任务崩溃/断电后板子永久 BUSY

### 5.5 看门狗（健康）

```
watchdog 每 60s 对 ONLINE/BUSY 设备做探测：
  探测 = 通过 flasher 查 target（openocd -c "targets" / jlink 连接）
  ├─ 成功 → last_seen 更新，保持状态
  ├─ 失败 1-2 次 → OFFLINE + 自动释放 allocation + 记事件
  └─ 失败 ≥3 次 → FAULT（需人工，不进分配池）
```

### 5.6 并行执行（pool）

```
pool.run(jobs=[{device: s32k-lab-01, test: ...}, ...])
  → 每 job 调 allocator.acquire（或指定设备）
  → ThreadPoolExecutor 并发跑 HardwareDeployer 流程
  → 全部完成/失败 → 统一 release
  → 汇总结果
```

## 6. Pipeline 集成点

新增 step：**hil-test**（对齐现有 test_qemu / test-qualification 模式）

```
spec 中声明 HIL 场景（GIVEN/WHEN/THEN）
  → hil-test step:
      1. allocator.acquire(platform)         # 拿板
      2. HardwareDeployer.flash(firmware)    # 刷写
      3. 跑测试用例（串口输出断言 / GPIO 采样）
      4. allocator.release()                 # 还板
      5. 生成 hil-test.json（证据进证据包）
```

**证据包**：HIL 报告进入 ASPICE SWE.6 合格性测试证据（真硬件验证 = 强证据）。

## 7. CLI 命令

```
yuleosh device list            # 状态总览（含 Dashboard 数据源）
yuleosh device add             # 注册设备
yuleosh device remove          # 移除设备
yuleosh device check           # 单设备健康探测
yuleosh device acquire         # 手动锁（调试用）
yuleosh device release         # 手动释放
yuleosh device events          # 查看事件日志
```

## 8. Dashboard 集成

- 设备状态卡片（online/busy/offline/fault 彩色状态）
- 设备占用历史（谁在用、多久）
- 看门狗告警列表
- 数据源：device REST API（对齐现有 api/v1 模式）

## 9. 测试策略（无硬件也能测）

| 层 | 测试 | 方式 |
|---|---|---|
| registry | CRUD/状态更新/持久化 | 纯单测（SQLite tmp） |
| allocator | acquire/release/排队/超时/过期回收 | 纯单测（mock registry） |
| watchdog | 掉线→OFFLINE→自动释放→FAULT | mock flasher 探测结果 |
| pool | 并行执行/结果汇总 | mock HardwareDeployer |
| cli | 命令解析/输出 | 单测 |
| **真实 HIL** | S32K 真板刷写+测试 | 有硬件时集成测试（skip 无硬件） |

**验收底线**（对齐 RULES.md §7 模块化设计优先）：
- 构建通过（无新 -Werror/ruff 错误）
- 单测覆盖 registry/allocator/watchdog/pool 核心逻辑
- 覆盖率 ≥80%（新增模块）

## 10. 落地顺序

| 步骤 | 内容 | 依赖 | 可测性 |
|---|---|---|---|
| S1 | models + registry（SQLite） | store | ✅ 纯单测 |
| S2 | allocator（锁/排队/超时/过期） | S1 | ✅ 纯单测 |
| S3 | watchdog + pool | S2 + hardware | ✅ mock 设备 |
| S4 | CLI + pipeline step + Dashboard | S3 | ✅ mock 设备 |
| S5 | 真实 S32K 适配（openocd/jlink 探测） | S4 + 硬件 | ⚠️ 需板子 |

**S1-S4 不需要真实硬件**（mock 设备即可开发验证），S5 等 S32K 板卡到位。

---

## 附：与产品说明书的关系

- Phase 1 "HIL 真实硬件验证（S32K）" 的实现路径 = 本设计 S1→S5
- 企业版功能边界（已拍板）：HIL 适配器闭源归 Enterprise → 设备管理层核心（registry/allocator）可作为开源 CLI 能力，高级并行调度/多团队共享池归企业版（待细化）
- 设备状态可视化 = Dashboard 新增模块，支撑"组织级看板产品化"（Phase 1 另一主线）

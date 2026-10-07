# 模块设计速写：loop_engine（系统级反馈闭环引擎）

> 包：`src/yuleosh/loop_engine/` ｜ 规模：13 .py ≈ 6306 行
> 关联：生产 Web 运行时为 ORPHAN；目前是 CLI 工具集

## 职责
系统级事件总线 + 反馈回路编排引擎：发布/订阅 `LoopEvent`、链式触发 4 个反馈回路（缺陷→需求 / 现场缺陷→FMEA / KPI→改进 / KG 自进化）、spec-delta 生成与 RCA。证据：`loop_engine/__init__.py:5-20`、`event_bus.py:1286-1303`。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `loop_engine/__init__.py` (137) | 包入口 | `LoopEngine` `:48`；`__all__` `:130` |
| `event_bus.py` (2301) | 核心总线 | `LoopEventType` `:83`；`LoopEvent` `:145`；`SystemEventBus` `:1286`；单例 `loop_bus = SystemEventBus(persistence_enabled=False)` `:2281`；`TokenBucket` `:389`；`DeadLetterQueue` `:518`；`EventQueuePersistence` `:939` |
| `chain.py` (405) | 链式规则 | `ChainConfig` `:182`；`ChainContext` `:86`；`DEFAULT_CHAIN_RULES` `:65`；`default_chain_config` `:394` |
| `feedback_handlers/*.py` (5, 1134) | 4 个回路 handler | `Loop1DefectToReqHandler` `loop1:50`（`subscribed_events` `:71`、`handle` `:83`）；`Loop2FieldToFMEAHandler` `loop2:108`；`Loop3KPIToImproveHandler` `loop3:44`；`Loop4KGSelfEvolveHandler` `loop4:51` |
| `rca_engine.py` (699) | RCA | `RCAEngine` `:181`；`RCAReport` `:38`；`generate_improvement_ticket` `:589` |
| `spec_delta_gen.py` (280) | spec-delta | `SpecDeltaGenerator` `:151`；`SpecDelta` `:56` |
| `cli.py` (760) | CLI 入口 | `build_loop_subparser` `:48`；`handle_loop_command`；各子命令 `status` `:109` |

## 公共 API / 入口点
- `LoopEngine(event_bus=...)`：`register_handler` `:63` / `start` `:77` / `stop` `:83` / `run_loop_once` `:94` / `status` `:114`
- `loop_bus` 单例：`on/off/emit` `:1511/:1544/:1567`、`emit_signed` `:1766`、`emit_async` `:1810`、`history` `:2222`、`stats` `:2240`、`dead_letter` `:1458`
- `LoopEventType` `:83` / `LoopEvent` `:145`；`ChainConfig`/`ChainContext`/`default_chain_config`；`FeedbackHandler`/`ActionResult`/`register_handler`/`get_registered_handlers`（`feedback_handlers/base.py:89/:47/:162/:181`）
- `SpecDeltaGenerator`/`SpecDelta`；`RCAEngine`/`RCAReport`

## 生产接线（真实调用方）
- **仅 CLI**：`cli/main.py:561` `from yuleosh.loop_engine.cli import build_loop_subparser`；`:991` `handle_loop_command`（`yuleosh loop ...`）。
- 包内部：`loop_engine/cli.py` 引用 `LoopEngine`/`loop_bus` 等。
- **除 CLI 外，无任何 API 路由 / pipeline step / hook / 后台循环引用 `loop_engine`** → 对生产 Web 服务运行时而言是 ORPHAN。

## 运行时触发方式
仅 CLI 子命令：`_build_engine()`（`cli.py:48`）每次命令才实例化 `LoopEngine` 并手动订阅 4 个 Handler（`cli.py:58-90`）。`emit()` 同步发布（`event_bus.py:1567`），`emit_async` `:1810` 才走线程池 worker。默认单例 `loop_bus` `persistence_enabled=False`（`:2281`），**无后台 worker 线程**。

## 环境变量 / 配置
- `YULEOSH_EVENT_SOURCE_SECRET`（`event_bus.py:271`，HMAC 默认空串）
- `OSH_HOME`（持久化/死信基目录 `:932`、`:1380` `OSH_HOME/.yuleosh/loop/dead_letter_queue.json`）

## 存储 / 状态模型
主要内存（历史上限 2000 `:1330-1331`、去重表、统计字典）；可选 JSON 持久化（`EventQueuePersistence` `:939`，`pending_events.json`/`processed_events.json`）默认关闭；死信队列 JSON（`:1379-1382`）；链式规则 `ChainConfig` 内存结构支持 save/load JSON（`:351/:363`）默认不持久化。

## 偏差 / 死代码（设计文档必记）
- **D1：生产 Web 运行时中闭环实际不运行**——`loop_bus` 在 API 服务进程零订阅者、无 worker 线程，事件总线是 no-op。设计文档须明确：loop_engine 当前是「CLI 工具集」，非驻后台闭环。
- **D2：`@register_handler` 装饰器注册表在真实路径是死代码**——4 个 Handler 头部用 `@register_handler`（`loop1:49` 等），但 CLI `_build_engine()` 未用 `get_registered_handlers()`，而是手动 import+实例化+`engine.register_handler`（`cli.py:56-90`）。两条注册机制并存、装饰器那条无接线效果。
- **D3：Handler 对 KB 硬依赖被 try/except 吞掉**——缺 KG 后端时对应 Loop 静默失效（`cli.py:59-90` 仅 `log.warning(... handler init skipped)`）。

## 规模
13 .py ≈ 6306 行。

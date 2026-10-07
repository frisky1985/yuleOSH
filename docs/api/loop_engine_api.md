# 闭环反馈引擎 (`loop_engine`) API 参考

> 代码根:`src/yuleosh/loop_engine/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`loop_engine` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/loop_engine.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_build_engine` | `()` | 构建并初始化 LoopEngine。 | `loop_engine/cli.py:48` |
| `_get_kg_store` | `()` | 获取 KG 存储后端 (如果可用)。 | `loop_engine/cli.py:96` |
| `cmd_status` | `(args)` | `yuleosh loop status` — 查看当前活跃的 loop 事件和状态。 | `loop_engine/cli.py:109` |
| `cmd_run` | `(args)` | `yuleosh loop run <name>` — 手动触发指定 loop。 | `loop_engine/cli.py:205` |
| `cmd_config` | `(args)` | `yuleosh loop config` — 查看/修改 loop 参数。 | `loop_engine/cli.py:279` |
| `cmd_dead_letter` | `(args)` | `yuleosh loop dead-letter` — 死信队列管理 (I4)。 | `loop_engine/cli.py:370` |
| `cmd_audit` | `(args)` | `yuleosh loop audit` — 审计日志查询 (ACC-505)。 | `loop_engine/cli.py:429` |
| `cmd_rollback` | `(args)` | `yuleosh loop rollback <journal_id>` — 回滚操作 (ACC-506)。 | `loop_engine/cli.py:546` |
| `_load_config` | `(config_path: str)` | 加载 loop 配置文件。 | `loop_engine/cli.py:644` |
| `_save_config` | `(config_path: str, config: dict)` | 保存 loop 配置文件。 | `loop_engine/cli.py:655` |
| `build_loop_subparser` | `(subparsers)` | 构建 `yuleosh loop` 子命令解析器。 | `loop_engine/cli.py:666` |
| `handle_loop_command` | `(args)` | Dispatch loop subcommands. | `loop_engine/cli.py:744` |
| `_get_chain_classes` | `()` | 延迟加载 ChainConfig 和 ChainContext (避免循环导入)。 | `loop_engine/event_bus.py:69` |
| `_default_persistence_path` | `()` | Return a safe default for EventQueuePersistence base_path. | `loop_engine/event_bus.py:921` |
| `register_handler` | `(cls: type[FeedbackHandler])` | 装饰器: 自动将 FeedbackHandler 子类注册到全局注册表。 | `loop_engine/feedback_handlers/base.py:162` |
| `get_registered_handlers` | `()` | 返回所有已注册的 FeedbackHandler 类。 | `loop_engine/feedback_handlers/base.py:181` |
| `unregister_handler` | `(name: str)` | 取消注册 handler (用于测试)。 | `loop_engine/feedback_handlers/base.py:186` |
| `clear_registry` | `()` | 清除所有注册 (用于测试)。 | `loop_engine/feedback_handlers/base.py:191` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `LoopEngine` | `()` | Loop Engineering 引擎 — 编排事件总线与反馈回路。 | `loop_engine/__init__.py:48` |
| `ChainContext` | `()` | 链式触发上下文 — 追踪当前链式调用的状态。 | `loop_engine/chain.py:86` |
| `ChainConfig` | `()` | 链式触发规则配置。 | `loop_engine/chain.py:182` |
| `LoopEventType` | `(str, enum.Enum)` | 系统级 Loop 事件类型枚举。 | `loop_engine/event_bus.py:83` |
| `LoopEvent` | `()` | 系统级事件数据模型。 | `loop_engine/event_bus.py:145` |
| `Subscription` | `()` | 订阅记录。 | `loop_engine/event_bus.py:233` |
| `SourceValidator` | `()` | 事件来源验证器。 | `loop_engine/event_bus.py:253` |
| `TokenBucket` | `()` | Token Bucket 速率限制器。 | `loop_engine/event_bus.py:389` |
| `DeadLetterQueue` | `()` | 死信队列 — 存储超限/验证失败的事件。 | `loop_engine/event_bus.py:518` |
| `AuditLog` | `()` | 审计日志 — 记录完整的事件处理历史。 | `loop_engine/event_bus.py:720` |
| `EventQueuePersistence` | `()` | 事件队列持久化 — 崩溃后自动恢复未消费的事件。 | `loop_engine/event_bus.py:939` |
| `CoalescingGroup` | `()` | 聚合窗口内的事件分组。 | `loop_engine/event_bus.py:1118` |
| `CoalescingManager` | `()` | 时间窗口聚合管理器。 | `loop_engine/event_bus.py:1152` |
| `SystemEventBus` | `()` | 系统级事件总线 (LE-001) — 生产加固版 (I4)。 | `loop_engine/event_bus.py:1286` |
| `RCAReport` | `()` | RCA 分析报告。 | `loop_engine/rca_engine.py:38` |
| `RCAEngine` | `()` | 根因分析引擎。 | `loop_engine/rca_engine.py:181` |
| `ChangeType` | `(str, enum.Enum)` | Spec-delta 变更类型。 | `loop_engine/spec_delta_gen.py:40` |
| `SpecDelta` | `()` | 单个 spec-delta 记录。 | `loop_engine/spec_delta_gen.py:57` |
| `SpecDeltaGenerator` | `()` | Spec-delta 自动生成器。 | `loop_engine/spec_delta_gen.py:151` |
| `ActionResult` | `()` | 反馈回路处理结果。 | `loop_engine/feedback_handlers/base.py:48` |
| `FeedbackHandler` | `(abc.ABC)` | 反馈回路处理器抽象基类。 | `loop_engine/feedback_handlers/base.py:89` |
| `Loop1DefectToReqHandler` | `(FeedbackHandler)` | Loop 1: 缺陷→需求回溯闭环。 | `loop_engine/feedback_handlers/loop1_defect_to_req.py:50` |
| `FMEAEntry` | `()` | FMEA 条目数据模型。 | `loop_engine/feedback_handlers/loop2_field_to_fmea.py:51` |
| `Loop2FieldToFMEAHandler` | `(FeedbackHandler)` | Loop 2: 现场缺陷→FMEA 闭环。 | `loop_engine/feedback_handlers/loop2_field_to_fmea.py:108` |
| `Loop3KPIToImproveHandler` | `(FeedbackHandler)` | Loop 3: KPI→RCA→改进闭环。 | `loop_engine/feedback_handlers/loop3_kpi_to_improve.py:44` |
| `Loop4KGSelfEvolveHandler` | `(FeedbackHandler)` | Loop 4: KG 置信度自进化。 | `loop_engine/feedback_handlers/loop4_kg_self_evolve.py:51` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `LoopEngine.__init__` | `(self, event_bus: SystemEventBus | None)` | — | `loop_engine/__init__.py:57` |
| `LoopEngine.register_handler` | `(self, handler: FeedbackHandler)` | 注册一个 FeedbackHandler 并订阅其监听的事件。 | `loop_engine/__init__.py:63` |
| `LoopEngine.start` | `(self)` | 启动 Loop Engine — 自动加载所有已注册的 FeedbackHandler。 | `loop_engine/__init__.py:77` |
| `LoopEngine.stop` | `(self)` | 停止 Loop Engine。 | `loop_engine/__init__.py:83` |
| `LoopEngine.run_loop_once` | `(self, loop_name: str, **kwargs)` | 手动触发指定 loop（用于 CLI 或测试）。 | `loop_engine/__init__.py:94` |
| `LoopEngine.status` | `(self)` | 获取当前引擎状态。 | `loop_engine/__init__.py:115` |
| `ChainContext.__init__` | `(self, root_event_id: str, max_depth: int)` | — | `loop_engine/chain.py:100` |
| `ChainContext.can_chain` | `(self, handler_name: str, event_type: str)` | 检查是否可以继续链式触发。 | `loop_engine/chain.py:108` |
| `ChainContext.mark_visited` | `(self, handler_name: str, event_type: str)` | 标记 handler 和事件已访问。 | `loop_engine/chain.py:136` |
| `ChainContext.child_context` | `(self, handler_name: str, event_type: str)` | 创建子上下文 (深度 +1，继承 visited 记录)。 | `loop_engine/chain.py:141` |
| `ChainContext.to_dict` | `(self)` | — | `loop_engine/chain.py:162` |
| `ChainConfig.__init__` | `(self, max_depth: int)` | — | `loop_engine/chain.py:194` |
| `ChainConfig.max_depth` | `(self)` | — | `loop_engine/chain.py:202` |
| `ChainConfig.max_depth` | `(self, value: int)` | — | `loop_engine/chain.py:206` |
| `ChainConfig.add_rule` | `(self, trigger_event: str, target_loop: str)` | 添加链式触发规则。 | `loop_engine/chain.py:213` |
| `ChainConfig.remove_rule` | `(self, trigger_event: str, target_loop: str)` | 移除链式触发规则。 | `loop_engine/chain.py:240` |
| `ChainConfig.get_targets` | `(self, trigger_event: str)` | 获取触发事件对应的所有目标 handler 名称。 | `loop_engine/chain.py:259` |
| `ChainConfig.clear_rules` | `(self)` | 清除所有规则。 | `loop_engine/chain.py:270` |
| `ChainConfig.has_rule` | `(self, trigger_event: str, target_loop: str)` | 检查规则是否存在。 | `loop_engine/chain.py:275` |
| `ChainConfig.list_rules` | `(self)` | 列出所有规则。 | `loop_engine/chain.py:280` |
| `ChainConfig.get_event_for_handler` | `(self, handler_name: str)` | 获取激活指定 handler 需要发出的事件类型。 | `loop_engine/chain.py:286` |
| `ChainConfig.get_handler_for_event` | `(self, event_type: LoopEventType)` | 获取订阅指定事件类型的 handler 名称 (反向查找)。 | `loop_engine/chain.py:297` |
| `ChainConfig.register_handler_event` | `(self, handler_name: str, event_type: LoopEventType)` | 注册自定义 handler → 事件映射。 | `loop_engine/chain.py:311` |
| `ChainConfig.load_defaults` | `(self)` | 加载默认链式规则。 | `loop_engine/chain.py:325` |
| `ChainConfig.to_dict` | `(self)` | 序列化为字典。 | `loop_engine/chain.py:335` |
| `ChainConfig.from_dict` | `(cls, data: dict)` | 从字典反序列化。 | `loop_engine/chain.py:343` |
| `ChainConfig.save` | `(self, path: str)` | 保存到 JSON 文件。 | `loop_engine/chain.py:351` |
| `ChainConfig.load` | `(cls, path: str)` | 从 JSON 文件加载。 | `loop_engine/chain.py:364` |
| `LoopEvent.to_dict` | `(self)` | — | `loop_engine/event_bus.py:186` |
| `LoopEvent.from_dict` | `(cls, d: dict)` | — | `loop_engine/event_bus.py:204` |
| `SourceValidator.__init__` | `(self, secret: str, enabled: bool, whitelist: Optional[list[str]], auto_whitelist: bool)` | — | `loop_engine/event_bus.py:268` |
| `SourceValidator.enabled` | `(self)` | — | `loop_engine/event_bus.py:283` |
| `SourceValidator.set_enabled` | `(self, enabled: bool)` | — | `loop_engine/event_bus.py:286` |
| `SourceValidator.set_secret` | `(self, secret: str)` | — | `loop_engine/event_bus.py:290` |
| `SourceValidator.add_to_whitelist` | `(self, source: str)` | — | `loop_engine/event_bus.py:294` |
| `SourceValidator.remove_from_whitelist` | `(self, source: str)` | — | `loop_engine/event_bus.py:298` |
| `SourceValidator.set_auto_whitelist` | `(self, enabled: bool)` | 设置是否自动白名单（无白名单时信任所有来源）。 | `loop_engine/event_bus.py:303` |
| `SourceValidator.auto_whitelist_enabled` | `(self)` | — | `loop_engine/event_bus.py:309` |
| `SourceValidator.is_whitelisted` | `(self, source: str)` | — | `loop_engine/event_bus.py:313` |
| `SourceValidator.whitelist` | `(self)` | — | `loop_engine/event_bus.py:317` |
| `SourceValidator.sign` | `(self, event_id: str, source: str)` | 生成 HMAC-SHA256 签名。 | `loop_engine/event_bus.py:321` |
| `SourceValidator.verify` | `(self, event_id: str, source: str, signature: str)` | 验证事件来源签名或白名单。 | `loop_engine/event_bus.py:338` |
| `SourceValidator.validate_source` | `(self, event: LoopEvent)` | 验证事件来源 — 供 EventBus 内部调用。 | `loop_engine/event_bus.py:373` |
| `TokenBucket.__init__` | `(self, default_rate: float, default_burst: int, per_type_rates: Optional[dict[str, float]])` | Args: | `loop_engine/event_bus.py:402` |
| `TokenBucket.enabled` | `(self)` | — | `loop_engine/event_bus.py:419` |
| `TokenBucket.set_enabled` | `(self, enabled: bool)` | — | `loop_engine/event_bus.py:422` |
| `TokenBucket.set_rate` | `(self, event_type: str, rate: float)` | 设置某事件类型的速率。 | `loop_engine/event_bus.py:426` |
| `TokenBucket.check` | `(self, event_type: str)` | 检查是否允许通过。 | `loop_engine/event_bus.py:455` |
| `TokenBucket.consume` | `(self, event_type: str)` | 消费一个 token。 | `loop_engine/event_bus.py:477` |
| `TokenBucket.stats` | `(self)` | 返回速率限制统计。 | `loop_engine/event_bus.py:495` |
| `DeadLetterQueue.__init__` | `(self, max_retries: int, backoff_factor: float, store, persist_path: Optional[str], max_queue: int)` | — | `loop_engine/event_bus.py:528` |
| `DeadLetterQueue.max_retries` | `(self)` | — | `loop_engine/event_bus.py:552` |
| `DeadLetterQueue.backoff_factor` | `(self)` | — | `loop_engine/event_bus.py:556` |
| `DeadLetterQueue.max_queue` | `(self)` | — | `loop_engine/event_bus.py:560` |
| `DeadLetterQueue.enqueue` | `(self, event: LoopEvent, reason: str)` | 将事件加入死信队列。 | `loop_engine/event_bus.py:563` |
| `DeadLetterQueue.list` | `(self, limit: int)` | 列出死信队列内容。 | `loop_engine/event_bus.py:601` |
| `DeadLetterQueue.retry_all` | `(self, retry_callback: Optional[Callable[[dict], Any]])` | 重试所有死信事件。 | `loop_engine/event_bus.py:613` |
| `DeadLetterQueue.clear` | `(self)` | 清空死信队列。 | `loop_engine/event_bus.py:656` |
| `DeadLetterQueue.count` | `(self)` | 返回死信队列当前长度。 | `loop_engine/event_bus.py:668` |
| `DeadLetterQueue.persist_path` | `(self)` | — | `loop_engine/event_bus.py:700` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.loop_engine import <公共符号>
# 详见 docs/modules/loop_engine.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 7 处生产引用(Grep `yuleosh.loop_engine` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/loop_engine/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

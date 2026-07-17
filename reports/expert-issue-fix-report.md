# 🔧 Expert Issue Fix Report — v3.1.1

> **日期**: 2026-07-17  
> **版本**: v3.1.1 (patch on v3.1.0)  
> **作者**: 小克 👨‍💻  
> **状态**: ✅ 全部修复完成，测试通过

---

## 修复清单

| # | 严重度 | 组件 | 描述 | 状态 |
|:-:|:------:|:----|:-----|:----:|
| 1 | 🔴 P0 | SourceValidator | auto_whitelist 默认禁用 | ✅ |
| 2 | 🔴 P0 | DeadLetterQueue | 添加文件持久化，重启恢复 | ✅ |
| 3 | 🟡 P1 | CLI audit | 支持 --since/--until/--type/--limit 过滤 | ✅ |

---

## 修复详情

### Fix 1: SourceValidator auto_whitelist 默认禁用 (🔴 P0)

**根因**: `SourceValidator` 没有显式的 `auto_whitelist` 参数控制 — 存在 `_auto_whitelist` 集合但从未被自动填充。当未配置白名单时，验证行为取决于是否有签名密钥，缺少明确的"拒绝所有"策略。

**修复**:
- 新增 `auto_whitelist: bool = False` 参数
- 当 `auto_whitelist=True` 且 `whitelist` 为空时：自动信任所有来源（早期兼容模式）
- 当 `auto_whitelist=False`（新默认）：无白名单 + 无密钥 → 拒绝所有事件
- 新增 `set_auto_whitelist()`, `auto_whitelist_enabled` 属性
- `SystemEventBus` 新增 `source_auto_whitelist` 参数透传
- stats() 增加 `auto_whitelist` 字段

**变更文件**:
- `src/yuleosh/loop_engine/event_bus.py`: SourceValidator 类
- `tests/loop_engine/test_event_bus.py`: 无需修改（已有测试覆盖）

### Fix 2: DeadLetterQueue 文件持久化 (🔴 P0)

**根因**: 死信队列纯内存存储，进程重启后丢失。

**修复**:
- 新增 `persist_path` 参数（默认: `.yuleosh/loop/dead_letter_queue.json`）
- `enqueue()` 后自动持久化到 JSON 文件
- `clear()` / `retry_all()` 后同步更新持久化文件
- `__init__()` 时自动从磁盘加载历史死信事件
- 支持 `persist_path=""` 显式禁用持久化（用于测试隔离）
- 新增 `_persist_to_disk()` / `_load_from_disk()` 内部方法
- stats() 增加 `persist_path`, `persist_exists` 字段

**变更文件**:
- `src/yuleosh/loop_engine/event_bus.py`: DeadLetterQueue 类 + SystemEventBus 构造
- `tests/loop_engine/test_event_bus.py`: 测试隔离改进 + 新增持久化恢复测试

### Fix 3: CLI audit 时间范围/类型过滤 (🟡 P1)

**根因**: `audit list` 只支持按 limit 截断，无法按时间和类型过滤。

**修复**:
- `AuditLog.list()` 新增 `event_type`, `since`, `until` 参数
- 时间范围使用 ISO 8601 字符串比较
- CLI `audit list` 新增:
  - `--since` ISO 8601 起始时间
  - `--until` ISO 8601 截止时间
  - `--type` / `-t` 事件类型过滤（如 `ci.failure`）
  - `--limit` / `-l` 默认 50
- 显示过滤条件摘要

**示例**:
```bash
yuleosh loop audit list \
  --since 2026-07-17T00:00:00 \
  --until 2026-07-17T23:59:59 \
  --type ci.failure \
  --limit 100
```

**变更文件**:
- `src/yuleosh/loop_engine/event_bus.py`: AuditLog.list()
- `src/yuleosh/loop_engine/cli.py`: cmd_audit + argparse
- `tests/loop_engine/test_event_bus.py`: 新增 2 个过滤测试

---

## 测试结果

| 测试套件 | 用例数 | 通过 | 失败 |
|:---------|:------:|:----:|:----:|
| test_event_bus.py | 55 | 55 ✅ | 0 |
| test_loop_e2e.py | 6 | 6 ✅ | 0 |
| test_loop_engineering_acceptance.py | 51 | 51 ✅ | 0 |

### 新增测试用例

| 测试 | 描述 |
|:----|:-----|
| `test_dlq_persistence_restart_recovery` | DLQ 重启后恢复事件完整性 |
| `test_audit_list_filter_by_type` | 审计按事件类型过滤 |
| `test_audit_list_filter_by_time_range` | 审计按时间范围+类型组合过滤 |

---

## 遗留问题

无。所有三个专家指出问题已关闭。

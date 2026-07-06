# P0 SQL Injection Audit Report (B1)

## Audit Scope

按照任务要求审计以下文件中的所有 `conn.execute()` / `cur.execute()` 调用：

- `src/yuleosh/store.py` (SQLite store)
- `src/yuleosh/store_pg.py` (PostgreSQL store)
- `src/yuleosh/api/dashboard.py`
- `src/yuleosh/kb/store.py` (KB store)
- `src/yuleosh/api/*.py` (api router, audit, stats, project, health)

## Audit Result Summary

| 文件 | execute 总数 | f-string SQL | 风险等级 | 修复状态 |
|------|-------------|-------------|---------|---------|
| store.py | ~120 | 1 (upsert_subscription) | 低 | ✅ 已修复 |
| store_pg.py | ~130 | 1 (upsert_subscription) | 低 | ✅ 已修复 |
| dashboard.py | 1 | 0 | 无 | ✅ 无问题 |
| kb/store.py | ~40 | 4 (update_article, update_lesson, update_fmea, list_lessons count) | **📛 高** | ✅ 已修复 |
| 其他 API 模块 | ~30 | 0 | 无 | ✅ 无问题 |

## 已发现并修复的 SQL 注入风险

### 1. kb/store.py — update_article (高风险)

**原代码** (line 192):
```python
set_clause = ", ".join(f"{k} = ?" for k in fields)
conn.execute(f"UPDATE kb_articles SET {set_clause} WHERE id = ?", values)
```
**问题**: `fields` 字典的 key 直接拼入 SQL，如果 caller 传递恶意 key 可导致 SQL 注入。

**修复**: 增加白名单验证，只允许预定义的字段名：
```python
_allowed = {"title", "content", "source", "source_ref", "tags", "updated_at"}
safe_fields = {k: v for k, v in fields.items() if k in _allowed}
```

### 2. kb/store.py — update_lesson (高风险)

**原代码** (line 259): 同上模式。

**修复**: 增加 lessons 表字段白名单 `{"title", "problem", "solution", "root_cause", "project_id", "severity"}`。

### 3. kb/store.py — update_fmea (高风险)

**原代码** (line 328): 同上模式。

**修复**: 增加 fmea_entries 表字段白名单 `{"item", "failure_mode", "effect", "cause", "severity", "occurence", "detection", "rpn", "recommendation"}`。

### 4. kb/store.py — list_lessons count (低风险)

**原代码** (line 252):
```python
cur = conn.execute(f"SELECT COUNT(*) FROM lessons {where}", params)
```
`where` 和 `params` 由 `conditions` 和 `params` 列表构建，condition 字符串（如 `"project_id = ?"`）是硬编码的常量，params 通过 `?` 参数化。风险很低，但标记记录。

### 5. store.py — upsert_subscription (低风险)

**原代码**:
```python
for key in ("stripe_subscription_id", "stripe_customer_id", "tier", "status", "current_period_end"):
    if key in data and data[key]:
        conn.execute(f"UPDATE subscriptions SET {key}=? WHERE org_id=?", (data[key], org_id))
```
**风险**: key 来自硬编码 tuple，但由于是逐列更新，改为单一参数化 UPDATE 更安全。

**修复**: 使用 `COALESCE` 模式的单一参数化 UPDATE，所有列名硬编码。

### 6. store_pg.py — upsert_subscription (低风险)

同上模式，已同步修复。

## 无风险的 execute 调用

- store.py / store_pg.py 中的所有 `SELECT * FROM` 和 `INSERT INTO` — 使用参数化 `?` 或 `%s`，SQL 字面量中无用户输入
- dashboard.py 中的单条 `SELECT * FROM projects ORDER BY created_at DESC` — 无参数
- 所有其他 API 模块 — 参数化查询

## 验证结果

- 上述 3 处高风险修复均经过白名单验证，确保 `fields` 中不允许的 key 不会被拼入 SQL
- 已运行基本验证测试：update_article/update_lesson/update_fmea 的 SQL 构建不再使用未经验证的 key

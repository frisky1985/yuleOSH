# `yuleosh.knowledge_management` 模块设计文档

> 子系统定位：loop 引擎内部知识条目持久化（article CRUD / 软删 / 状态机 / 版本 / 检索）
> 代码根：`src/yuleosh/knowledge_management/`
> 文档性质：详细设计（SWE.3），基于源码实地盘点。

---

## 0. 重要更正（先澄清常见误判）

**本模块不是双后端（SQLite + PostgreSQL）实现。** 它是 **SQLite-only**：

- 模块内 grep `psycopg|postgres|BaseStore|backend|YULEOSH_DB_URL` **全部零命中**（已验证）；
- 唯一 DB 驱动 `import sqlite3`（`store.py:21`），唯一 Store 类 `KBStore`（`store.py:69`，docstring "SQLite-backed knowledge base store"）；
- **不存在** `store_pg.py` / `_pg` 变体 / 后端选择逻辑 / `KNOWLEDGE_BACKEND` 环境变量。
- 仓库内真正的“双后端（SQLite + PostgreSQL）”仅存在于 `knowledge_graph/`（`KGStore` + `KGStorePG`，由 `YULEOSH_DB_URL` 选择）与顶层 `store.py`/`store_pg.py`。`kb/`、`memory/`、`knowledge_management/` 均按 ADR-001 设计为 **SQLite-only**（`:56-58`）。

---

## 1. 职责边界

- 模块定位（P0）：核心 KB 模块，提供 article CRUD、软删除、状态机、版本管理、检索/列表查询 API（`__init__.py:5-9`）。
- 架构身份（依据 `docs/adr/ADR-001-knowledge-subsystem-responsibilities.md:69-70`）：**loop-engine-internal module**，非通用知识库。其 `KnowledgeArticle` 为富 schema（25+ 字段），面向 spec 合规生命周期；与 `kb/` 的 RAG 读路径层职责不同。
- 设计借鉴 `knowledge_graph` 的 `KGStore` 模式（单例 / 迁移 / CRUD），但只实现 SQLite 版（`store.py:9`）。

---

## 2. 目录结构与规模

模块根 `__init__.py` / `models.py` / `queries.py` / `store.py`，**无子目录**。

| 文件 | 行数 | 职责 |
|---|---|---|
| `__init__.py` | 80 | 包入口，`get_store(**kwargs)`，重导出 |
| `models.py` | 123 | 数据模型 `KnowledgeArticle` + 枚举 |
| `queries.py` | 178 | 高层查询函数（接收 `KBStore`） |
| `store.py` | 574 | `KBStore`（线程安全单例，SQLite 持久化） |

---

## 3. 数据模型（`models.py`，纯 dataclass，非 pydantic）

**`KnowledgeArticle`**（`models.py:51`）：
`id`、`title`、`content`、`status: draft`（默认）、`safety_level: QM`、`created_by`、`updated_by`、`created_at`、`updated_at`、`version: "1.0.0"`、`confidence: int = 100`、`confidence_decay_policy: "usage_based"`、`is_deleted: bool = False`、`deleted_at`、`tags: list[str]`、`ota_binding: Optional[dict]`（`{ota_version, ota_manifest_hash}`）、`tcl_doc_slot`、`hw_bom: list[dict]`、`dtc_codes: list[str]`、`autosar_layers: list[str]`、`code_paths: list[str]`、`spec_refs: list[str]`、`safety_goals: list[dict]`、`test_refs: list[dict]`、`change_reason`、`review_notes`（`:59-85`）。

**模块级枚举/常量**（`models.py`）：
- `ARTICLE_STATUSES` = `{draft, review_pending, approved, published, deprecated, archived}`（`:17`）
- `SAFETY_LEVELS` = `{ASIL_A, ASIL_B, ASIL_C, ASIL_D, QM}`（`:28`）
- `VALID_TRANSITIONS: dict[str, set[str]]`（状态机，`:38`）
- `CONFIDENCE_DECAY_POLICIES` = `{"usage_based"}`（`:48`）

**持久化表**（`store.py:110-161`）：`km_articles`（全部字段映射，JSON 列存 `tags/dtc_codes/autosar_layers/code_paths/spec_refs/safety_goals/test_refs/ota_binding/tcl_doc_slot/hw_bom`）、`km_versions`、`km_meta`。

---

## 4. 关键组件

**`KBStore`**（`store.py:69`，线程安全单例，per `db_path`）：
- `__new__` 单例（`:75`）、`reset()`（`:93`）、`_migrate()`（`:107`）
- `create` / `get` / `update` / `soft_delete` / `restore` / `list` / `search` / `search_by_tags`（`:220-428`）
- 版本快照：`_create_version_snapshot` / `list_versions` / `get_version_snapshot`（`:475-511`）
- `get_stats` / `close`（`:529,572`）
- 模块级辅助：`_now` / `_new_id` / `_bump_version` / `_translate_status_transition`（`:39-61`）

**`queries.py`**：高层查询（无类，模块级函数，接收 `store`）：`search` / `list_articles` / `get_by_id` / `get_by_status` / `search_by_tags` / `list_deleted` / `get_stats` / `list_versions`（`:24-168`）。

**`__init__.py`**：`get_store(**kwargs)` 返回 `KBStore`（`:34`）；重导出 `search/list_articles/get_by_id/get_by_status/search_by_tags/list_deleted/get_stats/list_versions/KnowledgeArticle/ARTICLE_STATUSES/SAFETY_LEVELS/VALID_TRANSITIONS`（`:48-64`）。

> 全模块**无 `async def`**。

---

## 5. 与 `kb` / `knowledge` / `knowledge_graph` 的职责切分

依据 `docs/adr/ADR-001-knowledge-subsystem-responsibilities.md`：

- **责任矩阵只列 `knowledge_graph` / `kb` / `memory` 三个活跃子系统**，`knowledge_management/` **未列入矩阵**，身份为 “loop-engine-internal module”（`:69-70`）。
- 本模块 import 它们：**无**（grep 仅命中模块自身内部引用）。它们 import 本模块：**无**（grep 全仓零命中）。
- 与 `kb/` 的区别（`:31-43`）：`KnowledgeArticle`（本模块）25+ 字段、面向 spec 合规生命周期、生产 call site 仅 1 个；`KbArticle`（`kb/`）9 字段、面向用户 RAG 检索、30+ 生产入口。二者**非重复**——本模块是 loop 引擎富 schema 层，`kb/` 是 RAG 读路径。
- 与 `knowledge_graph/`：`knowledge_graph` 提供需求↔代码↔测试追溯图 + 影响分析 + 合并门禁（含双后端）；本模块不提供图/追溯能力，仅做知识条目的 CRUD/状态机/版本/检索。
- `knowledge/`：ADR-001:13-14 指出其为**已删除的死代码层**（`src/knowledge/store_*.py`），与本模块无关联。

**唯一生产调用方**：`src/yuleosh/loop_engine/cli.py:65-66` — `from yuleosh.knowledge_management.store import KBStore`，实例化为 `kg_store_km`，注入 `Loop2FieldToFMEAHandler`（现场缺陷 → FMEA 回路）。

---

## 6. 配置

- `YULEOSH_KB_DB`（`store.py:80-84`、`__init__.py:37-38`）：SQLite 库路径；未设则回退 `<OSH_HOME>/.yuleosh/knowledge_management.db`，再未设则 `CWD/.yuleosh/...`。
- `OSH_HOME`（`store.py:82`）：`YULEOSH_KB_DB` 未设时的默认库根。
- `KNOWLEDGE_BACKEND` / `YULEOSH_DB_URL`：**本模块不使用**（后者为 `knowledge_graph` 的 PG 选择开关）。

---

## 7. 测试

- `tests/test_knowledge_management.py`（771 行）：覆盖 `KBStore` / `KnowledgeArticle` / `queries.*` / `get_store` 包级 API。
- `tests/test_loop_engine_cli_unit.py:229`：以 `"yuleosh.knowledge_management.store.KBStore"` 作为 mock patch 目标。

---

## 8. 已知偏差 / 待决

1. 文档若沿用“双后端”假设即错误——**确为 SQLite-only**，已在 §0 更正。
2. 生产 call site 仅 1 个（loop_engine），模块化价值与维护成本的比例需评估。
3. ADR-001 责任矩阵未纳入本模块，建议补一条说明以消歧义。

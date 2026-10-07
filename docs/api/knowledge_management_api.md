# 知识管理 (`knowledge_management`) API 参考

> 代码根:`src/yuleosh/knowledge_management/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`knowledge_management` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/knowledge_management.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `get_store` | `(**kwargs)` | Return a KBStore instance. | `knowledge_management/__init__.py:34` |
| `search` | `(store: KBStore, query: str, status: Optional[str], include_deleted: bool, offset: int, limit: int)` | Search articles by text query on title and content. | `knowledge_management/queries.py:24` |
| `list_articles` | `(store: KBStore, status: Optional[str], include_deleted: bool, offset: int, limit: int)` | List articles, optionally filtered by status. | `knowledge_management/queries.py:58` |
| `get_by_id` | `(store: KBStore, article_id: str, include_deleted: bool)` | Get a single article by UUID. | `knowledge_management/queries.py:81` |
| `get_by_status` | `(store: KBStore, status: str, offset: int, limit: int)` | List articles by a specific status. | `knowledge_management/queries.py:91` |
| `search_by_tags` | `(store: KBStore, tags: list[str], match_all: bool, offset: int, limit: int)` | Search articles by tags. | `knowledge_management/queries.py:118` |
| `list_deleted` | `(store: KBStore, offset: int, limit: int)` | List soft-deleted articles (admin only). | `knowledge_management/queries.py:142` |
| `get_stats` | `(store: KBStore)` | Return KB statistics. | `knowledge_management/queries.py:160` |
| `list_versions` | `(store: KBStore, article_id: str, limit: int)` | List version history for an article. | `knowledge_management/queries.py:168` |
| `_now` | `()` | ISO-8601 timestamp for record keeping. | `knowledge_management/store.py:39` |
| `_new_id` | `()` | UUID v4 string. | `knowledge_management/store.py:44` |
| `_bump_version` | `(current: str)` | Increment patch segment of semantic version (major.minor.patch). | `knowledge_management/store.py:49` |
| `_translate_status_transition` | `(current: str, target: str)` | Validate status transition, return None if invalid, else target. | `knowledge_management/store.py:61` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `KnowledgeArticle` | `()` | A knowledge article in the KB module. | `knowledge_management/models.py:52` |
| `KBStore` | `()` | SQLite-backed knowledge base store. Thread-safe singleton per db_path. | `knowledge_management/store.py:69` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `KnowledgeArticle.to_dict` | `(self)` | Serialize to a plain dict safe for JSON/storage. | `knowledge_management/models.py:87` |
| `KnowledgeArticle.from_dict` | `(cls, data: dict)` | Deserialize from a dict (coming from store rows). | `knowledge_management/models.py:119` |
| `KBStore.reset` | `(cls)` | Clear all instances (for testing). Recreates new instances on next access. | `knowledge_management/store.py:94` |
| `KBStore.create` | `(self, article: KnowledgeArticle)` | Insert a new article. Generates UUID and timestamps if missing. | `knowledge_management/store.py:220` |
| `KBStore.get` | `(self, article_id: str, include_deleted: bool)` | Get a single article by ID. | `knowledge_management/store.py:245` |
| `KBStore.update` | `(self, article_id: str, updates: dict, updated_by: str)` | Update a non-deleted article. Auto-bumps version patch. | `knowledge_management/store.py:259` |
| `KBStore.soft_delete` | `(self, article_id: str, updated_by: str)` | Soft-delete an article. Returns True if affected. | `knowledge_management/store.py:336` |
| `KBStore.restore` | `(self, article_id: str, updated_by: str)` | Restore a soft-deleted article. Returns True if affected. | `knowledge_management/store.py:350` |
| `KBStore.list` | `(self, status: Optional[str], include_deleted: bool, offset: int, limit: int)` | List articles, optionally filtered by status. | `knowledge_management/store.py:364` |
| `KBStore.search` | `(self, query: str, status: Optional[str], include_deleted: bool, offset: int, limit: int)` | Full-text LIKE search on title and content. | `knowledge_management/store.py:397` |
| `KBStore.search_by_tags` | `(self, tags: list[str], match_all: bool, include_deleted: bool, offset: int, limit: int)` | Search articles by tags (stored as JSON array). | `knowledge_management/store.py:428` |
| `KBStore.list_versions` | `(self, article_id: str, limit: int)` | List version snapshots for an article. | `knowledge_management/store.py:490` |
| `KBStore.get_version_snapshot` | `(self, article_id: str, version: str)` | Restore a full article from a specific version snapshot. | `knowledge_management/store.py:511` |
| `KBStore.get_stats` | `(self)` | Return summary statistics. | `knowledge_management/store.py:529` |
| `KBStore.close` | `(self)` | Close the database connection. | `knowledge_management/store.py:572` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.knowledge_management import <公共符号>
# 详见 docs/modules/knowledge_management.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 4 处生产引用(Grep `yuleosh.knowledge_management` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/knowledge_management/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

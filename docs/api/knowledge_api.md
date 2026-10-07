# 知识 (`knowledge`) API 参考

> 代码根:`src/yuleosh/knowledge/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`knowledge` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/knowledge.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `build_knowledge_subparser` | `(subparsers)` | Add the 'knowledge' subcommand parser. | `knowledge/cli.py:23` |
| `handle_knowledge_command` | `(args)` | Dispatch the knowledge subcommand (returns exit code). | `knowledge/cli.py:50` |
| `_cmd_pending` | `(indexer: KnowledgeIndexer)` | — | `knowledge/cli.py:69` |
| `_cmd_approve` | `(indexer: KnowledgeIndexer, item: Optional[str], all_: bool)` | — | `knowledge/cli.py:87` |
| `_cmd_reject` | `(indexer: KnowledgeIndexer, item: Optional[str], all_: bool)` | — | `knowledge/cli.py:99` |
| `_cmd_audit` | `(indexer: KnowledgeIndexer, limit: int)` | — | `knowledge/cli.py:111` |
| `_now` | `()` | ISO-8601 UTC 时间戳。 | `knowledge/indexer.py:49` |
| `_content_hash` | `(kind: str, content: str)` | 去重哈希：kind + 规范化 content。 | `knowledge/indexer.py:54` |
| `_resolve_project_dir` | `(project_dir: Optional[str | Path])` | 项目根目录：显式传入 > OSH_HOME > 仓库根（当前文件推断）。 | `knowledge/indexer.py:60` |
| `_load_json` | `(path: Path)` | Read a JSON list, tolerating missing/corrupt files (non-fatal). | `knowledge/indexer.py:71` |
| `_write_json` | `(path: Path, items: list[dict])` | Atomically write a JSON list (tmp + replace). | `knowledge/indexer.py:83` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `KnowledgeIndexer` | `()` | 待生效/生效知识索引 + 人工确认流转。 | `knowledge/indexer.py:94` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `KnowledgeIndexer.__init__` | `(self, project_dir: Optional[str | Path])` | — | `knowledge/indexer.py:97` |
| `KnowledgeIndexer.record` | `(self, kind: str, content: str, source: str, meta: Optional[dict])` | 记录一条新沉淀到待生效索引（hash 去重，幂等）。 | `knowledge/indexer.py:105` |
| `KnowledgeIndexer.list_pending` | `(self)` | 列出待生效条目（新的在前）。 | `knowledge/indexer.py:152` |
| `KnowledgeIndexer.list_active` | `(self)` | 列出已生效条目（新的在前）。 | `knowledge/indexer.py:157` |
| `KnowledgeIndexer.approve` | `(self, item_id: Optional[str], all_: bool)` | 人工确认：pending → active。 | `knowledge/indexer.py:171` |
| `KnowledgeIndexer.reject` | `(self, item_id: Optional[str], all_: bool)` | 人工否决：从 pending 移除（不进入 active）。 | `knowledge/indexer.py:212` |
| `KnowledgeIndexer.audit_log` | `(self, limit: int)` | 读取审计日志（新的在前）。 | `knowledge/indexer.py:269` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.knowledge import <公共符号>
# 详见 docs/modules/knowledge.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 10 处生产引用(Grep `yuleosh.knowledge` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/knowledge/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

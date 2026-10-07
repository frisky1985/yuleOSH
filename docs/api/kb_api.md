# 知识库 (`kb`) API 参考

> 代码根:`src/yuleosh/kb/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`kb` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/kb.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `from .kb import handle_kb` |
| `"kb": handle_kb,` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `build_lesson_subparser` | `(subparsers)` | Add the 'lesson' subcommand group (yuleosh lesson create / kb lesson create). | `kb/cli.py:24` |
| `build_kb_subparser` | `(subparsers)` | Add the 'kb' subcommand parser. | `kb/cli.py:41` |
| `handle_kb_command` | `(args)` | Dispatch the kb subcommand. | `kb/cli.py:107` |
| `_resolve_ticket_path` | `(ticket_id: str)` | 定位 improvement_tickets/{ticket_id}.yaml。 | `kb/cli.py:247` |
| `_load_ticket` | `(ticket_id: str)` | 从 improvement_tickets/{ticket_id}.yaml 读取工单，返回 improvement_ticket 字段 dict。 | `kb/cli.py:265` |
| `handle_lesson_command` | `(args)` | Dispatch the top-level 'lesson' subcommand (or kb lesson). | `kb/cli.py:288` |
| `_handle_lesson_create` | `(args)` | Create a Lesson from an improvement ticket (工单一键沉淀知识). | `kb/cli.py:296` |
| `_parse_cppcheck_output` | `(text: str)` | Parse cppcheck plain-text output into violation dicts. | `kb/cli.py:398` |
| `_extract_rule_id` | `(message: str)` | Extract MISRA rule ID from a cppcheck MISRA addon message. | `kb/cli.py:485` |
| `_classify_misra_category` | `(rule_id: str | None)` | — | `kb/cli.py:535` |
| `_collect_source_files` | `(src_dir: str, project_root: str | None)` | Collect all .c/.h/.cpp files under *src_dir* (absolute or relative). | `kb/cli.py:550` |
| `_run_cppcheck_for_ingest` | `(files: list[str])` | Run cppcheck with MISRA addon and return raw output. | `kb/cli.py:567` |
| `_handle_ingest_misra` | `(args, store: KbStore)` | Handle the 'kb ingest-misra' subcommand. | `kb/cli.py:584` |
| `main` | `()` | Direct CLI entry for testing: python -m yuleosh.kb.cli <args>. | `kb/cli.py:663` |
| `_dedup_ref` | `(project_id: str, error_signature: str)` | — | `kb/codegen_failures.py:55` |
| `_short_sig` | `(errors: str)` | — | `kb/codegen_failures.py:61` |
| `_keywords` | `(text: str)` | — | `kb/codegen_failures.py:69` |
| `get_provider` | `(provider: str, **kwargs)` | Embedding 工厂（EI-M3C.1）。 | `kb/embedding.py:157` |
| `_token_estimate` | `(text: str)` | 粗略 token 估算（中文按字、英文按词，1 token ≈ 2 字符保守）。 | `kb/ingest.py:69` |
| `chunk_text` | `(source: str, content: str)` | 把文件内容按标题/段落分块（EI-M3D.2）。 | `kb/ingest.py:74` |
| `_make_chunk` | `(source: str, title: str, content: str)` | — | `kb/ingest.py:107` |
| `_split_long` | `(source: str, title: str, content: str)` | 超长段按字符窗口切分（重叠 10%）。 | `kb/ingest.py:117` |
| `collect_source_paths` | `(project_dir: str | Path, extra: list[str] | None)` | 收集摄取源文件路径（EI-M3D.1）。目录递归收集 *.md。 | `kb/ingest.py:142` |
| `ingest_project` | `(project_dir: str | Path, store, embedding_provider, vector_store, extra_sources: list[str] | None)` | 摄取项目文档（主入口，EI-M3D）。 | `kb/ingest.py:157` |
| `remove_stale_articles` | `(project_dir: str | Path, store)` | 清理已消失源文件的摄取记录（EI-M3D.3 文件删除同步）。 | `kb/ingest.py:211` |
| `_exists` | `(store, content_hash: str)` | content_hash 是否已入库（增量判定）。 | `kb/ingest.py:229` |
| `_strip_html` | `(text: str)` | Remove HTML tags and dangerous patterns from text (XSS write-path guard). | `kb/models.py:173` |
| `sanitize_kb_article_fields` | `(body: dict)` | Extract and validate only the allowed fields for a KbArticle. | `kb/models.py:332` |
| `sanitize_lesson_fields` | `(body: dict)` | Extract and validate only the allowed fields for a Lesson. | `kb/models.py:342` |
| `sanitize_fmea_fields` | `(body: dict)` | Extract and validate only the allowed fields for a FmeaEntry. | `kb/models.py:359` |
| `load_vector_extension` | `(conn: sqlite3.Connection)` | 尝试加载 sqlite-vec 扩展，返回是否可用。 | `kb/vector_store.py:35` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `CodegenFailureCase` | `()` | — | `kb/codegen_failures.py:42` |
| `CodegenFailureStore` | `()` | Records and retrieves codegen failure cases via KbStore. | `kb/codegen_failures.py:74` |
| `EmbeddingUnavailableError` | `(Exception)` | 嵌入服务不可用（调用方应降级 FTS5）。 | `kb/embedding.py:35` |
| `EmbeddingProvider` | `(Protocol)` | 文本向量化接口（EI-M3C.1）。 | `kb/embedding.py:39` |
| `OllamaEmbeddingProvider` | `()` | Ollama 本地嵌入（默认，数据不出域）。 | `kb/embedding.py:53` |
| `HttpEmbeddingProvider` | `()` | OpenAI 兼容 /embedding API（fallback 配置，默认不用）。 | `kb/embedding.py:113` |
| `SearchHit` | `()` | 融合检索结果。 | `kb/hybrid_search.py:28` |
| `HybridResult` | `()` | 融合检索返回。 | `kb/hybrid_search.py:47` |
| `HybridSearch` | `()` | 双路混合检索（EI-M3E.1）。 | `kb/hybrid_search.py:57` |
| `Chunk` | `()` | 分块结果。 | `kb/ingest.py:44` |
| `IngestReport` | `()` | 摄取报告。 | `kb/ingest.py:55` |
| `KbArticle` | `()` | A knowledge base entry (MISRA violations, best practices, etc.). | `kb/models.py:15` |
| `Lesson` | `()` | A lessons-learned entry. | `kb/models.py:64` |
| `FmeaEntry` | `()` | A FMEA entry (simplified). | `kb/models.py:117` |
| `_HTMLStripper` | `(html.parser.HTMLParser)` | Whitelist-style HTML stripper (M-1). | `kb/models.py:272` |
| `KbStore` | `()` | SQLite-backed store for the knowledge base tables. | `kb/store.py:18` |
| `VectorStoreUnavailableError` | `(Exception)` | sqlite-vec 扩展不可用。 | `kb/vector_store.py:31` |
| `VectorStore` | `()` | sqlite-vec 向量表封装（kb.db 内）。 | `kb/vector_store.py:46` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `CodegenFailureStore.__init__` | `(self, kb_store: Optional[KbStore], db_path: Optional[str])` | — | `kb/codegen_failures.py:77` |
| `CodegenFailureStore.record_failure` | `(self, project_id: str, session_id: str, result: 'CodegenResult', language: str)` | Store a failed codegen result. Dedup by (project_id, error_signature). | `kb/codegen_failures.py:82` |
| `CodegenFailureStore.record_resolution` | `(self, session_id: str, resolution: str)` | Update matching failure cases with a resolution note. | `kb/codegen_failures.py:126` |
| `CodegenFailureStore.find_similar` | `(self, error_text: str, language: str, limit: int)` | Search for past failure cases similar to *error_text*. | `kb/codegen_failures.py:143` |
| `CodegenFailureStore.format_for_prompt` | `(self, cases: list[CodegenFailureCase], max_chars: int)` | Format cases as a 'Past Similar Failures' block for LLM repair prompts. | `kb/codegen_failures.py:186` |
| `EmbeddingProvider.embed` | `(self, texts: list[str])` | 把文本列表转成向量列表（同序）。 | `kb/embedding.py:44` |
| `EmbeddingProvider.available` | `(self)` | 服务是否可用（不可用时调用方降级）。 | `kb/embedding.py:48` |
| `OllamaEmbeddingProvider.__init__` | `(self, model: str | None, base_url: str | None, timeout_s: int)` | — | `kb/embedding.py:58` |
| `OllamaEmbeddingProvider.available` | `(self)` | — | `kb/embedding.py:67` |
| `OllamaEmbeddingProvider.embed` | `(self, texts: list[str])` | — | `kb/embedding.py:81` |
| `HttpEmbeddingProvider.__init__` | `(self, api_key: str | None, model: str | None, url: str, timeout_s: int)` | — | `kb/embedding.py:118` |
| `HttpEmbeddingProvider.available` | `(self)` | — | `kb/embedding.py:128` |
| `HttpEmbeddingProvider.embed` | `(self, texts: list[str])` | — | `kb/embedding.py:131` |
| `HybridSearch.__init__` | `(self, store, vector_store, embedding_provider, top_k: int)` | — | `kb/hybrid_search.py:60` |
| `HybridSearch.search` | `(self, query: str, top_k: int | None, content_hashes: list[str] | None, tenant_org: str | None)` | 混合检索（RRF 融合）。 | `kb/hybrid_search.py:83` |
| `HybridSearch.unified_search` | `(self, query: str, top_k: int | None, tenant_org: str | None)` | 一次查询联合召回多源知识（EI-M4B.1/.2）。 | `kb/hybrid_search.py:180` |
| `KbArticle.to_dict` | `(self)` | Serialize to a JSON-compatible dict. | `kb/models.py:27` |
| `KbArticle.from_dict` | `(cls, d: dict)` | Deserialize from a dict (from JSON body or DB row). | `kb/models.py:42` |
| `Lesson.to_dict` | `(self)` | — | `kb/models.py:80` |
| `Lesson.from_dict` | `(cls, d: dict)` | — | `kb/models.py:95` |
| `FmeaEntry.to_dict` | `(self)` | — | `kb/models.py:137` |
| `FmeaEntry.from_dict` | `(cls, d: dict)` | — | `kb/models.py:154` |
| `_HTMLStripper.__init__` | `(self)` | — | `kb/models.py:282` |
| `_HTMLStripper.handle_starttag` | `(self, tag: str, attrs)` | — | `kb/models.py:296` |
| `_HTMLStripper.handle_startendtag` | `(self, tag: str, attrs)` | — | `kb/models.py:306` |
| `_HTMLStripper.handle_endtag` | `(self, tag: str)` | — | `kb/models.py:312` |
| `_HTMLStripper.handle_data` | `(self, data: str)` | — | `kb/models.py:323` |
| `KbStore.__init__` | `(self, db_path: Optional[str])` | — | `kb/store.py:24` |
| `KbStore.close` | `(self)` | Close the thread-local connection if open. | `kb/store.py:50` |
| `KbStore.create_article` | `(self, fields: dict)` | 创建知识库文章（EI-M3A.1：写入去重，防复发）。 | `kb/store.py:224` |
| `KbStore.cleanup_duplicate_articles` | `(self)` | 存量清理（EI-M3A.3）：按 content_hash 去重，保留每 hash 最新一条。 | `kb/store.py:326` |
| `KbStore.get_article` | `(self, article_id: int)` | — | `kb/store.py:383` |
| `KbStore.list_articles` | `(self, search: str | None, limit: int, offset: int, tenant_org: str | None)` | 列出文章（EI-M4A.1: tenant_org 非 None 时 SQL 层强制过滤）。 | `kb/store.py:389` |
| `KbStore.count_articles` | `(self, search: str | None, tenant_org: str | None)` | 文章计数（EI-M4A.1: tenant_org 非 None 时 SQL 层强制过滤）。 | `kb/store.py:432` |
| `KbStore.update_article` | `(self, article_id: int, fields: dict)` | — | `kb/store.py:503` |
| `KbStore.delete_article` | `(self, article_id: int)` | — | `kb/store.py:518` |
| `KbStore.create_lesson` | `(self, fields: dict)` | — | `kb/store.py:526` |
| `KbStore.get_lesson` | `(self, lesson_id: int)` | — | `kb/store.py:541` |
| `KbStore.list_lessons` | `(self, project_id: Optional[str], severity: Optional[str], ticket_id: Optional[str], limit: int, offset: int)` | — | `kb/store.py:547` |
| `KbStore.count_lessons` | `(self, project_id: Optional[str], severity: Optional[str], ticket_id: Optional[str])` | — | `kb/store.py:569` |
| `KbStore.update_lesson` | `(self, lesson_id: int, fields: dict)` | — | `kb/store.py:587` |
| `KbStore.delete_lesson` | `(self, lesson_id: int)` | — | `kb/store.py:600` |
| `KbStore.create_fmea` | `(self, fields: dict)` | — | `kb/store.py:608` |
| `KbStore.get_fmea` | `(self, fmea_id: int)` | — | `kb/store.py:626` |
| `KbStore.list_fmea` | `(self, sort_by: str, sort_desc: bool, limit: int, offset: int)` | — | `kb/store.py:632` |
| `KbStore.count_fmea` | `(self)` | — | `kb/store.py:646` |
| `KbStore.update_fmea` | `(self, fmea_id: int, fields: dict)` | — | `kb/store.py:651` |
| `KbStore.delete_fmea` | `(self, fmea_id: int)` | — | `kb/store.py:676` |
| `KbStore.deduplicate_misra_articles` | `(self)` | Deduplicate MISRA analysis articles keeping only the latest entry per | `kb/store.py:684` |
| `KbStore.list_deduped_misra_articles` | `(self, limit: int, offset: int)` | List MISRA analysis articles with client-side dedup. | `kb/store.py:775` |
| `KbStore.count_misra_violations_by_rule` | `(self)` | Count unique MISRA violations per rule, deduplicated by (file, line). | `kb/store.py:834` |
| `VectorStore.__init__` | `(self, conn: sqlite3.Connection, dim: int)` | — | `kb/vector_store.py:49` |
| `VectorStore.available` | `(self)` | — | `kb/vector_store.py:57` |
| `VectorStore.upsert` | `(self, content_hash: str, embedding: list[float], rowid: int | None)` | 写入向量（按 content_hash 幂等）。 | `kb/vector_store.py:70` |
| `VectorStore.search` | `(self, query_embedding: list[float], k: int, content_hashes: Optional[list[str]])` | 最近邻查询（k=10 默认，EI-M3C.3）。 | `kb/vector_store.py:100` |
| `VectorStore.count` | `(self)` | — | `kb/vector_store.py:136` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |
| `YULEOSH_EMBED_API_KEY` | _(见源码)_ |
| `YULEOSH_KB_DB` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.kb`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/cli/commands/traceability.py:307
from yuleosh.kb.store import KbStore

# src/yuleosh/cli/main.py:327
from yuleosh.kb.cli import build_kb_subparser, build_lesson_subparser

# src/yuleosh/hooks/pre_commit.py:24
from yuleosh.kb.store import KbStore

# src/yuleosh/hooks/post_merge.py:19
from yuleosh.kb.store import KbStore

# src/yuleosh/api/dashboard.py:1502
from yuleosh.kb.store import KbStore

# src/yuleosh/api/router.py:23
from .kb import handle_kb

# src/yuleosh/api/kb.py:15
from yuleosh.kb.store import KbStore

```

> 共 7 个文件引用本子系统；完整调用图见 `docs/modules/kb.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 9 处生产引用(Grep `yuleosh.kb` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/kb/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

# src/knowledge — Phase 1 知识管理 PostgreSQL 后端

## 状态

**待接入（Phase 1）**。当前知识管理功能由 `src/yuleosh/kb/`（SQLite）提供服务；
本目录是规划中的 PostgreSQL 升级实现，等待接入。

## 模块说明

| 文件 | 说明 |
|:-----|:-----|
| `interfaces.go` | Go 服务契约：KBServer 完整接口定义，每条方法标注 Spec 条款（KBS-01~16、KB-02/03 等） |
| `models.go` | Go 数据模型：KBStatus / SafetyLevel / AUTOSARLayer / LLClosureStatus 枚举，编码与 SQL SMALLINT 严格对齐 |
| `migrations/001_create_tables.sql` | PostgreSQL DDL：18 张表，含 ASIL 分级、AIAG-VDA H/M/L、RPN 生成列、DTC 售后回灌、跨 ECU 失效链、5 层测试映射 |
| `store_kb.py` | Python PostgreSQL 实现：KnowledgeBaseStore（psycopg2，沿用 knowledge_graph/store_pg.py 模式） |
| `store_ll.py` | Python PostgreSQL 实现：LessonsLearnedStore，8 状态闭环 + DTC 关联 + 审计日志（CROSS-04） |
| `store_fmea.py` | Python PostgreSQL 实现：FMEAStore，DFMEA/PFMEA 统一 + AIAG-VDA + 跨 ECU 失效链 + FMEA-09 fork |

## 架构定位

```
当前（SQLite）:  src/yuleosh/kb/store.py       ← api / hooks / cli 消费
Phase 1（PG）:   src/knowledge/store_*.py       ← 待接入，对标 knowledge_graph/store_pg.py 模式
DDL:             migrations/001_create_tables.sql
Go 服务契约:      interfaces.go + models.go
```

与 `src/yuleosh/knowledge_graph/` 的 `store.py`/`store_pg.py` 双后端模式一致，是项目既有范式。

## 数据源

- Spec: `spec/spec-knowledge-management.md v1.1.0`
- Tech: `spec/tech-knowledge-management.md`
- ADR: `docs/adr/`（待补充 Phase 1 接入决策）

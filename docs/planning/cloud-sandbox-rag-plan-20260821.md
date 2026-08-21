# yuleOSH 云端沙箱 + RAG — 原子需求排期表

> 2026-08-21 拍板定稿。RAG **需要**，与沙箱并列排期。
> 流程: 评审 → 开发 → 测试 → 验收（不采信自报，逐项验证）
> 接力规则: 从第一个未验收原子继续。

## 总体架构

```
┌─ 沙箱（M1-M2）─────────────────────────────┐
│ Pipeline → Executor 接口                    │
│   ├─ LocalExecutor: venv 隔离 + subprocess  │
│   └─ ContainerExecutor: docker/K8s 隔离     │
└────────────────────────────────────────────┘
┌─ RAG（M3-M4）──────────────────────────────┐
│ 数据源治理 → FTS5 + 向量(sqlite-vec)         │
│ → 混合检索 RRF → 租户过滤 → API              │
└────────────────────────────────────────────┘
```

## 原子需求

### M1 本地隔离底座

**M1-A. Executor 接口抽象 + LocalExecutor**
- 标识: `M1-A`
- 验收标准:
  1. `subprocess_executor.make_subprocess_runner` 的能力抽象为 `Executor` 接口（`execute(step, project_ctx, env) -> StepResult`）
  2. `LocalExecutor` 实现保持现有 worker 语义（子进程 + JSON 回传）
  3. 默认路径不回归：现有 pipeline 不传 executor 时行为与现在完全一致
  4. 全量 pytest 通过，无新增失败
- 依赖: 无
- 状态: 待评审

**M1-B. 项目 venv 自动创建/复用**
- 标识: `M1-B`
- 验收标准:
  1. 首次跑 pipeline 时自动创建 `<OSH_HOME>/.osh/venvs/<project>/`（python3.12 venv）
  2. 读取项目 requirements.txt / pyproject.toml 安装依赖（或 lazily 按需）
  3. 步骤执行时注入 PATH/VIRTUAL_ENV，子进程使用项目 venv 的 python
  4. 已有 venv 时复用，不重复创建
  5. 验收场景: 项目 A 依赖 flask==2.0、项目 B 依赖 flask==1.0，两项目并行跑 pipeline 互不污染，各自 import 版本正确
- 依赖: M1-A
- 状态: 待评审

### M2 云端容器执行

**M2-A. ContainerExecutor（docker run 封装）**
- 标识: `M2-A`
- 验收标准:
  1. `ContainerExecutor` 实现 `Executor` 接口，步骤在容器内执行
  2. 资源限额: `--memory` / `--cpus` 从 tenant plan TIER_LIMITS 映射
  3. 网络: 默认 `--network=none`，LLM/包管理走显式代理 env
  4. 非 root 用户运行，容器内只读根 + 仅项目目录可写
  5. docker 不存在时优雅报错（不 crash）
- 依赖: M1-A
- 状态: 待评审

**M2-B. 租户卷挂载 + 凭据注入**
- 标识: `M2-B`
- 验收标准:
  1. 挂载 `data/tenants/{tenant_id}/` 为容器工作卷，读写边界=租户目录
  2. API key 仅通过环境变量注入容器，不落盘项目目录
  3. 审计: 容器启动参数写入 audit log
- 依赖: M2-A
- 状态: 待评审

**M2-C. K8s Job/Pod runner + ResourceQuota**
- 标识: `M2-C`
- 验收标准:
  1. Helm chart 增加 runner: 每 pipeline 任务 = k8s Job
  2. per-tenant PVC 挂载（复用现有 pvc.yaml 模式）
  3. per-tenant ResourceQuota / NetworkPolicy 默认拒绝
  4. 本地 docker 模式不可用时降级提示（不阻塞单机使用）
- 依赖: M2-A, M2-B
- 状态: 待评审

### M3 RAG 基础

**M3-A. 数据源治理（修 misra_analysis 灌库 bug）**
- 标识: `M3-A`
- 验收标准:
  1. kb_articles 写入增加去重（content hash，同内容不重复插入）
  2. misra_analysis 来源改为只写汇总/违规统计，不逐条灌 articles；或显式白名单来源
  3. 存量 40,471 条重复数据清理（保留唯一记录，预计降至 ~100 量级）
  4. 全量 pytest 通过
- 依赖: 无
- 状态: 待评审

**M3-B. FTS5 全文检索替换 LIKE**
- 标识: `M3-B`
- 验收标准:
  1. kb_articles 建 FTS5 虚拟表（trigram tokenizer，中文可用）
  2. `kb search` 走 FTS5 MATCH，替代 `LIKE '%x%'`
  3. 中文关键词检索正确（如"错误处理"能召回含该词的文章）
  4. 排序合理（bm25），返回与旧 LIKE 语义兼容（不丢已有召回）
- 依赖: M3-A
- 状态: 待评审

**M3-C. EmbeddingProvider 抽象 + sqlite-vec 向量存储**
- 标识: `M3-C`
- 验收标准:
  1. `EmbeddingProvider` 接口（`embed(texts) -> list[list[float]]`），默认 bge-m3（Ollama），API 模式可配置
  2. sqlite-vec 扩展接入 kb.db，建向量表（id, content_hash, embedding, tenant_id, project_id, source, chunk_id）
  3. 向量写入 + 最近邻查询（k=10）可用
  4. 无 Ollama/无 sqlite-vec 时优雅降级（FTS5 仍可用）
- 依赖: M3-A, M3-B
- 状态: 待评审

**M3-D. 摄取管道（分块/embedding/增量）**
- 标识: `M3-D`
- 验收标准:
  1. 摄取源: docs/spec.md, TASK_STATUS.md, requirements/, lessons, fmea（按需扩展）
  2. 分块: 按标题/段落/表格，500-1000 tokens，重叠 10%
  3. 增量: content hash 变更才重新 embedding；文件删除同步清理
  4. 触发: 本地 git hook / CI 后处理 / 手动 `yuleosh kb ingest <project>`
- 依赖: M3-C
- 状态: 待评审

**M3-E. 混合检索 RRF + API**
- 标识: `M3-E`
- 验收标准:
  1. 检索接口: FTS5 关键词路 + 向量近邻路 → RRF 融合 → 排序结果
  2. REST API: `GET /api/v1/kb/search?q=...` 返回融合结果（含两路分数）
  3. 验收场景: 查询"哪个项目要求了错误处理"跨项目语义召回正确
  4. 检索耗时 < 500ms（本地）
- 依赖: M3-B, M3-C, M3-D
- 状态: 待评审

### M4 RAG 多租户 + 融合

**M4-A. 向量检索租户隔离**
- 标识: `M4-A`
- 验收标准:
  1. 检索 API 从 JWT 取 tenant_id，SQL 层强制过滤（不只应用层）
  2. 验收场景: 租户 A 检索任何关键词，结果不含租户 B 数据（构造 B 独有内容验证）
  3. 越权尝试返回空/403，不泄漏存在性
- 依赖: M3-E
- 状态: 待评审

**M4-B. kb / knowledge_graph / 向量三源联合召回**
- 标识: `M4-B`
- 验收标准:
  1. 一次查询联合召回: articles（向量+FTS5）+ lessons + fmea + KG 相关节点
  2. 结果按相关性融合排序，带来源标注
  3. 验收场景: 查"刹车失效"能同时召回 spec 需求、lesson 教训、FMEA 条目、KG 关联节点
- 依赖: M4-A
- 状态: 待评审

---

## 排期表（Bitable 同步）

| 标识 | 需求 | 优先级 | 负责 | 状态 | 依赖 | Commit | 验收 |
|:--|:--|:--|:--|:--|:--|:--|:--|
| M1-A | Executor 接口抽象 + LocalExecutor | P0 | 小克 | 待评审 | — | | |
| M1-B | 项目 venv 自动创建/复用 | P0 | 小克 | 待评审 | M1-A | | |
| M2-A | ContainerExecutor | P0 | 小克 | 待评审 | M1-A | | |
| M2-B | 租户卷 + 凭据注入 | P1 | 小克 | 待评审 | M2-A | | |
| M2-C | K8s Job runner | P1 | 小克 | 待评审 | M2-A, M2-B | | |
| M3-A | 数据源治理（灌库 bug） | P0 | 小克 | 待评审 | — | | |
| M3-B | FTS5 全文检索 | P1 | 小克 | 待评审 | M3-A | | |
| M3-C | Embedding + sqlite-vec | P1 | 小克 | 待评审 | M3-A, M3-B | | |
| M3-D | 摄取管道 | P1 | 小克 | 待评审 | M3-C | | |
| M3-E | 混合检索 RRF + API | P1 | 小克 | 待评审 | M3-B, C, D | | |
| M4-A | 向量租户隔离 | P2 | 小克 | 待评审 | M3-E | | |
| M4-B | 三源联合召回 | P2 | 小克 | 待评审 | M4-A | | |

**批次建议**:
- 批1（可并行）: M1-A, M3-A（无依赖）
- 批2: M1-B, M2-A, M3-B
- 批3: M2-B, M3-C
- 批4: M2-C, M3-D
- 批5: M3-E
- 批6: M4-A
- 批7: M4-B

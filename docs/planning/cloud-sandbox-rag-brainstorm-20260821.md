# yuleOSH 云端多租户 — 沙箱隔离 + RAG 向量库头脑风暴

> 日期: 2026-08-21
> 状态: Brainstorm（待评审拍板）
> 目标: 云端多用户开发 + 本地开发双模式；沙箱隔离避免项目间污染；RAG 管理各项目功能需求

---

## 0. 现状盘点（证据链）

| 能力 | 现状 | 位置 |
|:--|:--|:--|
| 多租户 | ✅ 文件系统级隔离 `data/tenants/{id}/` + 计费分层 free/pro/enterprise | `src/yuleosh/tenant/` |
| REST API | ✅ 模块化路由（auth/ci/pipeline/kb/kg/loops…） | `src/yuleosh/api/` |
| 部署 | ✅ Docker（python:3.13-slim）+ docker-compose + Helm chart | `deploy/` |
| 进程级步骤隔离 | ✅ 每步独立子进程，JSON 回传，杜绝 agent 状态污染 | `engine/subprocess_executor.py` |
| 插件代码沙箱 | ✅ builtins 白名单 + FS/网络/系统调用限制 | `plugins/sandbox.py` |
| git worktree | ❌ 无（**且不需要**：项目模型=独立目录+删 .git 的 copytree，见 §1.7） | `cli/template.py` L165-174 |
| 依赖隔离（venv/容器） | ❌ 所有项目共享同一 Python 环境（**真正缺口**） | — |
| 容器化任务执行 | ❌ pipeline 在宿主进程/子进程跑，无容器 | — |
| 知识库 | ⚠️ SQLite `kb.db` 22.6MB，**LIKE 关键词搜索** | `kb/store.py` L183 |
| 知识图谱 | ✅ SQLite nodes/edges + BFS | `knowledge_graph/store.py` |
| 向量检索/embedding | ❌ 零实现 | — |

---

## 1. 沙箱隔离方案

### 1.1 目标场景

- **云端 SaaS**：多租户并行跑 pipeline，每项目独立工作区、独立依赖、资源限额、安全边界
- **本地开发**：多项目在同一台机器，互不污染（依赖/Python 环境/git 分支）
- 同一套 pipeline 代码，两种模式都能跑

### 1.2 方案对比

| 方案 | 隔离维度 | 成本 | 适用 | 风险 |
|:--|:--|:--|:--|:--|
| **A. worktree + venv（本地为主）** | git 工作区 + Python 依赖 | 低 | 本地多项目 | 不防恶意代码 |
| **B. 容器任务执行（云端为主）** | 进程+FS+网络+依赖全隔离 | 中 | 云端 SaaS | 镜像/编排复杂度 |
| **C. 执行器抽象统一（A+B 底层）** | 接口层统一，后端可插拔 | 中 | 全场景 | 需设计好接口边界 |

**推荐：C 为骨架，A 为本地后端，B 为云端后端。**

### 1.3 执行器抽象（核心设计）

```
Pipeline (不变)
   └── Executor 接口 (新)
         ├── execute(step, project_ctx, env) -> StepResult
         ├── LocalExecutor    (A: venv + worktree + subprocess, 已有 subprocess_executor 演进)
         └── ContainerExecutor (B: docker/k8s job, 挂载租户卷, 资源限额)
```

关键点：
- 接口语义 = 现有 `subprocess_executor.make_subprocess_runner` 的抽象化
- `project_ctx` 携带: 租户 id、项目 id、git 引用、依赖清单、资源限额
- 云端默认 ContainerExecutor，本地默认 LocalExecutor，配置可切换

### 1.4 本地后端（A 细节）

- **项目 venv（核心）**：`<OSH_HOME>/.osh/venvs/<project>/`，`pip install -r requirements.txt`（或 uv，更快）
  - pipeline 各步骤执行时自动激活项目 venv（PATH/VIRTUAL_ENV 注入）
  - 工具链（cppcheck/cmake/QEMU）也可按项目锁定版本到 venv/bin
- **复用**：现有 `subprocess_executor` 的 worker 机制 + `OSH_HOME` 环境变量隔离
- **收益**：解决当前最痛的"多项目共享 Python 环境互相污染"
- **不采用 worktree**：项目已是独立目录模型（§1.7），无需 git 层额外隔离

### 1.5 云端后端（B 细节）

- **容器 per 项目**：`docker run --rm --network=none -v <tenant_volume>:/work -m 2g --cpus 2` 
  - `--network=none` 安全默认；LLM 调用走宿主代理（env 传入 API key 或代理地址）
  - 资源限额 = tenant plan 映射（free/pro/enterprise 已有 TIER_LIMITS）
- **K8s 演进**：Helm chart 增加 runner Deployment；每任务 = k8s Job/Pod
  - 挂载 PVC per 租户（已有 pvc.yaml）
  - ResourceQuota per namespace（租户粒度）
  - 网络策略 NetworkPolicy 默认拒绝
- **镜像策略**：基础镜像 + 按需工具层（编译链/交叉编译/QEMU 模拟器打不同 tag）

### 1.7 worktree 判定：不需要（证据链）

查证 `cli/template.py` L159-190 + `yuleosh_cli.py cmd_init` L452-486：

- `yuleosh init <dir>` → 在独立目录生成 specs/tasks/src/docs/evidence/.osh
- `yuleosh template init <name>` → `shutil.copytree` 拷贝模板为全新目录，**并删除 .git**（L168-174）
- pipeline 执行 = `cd <项目目录> && yuleosh pipeline run docs/spec.md`，project_dir 即项目根

**结论**：yuleOSH 已是"每项目独立目录 + 独立工作区"模型，项目间不共享 .git/.osh/会话/证据，天然隔离。worktree 解决的是"单仓库多分支并行"问题，与 yuleOSH 模型不匹配 → **不排期**。真正缺口是依赖环境共享（§1.4 M1-B venv）与云端多租户执行边界（§1.5）。

### 1.6 安全边界（两条都适用）

| 层 | 措施 |
|:--|:--|
| 进程 | 非 root 用户、资源限额（CPU/内存/磁盘/超时，已有 plugin timeout 机制可扩展） |
| 文件 | worktree/容器内只读根 + 仅项目目录可写 |
| 网络 | 默认禁止外联，LLM/包管理走显式代理白名单 |
| 凭据 | API key 只注入执行环境，不落盘项目目录 |

---

## 2. RAG 向量知识库方案

### 2.1 目标

- 管理各项目**功能需求**：需求文档、spec、TASK_STATUS、验收矩阵、lessons、FMEA
- 语义检索（"哪个项目要求了错误处理？" → 跨项目召回）
- 与现有 KB（articles/lessons/fmea）+ 知识图谱融合，不推倒重来

### 2.2 方案对比

| 方案 | 存储 | 检索 | 成本 | 适用 |
|:--|:--|:--|:--|:--|
| **A. SQLite 扩展向量** | sqlite-vec / sqlite-vss（复用 kb.db） | 向量 + FTS5 | 低 | 单机/中小规模 |
| **B. 独立向量库服务** | Chroma（嵌入式）/ Qdrant / Milvus | 纯向量 | 中 | 云端规模化 |
| **C. pgvector** | Postgres + 扩展 | 向量 + SQL | 中 | 已有 PG 基础设施 |

**推荐：A 起步（零新服务、复用 kb.db），预留 B 接口（向量存储抽象，可热切 Qdrant）。**

### 2.3 Embedding 模型

| 模型 | 语言 | 尺寸 | 部署 |
|:--|:--|:--|:--|
| bge-m3 | 多语言（中英） | 568M | 本地 Ollama/API，推荐（中文需求场景） |
| bge-small-zh | 中文 | 24M | 轻量本地 |
| OpenAI text-embedding-3-small | 多语言 | API | 云端 |

- 默认 bge-m3（中文需求文档为主），embedding 服务做接口抽象（`EmbeddingProvider`），可换 API

### 2.4 混合检索（Hybrid RAG，现代标准）

```
query
 ├─ 关键词路: SQLite FTS5 (title/content/tags) ──┐
 └─ 语义路:   embedding → 向量近邻 ──────────────┼─→ RRF 融合 → 排序结果
                                                └→ 注入 LLM 上下文
```

- FTS5 替代现有 `LIKE '%x%'`（快 100 倍 + 中文分词 fts5 tokenizer=trigram）
- RRF（Reciprocal Rank Fusion）融合两路，避免语义召回漏关键词

### 2.5 摄取管道（Ingestion）

```
项目文件 (docs/spec.md, TASK_STATUS.md, requirements/, lessons, fmea)
   → watcher/hook (文件变更触发)
   → 分块 (chunk: 按标题/段落/表格, 500-1000 tokens 重叠)
   → embedding
   → 写入 kb 向量表 (tenant_id + project_id + chunk_id)
```

- 增量：git hook / CI 后处理 / 定时扫描（本地）或 webhook（云端）
- 去重：content hash

### 2.6 多租户隔离（关键安全设计）

- 向量表/collection 强制 **tenant_id + project_id 过滤**（SQL 层 where，不只应用层）
- 检索 API 从 JWT 取租户，注入过滤条件，防跨租户泄漏
- 云端可切独立 collection per tenant

### 2.7 与现有 KB/知识图谱的关系

```
kb.db (articles/lessons/fmea)  ← 结构化事实 (已有)
knowledge_graph.db (nodes/edges) ← 关系推理 (已有)
kb 向量表 (新)                   ← 语义检索 (新增)
三者共用 project_id 外键，检索时可联合召回
```

---

## 3. 里程碑建议（原子化拆分）

> 老板拍板（2026-08-21）：RAG **需要**，与沙箱一起排期。修正顺序：M1 → M2 → M3 → M4（沙箱先行 → RAG 跟进，M2/M3 无依赖可并行推进）。
> 关键前置事实：kb.db 现状 40,471 条 articles 全部为 `misra_analysis` 灌入的重复 MISRA 违规记录（141B/条，无去重），lessons/fmea 为 0 → M3 摄取管道必须先做**数据源治理**（去重/分类/来源白名单），否则向量库索引的是垃圾。

### M1: 本地隔离底座（对应 1.4，worktree 已判定不需要见 §1.7）
- M1-A: Executor 接口抽象（从 subprocess_executor 提取）+ LocalExecutor
- M1-B: 项目 venv 自动创建/复用（`.osh/venvs/<proj>`）
- 验收: 两个项目不同依赖并行跑 pipeline 互不污染

### M2: 云端容器执行（对应 1.5）
- M2-A: ContainerExecutor（docker run 封装 + 资源限额 + 网络策略）
- M2-B: 租户卷挂载 + 凭据注入
- M2-C: K8s Job/Pod runner + ResourceQuota
- 验收: 云端多租户并行跑 pipeline，隔离互不干扰

### M3: RAG 基础（对应 2.4-2.5）
- M3-A: **数据源治理**（kb 去重/分类/来源白名单，修 misra_analysis 灌库 bug）
- M3-B: FTS5 全文检索替换 LIKE + 中文分词
- M3-C: EmbeddingProvider 抽象 + sqlite-vec 向量存储
- M3-D: 摄取管道（分块/embedding/增量）
- M3-E: 混合检索 RRF + API
- 验收: 语义检索"哪个项目要求了错误处理"跨项目召回正确

### M4: RAG 多租户 + 融合（对应 2.6-2.7）
- M4-A: 向量检索租户隔离（JWT → SQL 过滤）
- M4-B: kb/knowledge_graph/向量三源联合召回
- 验收: 租户 A 检索不到租户 B 数据

---

## 4. 待老板拍板

- ✅ 已拍板: 沙箱 = C（执行器抽象 + 本地 A + 云端 B）
- ✅ 已拍板: RAG = **需要**，进排期
- ✅ 已拍板: RAG 存储 = A（sqlite-vec 起步，接口抽象预留热切 Qdrant）
- ✅ 已拍板: Embedding = bge-m3 本地（Ollama），API 作 fallback 配置
- ✅ 已拍板: 里程碑 = M1 → M2 → M3 → M4（M2/M3 可并行）
- ⏳ 执行中: 原子需求拆分 → 排期表 → 评审 → 开发

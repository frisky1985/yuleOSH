# yuleOSH v3.13.0 — 多 Agent 隔离 + 统一 LLM 入口 + 覆盖率 85% 里程碑发布

> **发布日期**: 2026-08-09
> **版本**: v3.13.0
> **上一个发布 tag**: v3.12.1 (2026-08-05)
> **版本跨度**: v3.12.1 → v3.13.0

---

## 🎯 本版核心

从 v3.12.1 到 v3.13.0 共 **75 个 commit**，主线：**多 Agent 隔离体系（PR0+A/B1/B2/B3）+ 统一 LLM 入口 + 覆盖率 85% 里程碑 + 假绿系统性修复**。

---

## 🚀 v3.13.0 — 多 Agent 隔离 + 统一 LLM 入口

### 多 Agent 隔离 Pipeline（方案 PR0 + A + B1/B2/B3）
- **PR0**: `engine/handler_adapter.py` 签名适配层 — 33 个 handler 零改动兼容（session/noarg/invalid 三态 + StepResult 规范化）
- **A1-A4**: `agent_registry.py` 角色注册表 + 约束按角色隔离加载（pm/developer/qa 基线拆分，绝不混合其他角色注入）
- **方案 B1**: CheckpointEngine 驱动真实 Pipeline — session_factory + set_artifact 交接 + mock 全链 33 步
- **方案 B2**: subprocess 隔离执行器 — 进程级隔离 + 产物一致性门禁 + sqlite 状态（monkeypatch 污染根因修复）
- **方案 B3**: 执行看板 — `pages/pipeline-board.html` 按 agent 分组步骤卡片 + 3s 轮询 + retry/resume 操作入口（`/api/v1/pipeline/checkpoint|retry|resume`，401 fail-closed + 模块级锁防并发）

### 统一 LLM 入口（方案 C）
- `LLMClient.call_sync` 同步桥接（Py3.12 嵌套 loop 安全）+ LLMResponse→旧 dict 适配
- `AGENT_MODEL_ROUTES` agent→model 路由 + `TASK_RISK_LEVELS` 9 级分级 + **L3/L4 禁下钻硬规则**
- 双轨合一：pipeline 全部可走 LLMClient.call（token 预算 / provider 回退 / 成本审计）
- provider 级 fallback 降级链（LLM 调用失败自动降级备用 provider）

### 覆盖率 85% 里程碑（84% → 85.37%）
- 补 KG/handler/async/billing/tenant 测试（TestTenantRoutes 30 用例 → 97%）
- QG-007 layers 死代码修复 + KG Merge Gate scope_files 收窄（变更检测只统计 session 产物子图）
- `run_coverage_full.py` .coverage 损坏根因修复（外层 cov 与 pytest-cov 并发写冲突 → 独立 data_file + `-p no:cov`）

### 假绿系统性修复（T1-T10）
- audit 实质内容校验 / KG 阈值对齐 / CI 真跑去 `|| echo` 伪装 / coverage fail-under / mock 门禁不伪装 / security 指向真实模块
- H1-H8 注入式自检套件（防回退）+ H4 新鲜度 gate + MISRA L1 增量扫描接线
- traceability tamper-evident integrity gate（ASPICE P0）+ SWR-xxx 格式解析 + compliance 指标级校验（Covered≥Threshold / 追溯≥60% / SIL 真实通过 / review 实质内容）

### 知识注入 + 安全 + 其他
- 方案 A: pipeline 步骤统一知识注入层（14 新测试）；方案 B: 沉淀知识 hook 自动收集+人工确认生效
- `yuleosh audit verify` 审计日志 SHA-256 哈希链 + 证据包自动内嵌审计完整性证明
- 生产部署 fail-closed（compose 密码强制变量）+ 代码域 P0 清零（dashboard 去 mock / AL 评级改证据覆盖度）
- MISRA 工具链修复（_exclude_paths ** 递归 / deviations 持久化 file_pattern / spec coverage 通用 fallback）
- 测试环境隔离修复（event_bus /tmp 污染根治 + test_cli tmp_path + onboarding secret 恢复）

---

## ✅ 质量状态（v3.13.0）

| 指标 | 值 |
|:-----|:---|
| 全量测试 | 10814 passed / 0 failed（1 flaky 复跑 3 轮全过）/ 130 skipped，715s |
| 覆盖率 | **85.37%**（行 87.67% + 分支 78.52% 加权） |
| CI | 三层全绿（yuleOSH CI 23m56s / Honesty Gate / CodeQL+Semgrep） |
| ruff | 全部改动文件零新增 |

---

# yuleOSH v3.12.1 — 工具链打通 + CI 门禁复活发布

> **发布日期**: 2026-08-05
> **版本**: v3.12.1
> **上一个发布 tag**: v3.9.1 (2026-08-04)
> **版本跨度**: v3.10.0 → v3.10.1 → v3.11.0 → v3.12.0 → v3.12.1

---

## 🎯 本版核心

从 v3.9.1 到 v3.12.1 共 **43 个 commit**，主线：**CI 门禁复活 + 方法论平台化 + yuleDKCS 混合语言工具链打通**。

---

## 🚀 v3.12.1 — yuleDKCS 混合语言支持 + MISRA 工具链打通

### CI 混合语言支持（yuleOSH-check 5c4721a / d9355d3f）
- **config/yaml_validator/layer_config/layer_executor**: Go/Python 项目也能跑嵌入式 C MISRA；`project_language: mixed` 配置覆盖自动检测；Go monorepo 多模块 build/vet/test
- **review.py 关键 3 修**: cppcheck 相对路径 `-I`（绝对路径 .h 违规不匹配 baseline 根因）；exclude normpath（`./` 前缀致 exclude 失效）；scan_dirs 驱动文件发现
- **misra_report parser**: 跳过 information 级（checkersReport/unmatchedSuppression 等非违规误报）
- **layer_executor e2e**: pytest exit 5（no tests collected）→ skip 而非 fail（Go-only e2e 目录）
- **yuleDKCS 实测**: MISRA C:2023 **690 → 0 违规**（57 文件），三层 CI 全绿

### 集成测试环境探测（yuleDKCS）
- scenarios 12 测试 + security 3 测试加环境探测 skip：carsim/gateway 不可达时 SKIP 不 block CI

### 产物治理（yuleDKCS）
- gitignore carsim 二进制 / `.osh/` 运行产物 / `*.dump`（cppcheck 中间产物）

---

## ✨ v3.12.0 — 方法论平台化 + Pipeline 修复

### L3 方法论宿主平台化
- **L3-B 独立门禁引擎**: standalone 零依赖 + 一致性测试
- 一键挂载（yuleASR 试点成功）+ 独立门禁 CLI
- 模板 `.yuleosh/agents` 被根 .gitignore 忽略未入库修复

### Pipeline 修复
- **qemu-run** `timed_step self` 丢失 + c-coverage-gate project_dir 层级错误
- **spec THEN 误捕修复**: 场景内 SHALL 行不再被当独立需求
- **mock 全链 33 步 completed errors=0**: gate 阻断语义 + 11 review 步骤 mock 跳过；6 个 code-quality gate 一致跳过

---

## 🛡️ v3.11.0 — 方法论契约门禁

- **L2 Methodology Gate 可执行化**: 非方法论项目自动跳过 + 测试去 sys.path.insert
- Semgrep SARIF upload 无文件时报错修复（hashFiles 条件跳过）

---

## 🧠 v3.10.x — 方法论约束层 + 真实 LLM 集成

### v3.10.1
- **L1 方法论约束层**: 融合 mattpocock 工程方法论进 agent 行为

### v3.10.0 Track0/Track1
- **真实 LLM 集成修复**: pipeline 端到端验证第一批（此前 CI 门禁死亡 ≥11 天被修复）
- **CI 门禁复活**: ci.yml YAML 缩进错误修复（fd76c96e 引入）、Python 3.10/3.11 f-string 兼容（PEP 701）、tomllib→tomli fallback、code-quality 移除冗余 coverage 全量测试（CI 卡死根因）、恢复 cve-scan pip-audit 安装、lint kind + cppcheck 补装
- **测试跨版本修复**: B 类 10 个失败拆解 3 根因组（api_preview/review_selftest、status_pipeline mock 精准化、cross/evidence 注入挂包对象属性）
- **依赖声明补全**: openpyxl>=3.1.0、pytest-asyncio>=0.23
- **技能库**: 导入 mattpocock 41 技能 + 项目管理 SOP

## 🧠 Memory 记忆能力集成（2026-08-06，v3.12.1 增量）

将 Hermes agent 记忆能力移植到 yuleOSH：跨会话结构化事实存储 + 会话全文检索（方案 B）。

| 命令 | 说明 |
|:-----|:-----|
| `yuleosh memory remember/recall/forget/list/stats` | 结构化事实存储（entity/category/tags/trust/recall_count），信任强化（recall 命中 +0.1，上限 1.0） |
| `yuleosh memory log` + `yuleosh session search` | FTS5 全文检索会话/决策记录 |

- 独立 SQLite（`YULEOSH_MEMORY_DB` 可隔离），遵循 kb 模块模式
- FTS5 外部内容表 + AFTER INSERT/DELETE 触发器 + rebuild backfill（外部内容表不自动索引）
- 测试 `tests/test_memory_store.py` 13 passed；ruff memory 包 0 错误
- 后续（方案 C，未排期）：KG/RAG/LLM 联动，记忆注入 LLM 上下文

---

## ✅ 质量状态

| 指标 | 值 |
|:-----|:---|
| 全量测试 (v3.9.0 基线) | 10017 passed / 0 failed，cov 84.17% |
| v3.12.1 针对性回归 | 797 passed / 0 failed (CI/MISRA/层/pipeline 全组) |
| yuleDKCS 三层 CI | L1 MISRA 0 违规 + go 7 模块 / L2 cppcheck / L3 evidence 全绿 |
| 认证 | 复验 9.5/10 (v3.9.1)，v3.10+ 持续 |

---

## 📦 安装

```bash
pip install -e .        # 开发安装（editable）
# 或从源码:
pip install .
```

**注意**: 版本号已从 3.4.4 同步至 3.12.1（pyproject.toml + `__version__`）。

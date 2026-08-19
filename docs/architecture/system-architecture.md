# yuleOSH 系统架构与 Pipeline 流程详解

> **版本**: v3.12.x (main=02958fb) | 全量 10327 passed / 0 failed / cov 83.94%
> **定位**: 嵌入式软件合规开发自动化平台（ASPICE SWE 辅助工具）
> **形态**: CLI 优先 + Web Dashboard + 开源（Elastic-2.0）

---

## 一、总体架构（4 层 + 支撑模块）

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Presentation 层                              │
│   CLI (34 子命令)  │  Web Dashboard (Next.js + PostgreSQL)          │
│   src/yuleosh/cli/ │  src/yuleosh/ui/ + api/                        │
└──────────┬──────────────────────────────┬───────────────────────────┘
           ▼                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Application 层                               │
│   OpenSpec Engine    Agent Pipeline     CI/CD Engine    Loop Engine │
│   spec/              pipeline/          ci/             loop_engine/│
│   (SHALL 解析/校验/   (33 步编排)        (L1/L2/L3)      (KPI→工单   │
│    diff/状态机)                        + 4-Agent Review   →lesson)  │
└──────────┬──────────────────────────────┬───────────────────────────┘
           ▼                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Domain 层                                    │
│   llm/ (多 Provider + fallback + RAG + token 预算)                  │
│   kb/ knowledge_graph/ memory/   —— 知识三件套（KB/图谱/记忆）       │
│   audit/ evidence/ report/       —— 合规证据链                      │
│   codegen/ testgen/ review/ sil/ cross/ hardware/ —— 嵌入式工具链    │
└─────────────────────────────────────────────────────────────────────┘
           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Infrastructure 层                            │
│   store.py / store_pg.py (SQLite→PostgreSQL 多租户)                 │
│   adapter/ (dSPACE/Vector 硬件适配)  hooks/ (git hooks)             │
│   billing/ usage/ tenant/ rbac/ notify/ (SaaS 支撑)                 │
└─────────────────────────────────────────────────────────────────────┘
```

### 模块职责速查

| 模块 | 职责 | 关键文件 |
|------|------|---------|
| `spec/` | OpenSpec 解析/校验/diff/状态机 | merge.py, validate.py |
| `pipeline/` | 33 步 Agent 编排 | step_handlers/__init__.py, orchestrator.py |
| `ci/` | 3 层 CI + MISRA + 覆盖率 | layers/, misra_report/, coverage_* |
| `llm/` | 多模型 + fallback 降级链 + RAG | providers/, fallback.py, rag/ |
| `kb/` | 知识库（文章/Lesson/FMEA） | store.py, models.py |
| `knowledge_graph/` | 追溯图谱（函数级） | edge_builder.py, merge_gate.py |
| `memory/` | 跨会话事实记忆 | store.py |
| `audit/` | 审计日志 SHA-256 哈希链 | model.py |
| `evidence/` | 证据包生成/校验/签名 | manifest.py, check.py |
| `loop_engine/` | 自动闭环（KPI→工单→Lesson） | rca_engine.py, event_bus.py |
| `cross/` | 交叉编译 + SIL | sil_assert.py |
| `hardware/` | 烧录/监控/调试 | — |
| `api/` + `ui/` | Web 层 | server.py, dashboard.py |

---

## 二、完整 Pipeline 流程（24 子步骤，10 Gate 编排层，SWE.1~SWE.6 映射）

> 来源: `src/yuleosh/pipeline/step_handlers/__init__.py` PIPELINE_STEPS（真实注册清单）
> 编排: `src/yuleosh/pipeline/gates.py` GATES（10 Gate 对外稳定契约，R1-R4 分层原则见 RULES.md §14）
> 执行: `yuleosh pipeline run docs/spec.md` → orchestrator 逐步骤执行 → session.json 记录产物

### 阶段总览（按 ASPICE 过程域分组）

```
SWE.1 需求 ──▶ SWE.2 架构 ──▶ SWE.3 编码 ──▶ SWE.4 单元验证 ──▶ SWE.5 集成 ──▶ SWE.6 合格性
   │              │              │               │                │              │
 G1(4步)        G2(2步)        G3/G4/G5(5步)    G6(2步)         G7/G8/G9(8步)   G10(2步)
```

### 编排层 10 Gate（对外稳定契约，R2 变更须老板/架构评审拍板）

| Gate | 名称 | 子步骤 |
|:----:|:-----|:-------|
| G1 | SWE.1 需求 Gate | spec-check, super-analysis, prd, prd-review |
| G2 | SWE.2 架构 Gate | architecture, arch-review |
| G3 | SWE.3 实现 Gate | development, development-review, codegen-deploy, internal-code-review |
| G4 | 方案评审 Gate | claude-review |
| G5 | 测试规划 Gate | test-planning |
| G6 | SWE.4 单元验证 Gate | verify-loop, c-unit-test |
| G7 | SWE.5 集成 Gate | code-review, misra-review, integration-test, qemu-verify, coverage-review |
| G8 | 安全门禁 Gate | review-critical-safety, fault-injection |
| G9 | 合并门禁 Gate | merge-gate（CM Gate: KG 一致性 + 仓库管理检查） |
| G10 | SWE.6 合格性 Gate | test-qualification, final-report |

> gate status = 内部子步骤最差状态（failed > retry > skipped > passed），
> 报告聚合输出 `.osh/sessions/<id>/gate-summary.json`。

### 逐步骤清单

| # | 步骤 key | 执行 Agent | 步骤名 | Gate | SWE 映射 |
|---|---------|-----------|--------|:----:|:--------:|
| 1 | `spec-check` | 小明 | OpenSpec 合规检查 | G1 | SWE.1 |
| 2 | `super-analysis` | 小明 | S.U.P.E.R 启动分析（新需求）| G1 | SWE.1 |
| 3 | `prd` | Hermes | 产品需求分析 | G1 | SWE.1 |
| 4 | `prd-review` | 小马 | PRD 双视角审查（质量 + 产品 advisory）| G1 | SWE.1 |
| 5 | `architecture` | Claude | 架构设计 | G2 | SWE.2 |
| 6 | `arch-review` | 小克 | 架构审查 | G2 | SWE.2 |
| 7 | `development` | Claude | 开发计划与代码实现 | G3 | SWE.3 |
| 8 | `development-review` | 小克 | 开发产物审查（2026-08-19 前移）| G3 | SWE.3 |
| 9 | `codegen-deploy` | 小明 | 代码产物部署（护栏备份/回滚）| G3 | SWE.3 |
| 10 | `internal-code-review` | 小克 | 代码实现预审 | G3 | SWE.3 |
| 11 | `claude-review` | Claude | 方案评审（外部 agent，先挑战 spec 假设）| G4 | SWE.3 |
| 12 | `test-planning` | Claude | 测试规划（注入 claude-review blockers/suggestions）| G5 | SWE.3 |
| 13 | `verify-loop` | 小克 | 自测循环（self-test → codex-verify → self-test-review 合并）| G6 | SWE.4 |
| 14 | `c-unit-test` | 小克 | C 单元测试（Unity/Ceedling）| G6 | SWE.4 |
| 15 | `code-review` | 小克 | 集成审查超集（code + 嵌入式 12 专项合并）| G7 | SWE.5 |
| 16 | `misra-review` | 小马 | MISRA 合规审查（前置到单元测试后）| G7 | SWE.5 |
| 17 | `integration-test` | 小克 | 接口集成测试 | G7 | SWE.5 |
| 18 | `qemu-verify` | 小克 | QEMU 仿真验证（qemu-run + c-coverage-gate 合并）| G7 | SWE.5 |
| 19 | `coverage-review` | 小马 | 测试覆盖审查（测试后评估）| G7 | SWE.5 |
| 20 | `review-critical-safety` | 小明 | **⛔ 关键安全异常阻塞检查（P0 GATE）** | G8 | SWE.5 |
| 21 | `fault-injection` | 小克 | 故障注入测试 | G8 | SWE.5/6 |
| 22 | `merge-gate` | 小仓 | **CM Gate**（KG 图一致性 + 仓库管理 4 检查）| G9 | — |
| 23 | `test-qualification` | 小明 | 合格性测试 | G10 | SWE.6 |
| 24 | `final-report` | 小明 | 最终报告 | G10 | SWE.6 |

> 注: 嵌入式专项审查（linker/startup/rtos/memory/bsp/build/power/stack/mmio +
> interrupt/nvm/watchdog/timing = 12 专项）已合并进 `code-review` 超集步骤，
> 对外显示一个步骤，内部顺序执行保留各自专属 prompt/检查深度（能力不损失）。

### 审查步骤归属表

```
文档审查类 → G1(prd-review) G2(arch-review) G3(development-review)
             G6(self-test-review) G7(misra-review, coverage-review)
代码审查类 → G3(internal-code-review) G7(code-review 超集: 集成审查 + 12 专项)
门禁类     → G8(review-critical-safety)
外部评审   → G4(claude-review)
产品评审   → G1(prd-review 双视角: 质量 + 产品, advisory 建议性)
```

### 角色矩阵（九角色链条）

| 链条 | 角色 | 职责 |
|:--|:--|:--|
| 项目 | 小明 | 编排 + 进度/风险 |
| 产品 | Hermes | PRD 生成，产品蓝图 product-blueprint 对齐 |
| 需求 | 小明 | S.U.P.E.R 分析，spec 契约 |
| 架构 | Claude | arch-review 外部评审 |
| 开发 | Claude/Codex | development/codegen + 测试验证 |
| 审查 | 小马 | prd-review/arch-review/development-review/code-review/misra-review |
| 测试 | Codex/小克 | codex-verify + 单测/集成 |
| 合规 | 小马(MISRA) + 小明(P0 门禁) | MISRA 合规 + P0 安全门禁 |
| 仓库管理 | 小仓(CM) | merge-gate CM Gate：工作区清洁/提交规范/产物泄漏/部署护栏 |

### 执行机制

```
用户输入 spec.md
    │
    ▼
[OpenSpec Engine] 解析 SHALL/SHOULD/MAY + GIVEN/WHEN/THEN
    │ 校验层级 ID（RS/SWR）· 状态机 PROPOSED→APPROVED→IMPLEMENTED→VERIFIED
    ▼
[orchestrator.py] 逐步骤:
    for step in PIPELINE_STEPS:
        session.add_step(step_key, agent, step_name)
        output = handler(session, ...)        # 调用 step handler
        session.set_artifact(step_key, path)  # 产物入 session.json
        _propagate_step_verdict(...)          # review 步骤的 PASS/FAIL 决策传播
        # profile 过滤: ci/profile.filter_steps_for_profile()
    ▼
[编排层聚合] gates.write_gate_summary() → .osh/sessions/{id}/gate-summary.json
    ▼
[产物] .yuleosh/sessions/{session_id}/session.json + 各步骤输出
    ▼
[可选] 证据包导出 → evidence/ → audit verify → 归档
```

**关键设计**:
1. **多 Agent 矩阵**: 小明（编排/合规）、Hermes（产品/需求）、Claude（生成/方案评审）、小克（嵌入式专家审查/测试）、小马（质量/合规审查）、小仓（仓库管理 CM）——生成与审查分离
2. **两层视图**: 执行层 24 子步骤（外部 agent 独立超时 / P0 门禁 / --from-step / step_cache 全保留）+ 编排层 10 Gate（对外稳定契约，gate status = 子步骤最差状态）
3. **上下文安全**: context_guard 三档水位（≤50% 正常 / 50-80% 引用式注入 / >80% over_limit），禁止静默尾部截断
4. **⛔ P0 关键门**: review-critical-safety 是阻塞门，检测到关键安全异常直接卡停
5. **CM Gate**: merge-gate 扩展为仓库管理门禁（工作区清洁 warning / 提交规范 / 产物泄漏阻断 / 部署护栏），角色=小仓
6. **Profile 过滤**: 按项目类型（autosar/embedded/generic）过滤步骤

---

## 三、CI/CD 三层流水线（独立于 Agent Pipeline）

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  L1 Dev     │▶▶▶│  L2 Integ   │▶▶▶│  L3 System  │
│  单元测试    │   │  交叉编译    │   │  系统测试    │
│  覆盖率门禁  │   │  MISRA 静态  │   │  证据包      │
│  plan-lint  │   │  4-Agent 审  │   │  签名归档    │
└─────────────┘   └─────────────┘   └─────────────┘
   每次 commit        MR / PR           release tag
```

- **L1**: Go/Python/Embedded 三种语言路径，MISRA profile 验证失败 abort
- **L2**: 交叉编译 + cppcheck MISRA（映射率 ~99%）+ 4 代理并行代码审查
- **L3**: QEMU 系统验证 + 证据包（7 层完整性 + RSA-2048 签名 + 审计哈希链证明）

---

## 四、自动闭环（Loop Engine）

```
                    ┌──────────────────────────────────────────┐
                    │          loop_engine/event_bus           │
                    └──────────────────────────────────────────┘
KPI 超阈值 ──▶ Loop3 工单(requirement_id) ──▶ 修复 ──▶ closed
                                                        │
                        gap close (ASPICE 差距) ──▶ 工单 ─┤
                                                        ▼
                              lesson create --ticket ──▶ Lesson 沉淀
                                                        │
                                   traceability report ◀─┘
                           (每需求: tickets/lessons/闭环标志)
```

- **确定性差距**（KPI 数值/覆盖率/MISRA 计数）→ Loop3 自动生成工单
- **判断性差距**（ASPICE BP 缺口）→ `gap close` 人工确认后生成工单（可审计）
- **知识沉淀** → closed 工单一键 `lesson create` → 回链 ticket_id/requirement_id

---

## 五、安全与合规（横向能力）

| 能力 | 实现 |
|------|------|
| 审计日志 | SHA-256 哈希链（prev_hash 锚链 + 跨日延续）+ `yuleosh audit verify` |
| 证据包 | 7 层完整性检查 + RSA-2048 签名 + audit-log-verification 内嵌证明 |
| 认证 | HttpOnly cookie + refresh 轮换 + 每请求 nonce CSP |
| 生产语义 | compose 密码 `:?` 强制 + AUTH_DISABLED 默认 false（fail-closed）|
| 限流 | per-IP 限流 + 429 拒绝 |
| MISRA 诚实化 | 已知工具链限制显式 skip，不冒充修复 |

---

## 六、部署形态

```
Docker Compose (prod):
  nginx (TLS + CSP) → backend (FastAPI, :8080) → postgres (多租户)
                    └── caddy/monitoring/prometheus 可选
GitHub Actions: ci.yml (3.10~3.13 矩阵) + nightly-compose.yml (每晚验证) + codeql
```

---

## 七、一句话架构总结

> **yuleOSH = OpenSpec 需求引擎 + 33 步多 Agent 流水线（生成/审查分离）+ 3 层 CI/CD + 追溯知识图谱 + 审计哈希链**，覆盖 ASPICE SWE.1~SWE.6 全过程的嵌入式合规自动化平台。

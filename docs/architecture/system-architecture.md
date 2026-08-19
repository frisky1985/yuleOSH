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

## 二、完整 Pipeline 流程（33 步，SWE.1~SWE.6 映射）

> 来源: `src/yuleosh/pipeline/step_handlers/__init__.py` PIPELINE_STEPS（真实注册清单）
> 执行: `yuleosh pipeline run docs/spec.md` → orchestrator 逐步骤执行 → session.json 记录产物

### 阶段总览（按 ASPICE 过程域分组）

```
SWE.1 需求 ──▶ SWE.2 架构 ──▶ SWE.3 编码 ──▶ SWE.4 单元测试 ──▶ SWE.5 集成 ──▶ SWE.6 合格性
   │              │              │               │                │              │
   5 步           2 步           3 步            3 步            10+ 步         2 步
```

### 逐步骤清单

| # | 步骤 key | 执行 Agent | 步骤名 | SWE 映射 |
|---|---------|-----------|--------|:--------:|
| 1 | `spec-check` | 小明 | OpenSpec 合规检查 | SWE.1 |
| 2 | `super-analysis` | 小明 | S.U.P.E.R 启动分析（新需求）| SWE.1 |
| 3 | `prd` | Hermes | 产品需求分析 | SWE.1 |
| 4 | `prd-review` | 小马 | PRD 质量审查 | SWE.1 |
| 5 | `architecture` | Claude | 架构设计 | SWE.2 |
| 6 | `arch-review` | 小克 | 架构审查 | SWE.2 |
| 7 | `development` | Claude | 开发计划与代码实现 | SWE.3 |
| 8 | `development-review` | 小克 | 开发产物审查（2026-08-19 前移: 原名 devplan-review）| SWE.3 |
| 9 | `codegen-deploy` | 小明 | 代码产物部署（护栏备份/回滚）| SWE.3 |
| 10 | `internal-code-review` | 小克 | 代码实现预审 | SWE.3 |
| 11 | `test-planning` | Claude | 测试规划 | SWE.4 |
| 12 | `self-test` | Claude | 自测验证 | SWE.4 |
| 13 | `self-test-review` | 小克 | 自测结果审查 | SWE.4 |
| 14 | `c-unit-test` | 小克 | C 单元测试（Unity/Ceedling）| SWE.4 |
| 15 | `code-review` | Hermes | 集成代码审查（**2026-08-07 前移到集成测试前**）| SWE.5 |
| 16 | `integration-test` | 小克 | 接口集成测试 | SWE.5 |
| 17 | `misra-review` | 小马 | MISRA 合规审查（测试后评估）| SWE.5 |
| 18 | `coverage-review` | 小马 | 测试覆盖审查（测试后评估）| SWE.5 |
| 19 | `qemu-run` | QEMU | QEMU 仿真测试（L2）| SWE.5 |
| 20 | `c-coverage-gate` | 小克 | C 覆盖率门禁检查（L2）| SWE.5 |
| 21 | `review-linker` | 小克 | 链接脚本审查 | SWE.5 |
| 22 | `review-startup` | 小克 | 启动代码审查 | SWE.5 |
| 23 | `review-rtos` | 小克 | RTOS 配置审查 | SWE.5 |
| 24 | `review-memory` | 小克 | 内存安全审查 | SWE.5 |
| 25 | `review-bsp` | 小克 | BSP 板级支持包验证 | SWE.5 |
| 26 | `review-build` | 小克 | 编译输出验证 | SWE.5 |
| 27 | `review-power` | 小克 | 低功耗审查 | SWE.5 |
| 28 | `review-stack` | 小克 | 堆栈使用分析 | SWE.5 |
| 29 | `review-mmio` | 小克 | MMIO 配置审查 | SWE.5 |
| 30 | `review-critical-safety` | 小明 | **⛔ 关键安全异常阻塞检查（P0 GATE）** | SWE.5 |
| 31 | `fault-injection` | 小克 | 故障注入测试 | SWE.5/6 |
| 32 | `merge-gate` | 小马 | KG Merge Gate（图一致性）| — |
| 33 | `test-qualification` | 小明 | 合格性测试 | SWE.6 |
| 34 | `final-report` | 小明 | 最终报告 | SWE.6 |

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
[产物] .yuleosh/sessions/{session_id}/session.json + 各步骤输出
    ▼
[可选] 证据包导出 → evidence/ → audit verify → 归档
```

**关键设计**:
1. **多 Agent 矩阵**: 小明（编排/合规）、Hermes（需求/集成审查）、Claude（生成）、小克（嵌入式专家审查）、小马（质量/合规审查）——生成与审查分离
2. **审查门禁**: 每阶段转换前有 review 步骤（prd-review → arch-review → development-review → code-review → ...），verdict 传播到 session
3. **⛔ P0 关键门**: review-critical-safety 是阻塞门，检测到关键安全异常直接卡停
4. **Profile 过滤**: 按项目类型（autosar/embedded/generic）过滤步骤

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

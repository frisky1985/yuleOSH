# 🔍 Round 1 质量审查报告

> **审查者**: 小马 🐴 (Hermes, Quality Architect)  
> **审查时间**: 2026-06-07  
> **审查范围**: yuleOSH v0.2.0 Sprint 1 — AI Pipeline 真集成  
> **审查对象**: `src/llm/client.py`, `src/pipeline/run.py`, `docs/spec.md`

---

## 目录

1. [LLM Client 架构审查](#1-llm-client-架构审查)
2. [Pipeline 改造质量审查](#2-pipeline-改造质量审查)
3. [Spec 合规检查](#3-spec-合规检查)
4. [v0.2.0 验收矩阵](#4-v020-验收矩阵)
5. [改进建议](#5-改进建议)
6. [总结评分](#6-总结评分)

---

## 1. LLM Client 架构审查

### 1.1 模块结构

```
src/llm/
├── __init__.py          ← 空，可考虑导出 chat_completion
└── client.py            ← 核心：158 行，纯 urllib 实现
```

### 1.2 评分：⭐️⭐️⭐️⭐️ (8.5/10)

| 维度 | 评分 | 说明 |
|------|------|------|
| **模块边界** | ✅ 清晰 | 5 个私有函数 + 1 个公开 API，职责单一 |
| **零依赖** | ✅ 优秀 | 仅用 `urllib`，无需 `requests`/`httpx` |
| **错误处理** | ✅ 完善 | HTTPError / URLError / JSONDecodeError 全覆盖 |
| **重试机制** | ✅ 合理 | 指数退避 (1s, 2s, 4s)，log 清晰 |
| **可配置性** | ✅ 良好 | 环境变量 + 函数参数双重配置 |
| **文档** | ✅ 详细 | 模块 docstring + 函数 docstring 均有 |
| **类型提示** | ⚠️ 部分 | `_do_request` 参数类型标注有小瑕疵 |

### 1.3 值得肯定的设计决策

1. **零外部依赖** — 用 `urllib` 而非 `requests` 避免引入重量级依赖，对嵌入式工具链是合理选择
2. **三键兜底** — `LLM_API_KEY → DEEPSEEK_API_KEY → OPENAI_API_KEY`，符合多种部署场景
3. **JSON 响应结构标准化** — `chat_completion` 统一返回 `{content, model, usage}`，调用方不需要了解底层 API 差异
4. **`None content` 处理** — 发现 `content=null` 时自动转为 refusal 标记，避免下游炸裂
5. **日志埋点** — 每次请求都打 `model, prompt_len, user_len, attempt`，可观测性好

### 1.4 架构问题

#### P1 — 重试次数与 Spec 不匹配

```python
# client.py L92
def chat_completion(..., retries: int = 3) -> dict:
```

Spec 要求 "gracefully handle agent failures with retry (max 5 rounds)"。当前默认 3 次与 Spec 要求的 5 次不一致。

#### P2 — 缺少 RequestId / TraceId

每次 LLM 调用没有分配唯一 ID，导致：
- 日志中无法关联同一请求的多个 attempt
- 无法跨服务追踪
- 审计时缺少链路标识

#### P3 — 无连接池 / Keep-Alive

`urllib` 每请求重建 TCP 连接。Pipeline 中有 4+ 个 LLM 调用，每次建连浪费约 50-100ms。建议换 `httpx` 或 `urllib3` 连接池（如果允许引入依赖）。

#### P4 — Spec 解析逻辑重复

`step_super_analysis` 和 `step_claude_arch` 都在 `_parse_spec()` 中自行解析 spec Markdown。而 `spec/validate.py` 已经是规范的 spec 解析器。存在两套解析逻辑不一致的风险。

---

## 2. Pipeline 改造质量审查

### 2.1 评分：⭐️⭐️⭐️⭐️ (7.5/10)

| 维度 | 评分 | 说明 |
|------|------|------|
| **改造覆盖** | ⚠️ 部分 | 4/6 Phase 1 项完成 |
| **LLM 集成质量** | ✅ 良好 | 真实调用，token 日志，元数据头 |
| **错误处理** | ✅ 较好 | 逐级 try/except，Pipeline 级兜底 |
| **可观测性** | ✅ 较强 | 每条 Step 有 timing decorator + 结构化日志 |
| **Session 管理** | ✅ 稳健 | SQLite + JSON 双持久化 |
| **测试覆盖** | ⚠️ 不足 | E2E 测试未验证 LLM 真实调用 |

### 2.2 改动分析

#### ✅ `step_super_analysis` (改造成功)

```
改造前: 模板填充 "Situation: {{SITUATION}}"  
改造后: chat_completion(system_prompt, user_prompt) 带真实 spec 内容
```

**优点**:
- 传入了 parsed metadata（requirements 数、SHALL 数、scenario 数）
- 输出带 token 使用统计和 model 标识
- spec 内容截断到 12000 字符（合理折中）

**问题**:
- `spec_content[:12000]` 硬编码截断，如果 spec 大可能丢内容
- 六项中 "Priority" 跟第五项的 "P" 重复（S.U.P.E.R + P = 6 items，最后一个 P 是 Priority，但这个缩写本来是 S.U.P.E.R）

#### ✅ `step_claude_arch` (改造成功)

```
改造前: 目录扫描 + 模板输出  
改造后: 目录扫描 + spec 内容 + 源码片段 → 调 LLM 做真实架构分析
```

**优点**:
- 发现了真实的项目目录结构和源码
- 传入了关键文件 snippets
- LLM 返回 token 日志完整

**问题**:
- `spec_content[:8000]` 截断太短（vs. super_analysis 的 12000），可能丢失上下半部分
- `key_file_snippets` 只抓前 15 个文件、每个 2000 字符，如果核心文件多可能漏

#### ❌ `step_claude_dev` (未改造)

当前仍是 git log + 文件计数模板。v0.2.0 plan 要求接入 LLM。

#### ❌ `step_hermes_review` (未改造)

当前 `step_hermes_review` 只生成静态 JSON:
```python
review = {
    "status": "passed",
    "findings": [],
    "summary": "Code review completed. All spec requirements verified.",
}
```

这是**假审查**。v0.2.0 plan 要求调 LLM 做真实代码审查。

### 2.3 其他问题

1. **Spec 解析两套** — `_parse_spec()` 在 `run.py` 中独立实现，与 `src/spec/validate.py` 的解析逻辑重复。如果改 spec 格式需要同步改两处。

2. **`step_internal_review` 仍是文件存在性检查** — 检测 artifact 是否存在，但不检查内容质量。

3. **Final report 在 `completed` 前设状态** — 有竞态问题：
   ```python
   if step_key == "final-report":
       session.status = "completed"
   ```

4. **`_save(persist=False)` 逻辑** — 中间状态不持久化，但如果 Pipeline 在中间步骤崩溃，丢失了所有中间进度。

---

## 3. Spec 合规检查

> 基准: `docs/spec.md` v0.1.0 的 ALL SHALL/SHOULD 语句

### 3.1 Req-001: Agent 驱动的开发流水线 ✅△

| SHALL 要求 | 状态 | 判定说明 |
|------------|------|----------|
| SDD → DDD → TDD → CI/CD pipeline | ⚠️ Partial | Pipeline 存在，SDD/DDD 有 LLM 覆盖，TDD 自测 OK，CI/CD 仅 placeholder |
| OpenSpec 格式支持 | ✅ Done | `src/spec/validate.py` 校验 |
| Superpowers 14 Rules 全阶段执行 | ⚠️ Partial | 部分 Step 有 review，14 条规则未显式实现 |
| Harness Engineering 路由 (PM→Product→Arch/Dev) | ✅ Done | Pipeline 定义了 小明→Hermes→Claude 三步路由 |

### 3.2 Req-002: 需求管理 ✅△

| SHALL 要求 | 状态 | 判定说明 |
|------------|------|----------|
| 需求树层次 (SYS→SW→Feature→Scenario→Task) | ⚠️ Partial | `_parse_requirements` 能解析层级，但未结构化存储 |
| OpenSpec RFC 2119 格式 | ✅ Done | validate.py 校验 SHALL/SHOULD/MAY |
| Spec-delta 追踪 | ✅ Done | `src/spec/diff.py` 已实现 |
| S.U.P.E.R 启动分析 | ✅ Done | **本次改造核心产出**，真实 LLM 分析 ✅ |
| 需求基线化和版本化 | ❌ Not yet | MAY 要求，可延后 |

### 3.3 Req-003: 代码审查与 Agent 矩阵 ❌❌

| 要求 | 状态 | 判定说明 |
|------|------|----------|
| SHALL per-task blocking review by AI agents | ❌ Not done | `step_hermes_review` 是静态 JSON stub |
| SHALL dual-track review (非阻塞自检+阻塞审核) | ❌ Not done | 仅有内审，无 block/unblock 机制 |
| SHALL auto-reviewer routing based on task type | ❌ Not done | 路由仍硬编码 |
| SHOULD coverage-guardian > 98% | ❌ Not done | 无覆盖率门禁 |

### 3.4 Req-004: CI/CD 三层流水线 ❌

| 要求 | 状态 | 判定说明 |
|------|------|----------|
| SHALL 3-layer CI/CD | ⚠️ Partial | `src/ci/run.py` 有架子，未完整集成 |
| SHALL ARM/RISC-V/x86_64 交叉编译 | ❌ Not done | 依赖后续 sprint |
| SHALL MISRA-C/C++ 静态分析门禁 | ❌ Not done | 嵌入式场景特有需求 |
| SHALL auto-generate ASPICE compliance evidence | ⚠️ Partial | `src/evidence/pack.py` 存在 |
| SHOULD firmware signing + OTA | ❌ Not done | v0.1.0 MVP 不要求 |

### 3.5 Req-005: 追溯与证据链 ✅△

| 要求 | 状态 | 判定说明 |
|------|------|----------|
| SHALL traceability matrix (Req↔Design↔Code↔Test) | ⚠️ Partial | PRD 有映射但未自动生成矩阵 |
| SHALL archive agent review records as JSON evidence | ✅ Done | Pipeline 有 artifact 收集，但 review 内容欠缺 |
| SHALL export compliance pack for ASPICE audit | ⚠️ Partial | `pack.py` 存在，需要验证 |

### 3.6 Req-006 / Req-007 / 非功能需求

| 要求 | 状态 | 判定说明 |
|------|------|----------|
| SHALL Web UI | ✅ Done | `src/ui/server.py` |
| SHALL 5s 响应 (agent review) | ❌ Likely fail | LLM 调用通常 5-15s，需异步化 |
| SHALL 并行执行独立任务 | ✅ Done | Pipeline 设计支持并行（未完全利用） |
| SHALL agent failure retry max 5 rounds | ❌ Mismatch | `client.py` 默认 3 次，spec 要求 5 次 |
| SHOULD 任务执行日志 | ✅ Done | Pipeline session.json 包含 |

### 3.7 Spec 本身的问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| Superpowers 14 Rules 未展开 | P2 | Spec 引用但没有具体列出 14 条规则 |
| 5s 响应要求不合理 | P2 | LLM API 调用通常在 5-15s，5s 只能做异步 |
| Retry "max 5 rounds" vs 实际 3 次 | P2 | 文档与实现不一致，两者要统一 |

---

## 4. v0.2.0 验收矩阵

### Phase 1: Pipeline 接入 LLM API

| 序号 | 项目 | 负责 | 状态 | 验收标准 | 判定 |
|------|------|------|------|----------|------|
| 1 | `src/llm/client.py` — LLM API 客户端 | 小克 | ✅ **DONE** | 支持 chat completion，重试，环境变量配置 | ✅ 通过 |
| 2 | `super-analysis` → LLM | 小克 | ✅ **DONE** | 真实调 LLM 做 S.U.P.E.R 分析，输出 > 模板 | ✅ 通过 |
| 3 | `claude-arch` → LLM | 小克 | ✅ **DONE** | 真实调 LLM 做架构分析，用项目目录+源码 | ✅ 通过 |
| 4 | `claude-dev` → LLM | 小克 | ❌ **NOT DONE** | 调 LLM 生成开发计划/增量分析 | ❌ **阻塞** |
| 5 | `hermes-review` → LLM | 小克 | ❌ **NOT DONE** | 调 LLM 做真实代码审查 | ❌ **阻塞** |
| 6 | 测试 + 文档 | 小克 | ⚠️ **Partial** | E2E 测试覆盖 LLM 调用 | ⚠️ 待补充 |

### Phase 2: Pipeline 路由到真 Agent

| 序号 | 项目 | 状态 | 验收标准 | 判定 |
|------|------|------|----------|------|
| 1 | Claude 步骤 → Claude sub-agent | ❌ Not started | Sub-agent 上下文传递 | ❌ |
| 2 | Hermes 步骤 → Hermes sub-agent | ❌ Not started | Sub-agent 上下文传递 | ❌ |
| 3 | 小明步骤 → 小明自己做 | ❌ Not started | 同上 | ❌ |

### 总体完成率

| 阶段 | 完成 | 部分 | 未开始 |
|------|------|------|--------|
| Phase 1 (6项) | **3** | 1 | **2** |
| Phase 2 (3项) | 0 | 0 | **3** |
| **总计** | **33%** | **11%** | **56%** |

**总体判定**: ⚠️ **Conditional PASS** — 核心基础设施 (client.py) 和两个主要 Step 已完成。但剩 2 个 Phase 1 阻塞项 (claude-dev, hermes-review) 未完成，Phase 2 尚未开始。

---

## 5. 改进建议

### 🔴 P0 — 必须修复 (本轮)

1. **完成 claude-dev 接入 LLM** — `step_claude_dev` 当前是模板，按 Plan 必须调 LLM。建议将 git log + 文件计数作为上下文传给 LLM，让 LLM 生成增量开发报告。

2. **完成 hermes-review 接入 LLM** — `step_hermes_review` 是假审查。这是 Spec Req-003 的 SHALL 要求。建议：
   - 读取所有 artifact 文件作为上下文
   - 对比 spec 的 SHALL 要求与实际产出
   - LLM 输出 structured findings

3. **统一 retry 次数** — `client.py` 默认 3 次 vs Spec 5 次。要么改 client 默认值为 5，要么改 spec 为 3（更合理），必须有决定。

### 🟡 P1 — 高优先级 (Sprint 内)

4. **消除 Spec 解析重复** — `_parse_spec()` 在 `run.py` 中与 `src/spec/validate.py` 重复。建议：`run.py` 改为调用 `spec/validate.py` --json 输出，或者将 `_parse_spec` 提取到共用模块。

5. **RequestId/TraceId 注入** — 每个 LLM 请求分配 UUID，在日志和响应中带回。对调试和审计都重要。

6. **增加 LLM Client 单元测试** — 当前无 `test_llm_client.py`。至少覆盖：环境变量解析、构建 payload、错误处理路径。

### 🔵 P2 — 中优先级 (下个 Sprint)

7. **配置化 prompt 模板** — `step_super_analysis` 和 `step_claude_arch` 的 system_prompt 硬编码在函数体内。建议提取到 `prompts/` 目录或 config。

8. **考虑 httpx 连接池** — 如果 Pipeline 步骤数增加，`urllib` 每请求建连的开销会累积。建议评估引入 `httpx`。

9. **`_save(persist=False)` 策略优化** — 当前中间状态不保存，若 Pipeline 在运行中崩溃则丢失全部进度。建议每步完成都 persist，或至少 checkpoint 到磁盘。

10. **异步化 Agent Review** — Spec 要求 5s 内响应，但 LLM 调用需要 5-15s。考虑：
    - 异步启动 LLM 调用，立即返回 "pending" 状态
    - Webhook 或轮询获取结果
    - 时间不敏感的审查可延缓到 CI 阶段

### 🟢 P3 — 低优先级 (技术债务)

11. **清理 S.U.P.E.R 缩写的 double-P** — 系统 prompt 中 "S.U.P.E.R. analysis" 实际包含 6 项（S,U,P,E,R,P）。建议正名：要么 5 项（去掉 Priority），要么改缩写。

12. **改进 spec 截断策略** — 当前硬编码 12000/8000 字符。建议：
    - 按 token 数估算截断（1 char ≈ 0.25 token）
    - 或按 requirement 数量指数衰减

13. **Final report 竞态** — `if step_key == "final-report": session.status = "completed"` 发生在 handler 执行前，应为 handler 执行成功后设置。

---

## 6. 总结评分

| 维度 | 得分 | 评级 |
|------|------|------|
| **LLM Client 架构** | 8.5/10 | 🟢 Excellent |
| **Pipeline 改造质量** | 7.5/10 | 🟢 Good |
| **Spec 合规覆盖** | 6.0/10 | 🟡 Fair |
| **v0.2.0 进度** | 4.0/10 | 🔴 Behind |
| **Code Review 质量** | 8.0/10 | 🟢 Good |
| **整体** | **6.8/10** | 🟡 Needs Improvement |

### 一句话总结

> 🐴 **小马判定**: 底层基础设施 (`client.py`) 扎实，小克干得漂亮 👍。但 Phase 1 还剩 claude-dev 和 hermes-review 两个阻塞项没动，Spec Req-003 (代码审查) 完全未覆盖，**需要先清掉这两个 P0 再到 Phase 2**。

---

*审查完毕。小明如果有疑问随时喊我 🐴*

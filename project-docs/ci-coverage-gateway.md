# 覆盖率阶梯计划 — CI Coverage Gateway

> **版本**: v1.0.0 | **状态**: DRAFT  
> **维护人**: 小马 🐴 (质量架构师)  
> **规范依据**: ISO 26262-8 §8 / ASPICE SWE.4 / MISRA C:2023 测试建议  
> **最后更新**: 2026-06-14

---

## 1. 概述

### 1.1 目的

本文档定义 yuleOSH 项目行覆盖率（line coverage）在 CI pipeline 中的**阶梯式提升计划**。覆盖率门禁的阶梯化是为了：

1. **渐进收敛**：避免从 60% 一步跳到 85% 导致的开发阻塞和计划外赶工。
2. **可预测交付**：每个阶梯有明确的触发窗口和验收条件，团队可分配测试 sprint。
3. **质量可审计**：每个台阶的覆盖目标、达成证据和回退判定均可追溯。

### 1.2 范围

本文档适用于：

- CI pipeline 中 `--cov-fail-under` 参数的阈值管理
- 所有 `src/yuleosh/` 下的 Python 源文件的**行覆盖率**（line coverage）
- 覆盖率的**分支覆盖率**（branch coverage）作为辅助指标

### 1.3 术语定义

| 术语 | 定义 |
|:----|:-----|
| **Line Coverage** | 代码行被执行的比例，排除空行和注释。 |
| **Branch Coverage** | 条件语句中所有分支（if/else/elif）被覆盖的比例。 |
| **CI Gate** | pipeline 中 `pytest --cov-fail-under` 设定的最低通过阈值。 |
| **Hard Gate** | 覆盖率低于阈值时 **阻塞** PR 合并。 |
| **Soft Gate** | 覆盖率低于阈值时发出 **警告**，不阻塞合并，但触发自动通知。 |
| **Ladder Step** | 一个完整的覆盖目标阶段，含起始值、目标值、验收标准和回退条件。 |
| **Gap File** | `pytest --cov-report=term-missing` 输出中显示为未覆盖的文件。 |
| **Coverage Debt** | 主动决定暂不覆盖的代码区域，记录在 `docs/coverage-debt.md`。 |

---

## 2. 阶梯定义

### 2.1 阶梯总览

| 阶梯 | 阶段名 | CI Hard Gate | 达成窗口 | 验收要求 |
|:----:|:-------|:------------:|:---------|:---------|
| L0 | 当前基线 | **60%** | 已达成 | `--cov-fail-under=60` (当前配置) |
| L1 | 夯实基础 | **65%** | 2026-Q3 第 2 周 | 无红色 Gap File |
| L2 | 核心覆盖 | **70%** | 2026-Q3 第 6 周 | store_pg ≥90%, ci/run ≥80% |
| L3 | 深度渗透 | **75%** | 2026-Q4 第 2 周 | api/*.py ≥70%, store.py ≥80% |
| L4 | 全面达标 | **80%** | 2027-Q1 第 2 周 | 全模块 ≥70%, 无 >50 行未覆盖文件 |
| L5 | 卓越品质 | **85%** | 2027-Q2 第 2 周 | 全模块 ≥80%, branch ≥75% |

### 2.2 阶梯详细定义

#### L0 — 当前基线 (60%)

| 属性 | 值 |
|:----|:----|
| **状态** | ✅ **已达成** |
| **CI 配置** | `--cov-fail-under=60` |
| **当前实测** | ~62.3% (2026-06-14) |
| **覆盖缺口** | 主要缺口在 cross/*.py, api/*.py, store.py |

**GIVEN** CI pipeline 的 `--cov-fail-under` 设为 60
**WHEN** 整体行覆盖率 ≥ 60%
**THEN** CI SHALL 返回绿色 ✅

**GIVEN** 整体行覆盖率 < 60%
**WHEN** PR 被创建或更新
**THEN** CI SHALL 阻塞合并 (Hard Gate) ❌

#### L1 — 夯实基础 (65%)

| 属性 | 值 |
|:----|:----|
| **状态** | 🟡 **在途** |
| **CI 配置** | `--cov-fail-under=65` |
| **假定达成日期** | 2026-Q3 第 2 周 |
| **触发条件** | 上一个 Release 或 Sprint 的覆盖率趋势 ≥ 63% 且稳定 |

**L1 预期提升模块：**

| 模块 | 当前估算 | 目标 | 需新增测试 |
|:----|:--------:|:----:|:----------|
| `store.py` | ~40% | ≥55% | SQLite 存储各 CRUD 路径 + 异常处理 |
| `cross/flash.py` | ~45% | ≥55% | FlashRunner facade failover 路径 |
| `cross/target_config.py` | ~55% | ≥65% | JSON 解析 + 配置 fallback |
| `api/auth.py` | ~35% | ≥50% | JWT 验证 + 角色鉴权 |

**L1 触发条件：**

1. 🟢 **趋势触发**：最近连续 3 次 CI 运行的覆盖率 ≥ 63%
2. 🟢 **时间触发**：到达 2026-Q3 第 2 周
3. 🔴 **强制触发**：发现未覆盖的 P0 缺陷
4. 🟡 **SHALL**：L1 门禁在 `pytest.ini` 中配置为 `--cov-fail-under=65`
5. 🟡 **SHOULD**：L1 升级前的 1 周在 `#quality` 频道发布预告通知

**L1 验收标准：**

- [ ] CI 全量测试 671+ passed，0 failed
- [ ] `--cov-fail-under=65` 通过
- [ ] 所有 Gap File 不存在红色缺口（0% 或 <30% 覆盖）
- [ ] `docs/coverage-debt.md` 已建立并列出所有已知债务

**L1 回退机制：**

| 触发条件 | 回退操作 | 恢复条件 |
|:---------|:---------|:---------|
| 连续 5 次 CI 构建无法通过 L1 | 自动降级到 L0 (60%) | 质量架构师人工确认后恢复 |
| 关键模块覆盖率回退 >5% | 回退到 L0 并发出告警 | 缺陷修复后重新验证 L1 |
| L1 窗口无法在 2 周内达成 | 延期到下一个 Sprint | 报告延期原因 + 更新计划 |

```yaml
# pytest.ini 配置（L1 阶段）
# addopts = --cov=yuleosh --cov-report=term-missing --cov-report=html --cov-fail-under=65
```

---

#### L2 — 核心覆盖 (70%)

| 属性 | 值 |
|:----|:----|
| **状态** | ⏳ **计划中** |
| **CI 配置** | `--cov-fail-under=70` |
| **假定达成日期** | 2026-Q3 第 6 周 |
| **触发条件** | L1 稳定运行 ≥2 周 + 核心模块覆盖达标 |

**L2 预期提升模块：**

| 模块 | 当前估算 | 目标 | 需新增测试 |
|:----|:--------:|:----:|:----------|
| `store_pg.py` | 100% ✅ | **≥90%** (维持) | N/A — 已达目标 |
| `ci/run.py` | 83% ✅ | **≥80%** (维持) | N/A — 已达目标 |
| `store.py` | ~40% | **≥65%** | 完整 SQLite CRUD + 并发 + 迁移 |
| `api/auth.py` | ~35% | **≥60%** | 登录、注册、Token 刷新、RBAC |
| `api/projects.py` | ~30% | **≥50%** | 项目 CRUD + 权限校验 |
| `spec/engine.py` | ~55% | **≥65%** | 规范解析 Error path + 边界 case |

**L2 触发条件：**

1. L1 门禁持续通过 ≥10 个工作日
2. `store_pg.py` 覆盖率维持在 ≥95%
3. `ci/run.py` 覆盖率维持在 ≥80%
4. 核心模块（store_pg, ci/run, api/*）的覆盖率总和 ≥ 65%
5. **SHALL**：L2 升级前完成一次全量覆盖率审计

**L2 验收标准：**

- [ ] CI `--cov-fail-under=70` 连续通过 5 次构建
- [ ] `store_pg.py` 覆盖率 ≥90%
- [ ] `ci/run.py` 覆盖率 ≥80%
- [ ] `api/*.py` 覆盖率总和 ≥60%
- [ ] `store.py` 覆盖率 ≥65%
- [ ] 无文件覆盖率 <30%（特殊豁免除外）
- [ ] `docs/coverage-debt.md` 覆盖率债务 ≤ 300 行

**L2 回退机制：**

| 触发条件 | 回退操作 |
|:---------|:---------|
| 核心模块任一覆盖率低于目标 -5% | 回退到 L1，修复后重新验证 |
| 连续 3 次构建 L2 失败且与覆盖率无关 | 触发人工审查排除配置问题 |
| L2 窗口 + 2 周仍未达成 | 质量架构师介入，重新排期 |

---

#### L3 — 深度渗透 (75%)

| 属性 | 值 |
|:----|:----|
| **状态** | ⏳ **计划中** |
| **CI 配置** | `--cov-fail-under=75` |
| **假定达成日期** | 2026-Q4 第 2 周 |
| **触发条件** | L2 稳定运行 ≥3 周 + 全模块基础覆盖 |

**L3 预期提升模块：**

| 模块 | 当前估算 | 目标 | 需新增测试 |
|:----|:--------:|:----:|:----------|
| `api/*.py` | ~35% | **≥70%** | 所有 REST 端点错误路径 + 参数校验 |
| `cross/*.py` | ~40% | **≥60%** | 各 Runner（OpenOCD/JLink/PyOCD）错误处理 + fallback |
| `spec/*.py` | ~55% | **≥70%** | 复杂规范解析 + 嵌套场景 |
| `store.py` | ~40% | **≥80%** | 事务回滚 + 锁竞争 + 数据迁移 |
| `plugins/*.py` | ~25% | **≥50%** | 插件注册 + 执行 + 热加载 |
| `llm/*.py` | ~30% | **≥50%** | LLM 调用 + 重试 + 超时 + 降级 |

**L3 触发条件：**

1. L2 门禁持续通过 ≥15 个工作日
2. **SHALL**：覆盖缺口分析报告生成，识别 top-5 低覆盖模块
3. **SHOULD**：完成一轮 `smoke vs deep` 测试审计（验证 deep 测试覆盖了 smoke 之外的路径）
4. **SHALL**：无 P0 级别的覆盖缺陷（关键路径完全无测试）

**L3 验收标准：**

- [ ] CI `--cov-fail-under=75` 连续通过 5 次构建
- [ ] `api/*.py` 覆盖率 ≥70%
- [ ] `cross/*.py` 覆盖率 ≥60%
- [ ] `spec/*.py` 覆盖率 ≥70%
- [ ] 无文件覆盖率 <40%
- [ ] branch coverage ≥60%
- [ ] `docs/coverage-debt.md` 覆盖率债务 ≤ 200 行

**L3 回退机制：**

| 触发条件 | 回退操作 |
|:---------|:---------|
| 任一模块覆盖率低于其目标 -10% | 回退到 L2 |
| branch coverage <50% | 回退到 L2，添加分支覆盖改进计划 |
| 窗口 + 3 周仍未达成 | 与项目经理协商是否降低目标 |

---

#### L4 — 全面达标 (80%)

| 属性 | 值 |
|:----|:----|
| **状态** | ⏳ **远景** |
| **CI 配置** | `--cov-fail-under=80` |
| **假定达成日期** | 2027-Q1 第 2 周 |
| **触发条件** | L3 稳定 ≥1 个月 + 所有模块 ≥70% |

**L4 预期提升模块：**

| 模块 | 当前估算 | 目标 | 需新增测试 |
|:----|:--------:|:----:|:----------|
| `all modules` | 混合 | **≥70%** | 所有剩余模块补齐至 ≥70% |
| `cross/*.py` | ~40% | **≥75%** | SIL/HIL runner 错误处理 |
| `plugins/*.py` | ~25% | **≥65%** | 插件安全 + 沙箱 + 热卸载 |
| `llm/*.py` | ~30% | **≥65%** | 流式响应 + 模型切换 + token 管理 |
| `cli/*.py` | ~20% | **≥60%** | CLI 参数解析 + 各子命令 |

**L4 验收标准：**

- [ ] CI `--cov-fail-under=80` 连续通过 5 次构建
- [ ] 所有模块覆盖率 ≥70%
- [ ] 无文件覆盖率 <50%
- [ ] branch coverage ≥70%
- [ ] 覆盖率债务 ≤ 100 行
- [ ] **SHALL**：项目整体 SHALL 覆盖率（RTM）≥85%

**L4 回退机制：**

| 触发条件 | 回退操作 |
|:---------|:---------|
| 任意 2 个模块低于其目标 | 回退到 L3 |
| branch coverage <65% | 回退到 L3 + 审查需改进的分支 |
| 窗口 + 1 个月未达成 | 重新评估覆盖率目标的合理性 |

---

#### L5 — 卓越品质 (85%)

| 属性 | 值 |
|:----|:----|
| **状态** | ⏳ **远景** |
| **CI 配置** | `--cov-fail-under=85` |
| **假定达成日期** | 2027-Q2 第 2 周 |
| **触发条件** | L4 稳定 ≥2 个月 + 全模块 ≥80% |

**L5 验收标准：**

- [ ] CI `--cov-fail-under=85` 连续通过 5 次构建
- [ ] 所有模块覆盖率 ≥80%
- [ ] No 文件覆盖率 <65%
- [ ] branch coverage ≥75%
- [ ] 覆盖率债务 ≤ 50 行
- [ ] **SHALL**：项目整体 SHALL 覆盖率（RTM）≥90%

**L5 回退机制：**

| 触发条件 | 回退操作 |
|:---------|:---------|
| 超过临界值 5% | 回退到 L4 + 质量审计 |
| branch coverage <70% 超过 1 周 | 回退到 L4 |

---

## 3. CI Pipeline 集成方式

### 3.1 门禁配置模型

阶梯门禁 SHALL 通过 `pytest.ini` 中的 `--cov-fail-under` 参数控制：

```ini
[pytest]
testpaths = tests
pythonpath = src
addopts = --cov=yuleosh
         --cov-report=term-missing
         --cov-report=html:artifacts/coverage-report/
         --cov-fail-under=60
```

**GIVEN** 团队决定升级到 L1 (65%)
**WHEN** `pytest.ini` 中的 `--cov-fail-under` 从 60 修改为 65
**THEN** CI SHALL 自动执行新的门禁标准

### 3.2 门禁硬性规则

| # | 规则 | 强制等级 |
|:--|:-----|:--------:|
| CGW-R01 | `--cov-fail-under` SHALL 与当前的阶梯等级一致 | SHALL |
| CGW-R02 | 阶梯升级 SHOULD 在 Sprint Planning 上正式决议 | SHOULD |
| CGW-R03 | 阶梯降级 SHALL 由质量架构师确认触发原因后执行 | SHALL |
| CGW-R04 | 每次阶梯变更 SHALL 更新 `pytest.ini` 并提交到 master | SHALL |
| CGW-R05 | 每个阶梯达成时 SHALL 在 `docs/coverage-milestones.md` 记录 | SHALL |
| CGW-R06 | 门禁值与当前阶梯的偏差 SHALL 不超过 2%（CI 可容忍波动） | SHALL |
| CGW-R07 | 覆盖率报告 SHALL 在每次 CI 运行后自动归档到 `artifacts/coverage/` | SHALL |
| CGW-R08 | 覆盖率趋势 SHOULD 每周同步到项目看板 | SHOULD |

### 3.3 CI 流水线中的门禁执行

```
┌──────────────────────────────────────────────────────────┐
│                    CI Pipeline                             │
├──────────────────────────────────────────────────────────┤
│  Stage 1: Lint + Type Check                              │
│  → flake8, mypy, black --check                           │
├──────────────────────────────────────────────────────────┤
│  Stage 2: Smoke Tests (快速验证)                          │
│  → pytest -k "smoke" -x --timeout=60                     │
│  → 如果 smoke 失败则快速 fail，不再继续                   │
├──────────────────────────────────────────────────────────┤
│  Stage 3: Full Tests + Coverage Gate ★                  │
│  → pytest --cov=yuleosh --cov-fail-under={CURRENT_GATE}  │
│  → 产出: artifacts/coverage/coverage.json               │
│  → 产出: artifacts/coverage/coverage.html                │
├──────────────────────────────────────────────────────────┤
│  Stage 4: Coverage Trend Check (辅助)                    │
│  → 与上次对比，通知覆盖率变化 >3%                        │
│  → 不高亮红线，仅作为趋势通知                            │
├──────────────────────────────────────────────────────────┤
│  Stage 5: Gate Decision                                  │
│  → cov-fail-under 结果为硬门禁 → PASS/FAIL                │
│  → FAIL 时输出 Gap 文件列表 + 建议提升文件                │
└──────────────────────────────────────────────────────────┘
```

### 3.4 阶梯升级/降级脚本

```bash
#!/bin/bash
# ci/coverage-staircase.sh — 检查当前覆盖率状态并建议升级/降级

set -euo pipefail

CURRENT_GATE=$(grep -oP 'cov-fail-under=\K[0-9]+' pytest.ini || echo "60")
COVERAGE_RESULT=$(python -c "
import json
with open('artifacts/coverage/coverage.json') as f:
    data = json.load(f)
print(data.get('totals', {}).get('percent_covered', 0))
")
COVERAGE_RESULT=${COVERAGE_RESULT%.*}  # 取整

echo "📊 Current gate: ${CURRENT_GATE}%"
echo "📈 Measured coverage: ${COVERAGE_RESULT}%"

# 升级检查：实测高出门禁 ≥2% 且稳定
if [ $((COVERAGE_RESULT - CURRENT_GATE)) -ge 2 ]; then
    echo "✅ Coverage exceeds gate by ≥2% — ready for next step"
else
    echo "⏳ Coverage within gate margin — maintain current step"
fi

# 降级检查：实测连续低于门禁
if [ $((CURRENT_GATE - COVERAGE_RESULT)) -ge 3 ]; then
    echo "⚠️ Coverage falls below gate — consider downgrading"
fi
```

### 3.5 CI 通知集成

```yaml
# .github/workflows/coverage-notify.yml (示例)
name: Coverage Notify
on:
  workflow_run:
    workflows: ["CI Pipeline"]
    types: [completed]

jobs:
  notify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check coverage trend
        run: |
          LATEST=$(jq .totals.percent_covered artifacts/coverage/coverage.json)
          # 与上次提交的覆盖率比较
          if [ $(echo "$LATEST < $PREVIOUS - 3" | bc) -eq 1 ]; then
            echo "⚠️ Coverage dropped by >3%"
            # TODO: 发送飞书/webhook 通知
          fi
```

---

## 4. 各阶梯模块提升范例

### 4.1 L1 → L2 重点提升模块

#### `cross/flash.py` — FlashRunner failover 路径

```python
# 当前缺乏测试的路径（估算 ~45% → 目标 ~60%）
class FlashRunner:
    def flash(self, firmware_path: str, tool: str | None = None):
        preferred = tool or self.preferred_tool
        # ← 以下错误路径无测试覆盖
        try:
            runner = self._get_runner(preferred)
        except ToolNotFoundError:
            # ← 无人测试 fallback 路径
            for fallback in ["openocd", "jlink", "pyocd"]:
                try:
                    runner = self._get_runner(fallback)
                    break
                except ToolNotFoundError:
                    continue
            else:
                raise NoToolAvailableError(...)
        # ← happy path 有测试覆盖
        return runner.write(firmware_path)
```

**需要的测试：**
- `test_flash_runner_preferred_tool_not_found` → 验证 fallback 链
- `test_flash_runner_all_tools_unavailable` → 验证抛出 NoToolAvailableError
- `test_flash_runner_tool_override_invalid` → 验证无效 tool 参数的 fallback

#### `store.py` — SQLite CRUD + 事务

```python
# 当前 ~40% → 目标 ~65%
class Store:
    def get_project(self, project_id: str):
        # ← happy path 有测试
        row = self._execute("SELECT * FROM projects WHERE id=?", (project_id,))
        if row is None:
            # ← 无人测试 None 路径
            return None
        return Project(**row)
    
    def create_project(self, project: Project):
        try:
            self._execute("BEGIN")
            self._execute("INSERT INTO projects ...", ...)
            # ← 无人测试回滚路径
            self._execute("COMMIT")
        except Exception:
            self._execute("ROLLBACK")
            raise
```

**需要的测试：**
- `test_store_get_project_not_found` → 返回 None
- `test_store_create_project_rollback` → 验证失败时执行 ROLLBACK
- `test_store_concurrent_write` → 模拟锁竞争

### 4.2 L2 → L3 重点提升模块

#### `api/auth.py` — JWT + RBAC 覆盖

```python
# 当前 ~35% → 目标 ~60%
def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        # ← 无测试
        return None, "TOKEN_EXPIRED"
    except jwt.InvalidTokenError:
        # ← 无测试
        return None, "INVALID_TOKEN"
    return payload, None

def authorize(user: User, resource: str, action: str):
    # ← 以下路径无测试
    if user.role == "admin":
        return True
    if resource.startswith("org_"):
        return user.org_id == resource.split("_")[1]
    if resource == user.id:
        return True
    return False
```

**需要的测试：**
- `test_verify_token_expired` → 过期 token 返回 None + EXPIRED
- `test_verify_token_invalid_signature` → 无效签名返回 None + INVALID
- `test_authorize_admin_bypass` → admin 跳过资源校验
- `test_authorize_org_resource` → org 资源校验正确
- `test_authorize_deny` → 非匹配用户/资源返回 False

#### `spec/engine.py` — 规范解析边界 case

**需要的测试：**
- `test_parse_spec_malformed_shall` → 格式错误的 SHALL 语句
- `test_parse_spec_nested_scenarios` → 深层嵌套的 GIVEN/WHEN/THEN
- `test_parse_spec_empty_sections` → 空节的处理
- `test_parse_spec_duplicate_req_ids` → 重复需求 ID 的检测

### 4.3 L3 → L4 重点提升模块

#### `plugins/*.py` — 插件系统覆盖

**需要的测试：**
- `test_plugin_registration_duplicate` → 同名插件注册失败
- `test_plugin_execution_timeout` → 插件执行超时处理
- `test_plugin_hot_unload_mid_execution` → 运行中卸载
- `test_plugin_sandbox_escape_attempt` → 沙箱逃逸检测

#### `llm/*.py` — LLM 客户端降级

**需要的测试：**
- `test_llm_client_model_switch_fallback` → 主模型不可用时切换备用模型
- `test_llm_client_streaming_interrupted` → 流式响应中断重连
- `test_llm_client_token_limit_exceeded` → Token 超出限制的分片处理
- `test_llm_client_rate_limit_retry` → Rate limit 重试 + backoff

### 4.4 L4 → L5 重点提升模块

- **所有模块**的边界测试补齐
- **并发竞争**：多线程/多进程下的竞态条件测试
- **资源泄漏**：每个模块验证文件句柄/数据库连接的正确关闭
- **安全扫描**：注入、XSS、路径穿越等安全测试

---

## 5. 覆盖趋势跟踪

### 5.1 趋势记录格式

每次 Release 或里程碑达成，覆盖率数据 SHALL 记录到以下表格：

| 日期 | 版本 | 行覆盖率 | 分支覆盖率 | CI Gate | 阶梯 | 债务行数 |
|:----|:----|:--------:|:----------:|:------:|:----:|:--------:|
| 2026-06-01 | v0.9.0 | 49.7% | — | 49% | 过渡 | — |
| 2026-06-14 | v1.0.0 | 62.3% | — | **60%** | **L0** | 1200 |
| 2026-Q3-W2 | v1.0.x | **≥65%** | — | **65%** | **L1** | ≤1000 |
| 2026-Q3-W6 | v1.1.x | **≥70%** | ≥60% | **70%** | **L2** | ≤300 |
| 2026-Q4-W2 | v1.2.x | **≥75%** | ≥65% | **75%** | **L3** | ≤200 |
| 2027-Q1-W2 | v1.3.x | **≥80%** | ≥70% | **80%** | **L4** | ≤100 |
| 2027-Q2-W2 | v2.0.0 | **≥85%** | ≥75% | **85%** | **L5** | ≤50 |

### 5.2 趋势可视化

CI SHALL 在每次构建后更新 `artifacts/coverage/trend.json`：

```json
{
  "project": "yuleOSH",
  "latest_run": "2026-06-14T09:00:00Z",
  "current_gate": 60,
  "ladder_step": "L0",
  "trend": [
    {"date": "2026-06-01", "coverage": 49.7, "gate": 49},
    {"date": "2026-06-07", "coverage": 55.2, "gate": 55},
    {"date": "2026-06-10", "coverage": 58.1, "gate": 55},
    {"date": "2026-06-14", "coverage": 62.3, "gate": 60}
  ],
  "modules": {
    "store_pg.py": 100.0,
    "ci/run.py": 83.0,
    "store.py": 40.0,
    "cross/flash.py": 45.0,
    "cross/target_config.py": 55.0,
    "api/auth.py": 35.0,
    "spec/engine.py": 55.0,
    "plugins/*.py": 25.0,
    "llm/*.py": 30.0,
    "cli/*.py": 20.0
  }
}
```

---

## 6. 质量债务管理

### 6.1 覆盖率债务记录

所有被豁免的覆盖率缺口 SHALL 记录在 `docs/coverage-debt.md`：

```markdown
# 覆盖率质量债务

## 格式
- `{模块}::{方法}` — 缺多少行、原因、责任人、到期日

## 活跃债务
| ID | 模块 | 缺行数 | 原因 | 责任人 | 到期 |
|:---|:-----|:------:|:-----|:------|:----|
| DEBT-001 | cross/hil_runner.py | 85 | 无 HIL 硬件 | 硬件组 | 2026-Q4 |
| DEBT-002 | api/admin.py | 45 | 管理端暂未上线 | 后端组 | 2026-Q3 |
```

### 6.2 债务清理规则

| # | 规则 | 强制等级 |
|:--|:-----|:--------:|
| DEBT-R01 | 覆盖率债务 SHALL 在 `docs/coverage-debt.md` 中显式记录 | SHALL |
| DEBT-R02 | 每项债务 SHALL 有明确的到期日期 ≤90 天 | SHALL |
| DEBT-R03 | 债务到期后 CI SHALL 自动检查并提醒 | SHALL |
| DEBT-R04 | 同一模块债务超过 3 项时 SHOULD 触发模块级代码审查 | SHOULD |
| DEBT-R05 | 新模块提交时不应引入新的覆盖率债务 | SHOULD |

---

## 7. 角色与职责

| 角色 | 阶梯相关职责 |
|:-----|:--------------|
| **质量架构师** (小马 🐴) | 制定阶梯计划、批准升级/降级、审核覆盖率债务豁免 |
| **Sprint 负责人** | 在 Sprint Planning 分配测试覆盖率任务、跟踪进度 |
| **贡献者** | 为新增代码编写对应的测试，不降低覆盖率 |
| **CI 负责人** | 维护 CI pipeline 的阶梯门禁配置、自动通知 |
| **架构评审** (老陈) | 审核覆盖率债务的合理性，参与 L4/L5 升级决策 |

---

## 附录 A: 变更历史

| 版本 | 日期 | 变更 |
|:----|:----|:-----|
| v1.0.0 | 2026-06-14 | 初始版本：L0→L5 阶梯定义、CI集成、回退机制、模块范例 |

---

*本文档定义了 yuleOSH 项目覆盖率门禁的阶梯提升计划。各阶梯的 SHALL 要求为强制性，未达标将导致 CI 门禁阻塞合并。*

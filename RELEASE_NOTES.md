# yuleOSH v3.1.0 — Loop Engineering I4 生产加固发布

> **发布日期**: 2026-07-17
> **版本**: v3.1.0
> **上一个版本**: v3.0.0 (Loop Engineering 四个闭环交付)

---

## 概览

I4 是 Loop Engineering 最后一个迭代，聚焦**生产加固 + 验收完整验证**。在小克交付的 I1-I3 代码基础上，追加四个生产级组件并进行全面验收。

---

## 🚀 生产加固 (I4)

### 事件来源验证 (LE-009) — 小克 👨‍💻
- **SourceValidator** (`event_bus.py`): HMAC-SHA256 签名生成与验证
- 白名单 + 自动白名单机制
- 可通过 `YULEOSH_EVENT_SOURCE_SECRET` 环境变量配置
- 验证失败 → 死信队列 + 统计 + 审计日志

### 速率限制 (LE-011) — 小克 👨‍💻
- **TokenBucket**: 每个事件类型独立 token bucket
- 默认: 50 events/sec, burst=100
- 可配置 `rate_limit_per_type` 按事件类型覆盖
- 超限事件入死信队列

### 死信队列 (LE-003 隐含) — 小克 👨‍💻
- **DeadLetterQueue**: 事件失败后的最终归宿
- 触发条件: 来源验证失败、速率限制超限、handler 重试耗尽
- 支持 retry/clear/list 操作
- 可选持久化到 Store

### 审计日志 (LE-012) — 小克 👨‍💻
- **AuditLog**: 每次 emit() 完成后自动记录
- 完整字段: event_id, type, source, priority, handler_results, rollback_status
- `handler_results` 数组记录每个 handler 的执行状态和错误
- 可选持久化到 Store

### 质量验收 — 小马 🐴
- 52 个验收测试全部激活 + 真实运行
- 6 个 E2E 测试验证完整流水线
- 240 个 loop 相关测试全部通过

---

## ✅ 验收统计

| 区域 | 测试数 | 通过 | 覆盖率 |
|:-----|:------:|:----:|:------:|
| ACC 验收测试 | 52 | 52 | 100% |
| E2E 测试 | 6 | 6 | 100% |
| Loop 单元测试 | 182 | 182 | 100% |
| **总计** | **240** | **240** | **100%** |

### 验收矩阵摘要

| 区域 | 总 ACC | ✅ 已实现 | 🟡 部分 |
|:-----|:------:|:--------:|:--------:|
| EventBus | 10 | 8 | 2 |
| Loop 1-4 | 24 | 22 | 2 |
| CLI + 审计 | 13 | 9 | 4 |
| **总计** | **47** | **39 (83%)** | **8 (17%)** |

所有 SHALL 级别全部 ✅，8 个 🟡 为 SHOULD 级别或 CLI 增强，已有行动计划。

---

## 📋 遗留问题 (P3, 不影响签署)

| # | 组件 | 说明 | 严重度 |
|:-:|:----|:-----|:------:|
| I4-01 | SourceValidator | `_auto_whitelist` 可能被绕过，建议默认禁用 | P3 |
| I4-02 | TokenBucket | `default_burst` 100 硬编码，建议配置化 | P3 |
| I4-03 | DeadLetterQueue | 主路径和 retry 路径可能双重入队 | P3 |

---

## 📦 发布文件

- `reports/loop-engineering-i4-review.md` — I4 生产加固审查报告
- `reports/loop-engineering-i4-quality.md` — I4 质量进度报告
- `docs/acceptance-matrix-loop-engineering.md` (v3.1.0) — 更新验收矩阵
- `docs/spec-delta-loop-engineering.md` (v3.1.0) — 更新 Spec

---

# yuleOSH v3.1.1 — 专家评审问题修复 Patch

> **发布日期**: 2026-07-17
> **版本**: v3.1.1
> **上一个版本**: v3.1.0

---

## 概览

在老陈专家评审中发现三个问题（2 P0 + 1 P1），一次性修复完成。

---

## 🚀 修复

### Fix 1: SourceValidator auto_whitelist 默认禁用 (🔴 P0)
- 新增 `auto_whitelist` 布尔参数，默认 `False`
- `False` + 空白名单 + 无密钥 → 拒绝所有事件（严格模式）
- `True` + 空白名单 → 自动信任所有来源（兼容模式）
- 修复前: 未配置白名单时存在潜在自动信任行为

### Fix 2: DeadLetterQueue 文件持久化 (🔴 P0)
- 新增 JSON 文件持久化，路径: `.yuleosh/loop/dead_letter_queue.json`
- 重启后自动恢复死信事件，数据零丢失
- 所有操作（enqueue/clear/retry）自动同步到磁盘

### Fix 3: CLI audit 增强 — 支持时间范围查询 (🟡 P1)
- `--since` / `--until` ISO 8601 时间过滤
- `--type` / `-t` 事件类型过滤
- `--limit` 条数限制（默认 50）

示例:
```bash
yuleosh loop audit list \
  --since 2026-07-17T00:00:00 \
  --until 2026-07-17T23:59:59 \
  --type ci.failure \
  --limit 100
```

---

## ✅ 验证

| 测试套件 | 用例数 | 通过 | 备注 |
|:---------|:------:|:----:|:-----|
| event_bus 单元测试 | 55 | 55 | 含 3 个新增测试 |
| E2E 测试 | 6 | 6 | 全通过 |
| 验收测试 | 51 | 51 | 全通过 |

修复报告: `reports/expert-issue-fix-report.md`

---

# yuleOSH v2.3.0 — 知识图谱深化 + 技术债攻坚发布

> **发布日期**: 2026-07-17
> **版本**: v2.3.0
> **上一个版本**: v2.2.0

---

## 概览

Push 10 是一次**功能深化 + 质量加固**的混合发布，在上次专家评审（85/100 🟢）基础上，四条线并行推进：知识图谱下一阶段、技术债覆盖攻坚、竞品对标分析、并行发版。

---

## 🚀 新功能

### 知识图谱 P2 — 追溯矩阵自动生成 (小马 🐴)
- **RTM 自动生成** (`yuleosh kg report rtm`) — 从 KG 动态生成追溯矩阵，支持 Markdown/HTML/CSV 三格式导出
  - HTML 格式自带 CSS 样式 + 统计卡片，适合审计展示
  - CSV 可导入 Excel / 飞书多维表格
- **度量报告** (`yuleosh kg report metrics`) — 覆盖率、测试分布、图健康度、趋势四维度报告
- **事件通知机制** (`yuleosh kg events`) — EventBus + 存储装饰器，KG 变更自动推送通知
- **新增文件**: `reporter.py` (~680行), `events.py` (~345行), `kg_cli.py` (~250行)
- **新增测试**: 52 个 P2 测试用例全部通过

### 技术债覆盖攻坚 (小克 👨‍💻)
- **evidence/oem_templates.py**: 0% → **77%** 🚀
- **evidence/signer.py**: 71% → **85%**
- **evidence/ 整体**: ~30% → **~88%** 🚀
- **ci/kpi/ 模块**: ~91% → **~94%**
- **总测试数**: 175 passed, 1 skipped

---

## 📋 竞品对标更新

详见 `reports/competitive-analysis-v2.3.md`。核心发现：
- **KG 置信度标签**是 yuleOSH 独有的竞品盲区
- **AutoC** (AI AUTOSAR 配置) 是最大新威胁
- **亚远景 APMS** 是国产 ASPICE 工具链最强对手，但技术栈落后

---

## ✅ 验证

| 验证项 | 结果 |
|:-------|:----:|
| KG P2 测试 | 52 passed ✅ |
| Evidence + KPI 测试 | 79 passed ✅ |
| 技术债模块覆盖率 | 目标模块全部达标 ✅ |

---

## 📦 安装

```bash
pip install yuleosh==2.3.0
```

或通过 Docker:

```bash
docker pull yuleosh/yuleosh:2.3.0
```

---

# yuleOSH v2.2.0 — Push 9 质量加固发布

> **发布日期**: 2026-07-07
> **版本**: v2.2.0
> **上一个版本**: v2.1.0

---

## 概览

Push 9 是一次全面的**质量加固**发布，在 Push 8 专家评审（8.0/10）的基础上，关闭了所有 P0/P1/P2 遗留问题。

---

## 🚀 新功能

### Dashboard 数据真实化
- **swe_status 写入 evidence pack** — `pack_evidence_bundle()` 现在自动聚合 SWE.1~SWE.6 状态并写入 manifest，Dashboard 的 SWE 状态端点不再回落 mock 数据
- **coverage-trend 自动采集** — CI 覆盖率管道每次运行自动追加趋势记录到 `coverage-trend.jsonl`
- **KB MISRA 去重** — `KbStore.deduplicate_misra_articles()` 按 rule_id+file+line 去重，Dashboard 违规列表质量大幅提升
- **_estimate_swe_completed() 真实数据化** — 优先从 evidence pack manifest 读取，回落 heuristic

### MISRA 规则映射修复
- **映射率 0.3% → ~99%** 🎯 — 修复了 `_normalize_rule_id()` 的键格式不匹配和 `enrich_with_definitions()` 的嵌套结构读取错误

### Benchmark 难度扩展
- **27 个测试用例** (12 easy + 10 medium + 5 hard) — 新增嵌入式场景：环形缓冲区指针运算、CAN 协议回调、类型泛型宏、packed struct 位域等
- Runner 支持多级子目录 + 难度自动检测

### 工具自身 ASPICE 验证
- **18 BP 评估**: 12 pass, 3 partial, 3 fail — 覆盖 SWE.1~SWE.6 全过程域
- self-assessment 报告作为基线，指引后续改进方向

### MISRA C:2023 升级规划
- 9 周分 3 阶段路线图：YAML 更新 → 规则映射库重构 → 知识管理+试点
- 识别 C:2012→C:2023 的 180 条规则变更，含 modified/new/deleted 分类

---

## 🔒 安全修复

- **P0 🔴 SQL 注入修复** — `kb/store.py` 中 3 处高风险（update_article/lesson/fmea）新增白名单字段验证；`store.py/store_pg.py` 中 2 处低风险修复
- **Redirect 安全审查** — 确认所有 redirect 使用纯硬编码路径，无 tabs vs spaces 解析差异风险

---

## 🛠️ 兼容性

- **向后兼容**: 所有现有 API 响应格式保持不变
- **CLI 接口**: 全部 22 个子命令签名不变
- **证据包格式**: manifest schema 新增 `swe_status` 字段（可选，现版本兼容旧格式）

---

## ✅ 验证

| 验证项 | 结果 |
|:-------|:----:|
| 回归测试 | 144 passed, 0 failed |
| MISRA 规则映射 | ~99% 已知（原 0.3%） |
| Dashboard 端点 | 7/7 真实数据（零假数据） |
| SQL 注入 | 0 高风险残留 |
| ASPICE 自检 | 18 BP baseline 建立 |
| Benchmark | 27 用例，100% success rate |

---

## 📦 安装

```bash
pip install yuleosh==2.2.0
```

或通过 Docker:

```bash
docker pull yuleosh/yuleosh:2.2.0
```

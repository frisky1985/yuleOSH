# 🧑‍🏫 Expert Invite: CL2 审查 — 老陈

**邀请人**: 小马 🐴（质量架构师）
**邀请日期**: 2026-06-19
**审查人**: 老陈 👨‍🏫（前博世资深架构师 / ASPICE 审计师）
**审查对象**: yuleOSH Pipeline v2.0.1 → v2.0.2

---

## 一、审查背景

### 1.1 Sprint A 回顾

上一轮 Sprint A 审查（2026-06-18）评分 **90/100 ✅**，Pipeline 已通过 CL1 级质量门禁。老陈五轮审查轨迹：58→70→76→85→**90**，跨越 32 分。

### 1.2 昨晚（6月18日 23:00+）新增内容

在 Sprint A 评分 90/100 后，团队（小克）连夜完成了以下 CL2 模块的通宵交付：

#### 🔴 CL2 E01~E13 模块

| 审计项 | 内容 | 实现规模 | 状态 |
|:-------|:-----|:--------:|:----:|
| **E01** | gcov 编译链集成 | gcov_coverage.py 330 行 | ✅ |
| **E02** | lcov + genhtml 报告流水线 | gcov_coverage.py（含 lcov） | ✅ |
| **E03** | 覆盖阈值门禁（fail_under） | stages.py 覆盖率门禁逻辑 | ✅ |
| **E04** | 覆盖趋势追踪与基线 | coverage_trend.py 254 行 + CLI | ✅ |
| **E05** | 文档 YAML Schema 验证 | yaml_validator.py 271 行 | ✅ |
| **E06** | 文档状态门禁（MR 阻塞） | sync_check.py 322 行 + .sync-gate.yaml | ✅ |
| **E07** | 文档差异自动检测 | sync_check.py CLI 就绪 | ✅ 代码就绪，待 CI 集成 |
| **E08** | 过程性能基线 — 首次采集 | kpi.py 574 行 + CLI | ✅ |
| **E09** | 数据回填（60+ 数据点） | backfill_ci_history.py | ✅ |
| **E10** | 偏差管理 CLI + 审批链 | 已有覆盖 | ✅ |
| **E11** | ALM 适配器（Jira/Polarion） | jira.py + polarion.py + base.py | ✅ |
| **E12** | 验证计划文档更新 | misra-verification-plan.md | ✅ |
| **E13** | 审计证据包自动生成 | evidence CLI 初步就位 | ✅ |

#### 🔴 P2 Handler 三个全部完成

| Handler | 此前状态 | 当前状态 | 行数 |
|:--------|:--------:|:--------:|:----:|
| `review_bsp.py` | ✅ 已生产级（继承） | ✅ 已注册 | 1,041 行 |
| `review_build.py` | ❌ 3 行 stub | ✅ **850 行** 全量实现 | 850 行 |
| `review_power.py` | ❌ 3 行 stub | ✅ **735 行** 低功耗审查全量 | 735 行 |

**Pipeline 步数**: 23 步 → **26 步**（全部注册 ✅）

#### 🔴 KPI 基线采集引擎
- `src/yuleosh/ci/kpi.py` — 574 行，含 `record_kpi()` / `show_kpi_trend()`
- `yuleosh kpi status` / `kpi trend` / `kpi baseline save|list|diff` CLI
- E09 数据回填：60 个历史数据点（从 git 历史提取）

---

## 二、审查范围清单

### 范围 A：CL2 E01~E13 完整性审查（核心）

审查 CL2 审计计划中 E01~E13 的实现质量和审计就绪度：

| # | 项目 | 审查深度 | 预期方法 |
|:-:|:-----|:--------:|:---------|
| A-01 | **E01+E02** gcov/lcov 集成是否健壮 | ⭐⭐⭐ | 审查 gcov_coverage.py 源码 + CMake 集成 + CI artifact 输出 |
| A-02 | **E03** fail_under 门禁逻辑是否正确 | ⭐⭐⭐ | 注入低覆盖率 → pipeline 阻断实测；40%~60% warning 非阻断 |
| A-03 | **E04** 覆盖趋势 JSONL 格式和字段完整性 | ⭐⭐ | 检查 coverage-trend.jsonl schema + CLI 输出格式 |
| A-04 | **E05+E06** 文档同步门禁实现可靠性 | ⭐⭐⭐ | sync_check.py 源码审查 + 代码变更→文档阻断实测 |
| A-05 | **E08+E09** KPI 基线采集引擎合规性 | ⭐⭐⭐ | kpi.py 574 行源码审查 + 数据回填质量验证 |
| A-06 | **E11** ALM 适配器设计合理性 | ⭐⭐ | Jira/Polarion 适配器接口设计 + 注册表/工厂模式 |
| A-07 | **E13** 证据包结构完整性 | ⭐⭐ | 输出目录结构 + SHA256 + 时间戳 + Git commit 关联 |

### 范围 B：CL2 证据就绪度评估

对应 MISRA 验收矩阵 §17~§22（G-47~G-50）：

| # | 项目 | 审查深度 | 预期方法 |
|:-:|:-----|:--------:|:---------|
| B-01 | **PA 2.1 TM** 追溯管理就绪度 | ⭐⭐⭐ | 追溯矩阵自动生成 + 偏差审批链 + SWE.6 追溯 |
| B-02 | **PA 2.2 MP** 过程测量就绪度 | ⭐⭐⭐ | MISRA 趋势(≥90天) + C 覆盖率趋势 + 构建元数据 + KPI |
| B-03 | **PA 2.2 RI** 资源与基础设施 | ⭐⭐ | 工具资格文档 + Agent 审查持久化 + 工具版本锁定 |
| B-04 | CL2 证据包 CLI 可用性 | ⭐⭐ | `yuleosh evidence pack/check` 命令实测 |

### 范围 C：P2 Handler 最终质量确认

| # | 项目 | 审查深度 | 预期方法 |
|:-:|:-----|:--------:|:---------|
| C-01 | `review_build.py`（850 行）实现质量 | ⭐⭐⭐ | 源码审查：.map 解析、区段 diff、增长告警 |
| C-02 | `review_power.py`（735 行）实现质量 | ⭐⭐⭐ | 源码审查：看门狗/休眠/唤醒/时钟门控/风险等级 |
| C-03 | 26 步 Pipeline 左右对称性 | ⭐⭐ | V-Model 左半侧 ↔ 右半侧 step 对应关系 |
| C-04 | 3 个 P2 handler 注册配置正确性 | ⭐ | PIPELINE_STEPS 注册 + 各 Layer 分配 |

### 范围 D：残留缺口复查

| # | 项目 | 审查深度 | 预期方法 |
|:-:|:-----|:--------:|:---------|
| D-01 | `alloca`/VLA 运行时检测缺口评估 | ⭐⭐ | 影响范围评估 + Sprint B 优先级建议 |
| D-02 | `test_c_unit.py` `$$` bug 影响评估 | ⭐ | bug 严重度确认 + 预期修复方案 |
| D-03 | SWE.6 合格性测试（G-31）计划评估 | ⭐⭐ | 3 段式设计评审 + Sprint A 剩余的可行性 |

---

## 三、重点审查项

老陈可优先关注以下区域（按风险排序）：

### ⚡ 高风险（必须审查）

1. **KPI 基线引擎（kpi.py 574 行）**
   - 风险：数据采集链路可能遗漏关键指标；回填数据真实性需验证
   - 关注：`record_kpi()` 是否覆盖全部 8 个指标字段；CI 自动采集触发机制

2. **E01+E03 gcov 门禁实战可靠性**
   - 风险：gcov 门禁是 CL2 核心证据，若配置错误导致误阻断/漏阻断，审计师会判定不可靠
   - 关注：fail_under_line 默认值；general vs embedded profile 切换逻辑

3. **ALM 适配器接口设计（E11）**
   - 风险：Jira/Polarion stub 能否真正对接实际 ALM 系统；DeviationTicket ALM 字段已补（需确认完整性）
   - 关注：`AlmBaseAdapter` 5 个方法签名 + 错误处理 + 认证模型

### 🟡 中风险（建议审查）

4. **review_power.py（735 行）完整实现**
   - review_bsp（1041 行）上轮已通过，review_build 和 review_power 是新增，需确认质量不低于 BSP

5. **Pipeline 26 步 V-Model 左右对称性**
   - 上轮 23 步时对称度扣分（76→74），26 步后需重新评估对称性

6. **CL2 证据就绪度百分比评估**
   - 按 MISRA 验收矩阵 §20.x 的 41 项 CL2 验收项逐项核验实际状态

### 🟢 低风险（快速确认即可）

7. `sync_check.py` CI 集成进度
8. `backfill_ci_history.py` 数据可信度
9. `yuleosh kpi baseline` CLI 命令链完整度

---

## 四、预期产出

| # | 产出物 | 格式 | 预期篇幅 | 截止 |
|:-:|:-------|:----:|:--------:|:----:|
| 1 | CL2 审查报告（E01~E13 逐项审查结论） | Markdown | 15~30 页 | 审查后 2 工作日 |
| 2 | CL2 证据就绪度评级（PA 2.1/2.2 分项） | Markdown + 表格 | 3~5 页 | 审查后 2 工作日 |
| 3 | 残留缺口评估 + Sprint B 建议 | Markdown | 2~3 页 | 审查后 1 工作日 |
| 4 | **CL2 过审评分**（新维度的综合评分） | 分数/评级 | — | 审查后 2 工作日 |

### 预期评分模型

| CL2 就绪维度 | 权重 | 预期目标 |
|:-------------|:----:|:--------:|
| CL2 E01~E13 实现完整性 | 40% | ≥35/40 |
| PA 2.1 追溯管理 | 25% | ≥20/25 |
| PA 2.2 过程测量 | 25% | ≥18/25 |
| CL2 证据可审计性 | 10% | ≥8/10 |
| **CL2 综合就绪度** | **100%** | **≥81/100**（Sprint A 结束目标） |

---

## 五、审查前准备

老陈可提前查阅以下材料（均已更新至凌晨状态）：

| 材料 | 路径 | 用途 |
|:-----|:-----|:-----|
| CL2 审计计划 | `reports/cl2-audit-plan.md` | E01~E13 逐项定义 |
| MISRA 验收矩阵（最终版） | `specs/misra-acceptance-matrix.md` | §17~§22 CL2 验收项 |
| 缺陷清单（v2.1） | `reports/v2.1-defect-list.md` | 当前残留缺口一览 |
| Pipeline 优化计划 | `docs/pipeline-optimization-plan.md` | 附录 C~F，CL2 完整路线图 |
| Sprint A 终审报告 | `reports/expert-pipeline-final.md` | 上一轮得分 89→修正 90 |
| KPI 基线代码 | `src/yuleosh/ci/kpi.py` | 574 行核心实现 |
| gcov 覆盖率 | `src/yuleosh/ci/gcov_coverage.py` | 330 行 |
| ALM 适配器 | `src/yuleosh/alm/`（base/jira/polarion） | 工厂模式设计 |

---

## 六、审查日程建议

| 阶段 | 时长 | 内容 |
|:-----|:----:|:-----|
| 材料预审 | 1 天 | 老陈独立审阅上述材料 |
| 在线审查会 | 1.5~2 小时 | 焦点讨论：KPI 引擎、gcov 门禁、ALM 适配器 |
| 代码抽样审查 | 0.5 天 | 关键模块源码深度审查 |
| 报告撰写 | 1~2 天 | 产出上述 4 项产出物 |

---

*审查邀请由小马 🐴 基于 yuleOSH v2.0.2 编制。如有疑问请联系小马。*

# SPRINT PLAN — A-M1 & B-M1（2026-Q4 启动）

> 状态: Draft v1.0 · 2026-08-26
> 上游: `docs/ROADMAP-multistandard-legacy.md`（§A4 A-M1 / §B4 B-M1）
> 执行追踪: `TASK_STATUS.md` T-010 / T-011
> 人力假设: A 线 2 后端 · B 线 2 后端 + 1 prompt 工程师（S3 参与）
> 节奏: 2 周/sprint · 建议启动 2026-10-12（国庆后首个周一）——待人力与排期确认

---

## 0. 拆解原则

1. **任务粒度 ≤5 人天**，单人可闭环，产出物可评审
2. **风险前置**：A 线先立 golden 基线（重构安全网），B 线第一天验证 tree-sitter wheel 可用性（第一阻塞点）
3. **每任务带可测验收标准**——不达标不进入下一任务（沿用 Loop3 纪律）
4. **容量按 ~55% 负载排任务**——余量留给评审、集成、13455 全量回归（跑一轮本身是显著开销）

---

## 1. A-M1：Evidence Model 泛化（T-010）

总容量 2 后端 × 2 sprint = 40 人天，任务合计 **21.5 人天**。

### A1-S1（10-12 ~ 10-23）：Golden 基线 + Profile Schema

| ID | 任务 | 产出物 | 验收标准 | 人天 | 负责 |
|----|------|--------|----------|------|------|
| A1-01 | Golden 基线采集与稳定化 | `tests/golden/compliance_aspice_v3_1/` + 采集脚本 | 当前 `ComplianceChecker` 输出固化为 golden；时间戳/绝对路径 normalize；重复采集两次逐字节一致 | 2.5 | dev1 |
| A1-02 | StandardProfile schema 设计 | `src/yuleosh/compliance/profile.py`（dataclass 骨架） | 字段覆盖 `aspice_v3.1.yaml` 全部信息，无损映射表附 docstring | 2 | dev2 |
| A1-03 | Profile loader + 校验 + 单测 | `profile.py::load_profile()` + `tests/test_compliance_profile.py` | 缺字段/未知字段/profile 不存在三种报错均含字段路径与修复提示；单测 ≥12 | 3.5 | dev2 |
| A1-04 | Schema 评审会（S1 末） | 评审纪要 | 以"A-M2 ISO 26262 作者视角"走查——仅凭 schema 能否写出新 profile | 1 | 全员 |

**Sprint 验收：** schema 定稿 + golden 基线入库（CI 对比测试绿）。

### A1-S2（10-26 ~ 11-06）：Checker 改造 + 迁移 + 回归

| ID | 任务 | 产出物 | 验收标准 | 人天 | 负责 |
|----|------|--------|----------|------|------|
| A1-05 | ComplianceChecker profile 驱动改造 | `compliance_checker.py` 重构 | 构造函数注入 `StandardProfile`；不传时默认 `load_profile("aspice_v3.1")`；现有调用零改动可跑 | 4 | dev1 |
| A1-06 | aspice yaml 迁移 | `src/yuleosh/compliance/profiles/aspice_v3.1.yaml` | 数据无损迁移（逐字段 diff 为空）；旧路径删除（一次性切换，git 历史 + golden 双保底） | 1.5 | dev2 |
| A1-07 | CLI `--profile` 接入 | `src/yuleosh/cli/commands/`（compliance 命令） | `yuleosh compliance check --profile <name>`；未知 profile 报错并列出可用清单 | 1.5 | dev2 |
| A1-08 | evidence 消费方适配 | `evidence/aspice_check.py`、`evidence/oem_templates.py` 注册表骨架 | gap check 改读 profile；模板注册表接口立起（A-M2 填 ISO 26262 模板） | 2 | dev1 |
| A1-09 | profile-schema.md 编写规范 | `docs/standards/profile-schema.md` | 外部工程师仅凭此文档可编写新 profile（A-M2 的直接输入） | 1.5 | dev2 |
| A1-10 | **里程碑验收** | 验收记录 | ① golden 逐字节一致；② 13455+ 全量测试零回归；③ UART demo 端到端跑通 | 2 | 全员 |

**A-M1 里程碑验收（11-06）：** 与 ROADMAP §A4 一致——`--profile aspice_v3.1` 输出与重构前逐字节一致。

---

## 2. B-M1：C AST 扫描器（T-011）

总容量 2 后端 × 3 sprint + prompt 工程师 2 人天 = 62 人天，任务合计 **36 人天**（含 B1-11 的 2 人天）。

### B1-S1（10-12 ~ 10-23）：tree-sitter 集成 + 函数提取

| ID | 任务 | 产出物 | 验收标准 | 人天 | 负责 |
|----|------|--------|----------|------|------|
| B1-01 | py-tree-sitter 依赖引入 | `pyproject.toml`、`Dockerfile`、`Dockerfile.cross` | 版本锁定；linux x86_64 + mac arm64 wheel 验证；Docker 构建通过 | 1.5 | dev1 |
| B1-02 | 容错解析封装 | `src/yuleosh/knowledge_graph/c_parser.py` | `parse()` 永不抛异常；返回 tree + ERROR/MISSING node 统计；错误率可量化 | 3 | dev1 |
| B1-03 | 函数级提取 | `c_parser.py` 扩展 | 函数名/参数/返回类型/存储类/行区间/前导注释；含 K&R 老式声明 | 3 | dev2 |
| B1-04 | 冒烟基准 + 三固件选型 | `tests/test_c_parser_smoke.py`、选型记录 | benchmark/ 39 个 .c 全解析零崩溃；三固件 license 审查通过（Apache-2.0/MIT/BSD-3 优先）并落 `benchmark/legacy-cases/` | 3 | dev2 |

**Sprint 验收：** 冒烟测试 CI 化；三固件就位（候选：Zephyr sample / FreeRTOS demo / STM32 HAL 工程）。

### B1-S2（10-26 ~ 11-06）：调用图 + 状态 + 宏

| ID | 任务 | 产出物 | 验收标准 | 人天 | 负责 |
|----|------|--------|----------|------|------|
| B1-05 | 调用图提取 | `c_parser.py` 扩展 | call_expression → 边；函数指针取址/赋值记为 `potential-call` 独立边型（不静默丢弃） | 3 | dev1 |
| B1-06 | 全局状态 + ISR 提取 | `c_parser.py` 扩展 | 全局/静态变量 + volatile 标记 + 初始化值；ISR 识别（命名启发式 + 中断向量表模式） | 4.5 | dev2 |
| B1-07 | 宏处理策略 | `c_parser.py` + 宏白名单表 | stddef/stdint 常见宏白名单；函数式宏记 macro entity（低置信度）；`#ifdef` 分支全解析并标注 | 3.5 | dev1 |
| B1-08 | 中期质量门禁（S2 末） | 抽检报告 | 三固件各抽 30 函数人工核对，提取准确率 ≥90%；未达则 S3 首周补强，不带病进 S3 | 1 | 全员 |

**Sprint 验收：** 中期准确率 ≥90%；调用图/ISR 在至少一个固件上人工可视校验。

### B1-S3（11-09 ~ 11-20）：KG 入库 + CLI + 基准验收

| ID | 任务 | 产出物 | 验收标准 | 人天 | 负责 |
|----|------|--------|----------|------|------|
| B1-09 | c_code_scanner 对标接口 | `src/yuleosh/knowledge_graph/c_code_scanner.py` | 接口与 `code_scanner.py` 对齐（访问者模式 / ScanResult 结构）；Python/C 双扫描器并存 | 4 | dev1 |
| B1-10 | KG 入库 + 置信度初始规则 | `knowledge_graph` models 扩展 | 新 entity：CFunction/CGlobalVar/CMacro/ISR；置信度初值 clean 0.9 / 含 ERROR 0.5 / 宏重度 0.35（对齐 B3 三级流转阈值，S3 评审定稿） | 3.5 | dev2 |
| B1-11 | `yuleosh reverse scan` CLI | `src/yuleosh/cli/commands/reverse.py` | 输出扫描统计 + entity 计数 + 置信度分布报告 | 2 | prompt-eng |
| B1-12 | **里程碑验收** | `benchmark/legacy-cases/` + 验收报告 | 三固件零崩溃；函数/调用图人工抽检（各 30+）准确率 ≥95%；10 万行 <5 分钟；13455+ 全量零回归 | 4 | 全员 |

**B-M1 里程碑验收（11-20）：** 与 ROADMAP §B4 一致。

---

## 3. 依赖与关键路径

```
A线: A1-01 ─────────────────┐
    A1-02 → A1-03 → A1-04    ├→ A1-05 ──┐
                              │  A1-06/07 ┼→ A1-10 验收 ✓ (11-06)
    A1-09（schema 定稿即可写）─┘  A1-08 ───┘

B线: B1-01 → B1-02 ─┐
    B1-03 ←──────────┼→ B1-05/B1-06/B1-07 → B1-08 中期门禁
    B1-04 ───────────┘                        ↓
    B1-09 → B1-10 → B1-11 → B1-12 验收 ✓ (11-20)
```

- **A 线关键路径：** A1-02 → A1-03 → A1-04 → A1-05 → A1-10（schema 是全局阻塞点，评审会不可推迟）
- **B 线关键路径：** B1-01 → B1-02 → B1-05/07 → B1-09 → B1-10 → B1-12
- **跨线零代码依赖**（ROADMAP §3 结论维持）；唯一共享资源是"全员评审"时间窗

---

## 4. Sprint 纪律（对接 Loop3）

- **每 sprint 末全量回归**：13455+ 测试 + golden/冒烟门禁；跑完检查 improvement_tickets 零新增（T-009 已根治夹具泄漏，若再现即为真实缺陷）
- **新增 KPI 趋势项**：`c_ast_function_accuracy`（S2 起记录）、`c_ast_scan_duration`——写入 `kpi_trends/`，进 Loop3 监控
- **不达标不推进**：B1-08 中期门禁 <90% 时，S3 首周用于补强而非新功能

---

## 5. 风险前置清单

| 风险 | 触发点 | 前置动作 | 降级方案 |
|------|--------|----------|----------|
| tree-sitter wheel 不可用（linux 构建） | B1-01（S1 第 1 天验证） | Dockerfile.cross 构建验证 | vendor 语法源码自编译；最后手段降级 clang binding |
| golden 含非确定性字段 | A1-01（S1 第 1 天验证） | normalize 规则 | 字段白名单（只对比业务字段） |
| 函数指针导致调用图不完整 | B1-05（必然发生） | `potential-call` 边型显式建模 | 接受不完整，交 B-M2 的 LLM 推断补齐（有 KG 锚定） |
| 三固件 license 不合规 | B1-04 | 仅选 Apache-2.0/MIT/BSD-3 | GPL 项目只 fetch 不 vendor |
| 人力不到位（<4 后端） | 启动前 | A1/B1 各砍一人 → 串行执行 | B-M1 优先保（P0），A-M1 顺延一个月 |

---

## 6. 决策点（已锁定 2026-08-26）

| # | 决策点 | 结论 |
|---|--------|------|
| D1 | 启动日期 | **2026-10-12 确认**（国庆后首个周一） |
| D2 | aspice yaml 切换策略 | **一次性切换**（内部工具，git + golden 双保底） |
| D3 | 三固件选型 | **候选池锁定**（Zephyr sample / FreeRTOS demo / STM32 HAL），B1-04 出终选报告 |
| D4 | B1-10 置信度初值 | **0.9 / 0.5 / 0.35 起步**，S3 评审定稿 |

---

## 7. 挂账项（2026-08-26 盘点 — 不在本计划范围，挂账在案）

| 项 | 状态 | 处置 |
|----|------|------|
| project_venv 3 个全量资源竞争测试 | T-005 遗留：fd/进程竞争，单独/小组跑均过（测试基建，非代码缺陷） | 挂 A1-S2 全量回归窗口排查 |
| ClangTidyDriver 为 Stub | `ci/tool_drivers.py:318`，clang-tidy 输出解析未实现 | 与 B 线 C 工具链同域，随 B-M2 规划一并处理；期间静态分析继续用 cppcheck + 规则集 |

---

*本文档为 ROADMAP-multistandard-legacy.md（本地保留，商业敏感不入库）§A4/§B4 首两个里程碑的执行级拆解；A-M2/B-M2 及以后的拆解在 A-M1/B-M1 验收后进行（避免远期计划过早细化）。*

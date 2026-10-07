# `yuleosh.plan` 模块设计文档

> 子系统定位：自然语言任务描述 → 结构化实施计划生成（Ultra-Plan Agent）
> 代码根：`src/yuleosh/plan/`
> 文档性质：详细设计（SWE.3），基于源码实地盘点，非推测。

---

## 1. 职责边界

`plan` 模块是 **Ultra-Plan Agent** 的完整实现（`__init__.py:5-22`、`agent.py:5-22`）：从自然语言任务描述生成结构化实施计划，包含步骤拆解、Agent 分配、工时估算、验证标准、风险与前置条件，并支持渲染为 Markdown / JSON / CheckpointEngine 兼容步骤。

**与 `pipeline` 的边界**：`plan` 负责“生成与编排”，`pipeline` / `engine` 负责“执行”。`plan` 单向读取 `yuleosh.pipeline.step_handlers.PIPELINE_STEPS` 获取可用流水线步骤清单（`context.py:238`），在 `--apply` 时通过 `yuleosh.engine.checkpoint.CheckpointEngine` 把计划注入执行（`cli.py:186-201`），**不直接 import `yuleosh.pipeline` 引擎**。

---

## 2. 目录结构与规模

| 文件 | 行数 | 职责 |
|---|---|---|
| `__init__.py` | 48 | 包导出入口（公开 API 汇总） |
| `models.py` | 197 | 数据模型 `Plan` / `PlanStep` / `PlanStatus` / `AGENT_MAP` |
| `context.py` | 258 | 项目 / KG / 流水线上下文收集器 `PlanContext` |
| `generator.py` | 416 | 计划生成器 `PlanGenerator`（核心启发式算法） |
| `agent.py` | 189 | 主入口类 `PlanAgent` |
| `output.py` | 229 | 渲染器（Markdown / JSON / 流水线步骤） |
| `cli.py` | 233 | CLI 子命令实现 |

---

## 3. 关键组件与算法

### 3.1 上下文收集 `PlanContext`（`context.py:25`）
- `__init__(self, project_dir: str = ".")`（`context.py:32`）
- `get_project_summary()`、`get_kg_summary()`、`get_aspice_coverage()`、`get_existing_requirements()`、`get_pipeline_capabilities()`（`:38-227`）
- 懒加载 KG，避免无谓查询（`_lazy_kg` `:94`）

### 3.2 生成器 `PlanGenerator`（`generator.py:284`）
主流程 `generate(task, context) -> Plan`（`generator.py:287`）。核心启发式算法：

| 算法 | 实现位置 | 说明 |
|---|---|---|
| 关键词规则匹配 | `_RULES` 正则表 `:38-135`；`_match_rules` `:138` | 驱动步骤生成（test→补 test、ASIL→加合规安全门、KG→KG 校验、dashboard→前端、HIL→硬件前置） |
| 默认步骤补全 | `_add_default_steps` `:212` | 保证含 code-implementation / code-review / final-summary |
| 依赖图构建 | `_build_dependency_graph` `:186` | framework/planning 类步骤被后续步骤依赖 |
| 拓扑排序 / 重编号 | `_renumber_steps` `:257` | 按依赖数迭代拓扑排序并编号 `P1..Pn` |
| Agent 分配 | `_assign_agent` `:206`；映射 `models.py:39-47` | agent_key → 显示名 |
| 工时估算 | `_RULES` 硬编码 `effort_hours`；`Plan.total_effort_hours` 汇总 `:136`、`agent_breakdown` `:141` | |
| 前置/风险探测 | `_detect_prerequisites` `:147`；`_detect_risks` `:167` | |

### 3.3 入口 `PlanAgent`（`agent.py:44`）
- `plan(task) -> Plan`（`:66`）、`to_markdown` / `to_json` / `to_pipeline` / `save` / `save_markdown` / `approve` / `start_execution` / `complete`（`:105-161`）
- 包级便捷函数 `generate_plan(task, project_dir, save_to)`（`agent.py:170`；`__init__.py:24-28`）

> 注意：全部为**同步**函数，模块内无 `async def`。

---

## 4. 数据模型（`models.py`，均为 dataclass）

**`PlanStep`**（`models.py:53`）：
`step_id: str`、`name: str`、`description: str`、`agent: str`、`effort_hours: float`、`depends_on: list[str] = []`、`verification: str = ""`、`pipeline_step: Optional[str] = None`

**`Plan`**（`models.py:106`）：
`title / objective / background / technical_approach: str`、`steps: list[PlanStep] = []`、`risks / prerequisites: list[str] = []`、`generated_at: str`（UTC ISO8601）、`status: str = PlanStatus.DRAFT`
附加属性：`total_effort_hours` `:136`、`agent_breakdown` `:141`、`agent_count` `:149`

**`PlanStatus`**（`models.py:25`，常量类）：`DRAFT / REVIEW / APPROVED / EXECUTING / DONE / CANCELLED` + `VALID_STATUSES`

**`AGENT_MAP`**（`models.py:39-47`，dict）：agent_key → 显示名（code / review / orchestration / spec / test / architecture / compliance）

---

## 5. 对外接口

**CLI 子命令 `plan`**（`cli.py:58` `build_plan_subparser`，由 `cli/main.py:323-324` 注册）：
- 位置参数 `description`（自然语言任务）
- `--apply` / `-a`：经 `CheckpointEngine` 执行最近计划
- `--list` / `-l`、`--show [id]`、`--json`、`--project-dir`

**HTTP 端点**：**无**。`plan` 模块未暴露任何 REST 端点（`api/` 中无任何文件 `import yuleosh.plan`）。

**持久化**：`PlanAgent.save` / `save_markdown` 写 `.json` / `.md` 到磁盘；CLI 存于 `.yuleosh/plans/plan-<id>.json`（`cli.py:23,47-55`）。

---

## 6. 配置

- 仅读取环境变量 **`OSH_HOME`**：`cli.py:91`（`--project-dir` 默认值）、`context.py:257`（回退）。
- **无**配置文件（未发现 `settings` / `config` / `.toml` / `.yaml` 解析）。
- `plan` 自身不读取 LLM 密钥；密钥相关仅在注释/前置条件探测中作为字符串出现（`generator.py:162`）。

---

## 7. 集成点

- `plan` import 同仓：`yuleosh.knowledge_graph`（`context.py` 多处：`get_store` / `get_graph_stats` / `list_uncovered_requirements` / `list_orphan_code_files`）、`yuleosh.pipeline.step_handlers`（`PIPELINE_STEPS`）、`yuleosh.engine.checkpoint`（`CheckpointEngine`）。
- 外部 import `plan`：`src/yuleosh/cli/main.py:323,825`（`build_plan_subparser` / `handle_plan_command`）。

---

## 8. 测试

- `tests/test_plan_models_unit.py`（models 单测）
- `tests/test_plan_agent.py`（Ultra-Plan Agent 集成测试，`:294-332` 含 `context`）
- `tests/test_coverage_phase2_lowcov.py`、`tests/test_cli_main_adv_unit.py:762`（patch `handle_plan_command`）

---

## 9. 已知偏差 / 待决

- 模块无 HTTP 端点，与 `dashboard-design` 的“计划”UI 草案未对齐（若前端需展示计划，需新增 API 层或复用 `ui` 路由）。
- 工时估算为规则硬编码，非数据驱动，跨项目泛化能力有限。

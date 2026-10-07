# 计划/规划 (`plan`) API 参考

> 代码根:`src/yuleosh/plan/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`plan` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/plan.md` 若存在)。

## 2. HTTP 端点

| 线索(来自 router.py / ui/routes) |
| --- |
| `"plan": tenant.plan,` |
| `"plan": tenant.plan,` |
| `{"id": t.id, "name": t.name, "plan": t.plan, "created_at": t.created_at}` |
| `"plan": tenant.plan,` |
| `path_tail: "usage" | "plan" | "upgrade"` |
| `if method == "GET" and sub == "plan":` |
| `"plan": usage.get("plan", "free"),` |
| `"current_plan": subscription.get("plan", PLAN_FREE),` |
| `plan = body.get("plan", "").strip().lower()` |

> 注:以上为路由注册线索,完整方法/路径/参数以对应 handler 为准。
## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `generate_plan` | `(task: str, project_dir: str, save_to: Optional[str])` | One-shot convenience: create agent, plan, optionally save, return plan. | `plan/agent.py:170` |
| `_get_latest_plan_id` | `(project_dir: str)` | Get the most recent plan ID from the plans directory. | `plan/cli.py:26` |
| `_load_plan` | `(project_dir: str, plan_id: str)` | Load a plan from disk by ID. | `plan/cli.py:37` |
| `_save_plan` | `(project_dir: str, plan: Plan)` | Save a plan to disk and return its ID. | `plan/cli.py:47` |
| `build_plan_subparser` | `(subparsers)` | Add the 'plan' subcommand parser. | `plan/cli.py:58` |
| `handle_plan_command` | `(args: argparse.Namespace)` | Route plan subcommand to the appropriate handler. | `plan/cli.py:96` |
| `_handle_generate` | `(project_dir: str, description: str, as_json: bool)` | Generate a plan from a task description. | `plan/cli.py:134` |
| `_handle_apply` | `(project_dir: str)` | Execute the latest plan via CheckpointEngine. | `plan/cli.py:157` |
| `_handle_list` | `(project_dir: str)` | List saved plans. | `plan/cli.py:208` |
| `default_context` | `(project_dir: str | None)` | Build a PlanContext using the current project directory. | `plan/context.py:250` |
| `_match_rules` | `(task: str)` | Return all matching rule trigger infos for a task description. | `plan/generator.py:138` |
| `_detect_prerequisites` | `(task: str)` | Detect prerequisites from task keywords. | `plan/generator.py:147` |
| `_detect_risks` | `(task: str)` | Detect risks from task keywords. | `plan/generator.py:167` |
| `_build_dependency_graph` | `(matches: list[dict])` | Assign dependencies among matched steps. | `plan/generator.py:186` |
| `_assign_agent` | `(match_info: dict)` | Map agent_key to display name. | `plan/generator.py:206` |
| `_add_default_steps` | `(matches: list[dict])` | Ensure any standard pipeline steps not yet matched are considered. | `plan/generator.py:212` |
| `_renumber_steps` | `(steps: list[PlanStep])` | Assign sequential step IDs (P1, P2, ...) based on dependency order. | `plan/generator.py:257` |
| `_term_width` | `()` | Return terminal width or default 80. | `plan/output.py:54` |
| `to_markdown` | `(plan: Plan, with_ansi: bool)` | Render a Plan as structured Markdown. | `plan/output.py:64` |
| `to_json` | `(plan: Plan, **kwargs)` | Render a Plan as a JSON string. | `plan/output.py:179` |
| `to_pipeline_steps` | `(plan: Plan)` | Convert Plan steps to CheckpointEngine-compatible step definitions. | `plan/output.py:196` |
| `to_cli_output` | `(plan: Plan)` | Render a Plan for CLI display (ANSI-colored). | `plan/output.py:227` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `PlanAgent` | `()` | Ultra-Plan Agent — generate structured plans from task descriptions. | `plan/agent.py:44` |
| `PlanContext` | `()` | Project / KG / pipeline context used by PlanGenerator. | `plan/context.py:25` |
| `PlanGenerator` | `()` | Generates a structured Plan from a task description and context. | `plan/generator.py:284` |
| `PlanStatus` | `()` | Well-known plan lifecycle status values. | `plan/models.py:25` |
| `PlanStep` | `()` | A single step in an ultra-plan. | `plan/models.py:53` |
| `Plan` | `()` | A complete ultra-plan. | `plan/models.py:106` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `PlanAgent.__init__` | `(self, project_dir: str)` | — | `plan/agent.py:59` |
| `PlanAgent.plan` | `(self, task: str)` | Generate a structured Plan from a natural-language task. | `plan/agent.py:66` |
| `PlanAgent.to_markdown` | `(self, plan: Plan)` | Render a Plan as Markdown (CLI-friendly). | `plan/agent.py:105` |
| `PlanAgent.to_json` | `(self, plan: Plan)` | Render a Plan as a JSON string. | `plan/agent.py:109` |
| `PlanAgent.to_pipeline` | `(self, plan: Plan)` | Convert Plan steps to CheckpointEngine-compatible format. | `plan/agent.py:113` |
| `PlanAgent.save` | `(self, plan: Plan, path: str | Path)` | Save a Plan as JSON to disk. | `plan/agent.py:123` |
| `PlanAgent.save_markdown` | `(self, plan: Plan, path: str | Path)` | Save a Plan as Markdown to disk. | `plan/agent.py:135` |
| `PlanAgent.approve` | `(self, plan: Plan)` | Mark a plan as approved (ready for execution). | `plan/agent.py:149` |
| `PlanAgent.start_execution` | `(self, plan: Plan)` | Mark a plan as executing. | `plan/agent.py:155` |
| `PlanAgent.complete` | `(self, plan: Plan)` | Mark a plan as done. | `plan/agent.py:161` |
| `PlanContext.__init__` | `(self, project_dir: str)` | — | `plan/context.py:32` |
| `PlanContext.get_project_summary` | `(self)` | Return a dict describing the project directory structure. | `plan/context.py:38` |
| `PlanContext.get_kg_summary` | `(self)` | Return a summary of the current knowledge graph. | `plan/context.py:108` |
| `PlanContext.get_aspice_coverage` | `(self)` | Return per-ASPICE-layer coverage from the KG. | `plan/context.py:160` |
| `PlanContext.get_existing_requirements` | `(self)` | Return existing requirements from KG or spec files. | `plan/context.py:179` |
| `PlanContext.get_pipeline_capabilities` | `(self)` | Return the list of available CheckpointEngine pipeline steps. | `plan/context.py:227` |
| `PlanGenerator.generate` | `(self, task: str, context: dict | None)` | Generate a Plan from a natural-language task description. | `plan/generator.py:287` |
| `PlanStep.to_dict` | `(self)` | — | `plan/models.py:79` |
| `PlanStep.from_dict` | `(cls, d: dict)` | — | `plan/models.py:92` |
| `Plan.total_effort_hours` | `(self)` | Sum of all step effort estimates. | `plan/models.py:137` |
| `Plan.agent_breakdown` | `(self)` | Effort broken down by agent name. | `plan/models.py:142` |
| `Plan.agent_count` | `(self)` | Number of unique agents involved. | `plan/models.py:150` |
| `Plan.to_dict` | `(self)` | — | `plan/models.py:154` |
| `Plan.to_json` | `(self, **kwargs)` | Serialize to JSON string. | `plan/models.py:167` |
| `Plan.from_dict` | `(cls, d: dict)` | — | `plan/models.py:181` |
| `Plan.from_json` | `(cls, text: str)` | — | `plan/models.py:195` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |

## 5. 调用示例

> 基于上述公共 API;具体参数与返回以源码 `文件:行` 为准(本表为机械生成,未逐接口验证示例)。

```python
# from yuleosh.plan import <公共符号>
# 详见 docs/modules/plan.md(若存在)
```

## 6. 偏差 / 备注

- 生产调用方:✅ 有 7 处生产引用(Grep `yuleosh.plan` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/plan/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

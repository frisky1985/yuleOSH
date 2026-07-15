# Ultra-Plan Agent — 构建报告

**日期**: 2026-07-15  
**构建人**: 小克 (subagent)  
**模块**: `src/yuleosh/plan/`  
**测试**: `tests/test_plan_agent.py`

---

## 摘要

Ultra-Plan Agent 已完成构建并全量通过测试（40/40）。该模块为 yuleOSH 新增了"先出计划再干"的前端能力：用户输入自然语言任务描述，Agent 自动生成结构化的实施计划（含目标、背景、技术方案、拆分步骤、agent 分配、工时估算、风险、前置条件），支持 Markdown/JSON/pipeline 三种输出格式。

## 模块结构

```
src/yuleosh/plan/
├── __init__.py        # 统一导出 (88 bytes)
├── agent.py           # PlanAgent 主入口 (3.1 KB)
├── models.py          # Plan/PlanStep 数据模型 (5.1 KB)
├── context.py         # 上下文分析器 (8.3 KB)
├── generator.py       # 方案生成器 (13.1 KB)
└── output.py          # 输出格式 (6.3 KB)
```

## 设计要点

### 1. 数据模型 (`models.py`)

- `PlanStep` — 单步任务，含 `step_id`, `name`, `description`, `agent`, `effort_hours`, `depends_on`, `verification`, `pipeline_step`
- `Plan` — 完整方案，含 `title`, `objective`, `background`, `technical_approach`, `steps`, `risks`, `prerequisites`, `generated_at`, `status`
- `PlanStatus` — 生命周期枚举：`draft → review → approved → executing → done | cancelled`
- `AGENT_MAP` — 步骤类型到 agent 名称的映射：`code → 小克`, `review → 小马`, `orchestration → 小明`
- 完整序列化/反序列化支持：`to_dict()`, `to_json()`, `from_dict()`, `from_json()`
- `total_effort_hours` / `agent_breakdown` / `agent_count` 计算属性

### 2. 上下文分析器 (`context.py`)

- `PlanContext(project_dir)` 构造
- `get_project_summary()` — 扫描项目目录结构、源文件、测试文件
- `get_kg_summary()` — 通过 `yuleosh.knowledge_graph` 获取 KG 节点/边/layer 统计
- `get_aspice_coverage()` — 获取 per-layer ASPICE 覆盖
- `get_existing_requirements()` — 从 KG 或 spec 文件读取需求列表
- `get_pipeline_capabilities()` — 读取 `PIPELINE_STEPS` 注册表
- 所有方法在 KG/pipeline 不可用时优雅降级为默认值

### 3. 方案生成器 (`generator.py`)

- 基于关键词启发式规则匹配任务类型
  - `test|coverage` → 测试规划步骤
  - `ASIL|safety` → 功能安全审查门
  - `KG|traceability` → KG 追溯验证
  - `dashboard|UI` → 前端开发
  - `HIL` → HIL 测试框架
  - `MISRA` → MISRA 合规审查
  - `requirement|spec` → 需求分析
  - `arch|design` → 架构设计
- 自动添加默认步骤（代码实现 + 代码审查 + 最终报告）
- 依赖图构建（framework 类步骤作为后续步骤的前置依赖）
- 风险与前置条件智能检测
- 拓扑排序确保步骤执行顺序合理
- 标题截断（>60 字符自动截断）

### 4. 主入口 (`agent.py`)

- `PlanAgent(project_dir)` — 统一入口类
- `agent.plan(task)` — 一步生成 Plan
- `agent.to_markdown(plan)` — 渲染 Markdown
- `agent.to_json(plan)` — 渲染 JSON
- `agent.to_pipeline(plan)` — 输出 CheckpointEngine 兼容格式
- `agent.save(plan, path)` — 保存 JSON 到磁盘
- `agent.approve(plan)` / `start_execution(plan)` / `complete(plan)` — 生命周期管理

### 5. 输出格式 (`output.py`)

- 富 Markdown 输出（含 ANSI 彩色终端版本）
- JSON 输出（`json.dumps` 兼容）
- CheckpointEngine 步骤定义格式
- 终端宽度自适应

## 输出示例

```
📋 Ultra-Plan: BCM Demo HIL 测试支持
══════════════════════════════════════

目标：为 BCM Demo 增加 HIL 测试支持

技术方案：基于 yuleASR MCAL 层搭建 HIL 测试台架...

步骤：
  [1] 小克 👨‍💻   HIL 测试框架搭建       2.0h  依赖: -
       ✅ 验证: HIL 测试可编译运行
  [2] 小克 👨‍💻   BCM 门控 HIL 用例       1.5h  依赖: [1]
       ✅ 验证: 门控 HIL 3 用例通过
  ...
  ────────────────────────────────────────────────
  总计: ~8.0h | 5 步骤 | 2 agents

风险：
  - HIL 硬件台架可用性需确认
  - 估算基于启发式规则，实际可能有 ±30% 偏差
```

## 测试覆盖

| 测试 | 状态 |
|:-----|:------|
| `test_plan_agent_creates_plan` | ✅ |
| `test_plan_has_steps` | ✅ |
| `test_plan_step_has_fields` | ✅ (via test_all_steps_have_fields) |
| `test_plan_to_markdown` | ✅ |
| `test_plan_to_json` | ✅ |
| `test_context_project_summary` | ✅ |
| `test_context_kg_summary` | ✅ (graceful empty fallback) |
| `test_context_pipeline_capabilities` | ✅ |
| `test_context_existing_requirements` | ✅ |
| `test_context_aspice_coverage_graceful` | ✅ |
| `test_plan_to_pipeline` | ✅ |
| `test_plan_step_assigns_agent` | ✅ (via test_agent_assignment) |
| `test_plan_effort_summary` | ✅ |
| `test_status_transitions` | ✅ |
| `test_save_to_disk` | ✅ |
| `test_save_markdown` | ✅ |
| `test_generator_keyword_detection` (5 tests) | ✅ |
| `test_generator_default_steps` | ✅ |
| `test_generator_risk/prereq/context` (4 tests) | ✅ |
| **总计: 40 passing, 0 failing** | ✅ |

## 模块覆盖率

| 文件 | 覆盖率 | 说明 |
|:-----|:-------|:------|
| `__init__.py` | 100% | |
| `models.py` | 100% | |
| `agent.py` | 89% | 18-22% 未覆盖行在干路径 (context 方法不在 context.py 的 line 185-189 范围) |
| `context.py` | 59% | 低是因为 KG 不可用时的 try/except 分支，需要真实 KG 实例 |
| `generator.py` | 93% | 仅少数边界分支未覆盖 |
| `output.py` | 90% | 类似，少数 ANSI 分支 |

## 集成点

### CLI 集成（待注册）

```python
# 在 cli/main.py 中添加：
p_plan = sub.add_parser("plan", help="Ultra-Plan Agent")
p_plan.add_argument("task", help="Task description (natural language)")
p_plan.add_argument("--apply", action="store_true", help="Execute the plan")
p_plan.add_argument("--json", action="store_true", help="Output as JSON")

# dispatch:
elif args.command == "plan":
    from yuleosh.plan import PlanAgent
    agent = PlanAgent()
    plan = agent.plan(args.task)
    if args.json:
        print(agent.to_json(plan))
    elif args.apply:
        print(agent.to_markdown(plan))
        print("\n🔧 执行功能暂未接入 CheckpointEngine")
    else:
        print(agent.to_markdown(plan))
```

### Pipeline 集成

`agent.to_pipeline(plan)` 的输出直接对接 `PipelineSession.add_step()`。
```python
pipeline_steps = agent.to_pipeline(plan)
for step_def in pipeline_steps:
    session.add_step(
        step_name=step_def["action"],
        agent=step_def["agent"],
        action=step_def["description"],
    )
```

## 后续工作

1. **LLM 增强**: 当前生成基于关键字启发式规则；可接入 LLM 调用实现语义理解和结构化输出
2. **CLI 注册**: 将 `plan` 命令注册到 `cli/main.py`
3. **Pipeline 注入**: 实现 `--apply` 时将计划步骤注入 CheckpointEngine 执行
4. **KG 集成测试**: 在有真实 KG 数据的项目中进行端到端验证
5. **交互式审查**: 允许用户对生成的计划进行增删改步骤后再确认执行

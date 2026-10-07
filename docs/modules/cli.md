# 模块设计速写：cli（命令行接口）

> 包：`src/yuleosh/cli/` ｜ 规模：20 .py ≈ 6854 行
> 定位：系统顶层边界，薄消费者 / 分发器

## 职责
yuleOSH CLI 入口：init / template / spec / pipeline / ci / evidence / review / audit / kpi / kg / device / loop / onboard 等大量子命令。证据：`cli/main.py:7-8`（"yuleOSH — Embedded AI Development Platform CLI"）。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `cli/main.py` (1032) | 顶层解析器 + 分发器 | `main` `:582`；`_build_parser` `:145`；`ensure_osh_home` `:136`；`OSH_HOME` `:42` |
| `cli/commands/misc.py` (1421) | 最大命令组 | `cmd_pipeline_run` `:704`；`cmd_ci_run` `:747`；`cmd_evidence_pack` `:760`；`cmd_review_auto` `:717` |
| `cli/commands/*.py` (15) | 各命令实现 | `cmd_traceability_*` / `cmd_misra_*` / `cmd_swe6_*` / `cmd_review_diff` / `cmd_reverse_scan` / `cmd_compliance_check` / `cmd_gap_close` 等 |
| `cli/onboard.py` (607) / `cli/stats.py` (415) / `cli/template.py` (276) | 顶层命令模块 | — |

## 公共 API / 入口点
- 进程入口：`yuleosh/__main__.py:11`、`yuleosh/_entry.py:17` → `cli.main.main`
- 分发：`cli/main.py:582 main()`；子命令函数统一 re-export 于 `:63-133`（供测试/插件复用）

## 生产接线
- **外部生产调用者仅入口层**：`__main__.py:11` / `_entry.py:17` / `cli/yuleosh.sh:117,127`。
- 内部：`cli/main.py:63-133` 批量 re-export `cli/commands/*`；各命令延迟 import 业务包（`misc.py:705` 调 `pipeline.run.run_pipeline`，`:748` 调 `ci.run.run_layer{1,2,3}`）。
- 结论：除 `cli` 包外无生产模块调用者；CLI 是系统顶层边界，所有 `cli/commands/*` 经 `main.py` 分发可达，非 orphan。

## 运行时触发方式
`python3 -m yuleosh`（→ `__main__.py`）或 pip `yuleosh`（→ `_entry.py`）→ `main()` → `_build_parser()` 解析 → 按 `args.command` 分发（`:593-1028`）。大量子命令延迟 import 业务包（如 `demo`→`api.demo_wow`/`api.demo_quick` `:690-694`，`kg`→`knowledge_graph.kg_cli` `:947`，`hook`→`hooks.cli` `:821`，`plan`→`plan.cli` `:825`，`loop`→`loop_engine.cli` `:991`）。

## 环境变量 / 配置
- `OSH_HOME`（`main.py:42`，dev 默认 CWD）；`:137` `os.environ.setdefault("OSH_HOME", OSH_HOME)` 强制注入。
- 其余 env 经被调用业务包间接读取；CLI 自身不另读 env。

## 与 pipeline / engine 关系（见 engine.md）
- CLI 的 `pipeline run`/`pipeline status` 直接走 `pipeline.run.run_pipeline`/`status_pipeline`（不经 engine 的 `CheckpointEngine`）；`ci run` 走 `ci.run.run_layer{1,2,3}`。engine 主要由 API/看板驱动；二者仅在 `cli/yuleosh.sh` 旁路口通过 `engine.agent_checkpoint`/`engine.ci_checkpoint` 衔接。

## 偏差 / 待注意（设计文档必记）
- **D1：`cli/main.py` 是「巨型分发 monolith + re-export」**——v3.8.0 拆分后（`main.py:59-133` 注释）仍把所有 `cmd_*` 重新导入本模块保兼容；实际逻辑在 `cli/commands/*.py`（`main.py:140-143` 注释「All command functions below the A5 header are re-exported」）。
- **D2：模板命令三处导出**——`cli/template.py` 定义 + `cli/commands/__init__.py:2-3` re-export + `cli/main.py:102-107` 再 re-export `cmd_template_list`。
- **D3：docstring 与实际子命令不一致**——`main.py:11-27` 列举远少于实际注册（缺 kg/kpi/device/loop/plan/knowledge/skills/hook/methodology/gap/reverse/compliance/onboard/consistency/swe6/misra/coverage/audit/autosar 等）。
- **D4：`cmd_ci_run` 仅支持 layer 1/2/3**（`:750`，dict 无 `2.5`），而引擎 `create_ci_pipeline` 支持 1/2/2.5/3（`ci_checkpoint.py:77-187`）——CLI 缺 2.5/3。
- **D5：`__main__.py` 与 `_entry.py` 功能重复**（均 `from yuleosh.cli.main import main`）。

## 规模
20 .py ≈ 6854 行（root 5 个 2334 + commands 15 个 4520）。

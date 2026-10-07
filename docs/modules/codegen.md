# `codegen` 模块设计速写

> 本篇为「模块设计速写」（speed-write），基于 2026-10-07 实读 `src/yuleosh/codegen/`。
> 与代码冲突时以代码为准。

## 0. 概述
代码生成闭环（D3）：spec / 架构 → 代码 → 编译验证 → 自动修复。支持 **Python**
（`py_compile`）与 **C/C++**（`gcc -fsyntax-only` / `cc`）。LLM 以 `### FILE: <path>` 标记
+ 围栏代码块（或 JSON payload）输出，由引擎解析。无 CLI / 无 HTTP，是 Pipeline 的库式依赖。

## 1. 文件清单
| 文件 | 行数 |
|---|---|
| `codegen/__init__.py` | 45 |
| `codegen/layered.py` | 201 |
| `codegen/prompts.py` | 243 |
| `codegen/compilers.py` | 309 |
| `codegen/engine.py` | 1553 |

## 2. 核心职责
- **生成闭环**：`CodegenEngine.generate()` 的「生成 → 验证 → 修复」循环
  （`engine.py:272`），含：
  - seed 增量（`_sync_seed` `:724`、`collect_seed_sources`）、
  - 白名单框定 LLM 输出范围（`_build_allowlist` `:843`、`_filter_out_of_scope` `:870`）、
  - 3 次失败触发头脑风暴（`_brainstorm` `:884`，阈值 `brainstorm_after_failures=3`）、
  - void 抑制确定性同步（`_sync_void_suppressions` `:595`）、
  - 终验（`_final_verify` `:1174`）。
- **分层策略**：`LayeredCodegenEngine` 按 HAL → BSP → App 三阶段顺序生成
  （`layered.py:7-18`，`LAYER_CONFIGS` `:36`）。
- **Prompt 构建**：拼接 spec / PRD / 架构 / 契约 / seed 基线 + skills 注入
  （`prompts.py:113`）。

## 3. 关键类与函数（文件:行号）
- `CodegenEngine`（`engine.py:208`）：`generate` `:272`、`_call_llm` `:536`、`write_files` `:564`、
  `parse_generated_files` `:130`、`_check_seed_contract` `:1022`、
  `_check_structural_features` `:1055`、`_check_forbidden_features` `:1103`、`_write_report` `:1388`。
- 数据模型（dataclass）：`GeneratedFile` `:52`、`RoundFailure` `:61`、`CodegenResult` `:72`
  （`to_dict` `:95`）。
- 编译器（`compilers.py`）：`detect_language` `:40`、`verify_python` `:72`、`verify_c` `:102`、
  `discover_project_cflags` `:218`、`compile_verify` `:274`、`run_build_command` `:254`。
- 分层（`layered.py`）：`LayerConfig` `:28`、`LayeredCodegenEngine.generate_layered` `:111`。

## 4. 数据模型
`GeneratedFile`（`path/content/language`）、`RoundFailure`（`round_idx/error_signature/err_count/
is_behavior/files`）、`CodegenResult`（状态机 `generated|verified|failed|no-files` + 报告路径 +
brainstorm 结果）。`LayerConfig`（`name/file_globs/system_prompt_fragment/structural_features/
forbidden_features`）。均为 dataclass，非 pydantic。

## 5. 集成点
- import 其它子包：`pipeline.session`（`engine.py:37`）、`pipeline.run.chat_completion`（惰性
  `:545`）、`skills.prompt.render_skills`（`prompts.py:16`）、`pipeline.prompts`（`prompts.py:17`）。
- 被 import：
  - `pipeline/step_classes.py:10,384-385` → `CodegenEngine` / `build_codegen_prompt` 等。
  - `pipeline/step_handlers/execution.py:38,228-229,280,560` → codegen 多个入口。
  - `pipeline/step_handlers/analysis.py:267` → `collect_existing_headers`。
  - `kb/codegen_failures.py:36` → `CodegenResult`。

## 6. 配置 / 环境变量
- `OSH_CODEGEN_DIR`（`engine.py:120`）— 覆盖生成输出目录（默认 `artifacts/generated-code`）。
- `YULEOSH_CODEGEN_LLM_TIMEOUT`（`engine.py:553`，默认 `"120"`）— LLM 超时秒。
- session 配置键 `config["codegen"]`（`execution.py:249+`）：`cflags`（**优先级高于** CMakeLists
  自动发现）、`build_cmd`、`language`/`target_language`。

## 7. 测试
`test_codegen_engine.py`、`test_codegen_seed_incremental.py`、`test_codegen_seed_contract_20260816.py`、
`test_codegen_void_sync.py`、`test_codegen_verify_host_include.py`、`test_codegen_cflags.py`、
`test_codegen_brainstorm_20260816.py`、`test_codegen_behavior_guardrail.py`、`test_codegen_determinism.py`、
`test_codegen_development_step.py`、`test_codegen_failures.py`、`test_layered_codegen.py`、
`test_coverage_phase6_pipeline_llm.py`（间接 mock）。

## 8. 备注
codegen 集成完整、测试充分，偏差最小。设计文档若须补，建议聚焦「seed 契约 + 白名单框定」
两道反回归机制的动机说明。

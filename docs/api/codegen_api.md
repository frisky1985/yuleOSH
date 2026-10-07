# 代码生成 (`codegen`) API 参考

> 代码根:`src/yuleosh/codegen/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`codegen` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/codegen.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `detect_language` | `(files: list[str | Path])` | Detect the primary language from file extensions. | `codegen/compilers.py:40` |
| `_result` | `(ok: bool, language: str, command: str, output: str, returncode: int)` | — | `codegen/compilers.py:61` |
| `verify_python` | `(files: list[Path], python_cmd: str)` | Syntax-check Python files with ``python -m py_compile``. | `codegen/compilers.py:72` |
| `verify_c` | `(files: list[Path], cc: Optional[str], project_root: Optional[Path], cflags: Optional[list[str]])` | Syntax-check C/C++ files with ``gcc -fsyntax-only`` (or ``cc``). | `codegen/compilers.py:102` |
| `discover_project_cflags` | `(project_root: str | Path)` | 从项目 CMakeLists.txt 提取警告 flags (-W*)。 | `codegen/compilers.py:218` |
| `run_build_command` | `(build_cmd: list[str])` | Run a project build command (e.g. ``make``) and return the result. | `codegen/compilers.py:254` |
| `compile_verify` | `(files: list[Path], language: Optional[str], build_cmd: Optional[list[str]], python_cmd: str, cc: Optional[str], project_root: Optional[Path], cflags: Optional[list[str]])` | Verify generated files compile. | `codegen/compilers.py:274` |
| `default_output_dir` | `(project_dir: str | Path, session_name: str)` | ``<project_dir>/artifacts/generated-code/<session_name>``. | `codegen/engine.py:113` |
| `parse_generated_files` | `(llm_output: str)` | Parse an LLM codegen response into :class:`GeneratedFile` objects. | `codegen/engine.py:130` |
| `_safe_relative_path` | `(raw: str)` | Sanitize a generated relative path (strip ``../`` and leading slashes). | `codegen/engine.py:201` |
| `_strip_c_comments` | `(src: str)` | Strip C/C++ comments (/* */ and //) from source, preserving strings. | `codegen/engine.py:1397` |
| `build_codegen_report` | `(result: CodegenResult, session: PipelineSession)` | Render the codegen report markdown (file list / verify / rounds). | `codegen/engine.py:1464` |
| `collect_existing_headers` | `(project_dir: str | Path, max_files: int)` | 收集项目既有头文件内容 (src/**/include/*.h) 作为 API 契约。 | `codegen/prompts.py:38` |
| `collect_seed_sources` | `(project_dir: str | Path, max_files: int, max_chars: int)` | 收集项目现有 src 代码 (src/**/*.c, *.h) 作为 seed 基线。 | `codegen/prompts.py:64` |
| `_trunc_ref` | `(text: str, limit: int, ref: str)` | Reference-marked truncation for prompt injection (D1). | `codegen/prompts.py:98` |
| `build_codegen_prompt` | `(spec_content: str, spec_name: str, architecture_content: str, prd_content: str, super_analysis_content: str, skills: Optional[list[str]], target_language: Optional[str], existing_headers: str, seed_sources: str, context_content: str, contracts_json: str)` | Build ``(system_prompt, user_prompt)`` for code generation. | `codegen/prompts.py:113` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `GeneratedFile` | `()` | One code file parsed from the LLM response. | `codegen/engine.py:52` |
| `RoundFailure` | `()` | One failed codegen round — feeds the brainstorm analysis (2026-08-16). | `codegen/engine.py:61` |
| `CodegenResult` | `()` | Outcome of a codegen run (also serialized into the report). | `codegen/engine.py:72` |
| `CodegenEngine` | `()` | Runs the generate → verify → fix loop. | `codegen/engine.py:208` |
| `LayerConfig` | `()` | — | `codegen/layered.py:28` |
| `LayeredCodegenEngine` | `()` | Orchestrates HAL → BSP → App three-phase codegen. | `codegen/layered.py:96` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `CodegenResult.to_dict` | `(self)` | — | `codegen/engine.py:95` |
| `CodegenEngine.__init__` | `(self, output_dir: Optional[str | Path], max_retries: int, llm_client: Optional[Callable], verifier: Optional[Callable], max_tokens: int, seed_dir: Optional[str | Path], seed_contract: Optional[dict[str, set[str]]], behavior_verify: Optional[Callable], brainstorm_after_failures: int, structural_features: Optional[dict[str, list[str]]], forbidden_features: Optional[dict[str, list[str]]])` | — | `codegen/engine.py:221` |
| `CodegenEngine.generate` | `(self, session: PipelineSession, system_prompt: str, user_prompt: str, language_hint: Optional[str], build_cmd: Optional[list[str]], cflags: Optional[list[str]])` | Run the full generate → verify → fix loop. | `codegen/engine.py:272` |
| `CodegenEngine.write_files` | `(self, files: list[GeneratedFile], out_dir: Path)` | Write generated files under ``out_dir`` (path-traversal safe). | `codegen/engine.py:564` |
| `LayeredCodegenEngine.__init__` | `(self, layers: list[str] | None, base_engine_kwargs: dict | None)` | — | `codegen/layered.py:103` |
| `LayeredCodegenEngine.generate_layered` | `(self, session: Any, base_system_prompt: str, base_user_prompt: str, language_hint: str, **kw)` | Run all configured layers sequentially. | `codegen/layered.py:111` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_CODEGEN_DIR` | _(见源码)_ |
| `YULEOSH_CODEGEN_LLM_TIMEOUT` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.codegen`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/pipeline/step_handlers/execution.py:38
from yuleosh.codegen.prompts import collect_existing_headers, collect_seed_sources

# src/yuleosh/pipeline/step_handlers/analysis.py:267
from yuleosh.codegen.prompts import collect_existing_headers

# src/yuleosh/pipeline/step_classes.py:10
from yuleosh.codegen.prompts import collect_existing_headers

# src/yuleosh/kb/codegen_failures.py:36
from yuleosh.codegen.engine import CodegenResult

```

> 共 4 个文件引用本子系统；完整调用图见 `docs/modules/codegen.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 9 处生产引用(Grep `yuleosh.codegen` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/codegen/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

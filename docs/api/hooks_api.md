# 钩子 (`hooks`) API 参考

> 代码根:`src/yuleosh/hooks/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`hooks` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/hooks.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `_find_git_hooks_dir` | `(cwd: str | None)` | Locate .git/hooks/ by walking up from *cwd*. | `hooks/cli.py:55` |
| `_install_hook` | `(hooks_dir: Path, name: str, template: str)` | Write *template* to hooks_dir/name and make executable. Returns True if written. | `hooks/cli.py:70` |
| `cmd_hook_install` | `(cwd: str | None)` | Install yuleOSH hooks into .git/hooks/. | `hooks/cli.py:87` |
| `cmd_hook_run` | `(hook_name: str)` | Run a hook by name. | `hooks/cli.py:115` |
| `build_hook_subparser` | `(subparsers)` | Add the 'hook' subcommand parser. | `hooks/cli.py:131` |
| `handle_hook_command` | `(args)` | Dispatch hook subcommand. | `hooks/cli.py:146` |
| `_is_yuleosh_project` | `(cwd: str | Path)` | — | `hooks/post_merge.py:26` |
| `_classify_misra_category` | `(rule_id: Optional[str])` | — | `hooks/post_merge.py:36` |
| `_load_snapshot` | `(project_root: Path)` | — | `hooks/post_merge.py:48` |
| `_get_existing_kb_signatures` | `(store: KbStore)` | Return set of 'rule_id:file:line' tuples already in KB. | `hooks/post_merge.py:58` |
| `run_post_merge` | `(cwd: Optional[str])` | Run the post-merge hook. Returns 0 on success, 1 on error. | `hooks/post_merge.py:72` |
| `_is_yuleosh_project` | `(cwd: str | Path)` | Check whether *cwd* (or any parent) is a yuleOSH project. | `hooks/pre_commit.py:33` |
| `_get_staged_source_files` | `()` | Return list of staged .c/.h files. | `hooks/pre_commit.py:44` |
| `_parse_cppcheck_violations` | `(text: str)` | Parse cppcheck text output into structured violation dicts. | `hooks/pre_commit.py:63` |
| `_extract_rule_id` | `(message: str)` | Extract MISRA rule ID (e.g. '10.1', '12.3') from a cppcheck message. | `hooks/pre_commit.py:106` |
| `_run_cppcheck` | `(files: list[str])` | Run cppcheck with MISRA addon on *files* and return raw stdout+stderr. | `hooks/pre_commit.py:120` |
| `_load_last_snapshot` | `(project_root: Path)` | Load previously persisted violation snapshot, or return empty list. | `hooks/pre_commit.py:149` |
| `_save_snapshot` | `(project_root: Path, violations: list[dict])` | Persist current violation snapshot to disk. | `hooks/pre_commit.py:160` |
| `_classify_misra_category` | `(rule_id: Optional[str])` | Guess MISRA category (required/advisory) by rule number ranges. | `hooks/pre_commit.py:167` |
| `_create_kb_entries` | `(store: KbStore, violations: list[dict])` | Create KB articles for each violation that doesn't already exist. | `hooks/pre_commit.py:181` |
| `_find_new_violations` | `(current: list[dict], last: list[dict])` | Return violations in *current* that are NOT in *last*. | `hooks/pre_commit.py:206` |
| `run_pre_commit` | `(cwd: Optional[str])` | Run the pre-commit hook. Returns 0 (always non-blocking). | `hooks/pre_commit.py:223` |
| `_run_code_style_hook` | `(project_root: Path, abs_files: list[str])` | Run SWC code-style on staged files; warn on NEW violations only. | `hooks/pre_commit.py:318` |

### 3.2 公共类

_(无顶层类)_

### 3.3 类关键公共方法(节选)

_(无)_

## 4. 配置 / 环境变量

_(未发现 `os.environ` / `getenv` 引用)_

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.hooks`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/cli/main.py:319
from yuleosh.hooks.cli import build_hook_subparser

```

> 共 1 个文件引用本子系统；完整调用图见 `docs/modules/hooks.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 4 处生产引用(Grep `yuleosh.hooks` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/hooks/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

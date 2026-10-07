# 模块设计速写：hooks（Git 钩子）

> 包：`src/yuleosh/hooks/` ｜ 规模：4 .py ≈ 686 行
> 定位：真实接线、CLI 触发

## 职责
Git 钩子：pre-commit（对暂存 C/C++ 文件跑 MISRA cppcheck + SWC 代码风格扫描）与 post-merge（MISRA 快照沉淀进知识库 KB）。证据：`hooks/__init__.py:4`、`pre_commit.py:4`、`post_merge.py:4`。

## 关键文件与角色
| 文件 | 角色 | 关键符号（file:line） |
|---|---|---|
| `hooks/__init__.py` (9) | re-export | `run_pre_commit`/`run_post_merge` `:6-9` |
| `hooks/cli.py` (152) | 安装器 + 运行器 | `PRE_COMMIT_TEMPLATE` `:21`；`POST_MERGE_TEMPLATE` `:38`；`cmd_hook_install` `:87`；`cmd_hook_run` `:115`；`build_hook_subparser` `:131` |
| `hooks/pre_commit.py` (372) | 扫描逻辑 | `_run_cppcheck` `:120`；`_load_last_snapshot` `:149`；`_create_kb_entries` `:181`；`_find_new_violations` `:206`；`run_pre_commit` `:223`（**始终 return 0**）；`_run_code_style_hook` `:318` |
| `hooks/post_merge.py` (153) | 沉淀 | `_classify_misra_category` `:36`；`_get_existing_kb_signatures` `:58`；`run_post_merge` `:72` |

## 公共 API / 入口点
- `run_pre_commit`（`pre_commit.py:223`）、`run_post_merge`（`post_merge.py:72`）
- CLI：`cmd_hook_install`/`cmd_hook_run`/`build_hook_subparser`/`handle_hook_command`

## 生产接线（真实调用方）
- `cli/main.py:319` `build_hook_subparser`；`:820-822` `elif args.command=="hook": handle_hook_command`
- 子系统内：`cli.py:120` `run_pre_commit`；`:123` `run_post_merge`
- 除 CLI 外无其他生产调用方。

## 运行时触发方式
1. `yuleosh hook install`（`cli.py:87`）写 shell 模板到 `.git/hooks/` + 可执行位（`:83`）
2. Git 触发 `.git/hooks/pre-commit` → `yuleosh hook run pre-commit`（或 venv 路径，`:28-35`）；post-merge 同理（`:44-51`）
3. `main.py:820` → `handle_hook_command`（`cli.py:146`）→ `cmd_hook_run`（`cli.py:115`）→ `run_pre_commit`/`run_post_merge`

## 扩展机制
非插件/注册表式：`cmd_hook_run` 仅硬编码 `"pre-commit"`/`"post-merge"`（`cli.py:119-124`），未知名称直接报错。可配置点：SWC 代码风格规则文件 `swc-c-rules.yaml`（项目根，`pre_commit.py:329`，缺失则跳过 `:331`）。

## 环境变量 / 配置
- **模块本身不读环境变量**（grep `os.environ|getenv|ENV_` 无匹配）。项目识别靠 `.yuleosh/` 目录或 `yuleosh.yaml` 文件（`pre_commit.py:37-39`、`post_merge.py:29-31`）。
- 快照路径 `.yuleosh/ci/last-misra-snapshot.json`（`pre_commit.py:30`）、`last-code-style-snapshot.json`（`:315`）。

## 偏差 / 待注意（设计文档必记）
- **D1：pre-commit 永不阻断提交**——`run_pre_commit` 始终 `return 0`（`pre_commit.py:311-312`），新违例只打印警告。偏离「阻断型 pre-commit」直觉。
- `post_merge.py:130`/`pre_commit.py:293` 调 `KnowledgeIndexer`（`knowledge.indexer:94`）均 try/except 非致命（`post_merge.py:142-143`、`pre_commit.py:305-306`）。
- 重复代码：`_classify_misra_category` 在 `pre_commit.py:167` 与 `post_merge.py:36` 近重复。
- `_get_existing_kb_signatures`（`post_merge.py:58-69`）用 `title.split(":",1)` + `source_ref` 拼签名，解析较脆弱。

## 规模
4 .py ≈ 686 行。

# 知识图谱 (`knowledge_graph`) API 参考

> 代码根:`src/yuleosh/knowledge_graph/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码 `ast` 实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

`knowledge_graph` 子系统(职责见各公共符号 docstring 与各模块文档 `docs/modules/knowledge_graph.md` 若存在)。

## 2. HTTP 端点

本子系统不直接暴露 REST 端点(经 `api` 层或其它包包装);若有路由,见 `docs/modules/api.md` 与 `src/yuleosh/api/router.py`。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `get_store` | `(**kwargs)` | Return a KGStore / KGStorePG instance based on YULEOSH_DB_URL. | `knowledge_graph/__init__.py:37` |
| `import_data` | `(store, project_dir, create_snapshot)` | Bootstrap import from RTM + JSON + code scan. | `knowledge_graph/__init__.py:56` |
| `_parse_rtm_table` | `(md_text: str)` | Parse requirement-traceability-matrix.md table rows. | `knowledge_graph/bootstrap.py:47` |
| `_parse_shall_id` | `(raw_id: str)` | Parse a SHALL ID into (parent_id, sub_id). | `knowledge_graph/bootstrap.py:128` |
| `import_from_req_test_json` | `(store: KGStore, json_path: str)` | Import traceability data from req-test-mapping.json. | `knowledge_graph/bootstrap.py:144` |
| `import_from_rtm_md` | `(store: KGStore, md_path: str)` | Import traceability from requirement-traceability-matrix.md. | `knowledge_graph/bootstrap.py:212` |
| `scan_code_directory` | `(store: KGStore, project_base: str)` | Scan source and test directories to create CodeFile and CodeFunction nodes. | `knowledge_graph/bootstrap.py:332` |
| `bootstrap` | `(store: KGStore, project_dir: str, create_snapshot: bool)` | Full bootstrap: import all available traceability data. | `knowledge_graph/bootstrap.py:427` |
| `_c_language_for` | `(ext: str, is_test: bool)` | — | `knowledge_graph/c_code_scanner.py:147` |
| `_discover_c_files` | `(project_path: Path)` | — | `knowledge_graph/c_code_scanner.py:153` |
| `scan_directory` | `(store: KGStore, project_base: str)` | 递归扫描 ``project_base`` 下全部 .c/.h，写入 KG（对齐 code_scanner）。 | `knowledge_graph/c_code_scanner.py:166` |
| `scan_single_file` | `(store: KGStore, project_base: str, rel_path: str)` | 扫描单个 C 文件并写入/更新其节点（对齐 code_scanner.scan_single_file）。 | `knowledge_graph/c_code_scanner.py:404` |
| `_get_c_language` | `()` | 惰性加载 C grammar；首次调用后缓存。 | `knowledge_graph/c_parser.py:38` |
| `_count_errors` | `(root)` | 遍历语法树，统计 ERROR / MISSING 节点。 | `knowledge_graph/c_parser.py:112` |
| `parse` | `(source: bytes, filename: str)` | 解析 C 源码字节流（容错，永不抛异常）。 | `knowledge_graph/c_parser.py:144` |
| `parse_file` | `(path: str, encoding: str)` | 解析磁盘上的 C 文件（容错，永不抛异常）。 | `knowledge_graph/c_parser.py:188` |
| `_declarator_name` | `(declarator)` | 从 function_declarator（或其包装层）取函数名 identifier 节点。 | `knowledge_graph/c_parser.py:284` |
| `_param_list` | `(declarator)` | — | `knowledge_graph/c_parser.py:300` |
| `_declarator_base_type` | `(decl, collected: List[str])` | 把 pointer/array/parenthesized/qualified 包装层拆成类型标记（* / []），剥离名字。 | `knowledge_graph/c_parser.py:307` |
| `_extract_params` | `(plist)` | 从 parameter_list 抽取参数名与类型。 | `knowledge_graph/c_parser.py:329` |
| `_extract_head` | `(func_node)` | 从 function_definition / declaration 前导子节点抽取返回类型与存储类。 | `knowledge_graph/c_parser.py:364` |
| `_collect_comments` | `(root)` | 收集语法树中所有 comment 节点：(start, end, text) 按 start 排序。 | `knowledge_graph/c_parser.py:381` |
| `_leading_comment` | `(func_start: int, source_bytes: bytes, comments)` | 取紧邻函数上方、仅以空白（含空行）隔开的连续注释块。 | `knowledge_graph/c_parser.py:399` |
| `_extract_functions_from_tree` | `(root, source_bytes: bytes, filename: str)` | 遍历语法树，抽取所有函数定义与原型（容错：解析失败/坏树返回空列表）。 | `knowledge_graph/c_parser.py:420` |
| `_build_function` | `(node, fd, source_bytes: bytes, comments)` | — | `knowledge_graph/c_parser.py:446` |
| `extract_functions` | `(source: bytes, filename: str)` | 从 C 源码抽取全部函数（定义 + 原型），容错、永不抛异常。 | `knowledge_graph/c_parser.py:469` |
| `extract_functions_file` | `(path: str, encoding: str)` | 从磁盘 C 文件抽取函数（容错、永不抛异常）。 | `knowledge_graph/c_parser.py:491` |
| `_find_func_declarator` | `(node)` | 从 function_definition / declaration 取 function_declarator 子节点。 | `knowledge_graph/c_parser.py:569` |
| `_function_definitions` | `(root)` | 返回 [(函数名, function_definition 节点)]（仅顶层，不含原型）。 | `knowledge_graph/c_parser.py:577` |
| `_indirect_target` | `(func_child)` | 从间接调用算子（parenthesized / field_expression / pointer 等）提取可能的指针/对象名。 | `knowledge_graph/c_parser.py:595` |
| `_handle_call` | `(call_node, caller: str, edges: List[CallEdge], defined: set)` | 处理一个 call_expression，产出直接边或潜在边。 | `knowledge_graph/c_parser.py:613` |
| `_collect_calls` | `(func_node, caller: str, defined: set, edges: List[CallEdge])` | 遍历函数体，收集直接调用 + 函数指针取址/赋值（potential-call）。 | `knowledge_graph/c_parser.py:644` |
| `extract_call_graph` | `(source: bytes, filename: str)` | 从 C 源码抽取调用图（容错、永不抛异常）。 | `knowledge_graph/c_parser.py:719` |
| `extract_call_graph_file` | `(path: str, encoding: str)` | 从磁盘 C 文件抽取调用图（容错、永不抛异常）。 | `knowledge_graph/c_parser.py:761` |
| `_is_function_prototype` | `(decl_node)` | 顶层 declaration 直接含函数原型（function_declarator 且其 declarator 是裸标识符， | `knowledge_graph/c_parser.py:815` |
| `_var_declarator_info` | `(decl, type_marks: List[str])` | 从 declarator 抽变量名；指针/数组/函数指针标记追加到 type_marks。 | `knowledge_graph/c_parser.py:835` |
| `_initializer_text` | `(init_decl_node, limit: int)` | 从 init_declarator 取 = 后的初始化值文本（常量/字面量），过长截断。 | `knowledge_graph/c_parser.py:890` |
| `_extract_globals_from_tree` | `(root, source_bytes: bytes)` | — | `knowledge_graph/c_parser.py:906` |
| `_collect_vector_isrs` | `(root, func_names: set)` | 扫描 init_declarator 初始化器中的函数名（中断向量表注册）→ ISR 候选。 | `knowledge_graph/c_parser.py:985` |
| `_attr_isrs` | `(defs)` | ``__attribute__((interrupt/isr))`` 修饰的函数 → ISR。 | `knowledge_graph/c_parser.py:1018` |
| `_extract_isrs_from_tree` | `(root)` | — | `knowledge_graph/c_parser.py:1031` |
| `extract_globals` | `(source: bytes, filename: str)` | 从 C 源码抽取全局/静态变量（容错、永不抛异常）。 | `knowledge_graph/c_parser.py:1064` |
| `extract_globals_file` | `(path: str, encoding: str)` | 从磁盘 C 文件抽取全局变量（容错、永不抛异常）。 | `knowledge_graph/c_parser.py:1088` |
| `extract_isrs` | `(source: bytes, filename: str)` | 从 C 源码识别 ISR（容错、永不抛异常）。 | `knowledge_graph/c_parser.py:1102` |
| `extract_isrs_file` | `(path: str, encoding: str)` | 从磁盘 C 文件识别 ISR（容错、永不抛异常）。 | `knowledge_graph/c_parser.py:1132` |
| `_is_object_macro_whitelisted` | `(name: str)` | 对象宏是否落入标准库白名单（精确名或整数极值宏模式）。 | `knowledge_graph/c_parser.py:1196` |
| `_conditional_expr_text` | `(node)` | 从条件指令节点取条件表达式文本。 | `knowledge_graph/c_parser.py:1274` |
| `_find_endif_line` | `(node)` | 找条件块的 #endif 行（递归，取块子树内首个 #endif）。 | `knowledge_graph/c_parser.py:1291` |
| `_collect_branch_nodes` | `(node)` | 收集一个条件块的**全部分支节点**（含嵌套的 #elif/#else）。 | `knowledge_graph/c_parser.py:1303` |
| `_process_conditional_block` | `(node, depth: int, block_id: int, out: List[ConditionalInfo])` | 解析单个条件块的各分支，写入 ``out``。 | `knowledge_graph/c_parser.py:1328` |
| `_extract_conditionals_from_tree` | `(root)` | — | `knowledge_graph/c_parser.py:1414` |
| `_extract_macros_from_tree` | `(root, source_bytes: bytes)` | 遍历语法树，抽取所有宏定义（对象/函数式/flag），容错永不抛。 | `knowledge_graph/c_parser.py:1433` |
| `extract_macros` | `(source: bytes, filename: str)` | 从 C 源码抽取宏定义与条件编译分支（容错、永不抛异常）。 | `knowledge_graph/c_parser.py:1508` |
| `extract_macros_file` | `(path: str, encoding: str)` | 从磁盘 C 文件抽取宏与条件编译分支（容错、永不抛异常）。 | `knowledge_graph/c_parser.py:1552` |
| `extract_c_ast` | `(source: bytes, filename: str)` | 一次性解析并提取全部 C AST 信息（函数/全局/ISR/宏/调用图），**单次 parse**。 | `knowledge_graph/c_parser.py:1574` |
| `_save_checkpoint` | `(store: KGStore, changed_files: list[str])` | Save a checkpoint of all nodes and edges related to *changed_files*. | `knowledge_graph/checkpoint.py:20` |
| `_restore_checkpoint` | `(store: KGStore, checkpoint: dict)` | Restore a checkpoint saved by _save_checkpoint(). | `knowledge_graph/checkpoint.py:67` |
| `_delete_changed_file_nodes` | `(store: KGStore, changed_files: list[str])` | Soft-delete all nodes and hard-delete all edges related to changed files. | `knowledge_graph/checkpoint.py:107` |
| `kg_ci_append` | `(store: KGStore, build_id: str, changed_files: Optional[list[str]], meta: Optional[dict])` | CI append hook: record snapshot + optionally link changed files. | `knowledge_graph/ci_hook.py:33` |
| `_get_project_root` | `()` | Auto-detect project root from git root or OSH_HOME. | `knowledge_graph/ci_hook.py:162` |
| `_parse_changed_files` | `(raw: str)` | Parse comma-separated changed files into a list, stripping whitespace. | `knowledge_graph/ci_hook.py:180` |
| `_filter_project_files` | `(files: list[str])` | Keep only files inside src/yuleosh/ or tests/ with .py extension. | `knowledge_graph/ci_hook.py:187` |
| `main` | `()` | CLI entry point for kg CI hook. | `knowledge_graph/ci_hook.py:198` |
| `_is_git_repo` | `(project_dir: Path)` | True when the project dir is a git checkout. | `knowledge_graph/cm_checks.py:69` |
| `_git` | `(project_dir: Path, args: list[str])` | Run a git command in the project dir (never hangs). | `knowledge_graph/cm_checks.py:74` |
| `check_workspace_clean` | `(project_dir: Path)` | CM 检查 1: 工作区清洁 — 未提交改动 / 未跟踪文件。 | `knowledge_graph/cm_checks.py:87` |
| `check_commit_convention` | `(project_dir: Path)` | CM 检查 2: 提交规范 — HEAD commit message type(scope): subject。 | `knowledge_graph/cm_checks.py:134` |
| `check_generated_artifacts_leak` | `(project_dir: Path)` | CM 检查 3: 生成产物泄漏 — git ls-files 匹配产物路径 → 阻断 + 清单。 | `knowledge_graph/cm_checks.py:191` |
| `check_deploy_guardrail` | `(project_dir: Path | str, session_dir: Path | str | None, deploy_step_executed: bool)` | CM 检查 4: 部署护栏状态确认。 | `knowledge_graph/cm_checks.py:227` |
| `run_cm_checks` | `(project_dir: str | Path, session_dir: str | Path | None, deploy_step_executed: bool)` | Run all 4 CM checks and aggregate. | `knowledge_graph/cm_checks.py:317` |
| `_parse_file_ast` | `(filepath: Path)` | Parse a Python file with AST and collect functions/classes. | `knowledge_graph/code_scanner.py:118` |
| `scan_directory` | `(store: KGStore, project_base: str)` | Scan Python source and test directories using AST parsing. | `knowledge_graph/code_scanner.py:139` |
| `_create_function_node` | `(store: KGStore, file_nid: int, entry: dict, rel_path: str, func_type: str, extra_kind: Optional[str])` | Create a function/class node and its 'contains' edge. | `knowledge_graph/code_scanner.py:343` |
| `_regex_fallback` | `(store, file_nid, rel_path, py_file, func_type, edge_count_func)` | Fallback regex-based function extraction when AST parsing fails. | `knowledge_graph/code_scanner.py:404` |
| `_extract_c_functions` | `(content: str)` | Extract C function definitions from source text using simple regex. | `knowledge_graph/code_scanner.py:435` |
| `scan_single_file` | `(store: KGStore, project_base: str, rel_path: str)` | Scan a single Python file and create/update its nodes. | `knowledge_graph/code_scanner.py:477` |
| `_read_coverage_sqlite` | `(coverage_path: str)` | Read a .coverage SQLite database and return {file_path: set(line_numbers)}. | `knowledge_graph/coverage_importer.py:38` |
| `_read_coverage_json` | `(json_path: str)` | Read a .coverage.json file and return {file_path: set(line_numbers)}. | `knowledge_graph/coverage_importer.py:110` |
| `import_coverage` | `(store: KGStore, coverage_path: str, project_base: Optional[str])` | Import coverage data and create verifies edges between test and code functions. | `knowledge_graph/coverage_importer.py:158` |
| `_infer_test_to_source_mapping` | `(store: KGStore, project_base: str)` | Build a mapping from test file paths to source file paths. | `knowledge_graph/coverage_importer.py:313` |
| `_find_relevant_test_functions` | `(store: KGStore, source_path: str, test_to_source_map: dict[str, str], tests_by_file: dict[str, list[Node]])` | Find test_function nodes that are relevant to a given source file. | `knowledge_graph/coverage_importer.py:381` |
| `import_coverage_from_default` | `(store: KGStore, project_base: Optional[str])` | Import coverage data from the default .coverage file location. | `knowledge_graph/coverage_importer.py:479` |
| `_infer_layer_from_filename` | `(file_path: str)` | Infer ASPICE test layer from a test file path. | `knowledge_graph/edge_builder.py:46` |
| `_annotate_covers_layer` | `(store: KGStore)` | Annotate all 'covers' edges with layer information inferred from | `knowledge_graph/edge_builder.py:62` |
| `_merge_test_functions` | `(store: KGStore)` | Merge duplicate test_function nodes after bootstrap. | `knowledge_graph/edge_builder.py:148` |
| `_build_implements_edges` | `(store: KGStore)` | 从 covers + verifies 推导 implements 边。 | `knowledge_graph/edge_builder.py:280` |
| `_build_validates_edges` | `(store: KGStore)` | 从 integration/sil/hil 层级的 covers 边创建 validates 边（P0-5）。 | `knowledge_graph/edge_builder.py:413` |
| `_fallback_code_file_matching` | `(store: KGStore, project_base: Path)` | 对孤立 code_file 节点进行启发式需求匹配（P0-4b）。 | `knowledge_graph/edge_builder.py:467` |
| `_match_code_files_to_requirements` | `(store: KGStore, project_base: Path)` | Alias for _fallback_code_file_matching (P0-4b). | `knowledge_graph/edge_builder.py:560` |
| `_fix_orphan_test_files` | `(store: KGStore)` | 对孤立测试文件自动创建 covers 边（P0-4e）。 | `knowledge_graph/edge_builder.py:570` |
| `emit_on_upsert_node` | `(store: 'KGStore', original_upsert)` | Wrap store.upsert_node to emit events. | `knowledge_graph/events.py:219` |
| `emit_on_upsert_edge` | `(store: 'KGStore', original_upsert)` | Wrap store.upsert_edge to emit events. | `knowledge_graph/events.py:254` |
| `emit_on_delete_node` | `(original_delete)` | Wrap store.delete_node to emit events. | `knowledge_graph/events.py:282` |
| `emit_on_delete_edge` | `(original_delete)` | Wrap store.delete_edge to emit events. | `knowledge_graph/events.py:303` |
| `_emit_on_create_snapshot` | `(original_create)` | Wrap store.create_snapshot to emit events. | `knowledge_graph/events.py:325` |
| `instrument_store` | `(store: 'KGStore')` | Apply event-emitting wrappers to a KGStore instance. | `knowledge_graph/events.py:346` |
| `_get_git_root` | `()` | 返回 git 仓库根目录，如果不在 git 仓库中则返回 None。 | `knowledge_graph/git_hook_check.py:93` |
| `_get_hooks_dir` | `()` | 返回 .git/hooks 目录，如果不在 git 仓库中则返回 None。 | `knowledge_graph/git_hook_check.py:107` |
| `_get_hook_path` | `()` | 返回 post-commit hook 路径，如果不在 git 仓库中则返回 None。 | `knowledge_graph/git_hook_check.py:118` |
| `_get_installed_version` | `(hook_path: Path)` | 读取已安装 hook 的版本号。 | `knowledge_graph/git_hook_check.py:126` |
| `check_installed` | `()` | 检查 KG post-commit hook 是否已安装且可执行。 | `knowledge_graph/git_hook_check.py:140` |
| `is_version_current` | `()` | 检查已安装 hook 版本是否最新。 | `knowledge_graph/git_hook_check.py:152` |
| `get_status` | `()` | 返回 hook 安装状态的完整信息。 | `knowledge_graph/git_hook_check.py:167` |
| `install_hook` | `(force: bool)` | 安装或更新 KG post-commit hook。 | `knowledge_graph/git_hook_check.py:201` |
| `uninstall_hook` | `()` | 卸载 KG post-commit hook。 | `knowledge_graph/git_hook_check.py:245` |
| `_describe_changed_files` | `(files: list[str])` | 过滤出 src/yuleosh/ 和 tests/ 下的 Python 文件。 | `knowledge_graph/git_hook_check.py:273` |
| `get_changed_files_from_commit` | `()` | 获取最近一次 commit 的变更文件列表。 | `knowledge_graph/git_hook_check.py:284` |
| `main` | `()` | — | `knowledge_graph/git_hook_check.py:304` |
| `incremental_bootstrap` | `(store: KGStore, project_dir: str, changed_files: Optional[list[str]], create_snapshot: bool, build_id: Optional[str], snapshot_meta: Optional[dict])` | Incremental knowledge graph build from changed files. | `knowledge_graph/incremental.py:41` |
| `_get_store` | `(project_dir: str, kwargs: Optional[dict])` | Get a KG store, auto-selecting backend based on YULEOSH_DB_URL. | `knowledge_graph/kg_cli.py:39` |
| `_ensure_log_dir` | `(project_dir: str)` | Create the knowledge-graph log directory if it doesn't exist. | `knowledge_graph/kg_cli.py:48` |
| `_write_log` | `(project_dir: str, filename: str, content: str)` | Write content to a knowledge-graph log file. | `knowledge_graph/kg_cli.py:55` |
| `_get_changed_files_from_git` | `(base_ref: str)` | Get changed files from git diff against a base ref. | `knowledge_graph/kg_cli.py:63` |
| `cmd_build` | `(args)` | yuleosh kg build — Incremental knowledge graph build. | `knowledge_graph/kg_cli.py:86` |
| `cmd_bootstrap` | `(args)` | yuleosh kg bootstrap — Full bootstrap from traceability data. | `knowledge_graph/kg_cli.py:246` |
| `cmd_snapshot_list` | `(args)` | yuleosh kg snapshot list — List graph snapshots. | `knowledge_graph/kg_cli.py:269` |
| `cmd_snapshot_diff` | `(args)` | yuleosh kg snapshot diff A B — Compare two snapshots. | `knowledge_graph/kg_cli.py:296` |
| `cmd_query_impact` | `(args)` | yuleosh kg query impact <file_path> — Analyze change impact. | `knowledge_graph/kg_cli.py:348` |
| `cmd_stats` | `(args)` | yuleosh kg stats — Show graph statistics. | `knowledge_graph/kg_cli.py:425` |
| `cmd_report` | `(args)` | yuleosh kg report — Generate RTM and metrics reports. | `knowledge_graph/kg_cli.py:469` |
| `_cmd_report_rtm` | `(store, project_dir, args)` | Generate RTM report. | `knowledge_graph/kg_cli.py:487` |
| `_cmd_report_metrics` | `(store, project_dir, args)` | Generate metrics report. | `knowledge_graph/kg_cli.py:516` |
| `cmd_events` | `(args)` | yuleosh kg events — Event bus operations. | `knowledge_graph/kg_cli.py:553` |
| `_cmd_events_listen` | `(args, event_bus)` | Listen for KG events in real-time. | `knowledge_graph/kg_cli.py:571` |
| `_cmd_events_history` | `(args, event_bus)` | Show recent event history. | `knowledge_graph/kg_cli.py:620` |
| `_node_matches_scope` | `(node: dict, scope_files: list[str])` | True if a node's entity_id ties it to one of the scope files. | `knowledge_graph/merge_gate.py:91` |
| `_filter_nodes_by_scope` | `(nodes: list[dict], scope_files: list[str] | None)` | Narrow nodes to the session-artifact subgraph. | `knowledge_graph/merge_gate.py:115` |
| `_filter_edges_by_scope` | `(edges: list[dict], scoped_ids: set)` | Keep edges touching any of the scoped node ids. | `knowledge_graph/merge_gate.py:125` |
| `cmd_check_merge` | `(args)` | CLI implementation for ``yuleosh kg check-merge``. | `knowledge_graph/merge_gate.py:826` |
| `step_merge_gate` | `(session)` | Pipeline step handler for the KG Merge Gate (KG-42). | `knowledge_graph/merge_gate.py:925` |
| `_run_cm_gate_checks` | `(project_dir: str, session)` | Run the 4 deterministic CM checks (non-LLM). | `knowledge_graph/merge_gate.py:1090` |
| `_deploy_step_executed_in_session` | `(session)` | codegen-deploy (step 9) 是否在本 session 执行过 (completed)。 | `knowledge_graph/merge_gate.py:1107` |
| `_merge_cm_into_report` | `(report_path: str, cm_result: dict)` | Append the CM check results into the existing merge-gate report JSON. | `knowledge_graph/merge_gate.py:1116` |
| `_mock_store` | `()` | Create a minimal mock store for testing purposes. | `knowledge_graph/merge_gate.py:1139` |
| `c_entity_confidence` | `(entity_kind: str, has_error: bool, macro_heavy: bool)` | B1-10 置信度初值规则（三级流转阈值，对齐 B3）。 | `knowledge_graph/models.py:59` |
| `trace_by_req_id` | `(store: KGStore, req_id: str, include_tests: bool, include_functions: bool, layer: Optional[str])` | Trace downstream from a requirement. | `knowledge_graph/queries.py:36` |
| `trace_by_file_path` | `(store: KGStore, file_path: str)` | Trace upstream from a file to find requirements. | `knowledge_graph/queries.py:99` |
| `trace_by_test_function` | `(store: KGStore, test_fqn: str)` | Trace upstream from a test function to find requirements. | `knowledge_graph/queries.py:131` |
| `impact_analysis` | `(store: KGStore, changed_files: list[str], layer: Optional[str])` | Analyze the impact of changes to one or more files. | `knowledge_graph/queries.py:170` |
| `list_uncovered_requirements` | `(store: KGStore)` | Find requirement nodes with no outgoing 'covers' edges. | `knowledge_graph/queries.py:317` |
| `list_orphan_code_files` | `(store: KGStore)` | Find active code files with no edges at all. | `knowledge_graph/queries.py:323` |
| `list_snapshots` | `(store: KGStore, limit: int)` | List recent snapshots. | `knowledge_graph/queries.py:329` |
| `get_graph_stats` | `(store: KGStore)` | Return overall graph statistics. | `knowledge_graph/queries.py:334` |
| `get_aspice_coverage` | `(store: KGStore)` | Return an ASPICE coverage summary broken down by test layer. | `knowledge_graph/queries.py:343` |
| `get_confirmation_trace` | `(store: KGStore)` | 返回所有 validates 边的完整确认追溯链路（P0-5 SWE.5 确认）。 | `knowledge_graph/queries.py:420` |
| `trace_by_req_id` | `(store: KGStorePG, req_id: str, include_tests: bool, include_functions: bool, layer: Optional[str])` | Trace downstream from a requirement via RECURSIVE CTE. | `knowledge_graph/queries_pg.py:29` |
| `trace_by_file_path` | `(store: KGStorePG, file_path: str)` | Trace upstream from a file: find linked requirements. | `knowledge_graph/queries_pg.py:100` |
| `trace_by_test_function` | `(store: KGStorePG, test_fqn: str)` | Trace from a test function: find file and covered requirements. | `knowledge_graph/queries_pg.py:129` |
| `impact_analysis` | `(store: KGStorePG, changed_files: list[str], layer: Optional[str])` | Analyze impact of changed files. | `knowledge_graph/queries_pg.py:166` |
| `list_uncovered_requirements` | `(store: KGStorePG)` | Find requirement nodes with no outgoing 'covers' edges. | `knowledge_graph/queries_pg.py:201` |
| `list_orphan_code_files` | `(store: KGStorePG)` | Find active code files with no edges at all. | `knowledge_graph/queries_pg.py:207` |
| `list_snapshots` | `(store: KGStorePG, limit: int)` | List recent snapshots. | `knowledge_graph/queries_pg.py:213` |
| `get_graph_stats` | `(store: KGStorePG)` | Return overall graph statistics. | `knowledge_graph/queries_pg.py:218` |
| `get_aspice_coverage` | `(store: KGStorePG)` | Return an ASPICE coverage summary broken down by test layer. | `knowledge_graph/queries_pg.py:227` |
| `get_confirmation_trace` | `(store)` | 返回所有 validates 边的完整确认追溯链路（P0-5 SWE.5 确认）。 | `knowledge_graph/queries_pg.py:290` |
| `_build_rtm_rows` | `(store: KGStore, layer: Optional[str])` | Build RTM rows from the KG store. | `knowledge_graph/reporter.py:55` |
| `generate_rtm_markdown` | `(store: KGStore, layer: Optional[str], title: Optional[str])` | Generate a Markdown traceability matrix from the KG. | `knowledge_graph/reporter.py:155` |
| `generate_rtm_html` | `(store: KGStore, layer: Optional[str], title: Optional[str])` | Generate an HTML traceability matrix from the KG. | `knowledge_graph/reporter.py:270` |
| `generate_rtm_csv` | `(store: KGStore, layer: Optional[str])` | Generate a CSV traceability matrix from the KG. | `knowledge_graph/reporter.py:398` |
| `generate_rtm` | `(store: KGStore, fmt: str, layer: Optional[str], title: Optional[str])` | Generate traceability matrix in the specified format. | `knowledge_graph/reporter.py:428` |
| `generate_metrics` | `(store: KGStore, trend_snapshots: int, as_text: bool)` | Generate comprehensive metrics from the KG. | `knowledge_graph/reporter.py:455` |
| `format_metrics_text` | `(metrics: dict)` | Format metrics dict as human-readable text report. | `knowledge_graph/reporter.py:585` |
| `extract_shall_statements` | `(md_text: str)` | Extract SHALL statements from spec markdown text. | `knowledge_graph/spec_diff.py:39` |
| `extract_shall_ids` | `(md_text: str)` | Quick extraction: return just the ordered list of SHALL IDs from text. | `knowledge_graph/spec_diff.py:120` |
| `_normalize_statement` | `(text: str)` | Normalize a statement for diff comparison. | `knowledge_graph/spec_diff.py:126` |
| `analyze_spec_changes` | `(old_text: str, new_text: str)` | Analyze spec changes between old and new versions. | `knowledge_graph/spec_diff.py:137` |
| `analyze_spec_file_changes` | `(old_path: str, new_path: str)` | Analyze spec changes by comparing two spec files on disk. | `knowledge_graph/spec_diff.py:213` |
| `detect_spec_files_in_changes` | `(changed_files: list[str])` | Filter a list of changed files to only include *.spec.md files. | `knowledge_graph/spec_diff.py:237` |
| `apply_spec_changes_to_store` | `(store, changes: dict)` | Apply detected spec changes to the knowledge graph store. | `knowledge_graph/spec_diff.py:249` |
| `get_spec_changes_from_git` | `(git_base: str, spec_file: str)` | Get spec changes by git diff of a spec file. | `knowledge_graph/spec_diff.py:324` |
| `normalize_test_result` | `(result: dict)` | Normalize a single test result to a canonical format. | `knowledge_graph/verify_delta.py:35` |
| `parse_pytest_json_report` | `(json_path: str)` | Parse a pytest JSON report file. | `knowledge_graph/verify_delta.py:92` |
| `parse_yuleosh_ci_results` | `(project_dir: str)` | Parse yuleOSH CI test result files. | `knowledge_graph/verify_delta.py:135` |
| `parse_junit_xml` | `(xml_path: str)` | Parse JUnit XML format (without external dependency). | `knowledge_graph/verify_delta.py:165` |
| `get_code_function_from_test_func` | `(store, tfn_node)` | Resolve the code_function(s) verified by a test_function. | `knowledge_graph/verify_delta.py:243` |
| `get_requirements_from_test_func` | `(store, tfn_node)` | Resolve requirement(s) covered by a test_function. | `knowledge_graph/verify_delta.py:257` |
| `apply_single_test_result` | `(store, test_result: dict)` | Apply a single test result to the knowledge graph. | `knowledge_graph/verify_delta.py:282` |
| `apply_test_results` | `(store, test_results: list[dict], timestamp: Optional[str])` | Apply a batch of test results to the knowledge graph. | `knowledge_graph/verify_delta.py:380` |
| `load_test_results` | `(project_dir: str, json_path: Optional[str], junit_path: Optional[str])` | Load test results from available sources. | `knowledge_graph/verify_delta.py:448` |

### 3.2 公共类

| 类 | 基类 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `CFileScan` | `()` | 单文件 C 扫描结果（ScanResult 结构的逐项）。 | `knowledge_graph/c_code_scanner.py:48` |
| `CScanResult` | `()` | 一次目录扫描的聚合结果（对标 code_scanner.scan_directory 返回）。 | `knowledge_graph/c_code_scanner.py:76` |
| `CFunctionCollector` | `()` | 对标 code_scanner.FunctionCollector：收集单个 C 文件的 | `knowledge_graph/c_code_scanner.py:124` |
| `ErrorNode` | `()` | 单个错误/缺失节点的位置信息。 | `knowledge_graph/c_parser.py:52` |
| `CParseResult` | `()` | 一次解析的结果（容错，永不抛异常）。 | `knowledge_graph/c_parser.py:62` |
| `FunctionParam` | `()` | 单个函数参数（K&R 老式声明时 type 可能为空，类型在外部声明中解析）。 | `knowledge_graph/c_parser.py:246` |
| `FunctionInfo` | `()` | 一个函数（定义或原型）的提取结果。 | `knowledge_graph/c_parser.py:254` |
| `CallEdge` | `()` | 一条调用边（容错；永不抛异常）。 | `knowledge_graph/c_parser.py:520` |
| `CallGraph` | `()` | 一个 C 文件的调用图（容错；解析失败返回空图 + parse_ok=False）。 | `knowledge_graph/c_parser.py:540` |
| `GlobalVar` | `()` | 一个全局/静态变量（容错）。 | `knowledge_graph/c_parser.py:788` |
| `MacroInfo` | `()` | 一个宏定义（容错提取）。 | `knowledge_graph/c_parser.py:1204` |
| `ConditionalInfo` | `()` | 条件编译的一个分支（``#ifdef``/``#if``/... 全解析的产出之一）。 | `knowledge_graph/c_parser.py:1238` |
| `FunctionCollector` | `(ast.NodeVisitor)` | Collects all function/class definitions from a Python AST. | `knowledge_graph/code_scanner.py:47` |
| `KGDataclass` | `()` | Minimal event dataclass replacement — avoids dataclass import overhead. | `knowledge_graph/events.py:35` |
| `EventBus` | `()` | Thread-safe publish/subscribe event bus for KG operations. | `knowledge_graph/events.py:60` |
| `MergeGateConfig` | `()` | Configuration for the KG merge gate. | `knowledge_graph/merge_gate.py:46` |
| `GraphConsistencyChecker` | `()` | Performs graph consistency verification on the knowledge graph. | `knowledge_graph/merge_gate.py:135` |
| `ConfidenceChecker` | `()` | Checks traceability confidence in the knowledge graph. | `knowledge_graph/merge_gate.py:438` |
| `MergeGate` | `()` | Merge Gate orchestrator — coordinates all checks and produces verdict. | `knowledge_graph/merge_gate.py:591` |
| `Node` | `()` | A node in the knowledge graph. | `knowledge_graph/models.py:82` |
| `Edge` | `()` | An edge (relationship) in the knowledge graph. | `knowledge_graph/models.py:109` |
| `Snapshot` | `()` | A graph snapshot from a CI build. | `knowledge_graph/models.py:146` |
| `TraceResult` | `()` | Result of a trace query, with subgraph nodes and edges. | `knowledge_graph/models.py:167` |
| `NodePG` | `()` | A node in the knowledge graph. UUID primary key. | `knowledge_graph/models_pg.py:46` |
| `EdgePG` | `()` | An edge (relationship) in the knowledge graph. UUID foreign keys. | `knowledge_graph/models_pg.py:71` |
| `SnapshotPG` | `()` | A graph snapshot from a CI build. | `knowledge_graph/models_pg.py:108` |
| `TraceResultPG` | `()` | Result of a trace query, with subgraph nodes and edges. | `knowledge_graph/models_pg.py:129` |
| `KGStore` | `()` | SQLite-backed knowledge graph store. Thread-safe singleton per db_path. | `knowledge_graph/store.py:36` |
| `KGStorePG` | `()` | PostgreSQL-backed knowledge graph store. Thread-safe singleton per DSN. | `knowledge_graph/store_pg.py:49` |

### 3.3 类关键公共方法(节选)

| 方法 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `CFileScan.as_dict` | `(self)` | — | `knowledge_graph/c_code_scanner.py:61` |
| `CScanResult.code_files` | `(self)` | — | `knowledge_graph/c_code_scanner.py:82` |
| `CScanResult.test_files` | `(self)` | — | `knowledge_graph/c_code_scanner.py:86` |
| `CScanResult.function_count` | `(self)` | — | `knowledge_graph/c_code_scanner.py:90` |
| `CScanResult.global_count` | `(self)` | — | `knowledge_graph/c_code_scanner.py:94` |
| `CScanResult.isr_count` | `(self)` | — | `knowledge_graph/c_code_scanner.py:98` |
| `CScanResult.macro_count` | `(self)` | — | `knowledge_graph/c_code_scanner.py:102` |
| `CScanResult.call_edge_count` | `(self)` | — | `knowledge_graph/c_code_scanner.py:106` |
| `CScanResult.as_dict` | `(self)` | — | `knowledge_graph/c_code_scanner.py:109` |
| `CFunctionCollector.__init__` | `(self, rel_path: str, source_bytes: bytes)` | — | `knowledge_graph/c_code_scanner.py:132` |
| `CParseResult.root_node` | `(self)` | 语法树根节点（解析失败时为 None）。 | `knowledge_graph/c_parser.py:77` |
| `CParseResult.has_syntax_error` | `(self)` | 是否存在任何语法错误/缺失节点。 | `knowledge_graph/c_parser.py:82` |
| `CParseResult.error_rate` | `(self)` | 错误节点占比（0.0~1.0）；无节点时返回 0.0。 | `knowledge_graph/c_parser.py:87` |
| `CParseResult.as_dict` | `(self)` | 可序列化摘要（供日志/门禁使用）。 | `knowledge_graph/c_parser.py:93` |
| `FunctionInfo.as_dict` | `(self)` | 可序列化摘要（供下游调用图 / 知识图谱入库）。 | `knowledge_graph/c_parser.py:268` |
| `CallEdge.as_dict` | `(self)` | — | `knowledge_graph/c_parser.py:529` |
| `CallGraph.call_count` | `(self)` | — | `knowledge_graph/c_parser.py:550` |
| `CallGraph.potential_count` | `(self)` | — | `knowledge_graph/c_parser.py:554` |
| `CallGraph.as_dict` | `(self)` | — | `knowledge_graph/c_parser.py:557` |
| `GlobalVar.as_dict` | `(self)` | — | `knowledge_graph/c_parser.py:801` |
| `MacroInfo.as_dict` | `(self)` | — | `knowledge_graph/c_parser.py:1223` |
| `ConditionalInfo.as_dict` | `(self)` | — | `knowledge_graph/c_parser.py:1261` |
| `FunctionCollector.__init__` | `(self)` | — | `knowledge_graph/code_scanner.py:61` |
| `FunctionCollector.visit_FunctionDef` | `(self, node: ast.FunctionDef)` | Record a module-level function definition. | `knowledge_graph/code_scanner.py:66` |
| `FunctionCollector.visit_AsyncFunctionDef` | `(self, node: ast.AsyncFunctionDef)` | Record a module-level async function definition. | `knowledge_graph/code_scanner.py:73` |
| `FunctionCollector.visit_ClassDef` | `(self, node: ast.ClassDef)` | Record a class and its methods (without double-counting). | `knowledge_graph/code_scanner.py:79` |
| `KGDataclass.__init__` | `(self, event_type: str, source: str, data: Optional[dict])` | — | `knowledge_graph/events.py:40` |
| `KGDataclass.to_dict` | `(self)` | — | `knowledge_graph/events.py:47` |
| `EventBus.__init__` | `(self)` | — | `knowledge_graph/events.py:70` |
| `EventBus.on` | `(self, event_type: str, callback: Callable[[KGDataclass], Any])` | Subscribe to an event type. | `knowledge_graph/events.py:79` |
| `EventBus.once` | `(self, event_type: str, callback: Callable[[KGDataclass], Any])` | Subscribe to an event type for one invocation only. | `knowledge_graph/events.py:95` |
| `EventBus.off` | `(self, event_type: str, callback: Optional[Callable])` | Unsubscribe from an event type. | `knowledge_graph/events.py:109` |
| `EventBus.clear` | `(self)` | Remove all subscriptions. | `knowledge_graph/events.py:129` |
| `EventBus.emit` | `(self, event_type: str, source: str, data: Optional[dict])` | Emit an event. | `knowledge_graph/events.py:136` |
| `EventBus.history` | `(self, event_type: Optional[str], limit: int)` | Return recent event history, optionally filtered by type. | `knowledge_graph/events.py:187` |
| `EventBus.clear_history` | `(self)` | Clear the event history. | `knowledge_graph/events.py:205` |
| `MergeGateConfig.from_dict` | `(cls, d: dict)` | Create config from dict (e.g. from YAML config). | `knowledge_graph/merge_gate.py:79` |
| `GraphConsistencyChecker.__init__` | `(self, store, config: MergeGateConfig, scope_files: list[str] | None)` | — | `knowledge_graph/merge_gate.py:159` |
| `GraphConsistencyChecker.check_all` | `(self)` | Run all consistency checks and return results. | `knowledge_graph/merge_gate.py:195` |
| `ConfidenceChecker.__init__` | `(self, store, config: MergeGateConfig, scope_files: list[str] | None)` | — | `knowledge_graph/merge_gate.py:447` |
| `ConfidenceChecker.check_all` | `(self)` | Run confidence checks and return results. | `knowledge_graph/merge_gate.py:469` |
| `MergeGate.__init__` | `(self, store, project_dir: str, config: Optional[MergeGateConfig])` | — | `knowledge_graph/merge_gate.py:603` |
| `MergeGate.run` | `(self, changed_files: Optional[list[str]], base_ref: Optional[str])` | Execute the merge gate checks. | `knowledge_graph/merge_gate.py:614` |
| `Node.to_dict` | `(self)` | — | `knowledge_graph/models.py:94` |
| `Edge.to_dict` | `(self)` | — | `knowledge_graph/models.py:130` |
| `Snapshot.to_dict` | `(self)` | — | `knowledge_graph/models.py:155` |
| `TraceResult.to_dict` | `(self)` | — | `knowledge_graph/models.py:173` |
| `NodePG.to_dict` | `(self)` | — | `knowledge_graph/models_pg.py:57` |
| `EdgePG.to_dict` | `(self)` | — | `knowledge_graph/models_pg.py:92` |
| `SnapshotPG.to_dict` | `(self)` | — | `knowledge_graph/models_pg.py:117` |
| `TraceResultPG.to_dict` | `(self)` | — | `knowledge_graph/models_pg.py:135` |
| `KGStore.reset` | `(cls)` | Clear all instances (for testing). Recreates new instances on next access. | `knowledge_graph/store.py:60` |
| `KGStore.upsert_node` | `(self, node: Node)` | Insert or update a node. Returns the rowid. | `knowledge_graph/store.py:130` |
| `KGStore.get_node` | `(self, entity_type: str, entity_id: str)` | Get a node by its type+id. | `knowledge_graph/store.py:163` |
| `KGStore.get_node_by_id` | `(self, node_id: int)` | Get a node by its internal ID. | `knowledge_graph/store.py:172` |
| `KGStore.list_nodes` | `(self, entity_type: Optional[str], active_only: bool)` | List nodes, optionally filtered by type. | `knowledge_graph/store.py:178` |
| `KGStore.delete_node` | `(self, entity_type: str, entity_id: str)` | Soft-delete a node. Returns True if affected. | `knowledge_graph/store.py:198` |
| `KGStore.upsert_edge` | `(self, edge: Edge)` | Insert or update an edge. Returns the rowid. | `knowledge_graph/store.py:212` |
| `KGStore.get_edge` | `(self, source_id: int, target_id: int, edge_type: str)` | Get an edge by its source, target, and type. | `knowledge_graph/store.py:249` |
| `KGStore.list_edges` | `(self, edge_type: Optional[str])` | List all edges, optionally filtered by type. | `knowledge_graph/store.py:258` |

## 4. 配置 / 环境变量

| 变量 | 用途 |
| --- | --- |
| `OSH_HOME` | _(见源码)_ |
| `YULEOSH_DB_URL` | _(见源码)_ |

## 5. 调用示例

> 以下示例提取自生产代码真实调用方（`grep yuleosh.knowledge_graph`，排除自身包），可直接对照源码 `文件:行` 查阅，非臆造。

### 真实调用方片段

```python
# src/yuleosh/pipeline/step_handlers/__init__.py:89
from yuleosh.knowledge_graph.merge_gate import step_merge_gate

# src/yuleosh/llm/anchoring.py:136
from yuleosh.knowledge_graph.store import KGStore

# src/yuleosh/evidence/oem_templates.py:702
>>> from yuleosh.knowledge_graph import get_store

# src/yuleosh/kb/hybrid_search.py:239
from yuleosh.knowledge_graph.store import KGStore

# src/yuleosh/ci/dashboard_writer.py:38
from yuleosh import knowledge_graph  # noqa: F401

# src/yuleosh/ci/kpi/kg_source.py:27
from yuleosh.knowledge_graph.store import KGStore

# src/yuleosh/plan/context.py:99
from yuleosh.knowledge_graph import get_store

# src/yuleosh/cli/onboard.py:256
from yuleosh.knowledge_graph import get_store

# src/yuleosh/cli/commands/reverse.py:27
from yuleosh.knowledge_graph.store import KGStore

# src/yuleosh/cli/commands/traceability.py:102
from yuleosh.knowledge_graph import get_store

# src/yuleosh/cli/main.py:947
from yuleosh.knowledge_graph.kg_cli import (

# src/yuleosh/compliance/compliance_checker.py:759
from yuleosh.knowledge_graph import get_store

# src/yuleosh/api/kg.py:18
log = logging.getLogger("yuleosh.knowledge_graph.api.kg")

# src/yuleosh/api/kg_impact.py:38
from yuleosh.knowledge_graph import get_store

```

> 共 14 个文件引用本子系统；完整调用图见 `docs/modules/knowledge_graph.md`（若存在）。

## 6. 偏差 / 备注

- 生产调用方:✅ 有 39 处生产引用(Grep `yuleosh.knowledge_graph` 排除自身包)。
- 符号表为 `ast` 机械提取,包含内部符号;公共 API 以 `__init__.py` 导出与模块文档为准。
- 签名中可能含类型注解;参数默认值与详细语义见源码 `文件:行`。

---
_本文档由脚本基于 `src/yuleosh/knowledge_graph/` 生成,供团队查阅;如需精修可据源码头补充示例与端点明细。_

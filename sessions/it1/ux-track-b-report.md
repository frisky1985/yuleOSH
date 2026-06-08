# yuleOSH UX Track B — Pipeline mock 检测 报告

## 日期
2026-06-08

## 任务总结

### B-1: LLM key 检测
- 在 `src/pipeline/run.py` 中添加了 `_check_llm_key()` 函数
- 在 `run_pipeline()` 入口处检查 `LLM_API_KEY` / `OPENAI_API_KEY` 环境变量
- 两个都未设置时打印友好提示并 `sys.exit(1)`
- 当 `llm_client` 参数被注入（测试场景）或 `mock=True` 时跳过 key 检测

### B-2: --mock 模式
- 在 `yuleosh_cli.py` 的 `cmd_pipeline_run()` 中支持 `mock: bool = False` 参数
- 在 CLI 的 pipeline run 命令处理中检测 `--mock` 参数
- 自动从 `sys.argv` 中过滤出 spec 文件路径和 `--mock` 标志

### B-3: 更新帮助信息
- 更新了 `yuleosh_cli.py` 顶级文档字符串中的 pipeline run 用法为 `yuleosh pipeline run [--mock] <spec>`
- 更新了 usage 错误信息

## 修改的文件

| 文件 | 变更 |
|---|---|
| `src/pipeline/run.py` | 添加 `_check_llm_key()`，修改 `run_pipeline()` 增加 `mock` 参数 |
| `yuleosh_cli.py` | `cmd_pipeline_run` 支持 `mock` 参数，CLI 层解析 `--mock`，更新 docstring |
| `tests/test_pipeline_engine.py` | 更新 `test_pipeline_fails_without_llm_key` 使用 `mock=True` |

## 验收结果

| 场景 | 结果 |
|---|---|
| 无 LLM key 运行 `yuleosh pipeline run docs/spec.md` | 打印友好提示并退出 code 1 ✅ |
| 加 `--mock` 时运行 | 跳过 key 检测，正常跑 mock pipeline ✅ |
| 有 key / 注入 llm_client 时运行 | 正常运行真实/测试 pipeline ✅ |
| 所有测试通过 | 534 passed ✅ |

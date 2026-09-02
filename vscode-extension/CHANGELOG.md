# Change Log

## [4.2.0] - 2026-09-03

### Changed
- **Version sync**: 扩展版本与 yuleOSH 平台发布版对齐（`0.1.0` → `4.2.0`），使整套客户端共享同一版本号。
- **Documentation**: 命令表补齐到当前已注册的 15 条；修正项目仓库链接大小写（`frisky1985/yuleosh` → `frisky1985/yuleOSH`）；明确 `backendUrl` 默认值 `http://localhost:8080`；license 与 `package.json` 对齐（Elastic-2.0）。

## [0.1.0] - 2026-07-27

### Added
- **Pipeline management**: Run yuleOSH pipeline from VS Code
- **MISRA checks**: Run `yuleosh misra` and see violations inline as diagnostics
- **CI pipeline**: Execute `yuleosh ci run` with output channel logging
- **Integrated Dashboard**: Open yuleOSH dashboard in VS Code
- **Evidence Report**: WebView panel showing evidence/KPI summary with export
- **Code Actions**: "查看 MISRA 规则详情" and "打开 MISRA 文档" from diagnostics
- **Pipeline Status Tree**: Stage-based view (pending/running/pass/fail) with click-to-view-log
- **Status Bar**: Shows yuleOSH status + MISRA violation count, click for quick command menu
- **Auto-save diagnostics**: Automatically refreshes MISRA violations when saving C/C++ files
- **30s auto-refresh**: Pipeline stage tree auto-refreshes every 30 seconds
- **Device flashing**: Flash firmware to target hardware (ESP32, STM32, etc.)
- **External Dashboard**: Open yuleOSH web dashboard in browser

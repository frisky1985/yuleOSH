# Change Log

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

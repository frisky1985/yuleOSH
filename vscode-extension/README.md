# yuleOSH - AI-Powered Embedded Development Pipeline

yuleOSH brings AI-driven embedded development workflows directly into VS Code. Automate code review, pipeline execution, and device flashing — all from your editor.

> **版本同步**：本扩展与 yuleOSH 平台统一版本（当前 `4.2.0`）。后端默认地址 `http://localhost:8080`，与 Web 端保持一致；桌面端（Electron 内嵌后端）使用 `18788` 内部端口，由桌面壳自行管理。

## Features

- **Run Pipeline** — Execute the yuleOSH pipeline on your current project
- **Run CI** — Execute `yuleosh ci run` with output channel logging
- **Check MISRA** — Run `yuleosh misra` and see violations inline as diagnostics
- **View Status** — Show the current pipeline status
- **Show / Open Dashboard** — Open the yuleOSH web dashboard (in-editor preview or external browser)
- **Flash Device** — Flash compiled firmware to your target hardware (ESP32, ESP8266, STM32, RP2040)
- **Evidence Report** — WebView panel showing evidence/KPI summary with export
- **Open Evidence Dashboard** — Jump to the web Evidence page in browser (single-file download & history collapse)
- **MISRA Diagnostics** — Inline diagnostics, code actions, hover, rule detail & docs
- **Pipeline Status Tree** — Stage-based view (pending/running/pass/fail) with click-to-view-log
- **Status Bar** — yuleOSH status + MISRA violation count, click for quick command menu
- **Auto-save diagnostics** — Automatically refreshes MISRA violations when saving C/C++ files
- **Quick Command Menu** — One-click access to all commands

## Commands

| Command | Title | Description |
|---------|-------|-------------|
| `yuleosh.runPipeline` | yuleOSH: Run Pipeline | Run the full pipeline on the current project |
| `yuleosh.checkMisra` | yuleOSH: Check MISRA | Run MISRA check via CLI and refresh diagnostics |
| `yuleosh.runCi` | yuleOSH: Run CI | Execute `yuleosh ci run` |
| `yuleosh.showDashboard` | yuleOSH: Show Dashboard | Show the integrated dashboard (in-editor or external) |
| `yuleosh.viewStatus` | yuleOSH: View Status | Show the current pipeline status |
| `yuleosh.openDashboard` | yuleOSH: Open Dashboard (External) | Open the yuleOSH web dashboard in browser |
| `yuleosh.flashDevice` | yuleOSH: Flash Device | Flash the project to target hardware |
| `yuleosh.viewEvidence` | yuleOSH: View Evidence Report | Open the Evidence & KPI WebView panel |
| `yuleosh.loadMisraDiagnostics` | yuleOSH: Load MISRA Diagnostics | Load MISRA diagnostics from report |
| `yuleosh.reloadMisraReport` | yuleOSH: Reload MISRA Report | Reload MISRA report and refresh counts |
| `yuleosh.showMisraProblems` | yuleOSH: Show MISRA Problems | Focus the Problems panel |
| `yuleosh.showMisraRuleDetail` | yuleOSH: Show MISRA Rule Detail | Show detail for a MISRA rule |
| `yuleosh.openMisraDoc` | yuleOSH: Open MISRA Documentation | Open the MISRA rule documentation |
| `yuleosh.quickCommand` | yuleOSH: Quick Command Menu | Open the quick command picker |
| `yuleosh.viewPipelineLog` | yuleOSH: View Pipeline Stage Log | Show a pipeline stage log in output channel |
| `yuleosh.openEvidenceDashboard` | yuleOSH: Open Evidence Dashboard (External) | Open the web Evidence page (`/dashboard/evidence`) in browser — single-file download & 10-row collapse live there |

## Sidebar Views

The yuleOSH activity bar panel provides:

- **Pipeline Status** — Current pipeline state (running/passed/failed) with last run timestamp
- **Recent Reviews** — Code review results per file (issues found/passed)
- **Quick Actions** — One-click buttons for common operations

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `yuleosh.backendUrl` | `http://localhost:8080` | yuleOSH backend server URL (used by the dashboard open commands) |
| `yuleosh.autoReview` | `true` | Automatically trigger code review on save |
| `yuleosh.defaultTarget` | `esp32` | Default flash target (esp32, esp8266, stm32, rp2040) |

## Requirements

- [yuleOSH CLI](https://github.com/frisky1985/yuleOSH) installed and available in `$PATH` (`pip install yuleosh`)
- VS Code 1.96+

## Development

```bash
# Install dependencies
npm install

# Compile TypeScript
npm run compile

# Package extension
npm run package
```

## License

Elastic-2.0

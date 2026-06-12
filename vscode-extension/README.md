# yuleOSH - AI-Powered Embedded Development Pipeline

yuleOSH brings AI-driven embedded development workflows directly into VS Code. Automate code review, pipeline execution, and device flashing — all from your editor.

## Features

- **Run Pipeline** — Execute the yuleOSH pipeline on your current project
- **View Status** — Check pipeline and review results at a glance
- **Open Dashboard** — Launch the yuleOSH web dashboard in your browser
- **Flash Device** — Flash compiled firmware to your target hardware (ESP32, ESP8266, STM32, RP2040)

## Commands

| Command | Title | Description |
|---------|-------|-------------|
| `yuleosh.runPipeline` | yuleOSH: Run Pipeline | Run the full pipeline on the current project |
| `yuleosh.viewStatus` | yuleOSH: View Status | Show the current pipeline status |
| `yuleosh.openDashboard` | yuleOSH: Open Dashboard | Open the yuleOSH web dashboard |
| `yuleosh.flashDevice` | yuleOSH: Flash Device | Flash the project to target hardware |

## Sidebar Views

The yuleOSH activity bar panel provides:

- **Pipeline Status** — Current pipeline state (running/passed/failed) with last run timestamp
- **Recent Reviews** — Code review results per file (issues found/passed)
- **Quick Actions** — One-click buttons for common operations

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `yuleosh.backendUrl` | `http://localhost:8080` | yuleOSH backend server URL |
| `yuleosh.autoReview` | `true` | Automatically trigger code review on save |
| `yuleosh.defaultTarget` | `esp32` | Default flash target (esp32, esp8266, stm32, rp2040) |

## Requirements

- [yuleOSH CLI](https://github.com/frisky1985/yuleosh) installed and available in `$PATH`
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

MIT

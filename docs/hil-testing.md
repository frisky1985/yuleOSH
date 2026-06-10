# yuleOSH — Hardware-in-the-Loop (HIL) Testing

> v0.7.0 — Mock → OpenOCD/JLink 真实连接

## Architecture

```
HilTestRunner
  ├── FlashRunner (flash.py)
  │   ├── OpenOCD (openocd)
  │   ├── JLink (JLinkExe)
  │   └── PyOCD (pyocd)
  │
  ├── SerialMonitor (serial_monitor.py)
  │   ├── Real Serial (/dev/ttyUSB0)
  │   └── PipeMock (StringIO)
  │
  └── Assertions
      ├── expect(text, timeout)
      ├── expect_all([texts], timeout)
      └── expect_regex(pattern, timeout)
```

## Flash Tool Support

| Tool | Command | Target | Status |
|:-----|:--------|:-------|:-------|
| OpenOCD | `openocd` | ARM Cortex-M (STM32, NXP, etc.) | ✅ Supported |
| JLink | `JLinkExe` | ARM/RISC-V (via SEGGER) | ✅ Supported |
| PyOCD | `pyocd` | ARM Cortex-M | ✅ Supported |

## Usage

### Mock Mode (CI / no hardware)

```python
from cross.hil_runner import HilTestRunner

runner = HilTestRunner(target="stm32f4")
result = runner.run(
    firmware="build/hello-arm.elf",
    expect_pattern="Test PASSED",
    timeout=30,
)
# Uses serial mock — no real hardware needed
```

### Real Hardware Mode

```bash
# Set up udev rules for USB debug probe
# /etc/udev/rules.d/99-debug-probe.rules
SUBSYSTEM=="usb", ATTR{idVendor}=="1366", MODE="0666"  # SEGGER
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", MODE="0666"  # ST-LINK

# Run HIL test with real hardware
yuleosh ci run 2.5 --hardware
```

### Target Configuration

```python
from cross.target_config import TargetConfig

config = TargetConfig(
    name="stm32f4",
    arch="arm",
    flash_tool="openocd",
    serial_port="/dev/ttyACM0",
    baud_rate=115200,
    reset_command="monitor reset halt",
)
```

## Prerequisites for Real Hardware

| Component | Install |
|:----------|:--------|
| OpenOCD | `brew install openocd` / `apt install openocd` |
| JLink | [SEGGER J-Link Software](https://www.segger.com/downloads/jlink/) |
| PyOCD | `pip install pyocd` |
| ARM GCC | `brew install arm-none-eabi-gcc` |

## CI Integration

Layer 2.5 (`make ci-layer25`):
- Mock mode: Runs HIL test with PipeSerialMonitor (no hardware)
- Real mode: `make ci-layer25 HARDWARE=1` — requires debug probe connected

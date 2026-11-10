# demo-project

> **ECU Template**: bcm
> **MCU**: S32K312 | **ASIL**: ASIL B
> **Generated**: 2026-11-10 23:30 by yuleOSH init

---

## Overview

demo-project is a Body Control Module (BCM) built on the yuleOSH platform
with S32K312 MCU and target ASIL ASIL B.

## Features

- **Door Control**: Lock/unlock, window lift, mirror control, child lock
- **Light Control**: Headlight, turn signal, interior lighting, DRL
- **Wiper Control**: Speed control, rain sensor integration, wash-wipe
- **Power Management**: SLEEP/RUN/STOP modes, KL15/KL30 monitoring
- **Safety**: MPU protection (ASIL B), E2E protection, watchdog supervision

## Prerequisites

- Python 3.10+
- yuleOSH CLI installed
- ARM GCC toolchain (for cross-compilation)

## Quick Start

```bash
# Validate the specification
yuleosh spec validate docs/spec.md

# Run Layer 1 CI (linting + unit tests)
yuleosh ci run 1

# Run Layer 2 CI (integration tests)
yuleosh ci run 2

# Run Layer 3 CI (full verification)
yuleosh ci run 3
```

## Project Structure

```
├── docs/
│   ├── project-context.md        # Project overview
│   ├── spec.md                   # Requirements specification
│   ├── safety-concept.md         # Safety concept (HARA)
│   └── safety-architecture.md    # Safety architecture (DFA/MPU/FMEDA)
├── src/
│   ├── app/
│   │   ├── Door_SWC.c            # Door control SWC
│   │   ├── Light_SWC.c           # Light control SWC
│   │   ├── Wiper_SWC.c           # Wiper control SWC
│   │   ├── Power_SWC.c           # Power management SWC
│   │   └── Door_SWC.h / ...
│   └── bsw/                      # BSW configuration stubs
├── tests/
│   └── unit/                     # Unit test skeletons
├── ci-config.yaml                # CI pipeline configuration
├── yuleosh.yaml                  # Project metadata
├── .gitignore
└── README.md
```

## BSW Modules (12)


- **Mcu**

- **Dio**

- **Port**

- **Gpt**

- **Can**

- **Lin**

- **Spi**

- **Icu**

- **Pwm**

- **Adc**

- **Fls**

- **Wdg**


## Safety

This project targets ASIL B. All safety-critical functions are
protected by E2E profiles, MPU partitioning, and watchdog supervision.

See [safety-concept.md](docs/safety-concept.md) for HARA results and
[safety-architecture.md](docs/safety-architecture.md) for DFA/FMEDA details.

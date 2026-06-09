# yuleOSH — Test Firmware Fixtures

This directory contains minimal bare-metal firmware used for yuleOSH
SIL (Software-in-the-Loop) testing with QEMU.

## Structure

```
fixtures/
├── README.md              ← You are here
├── hello-arm/             ← ARM Cortex-M3 test firmware source
│   ├── hello.c            ← Main routine (UART output + halt)
│   ├── startup.c          ← Vector table + reset handler
│   └── Makefile           ← Build script (arm-none-eabi-gcc)
└── prebuilt/              ← Git-tracked pre-compiled .elf files
    └── .gitkeep
```

## How to build the test firmware

**Prerequisites:** Install `gcc-arm-none-eabi`:

```bash
# Ubuntu / Debian
sudo apt install gcc-arm-none-eabi

# macOS
brew install --cask gcc-arm-embedded

# Arch Linux
sudo pacman -S arm-none-eabi-gcc
```

**Build:**

```bash
cd hello-arm
make
```

This produces `build/hello-arm.elf`.

**Install to prebuilt/ (for CI):**

```bash
make install-prebuilt
```

This copies the .elf into `fixtures/prebuilt/` so the CI SIL stage
can find and run it without recompiling.

## How SIL tests use this firmware

1. The CI pipeline (`ci/run.py`, L2 → run_sil_tests) scans
   `tests/fixtures/prebuilt/*.elf`.
2. For each .elf found, it creates a `TargetConfig` and runs
   `sil_test()` from `cross/sil_runner.py`.
3. The runner boots QEMU with the .elf as `-kernel`, captures serial
   output, and asserts the expected patterns:

   - `Hello from yuleOSH cross-compilation test!`
   - `Architecture: ARM`
   - `Test Complete`

4. Results are saved to `.osh/ci/sil-test-results.json`.

## Adding new fixtures

1. Create a new subdirectory (e.g. `hello-riscv/`).
2. Add `main.c` (or equivalent) + `startup.S` (if needed).
3. Write a `Makefile` matching the target architecture.
4. Update `ci/run.py` → `run_sil_tests()` to detect the new .elf
   and set appropriate `qemu_machine` / `qemu_cpu` values.

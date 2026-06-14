# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""
yuleOSH — Target board configuration loader.

Provides ``TargetConfig`` dataclass and ``load_target_config()`` to parse
YAML target descriptions used by QEMU SIL Runner and Flash tools.

Usage::

    cfg = load_target_config("stm32f4", base_dir=".yuleosh/targets")
    assert cfg.mcu == "cortex-m4"
    assert cfg.qemu_machine == "stm32vldiscovery"
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------


@dataclass
class TargetConfig:
    """Compiled target board configuration.

    Attributes
    ----------
    name : str
        Short identifier (e.g. ``"stm32f4"``).
    mcu : str
        MCU core (e.g. ``"cortex-m4"``).
    arch : str
        Architecture family — ``"arm"``, ``"riscv"``, etc.
    qemu_machine : str
        QEMU machine identifier (e.g. ``"stm32vldiscovery"``).
    qemu_cpu : str
        QEMU CPU identifier (e.g. ``"cortex-m3"``).
    qemu_serial : str
        Full ``-chardev`` / ``-serial`` argument string for QEMU.
    qemu_extra_args : list[str]
        Additional QEMU command-line flags.
    elf : str | None
        Path to the compiled .elf binary (may be ``None`` in config YAML,
        filled at runtime).
    default_timeout : int
        Default SIL test timeout in seconds (default **30**).
    flash_openocd : str | None
        OpenOCD config file (e.g. ``"interface/stlink-v2.cfg target/stm32f4x.cfg"``).
    flash_jlink : dict | None
        J-Link settings (device, interface, speed).
    flash_pyocd : dict | None
        pyOCD settings (target, frequency).
    """

    name: str
    mcu: str
    arch: str
    qemu_machine: str
    qemu_cpu: str
    qemu_serial: str
    qemu_extra_args: list[str] = field(default_factory=list)
    elf: str | None = None
    default_timeout: int = 30
    flash_openocd: str | None = None
    flash_jlink: dict | None = None
    flash_pyocd: dict | None = None

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def is_arm(self) -> bool:
        return self.arch == "arm"

    @property
    def is_riscv(self) -> bool:
        return self.arch == "riscv"

    def build_qemu_cmd(self) -> list[str]:
        """Build the canonical QEMU command-line list for this target.

        Returns
        -------
        list[str]
            Ready to pass to ``subprocess.Popen`` (system emulator binary,
            machine, cpu, serial, extra args, and kernel/ELF).

        Raises
        ------
        ValueError
            If ``elf`` has not been set.
        """
        if not self.elf:
            raise ValueError(
                f"Target '{self.name}' has no .elf set — "
                "assign TargetConfig.elf before calling build_qemu_cmd()"
            )

        qemu_bin = self._qemu_binary()
        cmd: list[str] = [
            qemu_bin,
            "-machine", self.qemu_machine,
            "-cpu", self.qemu_cpu,
            "-nographic",
            "-kernel", self.elf,
            "-semihosting",
        ]
        # Parse qemu_serial string into separate args
        cmd.extend(self._parse_qemu_serial_args())
        cmd.extend(self.qemu_extra_args)
        return cmd

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _qemu_binary(self) -> str:
        if self.arch == "arm":
            return "qemu-system-arm"
        if self.arch == "riscv":
            return "qemu-system-riscv64"
        if self.arch == "aarch64":
            return "qemu-system-aarch64"
        raise ValueError(f"Unknown arch '{self.arch}' — cannot determine QEMU binary")

    def _parse_qemu_serial_args(self) -> list[str]:
        """Split ``qemu_serial`` string respecting quoted sections."""
        tokens = []
        for token in self.qemu_serial.split():
            tokens.append(token)
        return tokens

    def __repr__(self) -> str:
        return (
            f"TargetConfig(name='{self.name}', mcu='{self.mcu}', "
            f"arch='{self.arch}', machine='{self.qemu_machine}', "
            f"elf={self.elf!r}, timeout={self.default_timeout})"
        )


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

# Default search paths for target YAML files
_DEFAULT_SEARCH_DIRS: list[str] = [
    ".yuleosh/targets",
    "targets",
    "configs/targets",
]


def discover_targets(base_dir: str | None = None) -> dict[str, str]:
    """Discover available target YAML files.

    Parameters
    ----------
    base_dir : str | None
        Project root directory. If ``None``, uses the current working
        directory.

    Returns
    -------
    dict[str, str]
        Mapping of target name → absolute YAML file path.
    """
    if base_dir is None:
        base_dir = os.getcwd()

    results: dict[str, str] = {}
    search_dirs = _DEFAULT_SEARCH_DIRS + [base_dir]

    for search_dir in search_dirs:
        target_path = Path(search_dir)
        if not target_path.is_absolute():
            target_path = Path(base_dir) / search_dir
        if not target_path.is_dir():
            continue
        for yml_file in sorted(target_path.glob("*.yaml")):
            try:
                name = yml_file.stem  # e.g. "stm32f4"
                if name not in results:
                    results[name] = str(yml_file.resolve())
            except OSError:
                continue
    return results


def load_target_config(name: str, base_dir: str | None = None) -> TargetConfig:
    """Load and parse a target board YAML configuration.

    Parameters
    ----------
    name : str
        Target name (matches the YAML file stem, e.g. ``"stm32f4"``).
    base_dir : str | None
        Project root directory for relative path resolution.

    Returns
    -------
    TargetConfig
        Compiled dataclass.

    Raises
    ------
    FileNotFoundError
        If no YAML file is found for the given name.
    ValueError
        If the YAML content is malformed or a required key is missing.
    """
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to load target configs. "
            "Install it: pip install pyyaml"
        )

    if base_dir is None:
        base_dir = os.getcwd()

    yml_path = _find_target_yml(name, base_dir)
    raw = _load_yaml(yml_path)

    return _parse_target(name, raw, base_dir)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_target_yml(name: str, base_dir: str) -> str:
    """Search for ``<name>.yaml`` in default dirs and base_dir."""
    search_dirs = _DEFAULT_SEARCH_DIRS + ["."]

    for rel_dir in search_dirs:
        path = _resolve(rel_dir, base_dir) / f"{name}.yaml"
        if path.is_file():
            return str(path.resolve())

    # Also scan all *.yaml files for a top-level target name match
    discovered = discover_targets(base_dir)
    if name in discovered:
        return discovered[name]

    raise FileNotFoundError(
        f"Target YAML not found for '{name}'. "
        f"Searched: {', '.join(str(_resolve(d, base_dir)) for d in search_dirs)}"
    )


def _resolve(rel: str, base_dir: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else Path(base_dir) / p


def _load_yaml(path: str) -> dict[str, Any]:
    """Parse a YAML file and return the raw dict."""
    with open(path, "r") as f:
        raw: dict[str, Any] = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(
            f"Target YAML at '{path}' must contain a top-level mapping, "
            f"got {type(raw).__name__}"
        )
    return raw


def _parse_target(name: str, raw: dict[str, Any], base_dir: str) -> TargetConfig:
    """Extract target config from raw YAML dict, supporting both flat and
    nested ``<target_name>:<target_name>:``` styles.

    Two YAML formats are accepted:

    **Flat (top-level keys only)**::

        mcu: cortex-m4
        arch: arm
        qemu:
          machine: lm3s6965evb
          ...

    **Nested (target name is a top-level key)**::

        stm32f4:
          mcu: cortex-m4
          ...
    """
    # If the YAML has a key matching our target name, use that subsection
    if name in raw and isinstance(raw[name], dict):
        raw = raw[name]

    # Extract top-level values
    mcu = _pop(raw, "mcu", name)
    arch = _pop(raw, "arch", name)

    # QEMU section
    qemu = raw.pop("qemu", {})
    if not isinstance(qemu, dict):
        raise ValueError(
            f"Target '{name}': 'qemu' must be a mapping, "
            f"got {type(qemu).__name__}"
        )

    qemu_machine = _pop(qemu, "machine", f"{name}.qemu")
    qemu_cpu = _pop(qemu, "cpu", f"{name}.qemu")
    qemu_serial = qemu.get("serial", "-serial stdio")

    extra_args_raw = qemu.get("extra_args", [])
    if isinstance(extra_args_raw, str):
        qemu_extra_args = extra_args_raw.split()
    elif isinstance(extra_args_raw, list):
        qemu_extra_args = [str(a) for a in extra_args_raw]
    else:
        qemu_extra_args = []

    # Flash section
    flash = raw.pop("flash", {})
    flash_openocd: str | None = None
    flash_jlink: dict | None = None
    flash_pyocd: dict | None = None

    if isinstance(flash, dict):
        if "openocd" in flash:
            ocd = flash["openocd"]
            flash_openocd = ocd.get("config") if isinstance(ocd, dict) else str(ocd)
        if "jlink" in flash:
            flash_jlink = flash["jlink"] if isinstance(flash["jlink"], dict) else {}
        if "pyocd" in flash:
            flash_pyocd = flash["pyocd"] if isinstance(flash["pyocd"], dict) else {}

    # Timeout
    timeout = int(raw.pop("default_timeout", 30) or 30)

    return TargetConfig(
        name=name,
        mcu=mcu,
        arch=arch,
        qemu_machine=qemu_machine,
        qemu_cpu=qemu_cpu,
        qemu_serial=qemu_serial,
        qemu_extra_args=qemu_extra_args,
        default_timeout=timeout,
        flash_openocd=flash_openocd,
        flash_jlink=flash_jlink,
        flash_pyocd=flash_pyocd,
    )


def _pop(d: dict[str, Any], key: str, context: str) -> str:
    """Pop a required string value from *d*, raising on missing/None."""
    val = d.pop(key, None)
    if val is None:
        raise ValueError(
            f"Target '{context}': missing required key '{key}'"
        )
    return str(val)

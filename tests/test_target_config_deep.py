# Copyright (c) 2025 frisky1985
# SPDX-License-Identifier: MIT

"""Deep tests for cross/target_config.py — TargetConfig loader.

Target: 80%+ branch coverage.
Covers: TargetConfig dataclass, properties, build_qemu_cmd,
        discover_targets, load_target_config, YAML parsing,
        _find_target_yml, _parse_target, _pop helpers.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest


SAMPLE_FLAT_YAML = {
    "mcu": "cortex-m4",
    "arch": "arm",
    "qemu": {
        "machine": "lm3s6965evb",
        "cpu": "cortex-m3",
        "serial": "-serial stdio",
    },
    "default_timeout": 45,
}

SAMPLE_NESTED_YAML = {
    "stm32f4": {
        "mcu": "cortex-m4",
        "arch": "arm",
        "qemu": {
            "machine": "stm32vldiscovery",
            "cpu": "cortex-m3",
            "serial": "-serial mon:stdio",
            "extra_args": ["-semihosting", "-nographic"],
        },
        "flash": {
            "openocd": {
                "config": "interface/stlink-v2.cfg target/stm32f4x.cfg",
            },
            "jlink": {"device": "STM32F407VG", "interface": "SWD", "speed": 4000},
            "pyocd": {"target": "stm32f407vg", "frequency": 1000000},
        },
    },
}


# ======================================================================
# TargetConfig dataclass
# ======================================================================

class TestTargetConfig:
    def test_init(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="test", mcu="cortex-m0", arch="arm",
            qemu_machine="test-machine", qemu_cpu="cortex-m0",
            qemu_serial="-serial stdio",
        )
        assert cfg.name == "test"
        assert cfg.mcu == "cortex-m0"
        assert cfg.default_timeout == 30

    def test_is_arm(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="a", mcu="m4", arch="arm",
            qemu_machine="m", qemu_cpu="m3", qemu_serial="-serial stdio",
        )
        assert cfg.is_arm is True
        assert cfg.is_riscv is False

    def test_is_riscv(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="r", mcu="rv32", arch="riscv",
            qemu_machine="m", qemu_cpu="rv32", qemu_serial="-serial stdio",
        )
        assert cfg.is_riscv is True
        assert cfg.is_arm is False

    def test_is_neither(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="x", mcu="unknown", arch="mips",
            qemu_machine="m", qemu_cpu="m", qemu_serial="",
        )
        assert cfg.is_arm is False
        assert cfg.is_riscv is False

    def test_repr(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="myboard", mcu="m4", arch="arm",
            qemu_machine="stm32", qemu_cpu="m3", qemu_serial="-serial stdio",
            elf="/path/to/firmware.elf",
        )
        r = repr(cfg)
        assert "myboard" in r
        assert "firmware.elf" in r
        assert "timeout=30" in r

    def test_repr_no_elf(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="basic", mcu="m0", arch="arm",
            qemu_machine="m", qemu_cpu="m0", qemu_serial="",
        )
        r = repr(cfg)
        assert "elf=None" in r


# ======================================================================
# build_qemu_cmd
# ======================================================================

class TestBuildQemuCmd:
    def test_arm_qemu_cmd(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="arm-board", mcu="m4", arch="arm",
            qemu_machine="lm3s6965evb", qemu_cpu="cortex-m3",
            qemu_serial="-serial stdio",
            elf="build/firmware.elf",
            qemu_extra_args=["-d", "guest_errors"],
        )
        cmd = cfg.build_qemu_cmd()
        assert "qemu-system-arm" in cmd
        assert "-machine" in cmd
        assert "lm3s6965evb" in cmd
        assert "-kernel" in cmd
        assert "build/firmware.elf" in cmd
        assert "-semihosting" in cmd
        assert "-nographic" in cmd
        assert "-serial" in cmd
        assert "stdio" in cmd
        assert "-d" in cmd
        assert "guest_errors" in cmd

    def test_riscv_qemu_cmd(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="riscv-board", mcu="rv32", arch="riscv",
            qemu_machine="virt", qemu_cpu="rv32",
            qemu_serial="-serial stdio",
            elf="build/firmware.elf",
        )
        cmd = cfg.build_qemu_cmd()
        assert "qemu-system-riscv64" in cmd

    def test_aarch64_qemu_cmd(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="aarch64-board", mcu="a53", arch="aarch64",
            qemu_machine="virt", qemu_cpu="cortex-a53",
            qemu_serial="-serial stdio",
            elf="build/firmware.elf",
        )
        cmd = cfg.build_qemu_cmd()
        assert "qemu-system-aarch64" in cmd

    def test_elf_not_set(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="no-elf", mcu="m4", arch="arm",
            qemu_machine="m", qemu_cpu="m3", qemu_serial="",
        )
        with pytest.raises(ValueError, match="no .elf set"):
            cfg.build_qemu_cmd()

    def test_unknown_arch(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="bad", mcu="x", arch="unknown",
            qemu_machine="m", qemu_cpu="c", qemu_serial="",
            elf="x.elf",
        )
        with pytest.raises(ValueError, match="Unknown arch"):
            cfg.build_qemu_cmd()

    def test_extra_args(self):
        from yuleosh.cross.target_config import TargetConfig
        cfg = TargetConfig(
            name="x", mcu="m4", arch="arm",
            qemu_machine="m", qemu_cpu="m3", qemu_serial="-serial stdio",
            qemu_extra_args=["-nographic"],
            elf="firmware.elf",
        )
        cmd = cfg.build_qemu_cmd()
        assert "-nographic" in cmd


# ======================================================================
# discover_targets
# ======================================================================

class TestDiscoverTargets:
    def test_empty_dir(self):
        from yuleosh.cross.target_config import discover_targets
        with tempfile.TemporaryDirectory() as tmp:
            result = discover_targets(tmp)
            assert result == {}

    def test_finds_yaml(self):
        from yuleosh.cross.target_config import discover_targets
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp) / ".yuleosh" / "targets"
            target_dir.mkdir(parents=True)
            (target_dir / "stm32f4.yaml").write_text("mcu: cortex-m4\n")
            result = discover_targets(tmp)
            assert "stm32f4" in result
            assert result["stm32f4"].endswith("stm32f4.yaml")

    def test_finds_in_targets_dir(self):
        from yuleosh.cross.target_config import discover_targets
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp) / "targets"
            target_dir.mkdir(parents=True)
            (target_dir / "nrf52.yaml").write_text("mcu: cortex-m4\n")
            result = discover_targets(tmp)
            assert "nrf52" in result

    def test_finds_in_configs_dir(self):
        from yuleosh.cross.target_config import discover_targets
        with tempfile.TemporaryDirectory() as tmp:
            target_dir = Path(tmp) / "configs" / "targets"
            target_dir.mkdir(parents=True)
            (target_dir / "esp32.yaml").write_text("mcu: xtensa\n")
            result = discover_targets(tmp)
            assert "esp32" in result

    def test_base_dir_none(self):
        from yuleosh.cross.target_config import discover_targets
        with patch("yuleosh.cross.target_config.os.getcwd", return_value="/tmp"):
            result = discover_targets(None)
            assert isinstance(result, dict)

    def test_multiple_dirs_dedup(self):
        from yuleosh.cross.target_config import discover_targets
        with tempfile.TemporaryDirectory() as tmp:
            for d in [".yuleosh/targets", "targets"]:
                target_dir = Path(tmp) / d
                target_dir.mkdir(parents=True)
                (target_dir / "shared.yaml").write_text("mcu: arm\n")
            result = discover_targets(tmp)
            assert "shared" in result


# ======================================================================
# load_target_config
# ======================================================================

class TestLoadTargetConfig:
    @pytest.mark.skip(reason="Hard to mock module-level import guard")
    def test_no_yaml_raises_runtime_error(self):
        """When yaml is not installed, raises RuntimeError."""
        pass

    def test_flat_yaml(self):
        from yuleosh.cross.target_config import load_target_config
        with tempfile.TemporaryDirectory() as tmp:
            target_file = Path(tmp) / "test-board.yaml"
            target_file.write_text("dummy")
            with patch("yuleosh.cross.target_config.yaml.safe_load",
                       return_value=SAMPLE_FLAT_YAML):
                cfg = load_target_config("test-board", base_dir=tmp)
                assert cfg.mcu == "cortex-m4"
                assert cfg.arch == "arm"
                assert cfg.qemu_machine == "lm3s6965evb"
                assert cfg.qemu_cpu == "cortex-m3"
                assert cfg.default_timeout == 45

    def test_nested_yaml(self):
        from yuleosh.cross.target_config import load_target_config
        with tempfile.TemporaryDirectory() as tmp:
            target_file = Path(tmp) / "targets" / "stm32f4.yaml"
            target_file.parent.mkdir(parents=True)
            target_file.write_text("")
            with patch("yuleosh.cross.target_config.yaml.safe_load",
                       return_value=SAMPLE_NESTED_YAML):
                cfg = load_target_config("stm32f4", base_dir=tmp)
                assert cfg.mcu == "cortex-m4"
                assert cfg.arch == "arm"
                assert cfg.qemu_machine == "stm32vldiscovery"
                assert cfg.qemu_extra_args == ["-semihosting", "-nographic"]
                assert cfg.flash_openocd == "interface/stlink-v2.cfg target/stm32f4x.cfg"
                assert cfg.flash_jlink == {"device": "STM32F407VG", "interface": "SWD", "speed": 4000}
                assert cfg.flash_pyocd == {"target": "stm32f407vg", "frequency": 1000000}

    def test_not_found(self):
        from yuleosh.cross.target_config import load_target_config
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(FileNotFoundError, match="not found"):
                load_target_config("nonexistent-board", base_dir=tmp)

    def test_yaml_not_dict(self):
        from yuleosh.cross.target_config import load_target_config
        with tempfile.TemporaryDirectory() as tmp:
            target_file = Path(tmp) / "bad.yaml"
            target_file.write_text("")
            with patch("yuleosh.cross.target_config.yaml.safe_load",
                       return_value=["not a dict"]):
                with pytest.raises(ValueError, match="top-level mapping"):
                    load_target_config("bad", base_dir=tmp)


# ======================================================================
# _find_target_yml
# ======================================================================

class TestFindTargetYml:
    def test_found_in_discover(self):
        from yuleosh.cross.target_config import _find_target_yml
        with tempfile.TemporaryDirectory() as tmp:
            target_file = Path(tmp) / "targets" / "myboard.yaml"
            target_file.parent.mkdir(parents=True)
            target_file.write_text("mcu: m4\n")
            result = _find_target_yml("myboard", tmp)
            assert "myboard.yaml" in result

    def test_not_found(self):
        from yuleosh.cross.target_config import _find_target_yml
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(FileNotFoundError):
                _find_target_yml("nope", tmp)

    def test_absolute_path(self):
        from yuleosh.cross.target_config import _find_target_yml
        with tempfile.TemporaryDirectory() as tmp:
            target_file = Path(tmp) / "abs-board.yaml"
            target_file.write_text("mcu: m4\n")
            result = _find_target_yml("abs-board", str(Path(tmp).resolve()))
            assert result is not None


# ======================================================================
# _parse_target
# ======================================================================

class TestParseTarget:
    def test_qemu_not_dict(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "cortex-m4",
            "arch": "arm",
            "qemu": "not a dict",
        }
        with pytest.raises(ValueError, match="qemu.*must be a mapping"):
            _parse_target("bad", raw, "/tmp")

    def test_missing_mcu(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {"arch": "arm", "qemu": {"machine": "m", "cpu": "c"}}
        with pytest.raises(ValueError, match="missing required key"):
            _parse_target("bad", raw, "/tmp")

    def test_missing_arch(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {"mcu": "m4", "qemu": {"machine": "m", "cpu": "c"}}
        with pytest.raises(ValueError, match="missing required key"):
            _parse_target("bad", raw, "/tmp")

    def test_qemu_missing_machine(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "cortex-m4",
            "arch": "arm",
            "qemu": {"cpu": "cortex-m3"},
        }
        with pytest.raises(ValueError, match="missing required key"):
            _parse_target("bad", raw, "/tmp")

    def test_extra_args_string(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "m4",
            "arch": "arm",
            "qemu": {
                "machine": "m",
                "cpu": "c",
                "serial": "-serial stdio",
                "extra_args": "-nographic -d",
            },
        }
        cfg = _parse_target("test", raw, "/tmp")
        assert cfg.qemu_extra_args == ["-nographic", "-d"]

    def test_extra_args_other_type(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "m4",
            "arch": "arm",
            "qemu": {
                "machine": "m",
                "cpu": "c",
                "serial": "-serial stdio",
                "extra_args": 42,
            },
        }
        cfg = _parse_target("test", raw, "/tmp")
        assert cfg.qemu_extra_args == []

    def test_flash_openocd_string(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "m4",
            "arch": "arm",
            "qemu": {"machine": "m", "cpu": "c", "serial": ""},
            "flash": {"openocd": "interface/stlink.cfg target/stm32.cfg"},
        }
        cfg = _parse_target("test", raw, "/tmp")
        assert cfg.flash_openocd == "interface/stlink.cfg target/stm32.cfg"

    def test_flash_jlink_not_dict(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "m4",
            "arch": "arm",
            "qemu": {"machine": "m", "cpu": "c", "serial": ""},
            "flash": {"jlink": "not a dict"},
        }
        cfg = _parse_target("test", raw, "/tmp")
        assert cfg.flash_jlink == {}

    def test_flash_pyocd(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "m4",
            "arch": "arm",
            "qemu": {"machine": "m", "cpu": "c", "serial": ""},
            "flash": {"pyocd": {"target": "stm32f407", "frequency": 1000000}},
        }
        cfg = _parse_target("test", raw, "/tmp")
        assert cfg.flash_pyocd == {"target": "stm32f407", "frequency": 1000000}

    def test_no_flash_section(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "m4",
            "arch": "arm",
            "qemu": {"machine": "m", "cpu": "c", "serial": ""},
        }
        cfg = _parse_target("test", raw, "/tmp")
        assert cfg.flash_openocd is None
        assert cfg.flash_jlink is None
        assert cfg.flash_pyocd is None

    def test_flash_not_dict(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "m4",
            "arch": "arm",
            "qemu": {"machine": "m", "cpu": "c", "serial": ""},
            "flash": "not a dict",
        }
        cfg = _parse_target("test", raw, "/tmp")
        assert cfg.flash_openocd is None
        assert cfg.flash_jlink is None
        assert cfg.flash_pyocd is None

    def test_default_timeout_none(self):
        from yuleosh.cross.target_config import _parse_target
        raw = {
            "mcu": "m4",
            "arch": "arm",
            "qemu": {"machine": "m", "cpu": "c", "serial": ""},
            "default_timeout": None,
        }
        cfg = _parse_target("test", raw, "/tmp")
        assert cfg.default_timeout == 30


# ======================================================================
# _pop
# ======================================================================

class TestPop:
    def test_pop_string(self):
        from yuleosh.cross.target_config import _pop
        d = {"key": "value"}
        assert _pop(d, "key", "ctx") == "value"
        assert "key" not in d

    def test_pop_missing(self):
        from yuleosh.cross.target_config import _pop
        with pytest.raises(ValueError, match="missing required key"):
            _pop({}, "missing", "ctx")

    def test_pop_none(self):
        from yuleosh.cross.target_config import _pop
        with pytest.raises(ValueError, match="missing required key"):
            _pop({"key": None}, "key", "ctx")

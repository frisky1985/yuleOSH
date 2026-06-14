"""Smoke tests for yuleosh.cross.target_config."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_target_config_import():
    from yuleosh.cross.target_config import TargetConfig, load_target_config
    assert TargetConfig is not None
    assert callable(load_target_config)


def test_target_config_construction():
    from yuleosh.cross.target_config import TargetConfig
    cfg = TargetConfig(
        name="stm32f4", mcu="cortex-m4", arch="arm",
        qemu_machine="stm32vldiscovery", qemu_cpu="cortex-m4", qemu_serial="uart"
    )
    assert cfg.name == "stm32f4"
    assert cfg.mcu == "cortex-m4"
    assert cfg.arch == "arm"

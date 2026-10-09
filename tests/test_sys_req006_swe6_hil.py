"""SWE.6 反假绿回归测试 —— HIL 证据链（P0）。

守住反假绿硬规矩：SWE.6 的"目标/等效环境执行"证据只能来自真实 HIL
执行结果，禁止在以下情形伪造 sil 证据：
- 无可用 HIL 设备（device 层无 ONLINE+空闲设备）
- 有设备但无真实固件产物
- 有设备+固件但 HIL 真实执行失败

场景:
- A: 无 HIL 设备 → 不写 sil 证据（attempted=False）
- B: 有设备 + 真跑通 → 写 sil 证据(all_passed=True + 真实模块名) + checker 判 GREEN
- C: 有设备 + 真跑失败 → 不写 all_passed 证据（不假绿）
- D: 有设备但无固件 → 不写证据（attempted=False）
- E: _discover_firmware_artifact 跳过 hello/sample demo 固件
"""
import json
import pytest
import types
from pathlib import Path

from yuleosh.compliance.compliance_checker import ComplianceChecker
from yuleosh.compliance.profile import load_profile
from yuleosh.pipeline.step_handlers.test_qualification import (
    _discover_firmware_artifact,
    _run_hil_qualification,
)


class FakeDevice:
    def __init__(self, name="dev1", platform="stm32"):
        self.name = name
        self.platform = platform

    def is_available(self):
        return True


class FakeAllocator:
    def __init__(self, dev):
        self._dev = dev

    def acquire(self, platform=None, job_id="adhoc", timeout=120.0,
                ttl_seconds=None, preferred_device=None):
        return self._dev

    def release(self, device_id, job_id=None):
        return True


class FakeDeviceManager:
    def __init__(self, devices):
        self._devices = list(devices)
        self._alloc = FakeAllocator(devices[0]) if devices else None

    def list_devices(self):
        return self._devices

    @property
    def allocator(self):
        return self._alloc


def _make_runner(passed, error=None):
    """返回可被 HilTestRunner(target=...) 调用的假 runner 类。"""
    class _R:
        def __init__(self, target, *a, **k):
            self.target = target

        def run(self, firmware, timeout=30.0, **kw):
            return types.SimpleNamespace(
                passed=passed, error=error, test_log="hil-pass",
                flash_result=None, boot_log="", elapsed=1.0, phase_timings={},
            )
    return _R


@pytest.fixture
def project(tmp_path):
    (tmp_path / "build").mkdir()
    fw = tmp_path / "build" / "app.elf"
    fw.write_text("ELF")
    return tmp_path, fw


def _patch_device(monkeypatch, devices):
    mgr = FakeDeviceManager(devices)
    monkeypatch.setattr("yuleosh.device.DeviceManager",
                        lambda *a, **k: mgr)
    return mgr


def test_no_device_no_fake_evidence(project, monkeypatch):
    """A: 无 HIL 设备 → 绝不写 sil 假证据。"""
    tmp, fw = project
    _patch_device(monkeypatch, [])
    out = _run_hil_qualification(tmp, str(fw))
    assert out["attempted"] is False
    assert out["passed"] is False
    assert not (tmp / ".osh" / "ci" / "sil-app.json").exists()


def test_device_present_pass_writes_sil(project, monkeypatch):
    """B: 有设备 + 真跑通 → 写真实 sil 证据，checker 判 GREEN。"""
    tmp, fw = project
    dev = FakeDevice()
    _patch_device(monkeypatch, [dev])
    monkeypatch.setattr("yuleosh.cross.HilTestRunner", _make_runner(True))
    out = _run_hil_qualification(tmp, str(fw))
    assert out["attempted"] is True
    assert out["passed"] is True

    sil = tmp / ".osh" / "ci" / "sil-app.json"
    assert sil.exists()
    data = json.loads(sil.read_text())
    assert data["all_passed"] is True
    r = data["results"][0]
    assert r["passed"] is True
    assert "hello" not in r["elf"].lower()
    assert "sample" not in r["elf"].lower()

    checker = ComplianceChecker(project_dir=str(tmp),
                                profile=load_profile("aspice_v3.1"))
    assert checker._has_sil_results() is True


def test_device_present_fail_no_fake_evidence(project, monkeypatch):
    """C: 有设备 + 真跑失败 → 不写 all_passed 证据（不假绿）。"""
    tmp, fw = project
    dev = FakeDevice()
    _patch_device(monkeypatch, [dev])
    monkeypatch.setattr("yuleosh.cross.HilTestRunner",
                        _make_runner(False, error="boot failed"))
    out = _run_hil_qualification(tmp, str(fw))
    assert out["attempted"] is True
    assert out["passed"] is False
    assert not (tmp / ".osh" / "ci" / "sil-app.json").exists()


def test_no_firmware_no_fake_evidence(project, monkeypatch):
    """D: 有设备但无固件 → 不写证据（attempted=False）。"""
    tmp, fw = project
    dev = FakeDevice()
    _patch_device(monkeypatch, [dev])
    out = _run_hil_qualification(tmp, None)
    assert out["attempted"] is False
    assert out["reason"] == "no firmware artifact to flash on HIL"
    assert not (tmp / ".osh" / "ci" / "sil-app.json").exists()


def test_discover_firmware_skips_demo(tmp_path):
    """E: 固件发现跳过 hello/sample 等 demo 固件，只认真实产品固件。"""
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "hello.elf").write_text("x")
    real = tmp_path / "build" / "app.elf"
    real.write_text("ELF")
    found = _discover_firmware_artifact(tmp_path)
    assert found is not None
    assert "hello" not in Path(found).name.lower()

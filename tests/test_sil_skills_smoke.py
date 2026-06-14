"""Smoke tests for yuleosh.sil and yuleosh.skills modules."""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestSil:
    def test_import_init(self):
        from yuleosh.sil import SimStatus, Participant, SimResult, ModelConfig
        assert SimStatus is not None
        assert Participant is not None

    def test_sim_status_values(self):
        from yuleosh.sil import SimStatus
        assert SimStatus.RUNNING is not None
        assert SimStatus.PENDING is not None

    def test_participant_create(self):
        from yuleosh.sil import Participant
        p = Participant(name="test-participant", simulation_name="sim1",
                        firmware_path="/tmp/fw.elf")
        assert p.name == "test-participant"

    def test_sim_result_create(self):
        from yuleosh.sil import SimResult, SimStatus
        r = SimResult(status=SimStatus.COMPLETED, simulation_time_ns=1000000,
                      participants=[])
        assert r.status == SimStatus.COMPLETED

    def test_model_config_create(self):
        from yuleosh.sil import ModelConfig
        mc = ModelConfig(simulation_name="sim1",
                          participants={"ecu1": "/tmp/fw.elf"})
        assert mc.simulation_name == "sim1"
        assert "ecu1" in mc.participants
        assert mc.registry_uri == "silkit://localhost:8500"

    def test_sil_adapter_import(self):
        from yuleosh.sil.adapter import SILKitAdapter
        assert SILKitAdapter is not None

    def test_sil_adapter_create(self):
        from yuleosh.sil.adapter import SILKitAdapter
        adapter = SILKitAdapter()
        assert adapter is not None

    def test_sil_adapter_convert_testcases(self):
        from yuleosh.sil.adapter import SILKitAdapter
        adapter = SILKitAdapter()
        result = adapter.convert_testcases([{"id": "TC_001"}])
        assert isinstance(result, list)


class TestSkills:
    def test_import(self):
        from yuleosh.skills import SkillManifest, Workflow
        assert SkillManifest is not None
        assert Workflow is not None

    def test_skill_manifest_create(self):
        from yuleosh.skills import SkillManifest
        m = SkillManifest(name="test", version="1.0", description="d",
                          author="me", type="skill")
        assert m.name == "test"

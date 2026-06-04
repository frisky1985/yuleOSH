"""Tests for evidence engine."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "evidence"))

from pack import EvidenceCollector

def test_collector_init():
    """Test evidence collector initialization."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp, "0.1.0")
        assert c.version == "0.1.0"
        assert c.evidence_dir.exists()

def test_requirement_coverage():
    """Test requirement coverage generation."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp, "0.1.0")
        c.requirements = [{"name": "Req1", "shall_count": 3, "reason": "test"}]
        c.scenarios = [{"name": "Sc1", "given": ["a"], "when": ["b"], "then": ["c"]}]
        path = c.generate_requirement_coverage()
        assert os.path.exists(path)
        content = open(path).read()
        assert "Req1" in content
        assert "3" in content

def test_traceability_matrix():
    """Test traceability matrix generation."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.requirements = [{"name": "Req-A", "shall_count": 2, "reason": ""}]
        c.scenarios = [{"name": "Sc-A", "given": ["x"], "when": ["y"], "then": ["z"]}]
        path = c.generate_traceability_matrix()
        assert os.path.exists(path)
        content = open(path).read()
        assert "Req-A" in content

def test_compliance_pack():
    """Test compliance pack ZIP generation."""
    with tempfile.TemporaryDirectory() as tmp:
        c = EvidenceCollector(tmp)
        c.requirements = [{"name": "R1", "shall_count": 1, "reason": ""}]
        c.generate_traceability_matrix()
        c.generate_requirement_coverage()
        zip_path = c.pack_compliance_zip()
        assert os.path.exists(zip_path)
        import zipfile
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert len(names) > 0

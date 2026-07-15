"""Extended tests for evidence.pack — covering generate_evidence and main."""

import sys
import os
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from yuleosh.evidence.pack import generate_evidence, main


class TestGenerateEvidence:
    """Cover generate_evidence function paths."""

    def test_generate_evidence_with_project_dir(self):
        """generate_evidence: creates evidence dir and runs collection."""
        with tempfile.TemporaryDirectory() as tmp:
            # Create .osh directory
            osh_dir = os.path.join(tmp, ".osh")
            os.makedirs(osh_dir)

            artifacts = generate_evidence(project_dir=tmp)
            assert artifacts is not None
            assert len(artifacts) > 0

    def test_generate_evidence_default_dir(self):
        """generate_evidence: uses OSH_HOME env var."""
        with tempfile.TemporaryDirectory() as tmp:
            osh_dir = os.path.join(tmp, ".osh")
            os.makedirs(osh_dir)
            old_home = os.environ.get("OSH_HOME")
            os.environ["OSH_HOME"] = tmp
            try:
                artifacts = generate_evidence()
                assert artifacts is not None
            finally:
                if old_home:
                    os.environ["OSH_HOME"] = old_home
                else:
                    del os.environ["OSH_HOME"]

    def test_generate_evidence_pipeline_check(self):
        """generate_evidence: handles pipeline not running check."""
        with tempfile.TemporaryDirectory() as tmp:
            osh_dir = os.path.join(tmp, ".osh")
            os.makedirs(osh_dir)
            compliance_dir = os.path.join(tmp, ".osh", "compliance")
            os.makedirs(compliance_dir)
            pipeline_lock = os.path.join(compliance_dir, "pipeline.lock")
            # Write a stale lock file (older than 5 min)
            import time
            with open(pipeline_lock, "w") as f:
                f.write(f"{{}}\npipeline")
            old_mtime = time.time() - 600  # 10 minutes ago
            os.utime(pipeline_lock, (old_mtime, old_mtime))

            artifacts = generate_evidence(project_dir=tmp)
            assert artifacts is not None

    def test_generate_evidence_with_spec_path(self):
        """generate_evidence: accepts spec_path argument."""
        with tempfile.TemporaryDirectory() as tmp:
            osh_dir = os.path.join(tmp, ".osh")
            os.makedirs(osh_dir)

            # Create a dummy spec file
            spec_path = os.path.join(tmp, "spec.md")
            with open(spec_path, "w") as f:
                f.write("# Test Spec\n")

            artifacts = generate_evidence(project_dir=tmp, spec_path=spec_path)
            assert artifacts is not None


class TestMain:
    """Cover main() CLI entry point."""

    def test_main_no_args(self, monkeypatch):
        """main(): runs with no arguments."""
        with tempfile.TemporaryDirectory() as tmp:
            osh_dir = os.path.join(tmp, ".osh")
            os.makedirs(osh_dir)
            monkeypatch.chdir(tmp)
            monkeypatch.setattr(sys, "argv", ["pack"])
            # Should not raise
            try:
                main()
            except SystemExit:
                pass

    def test_main_with_spec_arg(self, monkeypatch):
        """main(): runs with spec path argument."""
        with tempfile.TemporaryDirectory() as tmp:
            osh_dir = os.path.join(tmp, ".osh")
            os.makedirs(osh_dir)
            spec_path = os.path.join(tmp, "myspec.md")
            with open(spec_path, "w") as f:
                f.write("# Spec\n")
            monkeypatch.setattr(sys, "argv", ["pack", spec_path])
            try:
                main()
            except SystemExit:
                pass

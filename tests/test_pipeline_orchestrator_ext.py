"""Tests for pipeline/orchestrator.py — Pipeline orchestrator."""

import pytest
from unittest.mock import patch, MagicMock
import pathlib as _pathlib


class TestOrchestrator:
    """Test orchestrator functions."""

    def test_mock_llm_client(self):
        """_mock_llm_client returns a working mock."""
        from yuleosh.pipeline.orchestrator import _mock_llm_client

        client = _mock_llm_client()
        result = client("system prompt", "user prompt")
        assert "content" in result
        assert "Mock Response" in result["content"]
        assert result["model"] == "mock-mode"
        assert result["usage"]["total_tokens"] == 1500

    def test_status_pipeline_no_sessions(self):
        """status_pipeline with no sessions."""
        from yuleosh.pipeline.orchestrator import status_pipeline

        mock_base = MagicMock()
        mock_base.iterdir.return_value = []
        mock_base.exists.return_value = False
        mock_base.__truediv__.return_value = mock_base

        # B 类修复（v3.10.0 Track1，组 2）：patch orchestrator 模块内的 Path 引用
        # （全局 patch pathlib.Path 在 from-import 绑定下不生效；且 3.10 的 pathlib
        # 内部解析 Path._flavour，全局替换会 AttributeError）。
        # 补 mock_base.exists=False → sdir.exists() 为假 → sessions 空 → 正常返回。
        with patch("yuleosh.pipeline.orchestrator.Path", return_value=mock_base):
            status_pipeline("session-1")

    def test_status_pipeline_with_sessions(self):
        """status_pipeline lists sessions."""
        from yuleosh.pipeline.orchestrator import status_pipeline

        mock_sfile = MagicMock()
        mock_sfile.exists.return_value = True
        mock_sfile.read_text.return_value = (
            '{"status": "completed", "steps": [{"status": "completed"}]}'
        )

        mock_session_dir = MagicMock()
        mock_session_dir.name = "s1"
        mock_session_dir.is_dir.return_value = True
        mock_session_dir.__truediv__.return_value = mock_sfile

        mock_base = MagicMock()
        mock_base.iterdir.return_value = [mock_session_dir]

        # B 类修复（v3.10.0 Track1，组 2）：mock.py 包装 __truediv__ 时以
        # func(self, other) 调用 → 签名必须收 2 参；直接返回目标 mock，
        # 避免 `mock_session_dir / ""` 二次递归。
        def mock_truediv(self, other):
            if isinstance(other, str) and other == "sessions":
                return mock_session_dir
            if isinstance(other, str) and other == "s1":
                return mock_session_dir
            if isinstance(other, str) and other == "session.json":
                return mock_sfile
            return mock_base

        mock_base.__truediv__ = mock_truediv
        mock_session_dir.__truediv__ = mock_truediv
        # sfile 用真实 open 会失败 → 补 builtins.open mock（json.load 读 f.read()）
        import builtins
        real_open = builtins.open

        def fake_open(path, *a, **kw):
            if path is mock_sfile:
                import io
                return io.StringIO(mock_sfile.read_text())
            return real_open(path, *a, **kw)

        # B 类修复（v3.10.0 Track1，组 2）：同 test_status_pipeline_no_sessions
        with patch("yuleosh.pipeline.orchestrator.Path", return_value=mock_base):
            with patch.object(builtins, "open", fake_open):
                status_pipeline(None)

    def test_main_no_args(self):
        """main without args exits."""
        from yuleosh.pipeline.orchestrator import main
        with patch("yuleosh.pipeline.orchestrator.sys.argv", ["run.py"]):
            with pytest.raises(SystemExit):
                main()

    def test_main_status(self):
        """main with status."""
        from yuleosh.pipeline.orchestrator import main
        with patch("yuleosh.pipeline.orchestrator.sys.argv", ["run.py", "status"]):
            with patch("yuleosh.pipeline.orchestrator.status_pipeline"):
                main()

    def test_main_profile(self):
        """main with --profile flag."""
        from yuleosh.pipeline.orchestrator import main

        with patch("yuleosh.pipeline.orchestrator.sys.argv",
                    ["run.py", "--profile", "safety", "/tmp/spec.md"]):
            with patch("yuleosh.pipeline.orchestrator.run_pipeline") as mock_run:
                mock_session = MagicMock()
                mock_session.status = "completed"
                mock_run.return_value = mock_session
                with pytest.raises(SystemExit):
                    main()

    @patch("yuleosh.pipeline.orchestrator.run_pipeline")
    def test_main_keyboard_interrupt(self, mock_run):
        """main with KeyboardInterrupt."""
        from yuleosh.pipeline.orchestrator import main
        with patch("yuleosh.pipeline.orchestrator.sys.argv", ["run.py", "/tmp/spec.md"]):
            mock_run.side_effect = KeyboardInterrupt()
            with pytest.raises(SystemExit):
                main()

    @patch("yuleosh.pipeline.orchestrator.run_pipeline")
    def test_main_unhandled_exception(self, mock_run):
        """main with unhandled exception."""
        from yuleosh.pipeline.orchestrator import main
        with patch("yuleosh.pipeline.orchestrator.sys.argv", ["run.py", "/tmp/spec.md"]):
            mock_run.side_effect = Exception("Unexpected")
            with pytest.raises(SystemExit):
                main()

    def test_main_spec(self):
        """main with spec path."""
        from yuleosh.pipeline.orchestrator import main
        with patch("yuleosh.pipeline.orchestrator.sys.argv",
                    ["run.py", "/tmp/spec.md"]):
            with patch("yuleosh.pipeline.orchestrator.run_pipeline") as mock_run:
                mock_session = MagicMock()
                mock_session.status = "completed"
                mock_run.return_value = mock_session
                with pytest.raises(SystemExit):
                    main()

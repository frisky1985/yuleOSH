"""Smoke tests for yuleosh.notify."""
import os, sys
from pathlib import Path
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class TestNotify:
    def test_import(self):
        from yuleosh.notify import NotifyConfig, get_config, set_config
        assert NotifyConfig is not None

    def test_notify_config_defaults(self):
        from yuleosh.notify import NotifyConfig
        cfg = NotifyConfig()
        assert cfg.feishu_url == ""

    def test_notify_config_custom(self):
        from yuleosh.notify import NotifyConfig
        cfg = NotifyConfig(feishu_url="https://hooks.feishu.cn",
                           email_smtp="smtp.example.com")
        assert "hooks" in cfg.feishu_url

    def test_get_config(self):
        from yuleosh.notify import get_config
        cfg = get_config()
        assert cfg is not None

    def test_set_config(self):
        from yuleosh.notify import set_config, get_config, NotifyConfig
        old = get_config()
        set_config(NotifyConfig(feishu_url="https://test.com"))
        new = get_config()
        assert new.feishu_url == "https://test.com"
        set_config(old)

    def test_to_dict(self):
        from yuleosh.notify import NotifyConfig
        cfg = NotifyConfig(feishu_url="https://test.url")
        d = cfg.to_dict()
        assert d["feishu_url"] == "https://test.url"

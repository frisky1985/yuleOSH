"""Tests for api/notify.py — Notification config endpoints."""

from unittest.mock import patch, MagicMock
from yuleosh.api.notify import handle_notify, _get_config, _put_config


class TestNotify:
    """Test notification config endpoint."""

    def test_get_config(self):
        """GET returns current config."""
        mock_cfg = MagicMock()
        mock_cfg.to_dict.return_value = {"feishu_url": "https://hooks.feishu.cn/xxx"}

        with patch("yuleosh.notify.get_config", return_value=mock_cfg):
            result, code = handle_notify("GET", "config", {}, {})
            assert code == 200
            assert "feishu_url" in result["data"]

    def test_put_config(self):
        """PUT updates config."""
        mock_cfg = MagicMock()
        mock_cfg.to_dict.return_value = {"feishu_url": "https://hooks.feishu.cn/yyy"}

        with patch("yuleosh.notify.get_config", return_value=mock_cfg):
            with patch("yuleosh.notify.set_config") as mock_set:
                result, code = handle_notify(
                    "PUT", "config", {"feishu_url": "https://hooks.feishu.cn/yyy"}, {}
                )
                assert code == 200

    def test_put_config_invalid_body(self):
        """PUT with non-dict body returns 400."""
        result, code = handle_notify("PUT", "config", "not-a-dict", {})
        assert code == 400

    def test_get_notify_root(self):
        """GET /notify (root) returns config."""
        mock_cfg = MagicMock()
        mock_cfg.to_dict.return_value = {"feishu_url": ""}

        with patch("yuleosh.notify.get_config", return_value=mock_cfg):
            result, code = handle_notify("GET", "", {}, {})
            assert code == 200

    def test_put_notify_root(self):
        """PUT /notify (root) updates config."""
        mock_cfg = MagicMock()
        mock_cfg.to_dict.return_value = {"feishu_url": "url"}

        with patch("yuleosh.notify.get_config", return_value=mock_cfg):
            with patch("yuleosh.notify.set_config"):
                result, code = handle_notify(
                    "PUT", "", {"feishu_url": "url"}, {}
                )
                assert code == 200

    def test_patch_not_allowed(self):
        """PATCH returns 405."""
        result, code = handle_notify("PATCH", "config", {}, {})
        assert code == 405

    def test_unknown_resource(self):
        """Unknown resource returns 404."""
        result, code = handle_notify("GET", "unknown", {}, {})
        assert code == 404

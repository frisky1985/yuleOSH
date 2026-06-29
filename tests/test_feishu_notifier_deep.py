"""Deep tests for yuleosh.report.feishu_notifier — Feishu webhook notifications."""

from unittest import mock
from urllib.error import URLError
import pytest

from yuleosh.report.feishu_notifier import (
    _post_json,
    _resolve_webhook_url,
)


# ------------------------------------------------------------------
# _post_json
# ------------------------------------------------------------------

@mock.patch("yuleosh.report.feishu_notifier.urlopen")
def test_post_json_success(mock_urlopen):
    """GIVEN valid URL and payload WHEN posting THEN returns True on success."""
    mock_response = mock.MagicMock()
    mock_response.status = 200
    mock_urlopen.return_value = mock_response
    mock_urlopen.return_value.__enter__.return_value = mock_response

    result = _post_json("https://example.com/webhook", {"key": "value"})
    assert result is True


@mock.patch("yuleosh.report.feishu_notifier.urlopen")
def test_post_json_failure(mock_urlopen):
    """GIVEN webhook returning non-200 WHEN posting THEN returns False."""
    from urllib.error import HTTPError
    mock_urlopen.side_effect = HTTPError(
        "https://example.com/webhook", 500, "Server Error", {}, None
    )

    result = _post_json("https://example.com/webhook", {"key": "value"})
    assert result is False


@mock.patch("yuleosh.report.feishu_notifier.urlopen")
def test_post_json_timeout(mock_urlopen):
    """GIVEN request timeout WHEN posting THEN returns False."""
    from urllib.error import URLError
    mock_urlopen.side_effect = URLError("timed out")

    result = _post_json("https://example.com/webhook", {"key": "value"})
    assert result is False


# ------------------------------------------------------------------
# _resolve_webhook_url
# ------------------------------------------------------------------

def test_resolve_webhook_url_cli_arg():
    """GIVEN CLI URL argument WHEN resolving THEN returns it."""
    url = _resolve_webhook_url(cli_url="https://hooks.example.com/abc")
    assert url == "https://hooks.example.com/abc"


@mock.patch.dict("yuleosh.report.feishu_notifier.os.environ", {}, clear=True)
def test_resolve_webhook_url_no_source():
    """GIVEN no URL source WHEN resolving THEN returns None."""
    url = _resolve_webhook_url()
    assert url is None


@mock.patch.dict("yuleosh.report.feishu_notifier.os.environ", {"FEISHU_WEBHOOK_URL": "https://env.webhook"}, clear=True)
def test_resolve_webhook_url_env_var():
    """GIVEN environment variable WHEN resolving THEN returns it."""
    url = _resolve_webhook_url()
    assert url == "https://env.webhook"

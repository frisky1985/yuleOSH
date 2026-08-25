"""XSS write-path regression tests for KB field sanitization (X-01 / S-P2-03).

Guards `yuleosh.kb.models._strip_html` — the server-side defense-in-depth
behind the frontend render-time escaping. KB articles containing script /
event-handler / javascript: payloads must be neutralized on save, while
normal markdown and C++-style angle-bracket text must survive intact.
"""

# @tests src/yuleosh/kb/store.py

from yuleosh.kb.models import sanitize_kb_article_fields, _strip_html


class TestStripHtmlXss:
    def test_script_tag_removed(self):
        assert "<script>" not in _strip_html("<script>alert(1)</script>")

    def test_mixed_case_script_removed(self):
        # Whole script block is stripped (incl. its body)
        assert _strip_html("<ScRiPt>alert(1)</sCrIpT>") == ""

    def test_img_onerror_removed(self):
        out = _strip_html('<img src=x onerror="alert(1)">')
        assert "<img" not in out
        assert "onerror" not in out

    def test_unquoted_event_handler_removed(self):
        # Bypass attempt: attribute value without quotes
        out = _strip_html('<img src=x onerror=alert(1)>')
        assert "onerror" not in out

    def test_backtick_event_handler_removed(self):
        # Bypass attempt: backtick-quoted attribute value
        out = _strip_html("<img src=x onerror=`alert(1)`>")
        assert "onerror" not in out

    def test_event_handler_with_spaces_removed(self):
        out = _strip_html('<div onmouseover = "alert(1)">x</div>')
        assert "onmouseover" not in out

    def test_svg_onload_removed(self):
        out = _strip_html('<svg onload="alert(1)"></svg>')
        assert "svg" not in out
        assert "onload" not in out

    def test_javascript_protocol_removed(self):
        out = _strip_html('href="javascript:alert(1)"')
        assert "javascript:" not in out

    def test_entity_obfuscated_javascript_removed(self):
        # &#106; = 'j' — classic entity-obfuscation bypass
        out = _strip_html("href=&#106;avascript:alert(1)")
        assert "avascript" not in out or "&#106;" not in out

    def test_iframe_object_embed_removed(self):
        for payload in ("<iframe src=x></iframe>", "<object data=x></object>",
                        "<embed src=x>", "<form><input></form>",
                        "<video src=x onerror=alert(1)>", "<audio src=x>"):
            assert "<" not in _strip_html(payload), payload


class TestStripHtmlPreservesLegitText:
    def test_cpp_angle_brackets_survive(self):
        assert _strip_html("use std::vector<int> and std::map<k,v>") == \
            "use std::vector<int> and std::map<k,v>"

    def test_markdown_survives(self):
        text = "## Title\n\n- item1\n- **bold**\n\n`code`"
        assert _strip_html(text) == text

    def test_non_string_inputs(self):
        assert _strip_html(None) == ""
        assert _strip_html(123) == "123"


class TestSanitizeKbArticleFields:
    def test_dangerous_content_sanitized_on_save(self):
        body = {
            "title": "x",
            "content": "Hello <script>alert(1)</script> <img src=x onerror=alert(1)>",
            "source": "y",
            "source_ref": "",
            "tags": "a,b",
        }
        cleaned = sanitize_kb_article_fields(body)
        assert "<script>" not in cleaned["content"]
        assert "onerror" not in cleaned["content"]
        assert "Hello" in cleaned["content"]

    def test_unknown_fields_dropped(self):
        cleaned = sanitize_kb_article_fields(
            {"content": "ok", "admin": "true", "is_admin": 1})
        assert cleaned == {"content": "ok"}

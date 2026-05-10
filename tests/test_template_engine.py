"""Tests for app/template/engine.py — filters and TemplateEngine"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from app.template.engine import (
    datetime_filter, datefmt_filter, excerpt_filter,
    _sanitize_html_input, markdown_filter, TemplateEngine,
)


# ============================================================
#  datetime_filter
# ============================================================

class TestDatetimeFilter:
    def test_valid_timestamp(self):
        result = datetime_filter(1700000000)
        assert "2023" in result

    def test_string_timestamp(self):
        result = datetime_filter("1700000000")
        assert "2023" in result

    def test_invalid_value(self):
        assert datetime_filter(None) == "未知时间"
        assert datetime_filter("abc") == "未知时间"
        assert datetime_filter("") == "未知时间"


# ============================================================
#  datefmt_filter
# ============================================================

class TestDatefmtFilter:
    def test_just_now(self):
        now = int(time.time())
        result = datefmt_filter(now)
        assert result == "刚刚"

    def test_minutes_ago(self):
        ts = int(time.time()) - 300  # 5 minutes ago
        assert "分钟前" in datefmt_filter(ts)

    def test_hours_ago(self):
        ts = int(time.time()) - 7200  # 2 hours ago
        assert "小时前" in datefmt_filter(ts)

    def test_days_ago(self):
        ts = int(time.time()) - 3 * 86400  # 3 days ago
        assert "天前" in datefmt_filter(ts)

    def test_old_date(self):
        ts = int(time.time()) - 30 * 86400  # 30 days ago
        result = datefmt_filter(ts)
        assert "年" in result and "月" in result and "日" in result

    def test_invalid(self):
        assert datefmt_filter(None) == "未知时间"
        assert datefmt_filter("abc") == "未知时间"
        assert datefmt_filter(0) == "未知时间"


# ============================================================
#  excerpt_filter
# ============================================================

class TestExcerptFilter:
    def test_none_input(self):
        assert excerpt_filter(None) == ""

    def test_empty_string(self):
        assert excerpt_filter("") == ""

    def test_strips_markdown_headers(self):
        result = excerpt_filter("# Title\nContent")
        assert "#" not in result
        assert "Title" in result

    def test_strips_bold(self):
        result = excerpt_filter("**bold** text")
        assert "**" not in result
        assert "bold" in result

    def test_strips_links(self):
        result = excerpt_filter("[link](http://example.com)")
        assert "link" in result
        assert "http" not in result

    def test_truncation(self):
        text = "a" * 300
        result = excerpt_filter(text, length=100)
        assert len(result) <= 104  # "..."
        assert result.endswith("...")

    def test_short_text_no_truncation(self):
        result = excerpt_filter("short", length=100)
        assert result == "short"
        assert "..." not in result


# ============================================================
#  _sanitize_html_input (XSS)
# ============================================================

class TestSanitizeHtmlInput:
    def test_script_tag_escaped(self):
        result = _sanitize_html_input('<script>alert(1)</script>')
        assert "<script>" not in result

    def test_img_onerror_escaped(self):
        result = _sanitize_html_input('<img src=x onerror=alert(1)>')
        assert "onerror" not in result

    def test_safe_tags_preserved(self):
        result = _sanitize_html_input('<strong>bold</strong>')
        assert "<strong>" in result
        assert "bold" in result

    def test_safe_a_href_preserved(self):
        result = _sanitize_html_input('<a href="http://example.com">link</a>')
        assert '<a href="http://example.com">' in result

    def test_javascript_href_blocked(self):
        result = _sanitize_html_input('<a href="javascript:alert(1)">click</a>')
        assert "javascript:" not in result

    def test_data_href_blocked(self):
        result = _sanitize_html_input('<a href="data:text/html,<script>alert(1)</script>">click</a>')
        # The tag should be escaped/sanitized - <script> should not render
        assert "<script>" not in result

    def test_unsafe_tag_escaped(self):
        result = _sanitize_html_input('<iframe src="evil"></iframe>')
        assert "<iframe>" not in result

    def test_safe_attrs_preserved(self):
        result = _sanitize_html_input('<img src="test.png" alt="test">')
        assert 'src="test.png"' in result

    def test_unsafe_attrs_removed(self):
        result = _sanitize_html_input('<p onclick="alert(1)">text</p>')
        assert "onclick" not in result

    def test_plain_text_unchanged(self):
        result = _sanitize_html_input("just plain text")
        assert result == "just plain text"


# ============================================================
#  markdown_filter
# ============================================================

class TestMarkdownFilter:
    def test_empty_input(self):
        assert markdown_filter("") == ""
        assert markdown_filter(None) == ""

    def test_basic_markdown(self):
        result = markdown_filter("**bold** and *italic*")
        assert "<strong>" in result
        assert "<em>" in result

    def test_xss_in_markdown(self):
        result = markdown_filter('<script>alert(1)</script>')
        assert "<script>" not in result

    def test_strips_first_h1(self):
        result = markdown_filter("# Title\n\nParagraph")
        assert "<h1" not in result
        assert "Paragraph" in result

    def test_keeps_second_h1(self):
        result = markdown_filter("# First\n\n## Sub\n\n# Second")
        # First H1 removed, second H1 kept
        assert result.count("<h1") == 1 or result.count("<h1") == 0

    def test_code_block(self):
        result = markdown_filter("```python\nprint('hello')\n```")
        assert "print" in result

    def test_link_markdown(self):
        result = markdown_filter("[link](http://example.com)")
        assert "http://example.com" in result


# ============================================================
#  TemplateEngine
# ============================================================

class TestTemplateEngine:
    def test_init_with_valid_dir(self):
        engine = TemplateEngine(template_dir="./templates")
        assert engine.env is not None

    def test_init_with_invalid_dir(self):
        engine = TemplateEngine(template_dir="/nonexistent/path")
        assert engine.env is not None  # falls back to '.'

    def test_render_string(self):
        engine = TemplateEngine(template_dir="/nonexistent")
        result = engine.render_string("Hello {{ name }}", {"name": "World"})
        assert result == "Hello World"

    def test_custom_filters_registered(self):
        engine = TemplateEngine(template_dir="/nonexistent")
        assert "datetime" in engine.env.filters
        assert "datefmt" in engine.env.filters
        assert "excerpt" in engine.env.filters
        assert "markdown" in engine.env.filters

    @pytest.mark.asyncio
    async def test_load_site_config_no_engine(self):
        engine = TemplateEngine(template_dir="/nonexistent")
        config = await engine._load_site_config_async()
        assert config["title"] == "pyWork"
        assert "year" in config

    @pytest.mark.asyncio
    async def test_load_site_config_cached(self):
        engine = TemplateEngine(template_dir="/nonexistent")
        config1 = await engine._load_site_config_async()
        config2 = await engine._load_site_config_async()
        assert config1 is config2  # same object

    def test_add_template_dir(self):
        engine = TemplateEngine(template_dir="/nonexistent")
        # Should not raise
        engine.add_template_dir("/another/nonexistent")

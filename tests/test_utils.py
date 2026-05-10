"""Tests for app/utils.py — highlight_excerpt function"""
import pytest
from app.utils import highlight_excerpt


class TestHighlightExcerpt:
    """Tests for highlight_excerpt"""

    def test_empty_text(self):
        assert highlight_excerpt("", "query") == ""

    def test_none_text(self):
        assert highlight_excerpt(None, "query") == ""

    def test_short_text_with_match(self):
        result = highlight_excerpt("Hello World", "World")
        assert '<span class="highlight">World</span>' in result
        assert "Hello" in result

    def test_case_insensitive(self):
        result = highlight_excerpt("Hello WORLD", "world")
        assert '<span class="highlight">WORLD</span>' in result

    def test_multiple_matches(self):
        result = highlight_excerpt("abc abc abc", "abc")
        assert result.count('<span class="highlight">abc</span>') == 3

    def test_xss_in_query_escaped(self):
        result = highlight_excerpt("test <script>alert(1)</script>", "<script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert '<span class="highlight">' in result

    def test_xss_in_text_escaped(self):
        result = highlight_excerpt("<img src=x onerror=alert(1)>", "img")
        # The matched "img" is wrapped in highlight span
        assert '<span class="highlight">' in result
        # The surrounding HTML is escaped by markupsafe
        assert "&lt;" in result or "<img" not in result

    def test_truncation_no_match(self):
        text = "a" * 300
        result = highlight_excerpt(text, "xyz", max_len=100)
        assert len(result) <= 110  # "..." + some tolerance
        assert result.endswith("...")

    def test_truncation_with_match_centered(self):
        text = "a" * 100 + "match" + "_" + "b" * 200
        result = highlight_excerpt(text, "match", max_len=50)
        assert '<span class="highlight">match</span>' in result
        assert "..." in result

    def test_truncation_match_at_start(self):
        text = "match" + "_" + "b" * 200
        result = highlight_excerpt(text, "match", max_len=50)
        assert '<span class="highlight">match</span>' in result

    def test_truncation_match_at_end(self):
        text = "b" * 200 + "_match"
        result = highlight_excerpt(text, "match", max_len=50)
        assert '<span class="highlight">match</span>' in result

    def test_special_regex_chars_in_query(self):
        result = highlight_excerpt("price is $100 (usd)", "$100")
        assert '<span class="highlight">$100</span>' in result

    def test_dot_in_query(self):
        result = highlight_excerpt("file.txt here", "file.txt")
        assert '<span class="highlight">file.txt</span>' in result

    def test_unicode_query(self):
        result = highlight_excerpt("这是一段中文文本", "中文")
        assert '<span class="highlight">中文</span>' in result

    def test_max_len_default_200(self):
        text = "a" * 300
        result = highlight_excerpt(text, "xyz")
        # Should be truncated to ~200 chars + "..."
        assert len(result) <= 210

    def test_text_shorter_than_max_len(self):
        result = highlight_excerpt("short text", "text", max_len=200)
        assert "..." not in result
        assert '<span class="highlight">text</span>' in result

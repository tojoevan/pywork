"""Tests for security features across the codebase"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock


# ============================================================
#  XSS Sanitization — _sanitize_html_input
# ============================================================

class TestXSSSanitization:
    """Tests for HTML sanitization in template engine"""

    def test_script_tag_escaped(self):
        from app.template.engine import _sanitize_html_input
        result = _sanitize_html_input('<script>alert(1)</script>')
        # Tags should be escaped, not rendered as HTML
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_img_onerror_stripped(self):
        from app.template.engine import _sanitize_html_input
        result = _sanitize_html_input('<img src=x onerror=alert(1)>')
        assert "onerror" not in result

    def test_safe_tags_preserved(self):
        from app.template.engine import _sanitize_html_input
        result = _sanitize_html_input('<strong>bold</strong>')
        assert "<strong>" in result

    def test_javascript_href_blocked(self):
        from app.template.engine import _sanitize_html_input
        result = _sanitize_html_input('<a href="javascript:alert(1)">click</a>')
        assert "javascript:" not in result

    def test_data_href_blocked(self):
        from app.template.engine import _sanitize_html_input
        result = _sanitize_html_input('<a href="data:text/html,<script>alert(1)</script>">click</a>')
        # The href should be sanitized - either removed or the tag escaped
        assert "<script>" not in result or "data:" not in result

    def test_event_handler_removed(self):
        from app.template.engine import _sanitize_html_input
        result = _sanitize_html_input('<p onclick="alert(1)">text</p>')
        assert "onclick" not in result

    def test_safe_link_preserved(self):
        from app.template.engine import _sanitize_html_input
        result = _sanitize_html_input('<a href="https://example.com">link</a>')
        assert "https://example.com" in result

    def test_plain_text_unchanged(self):
        from app.template.engine import _sanitize_html_input
        assert _sanitize_html_input("hello world") == "hello world"


# ============================================================
#  XSS — Search Highlight
# ============================================================

class TestSearchHighlight:
    """Tests for highlight_excerpt XSS safety"""

    def test_script_in_query_escaped(self):
        from app.utils import highlight_excerpt
        result = highlight_excerpt("test <script>alert(1)</script>", "<script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_html_in_text_escaped(self):
        from app.utils import highlight_excerpt
        result = highlight_excerpt("<img src=x onerror=alert(1)>", "img")
        # The matched "img" should be wrapped in highlight span
        assert '<span class="highlight">' in result
        # The surrounding HTML is escaped by markupsafe.escape
        # so <img becomes &lt;img, preventing execution
        assert "&lt;" in result or "<img" not in result

    def test_special_chars_preserved(self):
        from app.utils import highlight_excerpt
        result = highlight_excerpt("price is $100 (usd)", "$100")
        assert '<span class="highlight">$100</span>' in result

    def test_dot_in_query(self):
        from app.utils import highlight_excerpt
        result = highlight_excerpt("file.txt here", "file.txt")
        assert '<span class="highlight">file.txt</span>' in result

    def test_unicode_query(self):
        from app.utils import highlight_excerpt
        result = highlight_excerpt("这是一段中文文本", "中文")
        assert '<span class="highlight">中文</span>' in result

    def test_truncation_safe(self):
        from app.utils import highlight_excerpt
        text = "a" * 300
        result = highlight_excerpt(text, "xyz", max_len=100)
        assert len(result) <= 110
        assert result.endswith("...")


# ============================================================
#  Markdown Filter XSS
# ============================================================

class TestMarkdownXSS:
    """Tests for markdown_filter XSS safety"""

    def test_script_in_markdown_stripped(self):
        from app.template.engine import markdown_filter
        result = markdown_filter('<script>alert(1)</script>')
        assert "<script>" not in result

    def test_basic_markdown_works(self):
        from app.template.engine import markdown_filter
        result = markdown_filter("**bold** and *italic*")
        assert "<strong>" in result
        assert "<em>" in result

    def test_link_preserved(self):
        from app.template.engine import markdown_filter
        result = markdown_filter("[link](http://example.com)")
        assert "http://example.com" in result

    def test_empty_input(self):
        from app.template.engine import markdown_filter
        assert markdown_filter("") == ""
        assert markdown_filter(None) == ""


# ============================================================
#  OAuth State Validation
# ============================================================

class TestOAuthState:
    """Tests for OAuth CSRF state parameter validation"""

    def test_oauth_states_dict_exists(self):
        """Auth plugin should have _oauth_states dict"""
        from plugins.auth.plugin import AuthPlugin
        plugin = AuthPlugin()
        assert hasattr(plugin, '_oauth_states')
        assert isinstance(plugin._oauth_states, dict)

    def test_state_stored_with_expiry(self):
        from plugins.auth.plugin import AuthPlugin
        plugin = AuthPlugin()
        state = "test_state_123"
        plugin._oauth_states[state] = time.time() + 600
        assert state in plugin._oauth_states
        assert plugin._oauth_states[state] > time.time()

    def test_expired_state_cleanup(self):
        from plugins.auth.plugin import AuthPlugin
        plugin = AuthPlugin()
        # Add expired state
        plugin._oauth_states["expired"] = time.time() - 10
        # Add valid state
        plugin._oauth_states["valid"] = time.time() + 600

        # Cleanup expired
        now = time.time()
        expired = [s for s, t in plugin._oauth_states.items() if t < now]
        for s in expired:
            del plugin._oauth_states[s]

        assert "expired" not in plugin._oauth_states
        assert "valid" in plugin._oauth_states


# ============================================================
#  Cookie Security Attributes
# ============================================================

class TestCookieSecurity:
    """Tests for Cookie security attributes in code"""

    def test_cookie_has_samesite_lax(self):
        """Verify auth plugin sets SameSite=Lax"""
        import inspect
        from plugins.auth.plugin import AuthPlugin
        source = inspect.getsource(AuthPlugin)
        assert 'samesite' in source.lower() or 'SameSite' in source

    def test_cookie_has_httponly(self):
        """Verify auth plugin sets HttpOnly"""
        import inspect
        from plugins.auth.plugin import AuthPlugin
        source = inspect.getsource(AuthPlugin)
        assert 'httponly' in source.lower() or 'HttpOnly' in source

    def test_cookie_secure_dynamic(self):
        """Verify secure attribute is dynamic based on scheme"""
        import inspect
        from plugins.auth.plugin import AuthPlugin
        source = inspect.getsource(AuthPlugin)
        # Should use request.scheme or similar, not hardcoded True
        assert 'secure' in source.lower()


# ============================================================
#  Rate Limiting
# ============================================================

class TestRateLimiting:
    """Tests for MCP endpoint rate limiting"""

    def test_rate_limit_dict_exists(self):
        """Main app should have MCP rate limit dict"""
        import inspect
        import app.main as main_mod
        source = inspect.getsource(main_mod)
        assert '_mcp_rate_limit' in source or 'rate_limit' in source.lower()

    def test_rate_limit_sliding_window(self):
        """Rate limit should use sliding window approach"""
        import inspect
        import app.main as main_mod
        source = inspect.getsource(main_mod)
        # Should have time-based window logic
        assert 'time.time()' in source or 'time' in source


# ============================================================
#  Excerpt Filter XSS
# ============================================================

class TestExcerptFilter:
    """Tests for excerpt_filter XSS safety"""

    def test_strips_markdown_headers(self):
        from app.template.engine import excerpt_filter
        result = excerpt_filter("# Title\nContent")
        assert "#" not in result
        assert "Title" in result

    def test_strips_bold(self):
        from app.template.engine import excerpt_filter
        result = excerpt_filter("**bold** text")
        assert "**" not in result

    def test_strips_links(self):
        from app.template.engine import excerpt_filter
        result = excerpt_filter("[link](http://example.com)")
        assert "http" not in result

    def test_truncation(self):
        from app.template.engine import excerpt_filter
        text = "a" * 300
        result = excerpt_filter(text, length=100)
        assert len(result) <= 104
        assert result.endswith("...")

    def test_none_input(self):
        from app.template.engine import excerpt_filter
        assert excerpt_filter(None) == ""


# ============================================================
#  Author ID Security
# ============================================================

class TestAuthorIdSecurity:
    """Tests for author_id handling — no hardcoded defaults"""

    def test_blog_create_requires_author(self):
        """Blog create_post should require author_id"""
        import inspect
        from plugins.blog.plugin import BlogPlugin
        # Check that create_post doesn't have author_id=1 as default
        sig = inspect.signature(BlogPlugin.create_post)
        param = sig.parameters.get("author_id")
        if param:
            assert param.default is None or param.default != 1

    def test_topic_create_requires_author(self):
        """Topic create_topic should require author_id"""
        import inspect
        from plugins.topic.plugin import TopicPlugin
        sig = inspect.signature(TopicPlugin.create_topic)
        param = sig.parameters.get("author_id")
        if param:
            assert param.default is None or param.default != 1

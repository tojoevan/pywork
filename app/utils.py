"""公共工具函数"""
import re
import html as html_mod


def highlight_excerpt(text: str, query: str, max_len: int = 200) -> str:
    """生成带 HTML 高亮的摘要片段"""
    if not text:
        return ""

    if len(text) > max_len:
        idx = text.lower().find(query.lower())
        if idx >= 0:
            start = max(0, idx - max_len // 3)
            text = text[start:start + max_len]
            if start > 0:
                text = "..." + text
            if start + max_len < len(text):
                text = text + "..."
        else:
            text = text[:max_len] + "..."

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    text = pattern.sub(lambda m: f'<span class="highlight">{html_mod.escape(m.group())}</span>', text)
    return text

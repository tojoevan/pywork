"""Template engine with custom filters"""
from jinja2 import Environment, FileSystemLoader, select_autoescape
from typing import Dict, Any, Optional, List
import os
from datetime import datetime
import re
import markdown as md


# 自定义过滤器
def datetime_filter(timestamp: int) -> str:
    """时间戳转 ISO 格式"""
    return datetime.fromtimestamp(timestamp).isoformat()


def datefmt_filter(timestamp: int) -> str:
    """时间戳转友好格式"""
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt
    days = diff.days
    
    if days > 7:
        return dt.strftime('%Y年%m月%d日')
    elif days > 0:
        return f'{days} 天前'
    else:
        seconds = diff.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0:
            return f'{hours} 小时前'
        elif minutes > 0:
            return f'{minutes} 分钟前'
        else:
            return '刚刚'


def excerpt_filter(text: str, length: int = 200) -> str:
    """提取摘要"""
    # 处理 None 或 Undefined
    if not text or text is None:
        return ""
    
    text = str(text)
    
    # 移除 Markdown 标记
    text = re.sub(r'#+\s+', '', text)  # 标题
    text = re.sub(r'\*\*|\*|__|_', '', text)  # 强调
    text = re.sub(r'`[^`]+`', '', text)  # 行内代码
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # 链接
    text = re.sub(r'\n+', ' ', text)  # 换行
    text = text.strip()
    
    if len(text) > length:
        return text[:length] + '...'
    return text


def _sanitize_html_input(text: str) -> str:
    """预处理用户输入，移除危险的 HTML 标签和属性，保留安全的 Markdown 内容。
    
    策略：对原始输入中的 HTML 标签做白名单过滤，只允许 markdown extra 需要的
    安全标签通过，其余一律转义。这比过滤输出更安全，因为不会误杀 markdown
    扩展生成的合法 HTML。
    """
    from markupsafe import escape
    
    # 允许的标签（markdown extra / codehilite 会用到的）
    safe_tags = {
        'br', 'hr', 'p', 'div', 'span',
        'pre', 'code',
        'em', 'strong', 'b', 'i', 'u', 'del', 's', 'sub', 'sup',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'dl', 'dt', 'dd',
        'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption', 'colgroup', 'col',
        'blockquote', 'q', 'cite',
        'a', 'img',
        'abbr', 'acronym', 'kbd', 'samp', 'var', 'mark',
        'details', 'summary',
    }
    # 允许的属性（仅限特定标签）
    safe_attrs = {
        'a': {'href', 'title'},
        'img': {'src', 'alt', 'title', 'width', 'height'},
        'td': {'align', 'colspan', 'rowspan'},
        'th': {'align', 'colspan', 'rowspan'},
        'ol': {'start', 'type'},
        'code': {'class'},          # codehilite 用
        'pre': {'class'},           # codehilite 用
        'div': {'class'},           # codehilite 用
        'span': {'class'},          # codehilite 用
        'details': {'open'},
    }
    
    # 匹配 HTML 标签
    tag_pattern = re.compile(
        r'<(/?)(\w+)((?:\s+[^>]*?)?)(/?)>',
        re.DOTALL
    )
    
    def _replace_tag(m):
        closing = m.group(1)
        tag_name = m.group(2).lower()
        attrs_str = m.group(3)
        self_closing = m.group(4)
        
        if tag_name not in safe_tags:
            # 不在白名单 → 整个标签转义
            return str(escape(m.group(0)))
        
        # 过滤属性
        if closing or self_closing:
            allowed = set()
        else:
            allowed = safe_attrs.get(tag_name, set())
        
        if not allowed or not attrs_str.strip():
            # 无属性或不需要过滤
            if not allowed and attrs_str.strip():
                # 有属性但不允许 → 移除所有属性
                return f'<{closing}{tag_name}{self_closing}>'
            return m.group(0)
        
        # 解析并过滤属性
        attr_pattern = re.compile(r'(\w[\w-]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S+))')
        safe_attr_str = ''
        for am in attr_pattern.finditer(attrs_str):
            attr_name = am.group(1).lower()
            if attr_name in allowed:
                val = am.group(2) if am.group(2) is not None else (
                    am.group(3) if am.group(3) is not None else am.group(4)
                )
                # href/src 不允许 javascript: 协议
                if attr_name in ('href', 'src') and val.lower().strip().startswith(('javascript:', 'data:', 'vbscript:')):
                    continue
                safe_attr_str += f' {attr_name}="{val}"'
        
        return f'<{closing}{tag_name}{safe_attr_str}{self_closing}>'
    
    return tag_pattern.sub(_replace_tag, text)


def markdown_filter(text: str) -> str:
    """Markdown 转 HTML（带 XSS 防护）"""
    from markupsafe import Markup
    if not text:
        return ""
    
    # 预处理：移除危险 HTML，保留安全标签
    sanitized = _sanitize_html_input(str(text))
    
    html = md.markdown(
        sanitized,
        extensions=['extra', 'codehilite', 'toc'],
        extension_configs={
            'codehilite': {'css_class': 'highlight'}
        }
    )
    return Markup(html)


class TemplateEngine:
    """Jinja2 template engine with custom filters"""
    
    def __init__(self, template_dir: str = "./templates", engine=None):
        self.template_dir = template_dir
        self._engine = engine  # SQLiteEngine reference for lazy site config loading
        self._site_cache = None
        
        # 支持多目录加载（主模板 + 插件模板）
        loaders = []
        if os.path.exists(template_dir):
            loaders.append(FileSystemLoader(template_dir))
        
        # 自动发现插件模板目录
        plugins_dir = os.path.join(
            os.path.dirname(template_dir), 'plugins'
        )
        if os.path.exists(plugins_dir):
            for plugin in os.listdir(plugins_dir):
                plugin_tpl = os.path.join(plugins_dir, plugin, 'templates')
                if os.path.exists(plugin_tpl):
                    loaders.append(FileSystemLoader(plugin_tpl))
                # 也添加插件根目录，支持 "plugin_name/template.html" 格式
                plugin_root = os.path.join(plugins_dir, plugin)
                loaders.append(FileSystemLoader(plugin_root))
        
        if not loaders:
            loaders.append(FileSystemLoader('.'))
        
        from jinja2 import ChoiceLoader
        loader = ChoiceLoader(loaders) if len(loaders) > 1 else loaders[0]
        
        self.env = Environment(
            loader=loader,
            autoescape=select_autoescape(['html', 'xml']),
            enable_async=True
        )
        
        # 注册自定义过滤器
        self.env.filters['datetime'] = datetime_filter
        self.env.filters['datefmt'] = datefmt_filter
        self.env.filters['excerpt'] = excerpt_filter
        self.env.filters['markdown'] = markdown_filter
    
    def add_template_dir(self, template_dir: str):
        """添加模板目录"""
        # 创建新的加载器组合
        existing_loader = self.env.loader
        new_loader = FileSystemLoader(template_dir)
        
        from jinja2 import ChoiceLoader
        if isinstance(existing_loader, ChoiceLoader):
            loaders = list(existing_loader.loaders) + [new_loader]
        else:
            loaders = [existing_loader, new_loader]
        
        self.env.loader = ChoiceLoader(loaders)
    
    async def _load_site_config_async(self) -> Dict[str, Any]:
        """Async load site config from database"""
        if self._site_cache is not None:
            return self._site_cache
        
        default = {
            'title': 'pyWork',
            'description': '多用户数字工作台',
            'year': datetime.now().year
        }
        
        if self._engine is None:
            self._site_cache = default
            return default
        
        try:
            rows = await self._engine.fetchall("SELECT key, value FROM site_config")
            if rows:
                config = dict(default)
                for row in rows:
                    config[row['key']] = row['value']
                self._site_cache = config
            else:
                self._site_cache = default
        except Exception:
            self._site_cache = default
        
        return self._site_cache
    
    async def render(
        self,
        template_name: str,
        data: Dict[str, Any],
        site_config: Optional[Dict[str, Any]] = None,
        user: Optional[Dict[str, Any]] = None
    ) -> str:
        """Render a template (async)"""
        template = self.env.get_template(template_name)
        
        # 自动加载 site config（只读缓存）
        actual_site = site_config
        if actual_site is None:
            try:
                actual_site = await self._load_site_config_async()
            except Exception:
                # 出错时用默认
                actual_site = {
                    'title': 'pyWork',
                    'description': '多用户数字工作台',
                    'year': datetime.now().year
                }
        
        context = {
            'Site': actual_site,
            'User': user,
            **data
        }
        
        # 使用 render_async 因为 FastAPI 是异步环境
        return await template.render_async(**context)
    
    def render_string(
        self,
        template_str: str,
        data: Dict[str, Any]
    ) -> str:
        """Render from string"""
        template = self.env.from_string(template_str)
        return template.render(**data)
    
    def list_templates(self) -> List[str]:
        """列出所有模板"""
        return self.env.list_templates()

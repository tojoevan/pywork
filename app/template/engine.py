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


def markdown_filter(text: str) -> str:
    """Markdown 转 HTML"""
    from markupsafe import Markup
    if not text:
        return ""
    html = md.markdown(
        str(text),
        extensions=['extra', 'codehilite', 'toc'],
        extension_configs={
            'codehilite': {'css_class': 'highlight'}
        }
    )
    return Markup(html)


class TemplateEngine:
    """Jinja2 template engine with custom filters"""
    
    def __init__(self, template_dir: str = "./templates"):
        self.template_dir = template_dir
        
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
    
    async def render(
        self,
        template_name: str,
        data: Dict[str, Any],
        site_config: Optional[Dict[str, Any]] = None,
        user: Optional[Dict[str, Any]] = None
    ) -> str:
        """Render a template (async)"""
        template = self.env.get_template(template_name)
        
        context = {
            'Site': site_config or {
                'title': 'pyWork',
                'description': '多用户数字工作台',
                'year': datetime.now().year
            },
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

"""Template engine"""
from jinja2 import Environment, FileSystemLoader, PackageLoader, select_autoescape
from typing import Dict, Any, Optional
import os


class TemplateEngine:
    """Jinja2 template engine"""
    
    def __init__(self, template_dir: str = "./templates"):
        self.template_dir = template_dir
        
        if os.path.exists(template_dir):
            loader = FileSystemLoader(template_dir)
        else:
            loader = PackageLoader('app', 'templates')
        
        self.env = Environment(
            loader=loader,
            autoescape=select_autoescape(['html', 'xml']),
            enable_async=True
        )
    
    def render(
        self,
        template_name: str,
        data: Dict[str, Any],
        site_config: Optional[Dict[str, Any]] = None,
        user: Optional[Dict[str, Any]] = None
    ) -> str:
        """Render a template"""
        template = self.env.get_template(template_name)
        
        context = {
            'Site': site_config or {},
            'User': user,
            **data
        }
        
        return template.render(**context)
    
    def render_string(
        self,
        template_str: str,
        data: Dict[str, Any]
    ) -> str:
        """Render from string"""
        template = self.env.from_string(template_str)
        return template.render(**data)

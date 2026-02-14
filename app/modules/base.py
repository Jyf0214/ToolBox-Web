from abc import ABC, abstractmethod
from fastapi import APIRouter
from nicegui import ui

class BaseModule(ABC):
    def __init__(self):
        self.id = self.__class__.__name__.lower()
        self.router = APIRouter(prefix=f"/api/{self.id}")
        
    @property
    @abstractmethod
    def name(self):
        """模块展示名称"""
        pass

    @property
    @abstractmethod
    def icon(self):
        """模块图标 (Material Icons)"""
        pass

    @abstractmethod
    def setup_ui(self):
        """在 NiceGUI 页面中渲染 UI"""
        pass

    def setup_api(self):
        """可选：设置 FastAPI 路由"""
        pass

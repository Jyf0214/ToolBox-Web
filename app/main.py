import os
import asyncio
from fastapi import Request, Response
from nicegui import app, ui

from app.core.config import settings
from app.core.lifecycle import startup_handler, load_modules, sync_modules_with_db
from app.api.tracking import setup_tracking_api
from app.ui.setup import create_setup_page
from app.ui.main_page import create_main_page
from app.ui.admin import create_admin_page


# --- 缓存控制中间件 ---
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# --- 全局状态 ---
class State:
    needs_setup = True
    initialized = asyncio.Event()
    db_connected = False


state = State()
modules = []
module_instances = {}


# --- 初始化与路由 ---
@app.on_startup
async def on_startup():
    await startup_handler(state, modules, module_instances)


# 注册 API 路由
app.include_router(setup_tracking_api(state))

# 注册 UI 页面
create_setup_page(state)
create_main_page(state, modules)
create_admin_page(
    state,
    lambda: load_modules(modules, module_instances),
    lambda: sync_modules_with_db(state, modules),
)

# --- 启动应用 ---
ui.run(
    title=f"工具箱 v{settings.VERSION}",
    storage_secret=settings._SECRET_KEY or os.urandom(32).hex(),
    port=7860,
    viewport="width=device-width, initial-scale=1",
)

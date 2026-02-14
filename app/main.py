import os
import importlib
import inspect
from fastapi import Request
from nicegui import app, ui
from app.core.database import engine, Base
from app.models.models import Guest, User
from app.core.config import settings
from app.modules.base import BaseModule

# 自动发现并加载模块
modules = []
def load_modules():
    modules_dir = os.path.join(os.path.dirname(__file__), "modules")
    for item in os.listdir(modules_dir):
        if os.path.isdir(os.path.join(modules_dir, item)) and not item.startswith("_"):
            try:
                module_pkg = importlib.import_module(f"app.modules.{item}.router")
                for name, obj in inspect.getmembers(module_pkg):
                    if inspect.isclass(obj) and issubclass(obj, BaseModule) and obj is not BaseModule:
                        modules.append(obj())
            except Exception as e:
                print(f"Failed to load module {item}: {e}")

@app.on_startup
async def startup():
    # 创建数据库表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    load_modules()

# --- 身份验证逻辑 ---
def is_authenticated() -> bool:
    return app.storage.user.get('authenticated', False)

# --- 游客识别逻辑 ---
from fastapi import Request, Response
from app.core.database import AsyncSessionLocal
from sqlalchemy import select
from datetime import datetime

async def get_or_create_guest(fingerprint: str, ip: str):
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Guest).where(Guest.fingerprint == fingerprint))
        guest = result.scalars().first()
        if not guest:
            guest = Guest(fingerprint=fingerprint, ip_address=ip)
            db.add(guest)
        else:
            guest.ip_address = ip
            guest.last_seen = datetime.utcnow()
        await db.commit()
        return guest

# --- UI 布局 ---
@ui.page('/')
async def main_page(request: Request):
    site_title = await get_setting('site_name', settings.SITE_NAME)
    
    # 植入指纹识别脚本
    ui.add_head_html('<script src="https://cdn.jsdelivr.net/npm/@fingerprintjs/fingerprintjs@3/dist/fp.min.js"></script>')
    
    # ... (JS 逻辑保持不变)
    
    # 获取 IP
    client_ip = request.client.host
    if "x-forwarded-for" in request.headers:
        client_ip = request.headers["x-forwarded-for"].split(",")[0]

    ui.add_head_html(f"""
        <script>
            const fpPromise = FingerprintJS.load();
            fpPromise.then(fp => fp.get()).then(result => {{
                const visitorId = result.visitorId;
                // 调用一个隐藏的 API 来记录指纹
                fetch('/api/track_guest', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{fingerprint: visitorId, ip: '{client_ip}'}})
                }});
            }});
        </script>
    """)

    with ui.header().classes('items-center justify-between bg-slate-800 p-4'):
        ui.label(site_title).classes('text-2xl font-bold text-white')
        with ui.row():
            ui.button('Admin', on_click=lambda: ui.navigate.to('/admin')).props('flat color=white')

    with ui.tabs().classes('w-full') as tabs:
        for module in modules:
            ui.tab(module.name, icon=module.icon)

    with ui.tab_panels(tabs, value=modules[0].name if modules else None).classes('w-full'):
        for module in modules:
            with ui.tab_panel(module.name):
                module.setup_ui()

from app.core.settings_manager import get_setting, set_setting

@ui.page('/admin')
async def admin_page():
    if not is_authenticated():
        # ... (登录卡片保持不变)
        with ui.card().classes('absolute-center w-80'):
            ui.label('Admin Login').classes('text-h6')
            password = ui.input('Password', password=True).classes('w-full')
            def login():
                if password.value == os.getenv("ADMIN_PASSWORD", "admin"):
                    app.storage.user.update({'authenticated': True})
                    ui.navigate.to('/admin')
                else:
                    ui.notify('Invalid password', color='negative')
            ui.button('Login', on_click=login).classes('w-full')
        return

    with ui.header().classes('bg-slate-900 items-center justify-between p-4'):
        ui.label('Admin Dashboard').classes('text-xl text-white')
        ui.button('Back to Home', on_click=lambda: ui.navigate.to('/')).props('flat color=white')
        ui.button('Logout', on_click=lambda: (app.storage.user.update({'authenticated': False}), ui.navigate.to('/'))).props('flat color=white')

    current_site_name = await get_setting('site_name', settings.SITE_NAME)

    with ui.column().classes('p-8 w-full max-w-2xl mx-auto'):
        ui.label('General Settings').classes('text-2xl mb-4')
        site_name_input = ui.input('Site Name', value=current_site_name).classes('w-full')
        
        async def save():
            await set_setting('site_name', site_name_input.value)
            ui.notify('Settings saved successfully!')
            
        ui.button('Save All', on_click=save).classes('mt-4')

        ui.separator().classes('my-8')
        
        ui.label('Guest Statistics').classes('text-2xl mb-4')
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Guest).order_by(Guest.last_seen.desc()).limit(10))
            guests = result.scalars().all()
            with ui.list().props('bordered separator'):
                for guest in guests:
                    with ui.item():
                        with ui.item_section():
                            ui.item_label(f"IP: {guest.ip_address}")
                            ui.item_label(f"Fingerprint: {guest.fingerprint[:10]}...").props('caption')
                        with ui.item_section().props('side'):
                            ui.label(guest.last_seen.strftime('%Y-%m-%d %H:%M'))

# 运行应用
from pydantic import BaseModel
class GuestData(BaseModel):
    fingerprint: str
    ip: str

@app.post('/api/track_guest')
async def track_guest(data: GuestData):
    await get_or_create_guest(data.fingerprint, data.ip)
    return {"status": "ok"}

ui.run(title=settings.SITE_NAME, storage_secret=settings.SECRET_KEY)

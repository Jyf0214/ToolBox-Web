import os
import importlib
import inspect
import secrets
from datetime import datetime
from fastapi import Request
from nicegui import app, ui
from sqlalchemy import select
from pydantic import BaseModel
from passlib.context import CryptContext

from app.core.database import engine, Base, AsyncSessionLocal
from app.models.models import Guest, User
from app.core.config import settings
from app.modules.base import BaseModule
from app.core.settings_manager import get_setting, set_setting, get_or_create_secret_key

# --- 安全与认证配置 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def is_authenticated() -> bool:
    return app.storage.user.get('authenticated', False)

# --- 模块加载 ---
modules = []
def load_modules():
    modules.clear()
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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings._SECRET_KEY = await get_or_create_secret_key()
    app.storage.secret = settings._SECRET_KEY

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.is_admin == True))
        admin_exists = result.scalars().first() is not None
        app.storage.extra['needs_setup'] = not admin_exists
            
    load_modules()

# --- 游客逻辑 ---
class GuestData(BaseModel):
    fingerprint: str
    ip: str

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

@app.post('/api/track_guest')
async def track_guest(data: GuestData):
    await get_or_create_guest(data.fingerprint, data.ip)
    return {"status": "ok"}

# --- UI 页面 ---

@ui.page('/setup')
async def setup_page():
    if not app.storage.extra.get('needs_setup', True):
        ui.navigate.to('/')
        return

    with ui.card().classes('absolute-center w-96 shadow-lg'):
        ui.label('ToolBox Setup').classes('text-h5 text-center mb-4')
        admin_username = ui.input('Admin Username', value='admin').classes('w-full')
        admin_password = ui.input('Admin Password', password=True, password_toggle_button=True).classes('w-full')
        site_name_input = ui.input('Site Name', value='My ToolBox').classes('w-full')

        async def complete_setup():
            if not admin_username.value or not admin_password.value:
                ui.notify('Fields cannot be empty', color='negative')
                return
            async with AsyncSessionLocal() as db:
                user = User(username=admin_username.value, hashed_password=get_password_hash(admin_password.value), is_admin=True)
                db.add(user)
                await db.commit()
            await set_setting('site_name', site_name_input.value)
            app.storage.extra['needs_setup'] = False
            ui.notify('Setup complete!', color='positive')
            ui.navigate.to('/admin')

        ui.button('Finish Setup', on_click=complete_setup).classes('w-full mt-4')

@ui.page('/')
async def main_page(request: Request):
    if app.storage.extra.get('needs_setup', True):
        ui.navigate.to('/setup')
        return

    site_title = await get_setting('site_name', settings.SITE_NAME)
    ui.add_head_html('<script src="https://cdn.jsdelivr.net/npm/@fingerprintjs/fingerprintjs@3/dist/fp.min.js"></script>')
    
    client_ip = request.client.host
    if "x-forwarded-for" in request.headers:
        client_ip = request.headers["x-forwarded-for"].split(",")[0]

    ui.add_head_html(f"""
        <script>
            const fpPromise = FingerprintJS.load();
            fpPromise.then(fp => fp.get()).then(result => {{
                fetch('/api/track_guest', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{fingerprint: result.visitorId, ip: '{client_ip}'}})
                }});
            }});
        </script>
    """)

    with ui.header().classes('items-center justify-between bg-slate-800 p-4'):
        ui.label(site_title).classes('text-2xl font-bold text-white')
        ui.button('Admin', on_click=lambda: ui.navigate.to('/admin')).props('flat color=white icon=settings')

    if not modules:
        ui.label('No modules loaded.').classes('p-8 text-center w-full')
    else:
        with ui.tabs().classes('w-full') as tabs:
            for m in modules:
                ui.tab(m.name, icon=m.icon)
        with ui.tab_panels(tabs, value=modules[0].name).classes('w-full'):
            for m in modules:
                with ui.tab_panel(m.name):
                    m.setup_ui()

@ui.page('/admin')
async def admin_page():
    if app.storage.extra.get('needs_setup', True):
        ui.navigate.to('/setup')
        return

    if not is_authenticated():
        with ui.card().classes('absolute-center w-80 shadow-lg'):
            ui.label('Admin Login').classes('text-h6 mb-2')
            pwd = ui.input('Password', password=True).classes('w-full')
            async def login():
                async with AsyncSessionLocal() as db:
                    res = await db.execute(select(User).where(User.is_admin == True))
                    admin = res.scalars().first()
                    if admin and verify_password(pwd.value, admin.hashed_password):
                        app.storage.user.update({'authenticated': True})
                        ui.navigate.to('/admin')
                    else:
                        ui.notify('Invalid Credentials', color='negative')
            ui.button('Login', on_click=login).classes('w-full mt-2')
        return

    with ui.header().classes('bg-slate-900 items-center justify-between p-4'):
        ui.label('Admin Panel').classes('text-xl text-white')
        with ui.row():
            ui.button('Home', on_click=lambda: ui.navigate.to('/')).props('flat color=white')
            ui.button('Logout', on_click=lambda: (app.storage.user.update({'authenticated': False}), ui.navigate.to('/'))).props('flat color=white')

    with ui.column().classes('p-8 w-full max-w-2xl mx-auto'):
        ui.label('Settings').classes('text-2xl mb-4')
        current_name = await get_setting('site_name', settings.SITE_NAME)
        name_input = ui.input('Site Name', value=current_name).classes('w-full')
        ui.button('Save', on_click=lambda: (set_setting('site_name', name_input.value), ui.notify('Saved'))).classes('mt-2')

        ui.separator().classes('my-8')
        ui.label('Recent Visitors').classes('text-2xl mb-4')
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(Guest).order_by(Guest.last_seen.desc()).limit(10))
            for g in res.scalars().all():
                with ui.card().classes('w-full mb-2 p-4'):
                    ui.label(f"IP: {g.ip_address} | Last: {g.last_seen.strftime('%H:%M:%S')}")

# 启动，指定端口为 7860
ui.run(title="ToolBox", storage_secret="init-temp-key", port=7860)

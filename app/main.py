import os
import importlib
import inspect
import asyncio
import traceback
from datetime import datetime
from fastapi import Request, Response
from nicegui import app, ui
from pydantic import BaseModel
import bcrypt

from sqlalchemy import select
from app.core.database import (
    Base,
    AsyncSessionLocal,
    create_engine_with_ssl_fallback,
    create_session_local,
)
from app.models.models import Guest, User
from app.core.config import settings
from app.modules.base import BaseModule
from app.core.settings_manager import get_setting, set_setting, get_or_create_secret_key


# --- 缓存控制 ---
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers[
        "Cache-Control"
    ] = "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# --- 安全与认证配置 ---


# 全局状态
class State:
    needs_setup = True
    initialized = asyncio.Event()
    db_connected = False  # 新增：数据库连接状态


state = State()


def get_password_hash(password: str) -> str:
    # 使用 bcrypt 直接哈希
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    # 使用 bcrypt 验证
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def is_authenticated() -> bool:
    return app.storage.user.get("authenticated", False)


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
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseModule)
                        and obj is not BaseModule
                    ):
                        modules.append(obj())
            except Exception as e:
                print(f"Failed to load module {item}: {e}")


@app.on_startup
async def startup():
    try:
        print("Initializing database engine and trying connection with SSL fallback...")
        await asyncio.wait_for(
            create_engine_with_ssl_fallback(), timeout=20
        )  # 增加超时时间
        create_session_local()  # 创建 SessionLocal
        print("Database engine and session created successfully.")
        state.db_connected = True  # 数据库连接成功

        # 尝试创建所有表
        async with AsyncSessionLocal() as session:
            await session.run_sync(Base.metadata.create_all)
        print("Database tables created/checked successfully.")

    except Exception as e:
        print(f"CRITICAL ERROR: Failed to initialize database: {e}")
        traceback.print_exc()  # 打印完整的堆栈信息
        state.db_connected = False  # 数据库连接失败
        # 即使失败也释放事件，避免页面无限死锁
        state.initialized.set()  # 确保事件被设置，防止无限等待
        return

    try:
        settings._SECRET_KEY = await get_or_create_secret_key()
        app.storage.secret = settings._SECRET_KEY

        # 只有在数据库连接成功时才检查管理员是否存在，否则强制进入访客模式
        if state.db_connected:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(User).where(User.is_admin))
                admin_exists = result.scalars().first() is not None
            state.needs_setup = admin_exists is None
        else:
            state.needs_setup = (
                False  # 数据库未连接，不进行 setup 流程，直接进入访客模式
            )

    except Exception as e:
        print(f"Error during post-initialization: {e}")
    finally:
        load_modules()  # 无论数据库连接成功与否，都加载模块
        state.initialized.set()  # 确保事件被设置，防止无限等待


# --- 游客逻辑 ---
class GuestData(BaseModel):
    fingerprint: str
    ip: str


async def get_or_create_guest(fingerprint: str, ip: str):
    try:
        await asyncio.wait_for(state.initialized.wait(), timeout=10)
    except asyncio.TimeoutError:
        ui.notify("Database connection timeout.", color="negative")
        return  # 数据库超时，访客追踪不可用

    if not state.db_connected:  # 数据库未连接，访客追踪不可用
        return

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Guest).where(Guest.fingerprint == fingerprint)
        )
        guest = result.scalars().first()
        if not guest:
            guest = Guest(fingerprint=fingerprint, ip_address=ip)
            session.add(guest)
        else:
            guest.ip_address = ip
            guest.last_seen = datetime.utcnow()
        await session.commit()


@app.post("/api/track_guest")
async def track_guest(data: GuestData):
    await get_or_create_guest(data.fingerprint, data.ip)
    return {"status": "ok"}


# --- UI 页面 ---


@ui.page("/setup")
async def setup_page():
    if not state.needs_setup:
        ui.navigate.to("/")
        return

    with ui.card().classes("absolute-center w-[90vw] max-w-md shadow-lg p-6"):
        ui.label("ToolBox Setup").classes("text-h5 text-center mb-4")
        admin_username = ui.input("Admin Username", value="admin").classes("w-full")
        admin_password = ui.input(
            "Admin Password", password=True, password_toggle_button=True
        ).classes("w-full")
        site_name_input = ui.input("Site Name", value="My ToolBox").classes("w-full")

        async def complete_setup():
            try:
                await asyncio.wait_for(state.initialized.wait(), timeout=10)
            except asyncio.TimeoutError:
                ui.notify("Database connection timeout.", color="negative")
                return

            if not admin_username.value or not admin_password.value:
                ui.notify("Fields cannot be empty", color="negative")
                return

            if not state.db_connected:
                ui.notify(
                    "Database is not connected. Cannot complete setup.",
                    color="negative",
                )
                return

            async with AsyncSessionLocal() as session:
                user = User(
                    username=admin_username.value,
                    hashed_password=get_password_hash(admin_password.value),
                    is_admin=True,
                )
                session.add(user)
                await session.commit()

            await set_setting("site_name", site_name_input.value)
            state.needs_setup = False
            ui.notify("Setup complete!", color="positive")
            ui.navigate.to("/admin")

        ui.button("Finish Setup", on_click=complete_setup).classes("w-full mt-4")


@ui.page("/")
async def main_page(request: Request):
    try:
        await asyncio.wait_for(state.initialized.wait(), timeout=10)
    except asyncio.TimeoutError:
        ui.notify("Database connection timeout.", color="negative")
        ui.navigate.to(
            "/error?msg=Database%20connection%20timeout."
        )  # 可以创建一个错误页面显示
        return

    if state.needs_setup:
        ui.navigate.to("/setup")
        return

    site_title = await get_setting("site_name", settings.SITE_NAME)
    ui.add_head_html(
        '<script src="https://cdn.jsdelivr.net/npm/@fingerprintjs/fingerprintjs@3/dist/fp.min.js"></script>'
    )

    client_ip = request.client.host
    if "x-forwarded-for" in request.headers:
        client_ip = request.headers["x-forwarded-for"].split(",")[0]

    ui.add_head_html(
        f"""
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
    """
    )

    with ui.header().classes("items-center justify-between bg-slate-800 p-4 flex-wrap"):
        ui.label(site_title).classes("text-2xl font-bold text-white")
        ui.button(icon="settings", on_click=lambda: ui.navigate.to("/admin")).props(
            "flat color=white"
        ).disable() if not state.db_connected else None

    if not modules:
        ui.label("No modules loaded.").classes("p-8 text-center w-full")
    else:
        with ui.tabs().classes("w-full overflow-x-auto") as tabs:
            for m in modules:
                ui.tab(m.name, icon=m.icon)
        with ui.tab_panels(tabs, value=modules[0].name).classes("w-full"):
            for m in modules:
                with ui.tab_panel(m.name):
                    m.setup_ui()


@ui.page("/admin")
async def admin_page():
    try:
        await asyncio.wait_for(state.initialized.wait(), timeout=10)
    except asyncio.TimeoutError:
        ui.notify("Database connection timeout.", color="negative")
        ui.navigate.to("/error?msg=Database%20connection%20timeout.")
        return

    if state.needs_setup:
        ui.navigate.to("/setup")
        return

    if not is_authenticated():
        with ui.card().classes("absolute-center w-[90vw] max-w-xs shadow-lg p-6"):
            ui.label("Admin Login").classes("text-h6 mb-2")
            if not state.db_connected:
                ui.label(
                    "Admin functions are unavailable (Database disconnected)."
                ).classes("text-negative mb-4")
            pwd = ui.input("Password", password=True).classes("w-full")
            pwd.disable() if not state.db_connected else None

            async def login():
                async with AsyncSessionLocal() as session:
                    admin = await session.execute(select(User).where(User.is_admin))
                    admin = admin.scalars().first()
                    if admin and verify_password(pwd.value, admin.hashed_password):
                        app.storage.user.update({"authenticated": True})
                        ui.navigate.to("/admin")
                    else:
                        ui.notify("Invalid Credentials", color="negative")

            ui.button("Login", on_click=login).classes(
                "w-full mt-2"
            ).disable() if not state.db_connected else None
        return

    with ui.header().classes("bg-slate-900 items-center justify-between p-4 flex-wrap"):
        ui.label("Admin Panel").classes("text-xl text-white")
        with ui.row().classes("items-center"):
            ui.button(icon="home", on_click=lambda: ui.navigate.to("/")).props(
                "flat color=white"
            ).classes("sm:hidden")
            ui.button("Home", on_click=lambda: ui.navigate.to("/")).props(
                "flat color=white"
            ).classes("hidden sm:block")

            ui.button(
                icon="logout",
                on_click=lambda: (
                    app.storage.user.update({"authenticated": False}),
                    ui.navigate.to("/"),
                ),
            ).props("flat color=white").classes("sm:hidden")
            ui.button(
                "Logout",
                on_click=lambda: (
                    app.storage.user.update({"authenticated": False}),
                    ui.navigate.to("/"),
                ),
            ).props("flat color=white").classes("hidden sm:block")

    with ui.column().classes("p-4 sm:p-8 w-full max-w-2xl mx-auto"):
        ui.label("Settings").classes("text-2xl mb-4")
        current_name = await get_setting("site_name", settings.SITE_NAME)

        if not state.db_connected:  # 数据库未连接，设置功能禁用
            ui.label("Settings are unavailable (Database disconnected).").classes(
                "text-negative mb-4"
            )
            name_input = (
                ui.input("Site Name", value=current_name).classes("w-full").disable()
            )
            ui.button(
                "Save", on_click=lambda: ui.notify("Database disconnected.")
            ).classes("mt-2").disable()
        else:
            name_input = ui.input("Site Name", value=current_name).classes("w-full")
            ui.button(
                "Save",
                on_click=lambda: (
                    set_setting("site_name", name_input.value),
                    ui.notify("Saved"),
                ),
            ).classes("mt-2")

        ui.separator().classes("my-8")
        ui.label("Recent Visitors").classes("text-2xl mb-4")

        if not state.db_connected:  # 数据库未连接，访客列表不可用
            ui.label(
                "Recent visitors list is unavailable (Database disconnected)."
            ).classes("text-negative")
        else:
            async with AsyncSessionLocal() as session:
                guests = await session.execute(
                    select(Guest).order_by(Guest.last_seen.desc()).limit(10)
                )
                for g in guests.scalars().all():
                    with ui.card().classes("w-full mb-2 p-4"):
                        ui.label(
                            f"IP: {g.ip_address} | Last: {g.last_seen.strftime('%H:%M:%S')}"
                        )


# 启动，指定端口为 7860
ui.run(
    title="ToolBox",
    storage_secret="dynamic-key-placeholder",
    port=7860,
    viewport="width=device-width, initial-scale=1",
)  # nosec

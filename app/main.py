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

from sqlalchemy import select, update
from app.core.database import (
    Base,
    AsyncSessionLocal,
    create_engine_with_ssl_fallback,
    create_session_local,
)
from app.models.models import Guest, User, Tool
from app.core.config import settings
from app.modules.base import BaseModule
from app.core.settings_manager import get_setting, set_setting, get_or_create_secret_key
from app.core.updater import check_for_updates, pull_updates, get_latest_commit_message


# --- 缓存控制 ---
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
    )
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
module_instances = {}


def load_modules():
    modules.clear()
    module_instances.clear()
    modules_dir = os.path.join(os.path.dirname(__file__), "modules")
    if not os.path.exists(modules_dir):
        return
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
                        instance = obj()
                        modules.append(instance)
                        module_instances[instance.id] = instance
            except Exception as e:
                print(f"Failed to load module {item}: {e}")


async def sync_modules_with_db():
    if not state.db_connected:
        return

    async with AsyncSessionLocal() as session:
        # 获取数据库中的所有模块
        result = await session.execute(select(Tool))
        db_tools = {t.name: t for t in result.scalars().all()}

        # 同步当前加载的模块到数据库
        current_module_ids = set()
        for m in modules:
            current_module_ids.add(m.id)
            if m.id not in db_tools:
                new_tool = Tool(
                    name=m.id,
                    display_name=m.name,
                    is_enabled=m.default_enabled,
                    is_guest_allowed=True,
                )
                session.add(new_tool)
            else:
                # 更新显示名称（如果发生变化）
                if db_tools[m.id].display_name != m.name:
                    db_tools[m.id].display_name = m.name

        await session.commit()


@app.on_startup
async def startup():
    try:
        print("正在初始化数据库引擎并尝试通过 SSL 回退进行连接...")
        await asyncio.wait_for(
            create_engine_with_ssl_fallback(), timeout=20
        )  # 增加超时时间
        create_session_local()  # 创建 SessionLocal
        print("数据库引擎和会话创建成功。")
        state.db_connected = True  # 数据库连接成功

        # 尝试创建所有表
        async with AsyncSessionLocal() as session:
            await session.run_sync(Base.metadata.create_all)
        print("数据库表创建/检查成功。")

    except Exception as e:
        print(f"严重错误：无法初始化数据库: {e}")
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
        print(f"初始化后处理出错: {e}")
    finally:
        load_modules()  # 无论数据库连接成功与否，都加载模块
        await sync_modules_with_db()
        # 设置每个模块的 API 并包含路由
        for m in modules:
            m.setup_api()
            app.include_router(m.router)
        state.initialized.set()  # 确保事件被设置，防止无限等待


# --- 游客逻辑 ---
class GuestData(BaseModel):
    fingerprint: str
    ip: str


async def get_or_create_guest(fingerprint: str, ip: str):
    try:
        await asyncio.wait_for(state.initialized.wait(), timeout=10)
    except asyncio.TimeoutError:
        ui.notify("数据库连接超时。", color="negative")
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
        ui.label("工具箱初始化设置").classes("text-h5 text-center mb-4")
        admin_username = ui.input("管理员用户名", value="admin").classes("w-full")
        admin_password = ui.input(
            "管理员密码", password=True, password_toggle_button=True
        ).classes("w-full")
        site_name_input = ui.input("站点名称", value="我的工具箱").classes("w-full")

        async def complete_setup():
            try:
                await asyncio.wait_for(state.initialized.wait(), timeout=10)
            except asyncio.TimeoutError:
                ui.notify("数据库连接超时。", color="negative")
                return

            if not admin_username.value or not admin_password.value:
                ui.notify("字段不能为空", color="negative")
                return

            if not state.db_connected:
                ui.notify(
                    "数据库未连接，无法完成初始化设置。",
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
            ui.notify("初始化完成！", color="positive")
            ui.navigate.to("/admin")

        ui.button("完成设置", on_click=complete_setup).classes("w-full mt-4")


@ui.page("/")
async def main_page(request: Request):
    try:
        await asyncio.wait_for(state.initialized.wait(), timeout=10)
    except asyncio.TimeoutError:
        ui.notify("数据库连接超时。", color="negative")
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
        with ui.row().classes("items-center"):
            ui.label(site_title).classes("text-2xl font-bold text-white")
            ui.label(f"v{settings.VERSION}").classes("text-xs text-slate-300 ml-2")
        ui.button(icon="settings", on_click=lambda: ui.navigate.to("/admin")).props(
            "flat color=white"
        ).disable() if not state.db_connected else None

    if not modules:
        ui.label("未加载任何模块。").classes("p-8 text-center w-full")
    else:
        # 获取模块在数据库中的状态
        enabled_modules = []
        if state.db_connected:
            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Tool))
                db_tools = {t.name: t for t in result.scalars().all()}

            is_admin = is_authenticated()
            for m in modules:
                tool_info = db_tools.get(m.id)
                if tool_info:
                    if not tool_info.is_enabled:
                        continue
                    if not is_admin and not tool_info.is_guest_allowed:
                        continue
                enabled_modules.append(m)
        else:
            # 数据库未连接时，默认显示所有加载的模块（作为降级方案）
            enabled_modules = modules

        if not enabled_modules:
            ui.label("当前没有可用的工具。").classes("p-8 text-center w-full")
        else:
            with ui.tabs().classes("w-full overflow-x-auto") as tabs:
                for m in enabled_modules:
                    ui.tab(m.name, icon=m.icon)
            with ui.tab_panels(tabs, value=enabled_modules[0].name).classes("w-full"):
                for m in enabled_modules:
                    with ui.tab_panel(m.name):
                        m.setup_ui()


@ui.page("/admin")
async def admin_page():
    try:
        await asyncio.wait_for(state.initialized.wait(), timeout=10)
    except asyncio.TimeoutError:
        ui.notify("数据库连接超时。", color="negative")
        ui.navigate.to("/error?msg=Database%20connection%20timeout.")
        return

    if state.needs_setup:
        ui.navigate.to("/setup")
        return

    if not is_authenticated():
        with ui.card().classes("absolute-center w-[90vw] max-w-xs shadow-lg p-6"):
            ui.label("管理登录").classes("text-h6 mb-2")
            if not state.db_connected:
                ui.label("管理功能不可用（数据库未连接）。").classes(
                    "text-negative mb-4"
                )
            pwd = ui.input("密码", password=True).classes("w-full")
            pwd.disable() if not state.db_connected else None

            async def login():
                async with AsyncSessionLocal() as session:
                    admin = await session.execute(select(User).where(User.is_admin))
                    admin = admin.scalars().first()
                    if admin and verify_password(pwd.value, admin.hashed_password):
                        app.storage.user.update({"authenticated": True})
                        ui.navigate.to("/admin")
                    else:
                        ui.notify("凭据无效", color="negative")

            ui.button("登录", on_click=login).classes(
                "w-full mt-2"
            ).disable() if not state.db_connected else None
        return

    with ui.header().classes("bg-slate-900 items-center justify-between p-4 flex-wrap"):
        with ui.row().classes("items-center"):
            ui.label("管理后台").classes("text-xl text-white")
            ui.label(f"v{settings.VERSION}").classes("text-xs text-slate-400 ml-2")
        with ui.row().classes("items-center"):
            ui.button(icon="home", on_click=lambda: ui.navigate.to("/")).props(
                "flat color=white"
            ).classes("sm:hidden")
            ui.button("首页", on_click=lambda: ui.navigate.to("/")).props(
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
                "登出",
                on_click=lambda: (
                    app.storage.user.update({"authenticated": False}),
                    ui.navigate.to("/"),
                ),
            ).props("flat color=white").classes("hidden sm:block")

    with ui.column().classes("p-4 sm:p-8 w-full max-w-2xl mx-auto"):
        ui.label("设置").classes("text-2xl mb-4")
        current_name = await get_setting("site_name", settings.SITE_NAME)

        if not state.db_connected:  # 数据库未连接，设置功能禁用
            ui.label("设置不可用（数据库未连接）。").classes("text-negative mb-4")
            name_input = (
                ui.input("站点名称", value=current_name).classes("w-full").disable()
            )
            ui.button("保存", on_click=lambda: ui.notify("数据库未连接。")).classes(
                "mt-2"
            ).disable()
        else:
            name_input = ui.input("站点名称", value=current_name).classes("w-full")
            ui.button(
                "保存",
                on_click=lambda: (
                    set_setting("site_name", name_input.value),
                    ui.notify("已保存"),
                ),
            ).classes("mt-2")

        ui.separator().classes("my-8")
        with ui.row().classes("w-full items-center justify-between mb-4"):
            ui.label("工具管理").classes("text-2xl")

            async def handle_refresh():
                load_modules()
                await sync_modules_with_db()
                ui.notify("已重新扫描模块文件夹")
                ui.navigate.to("/admin")

            ui.button("刷新工具列表", on_click=handle_refresh).props(
                "flat icon=refresh"
            )

        if not state.db_connected:
            ui.label("工具管理不可用（数据库未连接）。").classes("text-negative")
        else:

            async def toggle_tool(tool_name, field, value):
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(Tool)
                        .where(Tool.name == tool_name)
                        .values({field: value})
                    )
                    await session.commit()
                ui.notify(f"已更新 {tool_name}")

            async with AsyncSessionLocal() as session:
                result = await session.execute(select(Tool).order_by(Tool.id))
                tools = result.scalars().all()

                with ui.column().classes("w-full gap-4"):
                    for t in tools:
                        with ui.card().classes("w-full p-4"):
                            with ui.row().classes(
                                "w-full items-center justify-between"
                            ):
                                with ui.column():
                                    ui.label(t.display_name).classes(
                                        "text-lg font-bold"
                                    )
                                    ui.label(f"ID: {t.name}").classes(
                                        "text-xs text-slate-500"
                                    )

                                with ui.row().classes("items-center gap-4"):
                                    with ui.column().classes("items-center"):
                                        ui.label("启用").classes("text-xs")
                                        ui.switch(
                                            value=t.is_enabled,
                                            on_change=lambda e, name=t.name: (
                                                toggle_tool(name, "is_enabled", e.value)
                                            ),
                                        )
                                    with ui.column().classes("items-center"):
                                        ui.label("游客可用").classes("text-xs")
                                        ui.switch(
                                            value=t.is_guest_allowed,
                                            on_change=lambda e, name=t.name: (
                                                toggle_tool(
                                                    name, "is_guest_allowed", e.value
                                                )
                                            ),
                                        )

        ui.separator().classes("my-8")
        ui.label("系统更新").classes("text-2xl mb-4")

        update_status_label = ui.label("点击检查更新按钮查看是否有新版本").classes(
            "text-slate-600 mb-4"
        )
        update_info_label = ui.label("").classes("text-sm text-slate-500 mb-4")
        update_button = ui.button("检查更新", color="primary")

        async def handle_check_update():
            update_button.disable()
            update_status_label.set_text("正在检查更新...")
            update_info_label.set_text("")

            try:
                (
                    has_update,
                    local_commit,
                    remote_commit,
                    message,
                ) = await asyncio.get_event_loop().run_in_executor(
                    None, check_for_updates
                )

                if has_update:
                    update_status_label.set_text(f"{message}").classes(
                        "text-positive font-bold"
                    )
                    update_info_label.set_text(
                        f"本地版本: {local_commit} → 远程版本: {remote_commit}"
                    )
                    update_button.set_text("立即更新").props("color=positive")
                    update_button.on_click(handle_pull_update)
                else:
                    update_status_label.set_text(message).classes("text-slate-600")
                    if local_commit and remote_commit:
                        update_info_label.set_text(f"当前版本: {local_commit}")
            except Exception as e:
                update_status_label.set_text(f"检查更新出错: {str(e)}").classes(
                    "text-negative"
                )
            finally:
                update_button.enable()

        async def handle_pull_update():
            update_button.disable()
            update_status_label.set_text("正在拉取更新...")

            try:
                success, message = await asyncio.get_event_loop().run_in_executor(
                    None, pull_updates
                )

                if success:
                    # 获取最新提交的日志
                    (
                        log_success,
                        log_message,
                    ) = await asyncio.get_event_loop().run_in_executor(
                        None, get_latest_commit_message
                    )
                    if log_success:
                        update_status_label.set_text(
                            f"更新成功！最新提交: {log_message}"
                        ).classes("text-positive font-bold")
                    else:
                        update_status_label.set_text("更新成功！").classes(
                            "text-positive font-bold"
                        )
                    update_button.set_text("重启应用以应用更新").props("color=warning")
                    update_button.disable()
                    ui.notify("更新完成，请重启应用", color="positive", timeout=5000)
                else:
                    update_status_label.set_text(message).classes("text-negative")
                    update_button.set_text("重试更新").props("color=negative")
            except Exception as e:
                update_status_label.set_text(f"更新出错: {str(e)}").classes(
                    "text-negative"
                )
            finally:
                update_button.enable()

        update_button.on_click(handle_check_update)

        ui.separator().classes("my-8")
        ui.label("最近访客").classes("text-2xl mb-4")

        if not state.db_connected:  # 数据库未连接，访客列表不可用
            ui.label("最近访客列表不可用（数据库未连接）。").classes("text-negative")
        else:
            async with AsyncSessionLocal() as session:
                guests = await session.execute(
                    select(Guest).order_by(Guest.last_seen.desc()).limit(10)
                )
                for g in guests.scalars().all():
                    with ui.card().classes("w-full mb-2 p-4"):
                        ui.label(
                            f"IP: {g.ip_address} | 最后访问: {g.last_seen.strftime('%Y-%m-%d %H:%M:%S')}"
                        )


# 启动，指定端口为 7860
ui.run(
    title=f"工具箱 v{settings.VERSION}",
    storage_secret="dynamic-key-placeholder",
    port=7860,
    viewport="width=device-width, initial-scale=1",
)  # nosec

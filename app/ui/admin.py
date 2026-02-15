import asyncio
import secrets
import string
import time
from datetime import datetime
from nicegui import ui, app
from fastapi import Request
from sqlalchemy import select, update

from app.core import database
from app.models.models import Tool, User, Guest
from app.core.config import settings
from app.core.settings_manager import get_setting, set_setting
from app.core.auth import is_authenticated, verify_password, get_password_hash
from app.core.updater import check_for_updates, pull_updates

# 存储重置数据
reset_data = {}

# 登录限流: {ip: {"count": int, "last_attempt": float}}
login_attempts = {}
MAX_ATTEMPTS = 5
LOCKOUT_TIME = 300  # 5 分钟


def create_admin_page(state, load_modules_func, sync_modules_func):
    @ui.page("/admin")
    async def admin_page(request: Request):
        client_ip = request.client.host

        if state.needs_setup:
            ui.navigate.to("/setup")
            return

        # 使用 refreshable 包装整个内容
        @ui.refreshable
        async def render_content():
            if not is_authenticated():
                # --- 登录限流检查 ---
                now = time.time()
                if client_ip in login_attempts:
                    attempts = login_attempts[client_ip]
                    if attempts["count"] >= MAX_ATTEMPTS:
                        if now - attempts["last_attempt"] < LOCKOUT_TIME:
                            remaining = int(
                                LOCKOUT_TIME - (now - attempts["last_attempt"])
                            )
                            with ui.card().classes(
                                "absolute-center w-[90vw] max-w-sm shadow-xl p-8 text-center"
                            ):
                                ui.icon("lock", color="negative").classes("text-6xl mb-4")
                                ui.label("访问受限").classes("text-h5 mb-2")
                                ui.label(
                                    f"由于多次尝试登录失败，您的 IP 已被临时锁定。请在 {remaining} 秒后再试。"
                                ).classes("text-slate-500")
                            return
                        else:
                            login_attempts[client_ip] = {"count": 0, "last_attempt": 0}

                with ui.card().classes(
                    "absolute-center w-[90vw] max-w-sm shadow-2xl p-0 overflow-hidden border-t-4 border-primary"
                ):
                    with ui.column().classes("p-8 w-full"):
                        with ui.row().classes("w-full items-center justify-center mb-6"):
                            ui.icon("admin_panel_settings", color="primary").classes(
                                "text-4xl mr-2"
                            )
                            ui.label("管理控制台").classes("text-h5 font-bold")

                        if not state.db_connected:
                            with ui.row().classes(
                                "w-full bg-red-50 p-3 rounded-lg mb-4 items-center"
                            ):
                                ui.icon("error", color="negative").classes("text-lg mr-2")
                                ui.label("数据库未连接，登录暂不可用").classes(
                                    "text-negative text-xs"
                                )

                        user_input = (
                            ui.input("用户名")
                            .classes("w-full mb-2")
                            .props('outlined dense prepend-icon="person"')
                        )
                        pwd = (
                            ui.input("密码", password=True)
                            .classes("w-full mb-6")
                            .props('outlined dense prepend-icon="lock"')
                        )

                        async def login():
                            if not state.db_connected:
                                ui.notify("无法登录：数据库连接失败", color="negative")
                                return
                            if not user_input.value or not pwd.value:
                                ui.notify("请输入用户名和密码", color="warning")
                                return

                            if client_ip not in login_attempts:
                                login_attempts[client_ip] = {"count": 0, "last_attempt": 0}

                            try:
                                async with database.AsyncSessionLocal() as session:
                                    result = await session.execute(
                                        select(User).where(
                                            User.username == user_input.value,
                                            User.is_admin,
                                        )
                                    )
                                    admin = result.scalars().first()
                                    if admin and verify_password(
                                        pwd.value, admin.hashed_password
                                    ):
                                        login_attempts[client_ip] = {
                                            "count": 0,
                                            "last_attempt": 0,
                                        }
                                        # 更新验证状态
                                        app.storage.user["authenticated"] = True
                                        ui.notify("登录成功，欢迎回来", color="positive")
                                        # 刷新当前页面内容
                                        render_content.refresh()
                                    else:
                                        login_attempts[client_ip]["count"] += 1
                                        login_attempts[client_ip]["last_attempt"] = (
                                            time.time()
                                        )
                                        rem = MAX_ATTEMPTS - login_attempts[client_ip][
                                            "count"
                                        ]
                                        if rem > 0:
                                            ui.notify(
                                                f"用户名或密码错误，还可以尝试 {rem} 次",
                                                color="negative",
                                            )
                                        else:
                                            ui.notify(
                                                "尝试次数过多，IP 已被锁定", color="negative"
                                            )
                                            render_content.refresh()
                            except Exception as e:
                                ui.notify(f"登录过程出错: {e}", color="negative")

                        pwd.on("keydown.enter", login)
                        user_input.on("keydown.enter", login)
                        ui.button("进入系统", on_click=login).classes(
                            "w-full h-12 text-lg shadow-md"
                        ).props("elevated")

                        with ui.row().classes("w-full justify-center mt-4"):
                            ui.button(
                                "找回权限", on_click=lambda: reset_dialog.open()
                            ).props("flat size=sm color=grey icon=help_outline")
                return

            # --- 管理界面重构 (侧边栏布局) ---
            with ui.header().classes(
                "bg-slate-900 items-center justify-between px-4 py-2"
            ):
                with ui.row().classes("items-center"):
                    ui.button(
                        on_click=lambda: left_drawer.toggle(), icon="menu"
                    ).props("flat color=white").classes("sm:hidden")
                    ui.label("ToolBox Admin").classes("text-xl font-bold text-white ml-2")
                    ui.label(f"v{settings.VERSION}").classes(
                        "text-xs text-slate-400 ml-2 hidden sm:block"
                    )
                with ui.row().classes("items-center gap-2"):
                    ui.button(
                        "退出",
                        icon="logout",
                        on_click=lambda: (
                            app.storage.user.update({"authenticated": False}),
                            ui.navigate.to("/admin"), # 退出时可以跳转回登录
                            render_content.refresh()
                        ),
                    ).props("flat color=white size=sm").classes("rounded-lg")

            with ui.left_drawer(value=True).classes("bg-slate-50 border-r") as left_drawer:
                with ui.column().classes("w-full p-4 gap-2"):
                    nav_dashboard = ui.button("控制面板", icon="dashboard", on_click=lambda: switch_to("dashboard")).props("flat align=left").classes("w-full rounded-lg text-slate-600")
                    nav_settings = ui.button("站点设置", icon="settings", on_click=lambda: switch_to("settings")).props("flat align=left").classes("w-full rounded-lg text-slate-600")
                    nav_tools = ui.button("工具管理", icon="build", on_click=lambda: switch_to("tools")).props("flat align=left").classes("w-full rounded-lg text-slate-600")
                    nav_update = ui.button("系统更新", icon="system_update", on_click=lambda: switch_to("update")).props("flat align=left").classes("w-full rounded-lg text-slate-600")
                    nav_logs = ui.button("访问日志", icon="list_alt", on_click=lambda: switch_to("logs")).props("flat align=left").classes("w-full rounded-lg text-slate-600")
                    
                    ui.separator().classes("my-4")
                    ui.button("回到首页", icon="home", on_click=lambda: ui.navigate.to("/")).props("flat align=left").classes("w-full rounded-lg text-slate-600")

            sections = {}

            def switch_to(name):
                for k, v in sections.items():
                    v.set_visibility(k == name)
                # Update nav styles
                for btn, n in [(nav_dashboard, "dashboard"), (nav_settings, "settings"), (nav_tools, "tools"), (nav_update, "update"), (nav_logs, "logs")]:
                    if n == name:
                        btn.classes(add="bg-primary text-white", remove="text-slate-600")
                    else:
                        btn.classes(remove="bg-primary text-white", add="text-slate-600")

            with ui.column().classes("p-4 sm:p-8 w-full max-w-5xl mx-auto"):
                # ... [此处保持原有的 Dashboard, Settings, Tools, Update, Logs 代码块不变] ...
                # (为了简洁，我将在 new_string 中包含完整的逻辑块，但在 replace 时我会确保内容一致)
                
                # --- 控制面板 ---
                with ui.column().classes("w-full") as sections["dashboard"]:
                    ui.label("控制面板").classes("text-2xl font-bold mb-6")
                    with ui.row().classes("w-full gap-4"):
                        async def get_stats():
                            async with database.AsyncSessionLocal() as session:
                                tool_count = (await session.execute(select(Tool))).scalars().all()
                                guest_count = (await session.execute(select(Guest))).scalars().all()
                                return len(tool_count), len(guest_count)
                        tc, gc = await get_stats() if state.db_connected else (0, 0)
                        with ui.card().classes("flex-1 p-6 items-center shadow-sm border"):
                            ui.label(str(tc)).classes("text-3xl font-bold text-primary")
                            ui.label("总工具数").classes("text-slate-500 text-sm")
                        with ui.card().classes("flex-1 p-6 items-center shadow-sm border"):
                            ui.label(str(gc)).classes("text-3xl font-bold text-secondary")
                            ui.label("历史访客").classes("text-slate-500 text-sm")
                        with ui.card().classes("flex-1 p-6 items-center shadow-sm border"):
                            ui.label("在线" if state.db_connected else "离线").classes(f"text-xl font-bold {'text-green-500' if state.db_connected else 'text-red-500'}")
                            ui.label("数据库状态").classes("text-slate-500 text-sm")

                # --- 站点设置 ---
                with ui.column().classes("w-full hidden") as sections["settings"]:
                    ui.label("站点设置").classes("text-2xl font-bold mb-6")
                    with ui.card().classes("w-full p-6 shadow-sm border"):
                        current_name = await get_setting("site_name", settings.SITE_NAME)
                        name_input = ui.input("站点名称", value=current_name).classes("w-full").props("outlined")
                        if not state.db_connected:
                            name_input.disable()
                        with ui.row().classes("w-full justify-end mt-6"):
                            async def save_settings():
                                await set_setting("site_name", name_input.value)
                                ui.notify("设置已保存", color="positive")
                            ui.button("保存修改", on_click=save_settings, icon="save").classes("px-6").disable() if not state.db_connected else ui.button("保存修改", on_click=save_settings, icon="save").classes("px-6")

                # --- 工具管理 ---
                with ui.column().classes("w-full hidden") as sections["tools"]:
                    with ui.row().classes("w-full items-center justify-between mb-6"):
                        ui.label("工具管理").classes("text-2xl font-bold")
                        async def handle_refresh_tools():
                            load_modules_func()
                            await sync_modules_func()
                            ui.notify("已重新扫描模块文件夹", color="info")
                            refresh_tool_list.refresh()
                        ui.button("刷新列表", icon="refresh", on_click=handle_refresh_tools).props("outline size=sm")

                    @ui.refreshable
                    async def refresh_tool_list():
                        if not state.db_connected:
                            ui.label("数据库未连接").classes("text-negative")
                            return
                        async with database.AsyncSessionLocal() as session:
                            result = await session.execute(select(Tool).order_by(Tool.id))
                            tools = result.scalars().all()
                            if not tools:
                                ui.label("暂无工具，请点击右上角刷新").classes("text-slate-400 italic")
                                return
                            with ui.grid(columns=(1, 'md:2', 'lg:2')).classes("w-full gap-4"):
                                for t in tools:
                                    with ui.card().classes("p-4 shadow-sm border hover:shadow-md transition-shadow"):
                                        with ui.row().classes("w-full items-start justify-between"):
                                            with ui.column().classes("flex-1"):
                                                ui.label(t.display_name).classes("text-lg font-bold truncate")
                                                ui.label(t.name).classes("text-xs text-slate-400 font-mono")
                                            async def toggle_tool(tool_name, field, value):
                                                async with database.AsyncSessionLocal() as session_int:
                                                    await session_int.execute(update(Tool).where(Tool.name == tool_name).values({field: value}))
                                                    await session_int.commit()
                                                ui.notify(f"已更新 {tool_name}")
                                            with ui.column().classes("items-end"):
                                                ui.switch("启用", value=t.is_enabled, on_change=lambda e, name=t.name: toggle_tool(name, "is_enabled", e.value)).props("dense")
                                                ui.switch("游客", value=t.is_guest_allowed, on_change=lambda e, name=t.name: toggle_tool(name, "is_guest_allowed", e.value)).props("dense")
                    await refresh_tool_list()

                # --- 系统更新 ---
                with ui.column().classes("w-full hidden") as sections["update"]:
                    ui.label("系统更新").classes("text-2xl font-bold mb-6")
                    with ui.card().classes("w-full p-8 shadow-sm border items-center text-center"):
                        ui.icon("system_update_alt", color="primary").classes("text-6xl mb-4")
                        status_label = ui.label("检查系统是否有可用更新").classes("text-lg mb-2")
                        info_label = ui.label(f"当前版本: v{settings.VERSION}").classes("text-sm text-slate-500 mb-6")
                        with ui.row().classes("gap-4"):
                            check_btn = ui.button("检查更新", icon="search").props("elevated")
                            pull_btn = ui.button("拉取更新", icon="cloud_download").props("outline").classes("hidden")
                            async def check_update():
                                check_btn.disable()
                                status_label.set_text("正在连接服务器...")
                                try:
                                    has_up, local, remote, msg = await asyncio.get_event_loop().run_in_executor(None, check_for_updates)
                                    status_label.set_text(msg)
                                    if has_up:
                                        info_label.set_text(f"发现新版本: {remote} (当前: {local})")
                                        pull_btn.set_visibility(True)
                                    else:
                                        info_label.set_text(f"当前已是最新版本 (v{local})")
                                except Exception as e_up:
                                    status_label.set_text(f"检查失败: {e_up}")
                                finally:
                                    check_btn.enable()
                            async def pull_update_action():
                                pull_btn.disable()
                                status_label.set_text("正在更新...")
                                try:
                                    success, msg = await asyncio.get_event_loop().run_in_executor(None, pull_updates)
                                    status_label.set_text(msg)
                                    if success:
                                        ui.notify("更新成功，请手动重启应用以生效", color="positive", duration=10)
                                except Exception as e_pull:
                                    status_label.set_text(f"更新失败: {e_pull}")
                                finally:
                                    pull_btn.enable()
                            check_btn.on_click(check_update)
                            pull_btn.on_click(pull_update_action)

                # --- 访问日志 ---
                with ui.column().classes("w-full hidden") as sections["logs"]:
                    ui.label("最近访客").classes("text-2xl font-bold mb-6")
                    if state.db_connected:
                        async with database.AsyncSessionLocal() as session:
                            res = await session.execute(select(Guest).order_by(Guest.last_seen.desc()).limit(20))
                            guests = res.scalars().all()
                            if not guests:
                                ui.label("尚无访问记录").classes("text-slate-400 italic")
                            else:
                                with ui.card().classes("w-full p-0 overflow-hidden border"):
                                    with ui.column().classes("w-full divide-y"):
                                        for g in guests:
                                            with ui.row().classes("w-full p-4 items-center justify-between hover:bg-slate-50"):
                                                with ui.row().classes("items-center"):
                                                    ui.icon("public", color="slate-400").classes("mr-3")
                                                    ui.label(g.ip_address).classes("font-mono font-bold")
                                                ui.label(g.last_seen.strftime('%Y-%m-%d %H:%M:%S')).classes("text-xs text-slate-500")
                    else:
                        ui.label("数据库未连接").classes("text-negative")

                switch_to("dashboard")

        # 初始调用
        await render_content()

        # --- 重置密码对话框 (全局单例) ---
        with ui.dialog() as reset_dialog, ui.card().classes("w-full max-w-md"):
            with ui.column().classes("p-6 w-full"):
                ui.label("安全验证与维护").classes("text-h6 mb-2")
                status_msg = ui.label("请输入管理员用户名以开始验证").classes(
                    "text-sm text-slate-500 mb-6"
                )

                with ui.column().classes("w-full gap-4"):
                    r_user_input = ui.input("管理员用户名").classes("w-full")
                    r_code_input = ui.input("重置码").classes("w-full hidden")
                    new_pwd_input = ui.input("新密码", password=True).classes(
                        "w-full hidden"
                    )

                    def generate_random_code():
                        alphabet = (
                            string.ascii_letters + string.digits + "!@#$%^&*"
                        )
                        return "".join(
                            secrets.choice(alphabet) for _ in range(32)
                        )

                    async def request_code():
                        if not r_user_input.value:
                            ui.notify("请输入用户名", color="warning")
                            return
                        now_req = time.time()
                        ip_info = reset_data.get(client_ip, {"last_request": 0})
                        if now_req - ip_info["last_request"] < 60:
                            ui.notify("请求太频繁，请稍后再试", color="warning")
                            return
                        code = generate_random_code()
                        reset_data[client_ip] = {
                            "code": code,
                            "user": r_user_input.value,
                            "expires": now_req + 600,
                            "step": 1,
                            "last_request": now_req,
                        }
                        print("\n" + "!" * 20 + " 重置验证 (第 1 步) " + "!" * 20)
                        print(f"用户: {r_user_input.value} | IP: {client_ip}")
                        print(f"验证码 1: {code}")
                        print("!" * 60 + "\n")
                        r_code_input.set_visibility(True)
                        r_user_input.disable()
                        status_msg.set_text("第 1 次验证：请输入终端显示的 32 位重置码")
                        req_btn.set_visibility(False)
                        verify_btn.set_visibility(True)
                        ui.notify("验证码 1 已发送至终端", color="positive")

                    async def verify_step():
                        info = reset_data.get(client_ip)
                        if not info or time.time() > info["expires"]:
                            ui.notify("验证已超时，请重新开始", color="warning")
                            reset_dialog.close()
                            return
                        if r_code_input.value != info["code"]:
                            ui.notify("验证码错误", color="negative")
                            return
                        if info["step"] == 1:
                            new_code = generate_random_code()
                            info["code"] = new_code
                            info["step"] = 2
                            r_code_input.value = ""
                            status_msg.set_text("第 2 次验证：请输入终端显示的【新】验证码")
                            print("\n" + "!" * 20 + " 重置验证 (第 2 步) " + "!" * 20)
                            print(f"用户: {info['user']} | IP: {client_ip}")
                            print(f"验证码 2: {new_code}")
                            print("!" * 60 + "\n")
                            ui.notify("验证码 2 已发送至终端", color="info")
                        elif info["step"] == 2:
                            status_msg.set_text("验证通过！现在可以重置密码或数据库。")
                            r_code_input.set_visibility(False)
                            new_pwd_input.set_visibility(True)
                            verify_btn.set_visibility(False)
                            action_row.set_visibility(True)
                            ui.notify("身份确认成功", color="positive")

                    async def reset_password():
                        info = reset_data.get(client_ip)
                        if not new_pwd_input.value:
                            ui.notify("请输入新密码", color="warning")
                            return
                        try:
                            async with database.AsyncSessionLocal() as session:
                                res = await session.execute(select(User).where(User.username == info["user"], User.is_admin))
                                admin_user = res.scalars().first()
                                if not admin_user:
                                    ui.notify("权限验证失败", color="negative")
                                    return
                                admin_user.hashed_password = get_password_hash(new_pwd_input.value)
                                await session.commit()
                            ui.notify("密码已重置", color="positive")
                            reset_dialog.close()
                            del reset_data[client_ip]
                        except Exception as e:
                            ui.notify(f"重置失败: {e}", color="negative")

                    async def dangerous_reset_db():
                        try:
                            async with database.engine.begin() as conn_db:
                                from app.core.database import Base
                                await conn_db.run_sync(Base.metadata.drop_all)
                                await conn_db.run_sync(Base.metadata.create_all)
                            ui.notify("数据库已彻底重置", color="positive")
                            state.needs_setup = True
                            reset_dialog.close()
                            ui.navigate.to("/setup")
                        except Exception as e:
                            ui.notify(f"数据库重置失败: {e}", color="negative")

                    req_btn = ui.button("获取重置码", on_click=request_code).classes("w-full shadow-md")
                    verify_btn = ui.button("确认验证", on_click=verify_step).classes("w-full hidden shadow-md")
                    with ui.row().classes("w-full justify-between hidden") as action_row:
                        ui.button("重置密码", on_click=reset_password).props("color=primary elevated")
                        with ui.button("重置数据库", icon="warning").props("color=negative outline"):
                            with ui.menu():
                                ui.menu_item("确认彻底删除所有数据？", on_click=dangerous_reset_db)
                    with ui.row().classes("w-full justify-end mt-4"):
                        ui.button("取消", on_click=reset_dialog.close).props("flat")

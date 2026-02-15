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
                    nav_maintenance = ui.button("系统维护", icon="handyman", on_click=lambda: switch_to("maintenance")).props("flat align=left").classes("w-full rounded-lg text-slate-600")
                    nav_queue = ui.button("队列监控", icon="reorder", on_click=lambda: switch_to("queue")).props("flat align=left").classes("w-full rounded-lg text-slate-600")
                    nav_logs = ui.button("访问日志", icon="list_alt", on_click=lambda: switch_to("logs")).props("flat align=left").classes("w-full rounded-lg text-slate-600")
                    
                    ui.separator().classes("my-4")
                    ui.button("回到首页", icon="home", on_click=lambda: ui.navigate.to("/")).props("flat align=left").classes("w-full rounded-lg text-slate-600")

            sections = {}

            def switch_to(name):
                for k, v in sections.items():
                    v.set_visibility(k == name)
                # Update nav styles
                for btn, n in [(nav_dashboard, "dashboard"), (nav_settings, "settings"), (nav_tools, "tools"), (nav_update, "update"), (nav_maintenance, "maintenance"), (nav_queue, "queue"), (nav_logs, "logs")]:
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
                                                                            with ui.row().classes("items-center"):
                                                                                ui.label(t.display_name).classes("text-lg font-bold truncate")
                                                                                if t.rate_limit_count > 0:
                                                                                    ui.badge(f"{t.rate_limit_count}/{t.rate_limit_period}s", color="orange").props("outline")
                                                                            ui.label(t.name).classes("text-xs text-slate-400 font-mono")
                                                                        
                                                                        async def toggle_tool(tool_name, field, value):
                                                                            async with database.AsyncSessionLocal() as session_int:
                                                                                await session_int.execute(
                                                                                    update(Tool).where(Tool.name == tool_name).values({field: value})
                                                                                )
                                                                                await session_int.commit()
                                                                            ui.notify(f"已更新 {tool_name}")
                                
                                                                        with ui.column().classes("items-end gap-1"):
                                                                            ui.switch("启用", value=t.is_enabled, 
                                                                                     on_change=lambda e, name=t.name: toggle_tool(name, "is_enabled", e.value)).props("dense")
                                                                            ui.switch("游客", value=t.is_guest_allowed, 
                                                                                     on_change=lambda e, name=t.name: toggle_tool(name, "is_guest_allowed", e.value)).props("dense")
                                                                            
                                                                            async def open_settings(tool_obj):
                                                                                with ui.dialog() as settings_dialog, ui.card().classes("p-6 w-full max-w-sm"):
                                                                                    ui.label(f"配置 - {tool_obj.display_name}").classes("text-h6 mb-4")
                                                                                    limit_input = ui.number("速率限制 (次数)", value=tool_obj.rate_limit_count, format="%.0f", help="0 表示不限制").classes("w-full")
                                                                                    period_input = ui.number("统计周期 (秒)", value=tool_obj.rate_limit_period, format="%.0f").classes("w-full")
                                                                                    
                                                                                    with ui.row().classes("w-full justify-end mt-6 gap-2"):
                                                                                        ui.button("取消", on_click=settings_dialog.close).props("flat")
                                                                                        async def save_tool_settings():
                                                                                            async with database.AsyncSessionLocal() as session_save:
                                                                                                await session_save.execute(
                                                                                                    update(Tool).where(Tool.name == tool_obj.name).values({
                                                                                                        "rate_limit_count": int(limit_input.value or 0),
                                                                                                        "rate_limit_period": int(period_input.value or 60)
                                                                                                    })
                                                                                                )
                                                                                                await session_save.commit()
                                                                                            ui.notify("工具配置已保存")
                                                                                            settings_dialog.close()
                                                                                            refresh_tool_list.refresh()
                                                                                        ui.button("保存", on_click=save_tool_settings).props("elevated")
                                                                                settings_dialog.open()
                                
                                                                            ui.button(icon="settings", on_click=lambda t_obj=t: open_settings(t_obj)).props("flat dense size=sm color=grey")
                                
                    await refresh_tool_list()

                            # --- 系统更新 ---

                            with ui.column().classes("w-full hidden") as sections["update"]:

                                ui.label("系统更新").classes("text-2xl font-bold mb-6")

                                with ui.card().classes("w-full p-8 shadow-sm border"):

                                    with ui.column().classes("w-full items-center text-center"):

                                        ui.icon("system_update_alt", color="primary").classes("text-6xl mb-4")

                                        status_label = ui.label("检查系统是否有可用更新").classes("text-lg mb-2")

                                        info_label = ui.label(f"当前版本: v{settings.VERSION}").classes("text-sm text-slate-500 mb-6")

                                    

                                    # 日志对比区域

                                    changelog_container = ui.column().classes("w-full mt-4 hidden")

                                    with changelog_container:

                                        ui.separator().classes("mb-4")

                                        ui.label("更新日志对比").classes("text-sm font-bold text-slate-700 mb-2")

                                        with ui.row().classes("w-full gap-4"):

                                            with ui.column().classes("flex-1"):

                                                ui.label("本地 (当前)").classes("text-xs text-slate-400")

                                                local_scroll = ui.scroll_area().classes("h-64 border rounded p-2 bg-slate-50 text-xs")

                                            with ui.column().classes("flex-1"):

                                                ui.label("远程 (最新)").classes("text-xs text-primary")

                                                remote_scroll = ui.scroll_area().classes("h-64 border rounded p-2 bg-blue-50 text-xs")

                

                                    with ui.row().classes("w-full justify-center gap-4 mt-8"):

                                        check_btn = ui.button("检查更新", icon="search").props("elevated")

                                        pull_btn = ui.button("立即开始更新", icon="cloud_download").props("color=positive elevated").classes("hidden")

                

                                        async def check_update():

                                            check_btn.disable()

                                            status_label.set_text("正在同步远程仓库...")

                                            try:

                                                from app.core.updater import get_local_changelog, get_remote_changelog

                                                has_up, local_v, remote_v, msg = await asyncio.get_event_loop().run_in_executor(None, check_for_updates)

                                                

                                                # 获取日志

                                                _, local_log = get_local_changelog()

                                                _, remote_log = await asyncio.get_event_loop().run_in_executor(None, get_remote_changelog)

                                                

                                                local_scroll.clear()

                                                with local_scroll:

                                                    ui.markdown(local_log or "无日志")

                                                

                                                remote_scroll.clear()

                                                with remote_scroll:

                                                    ui.markdown(remote_log or "无日志")

                                                

                                                changelog_container.set_visibility(True)

                                                status_label.set_text(msg)

                                                

                                                if has_up:

                                                    info_label.set_text(f"检测到新版本: v{remote_v} (当前: v{local_v})")

                                                    pull_btn.set_visibility(True)

                                                else:

                                                    info_label.set_text(f"您已经是最新版本 (v{local_v})")

                                                    pull_btn.set_visibility(False)

                                                    

                                            except Exception as e_up:

                                                status_label.set_text(f"检查失败: {e_up}")

                                            finally:

                                                check_btn.enable()

                

                                        async def confirm_update():

                                            with ui.dialog() as confirm_dialog, ui.card().classes("p-6"):

                                                ui.label("确认更新系统？").classes("text-h6 mb-4")

                                                ui.label("系统将拉取最新代码并可能需要手动重启。更新过程中请勿切断电源。").classes("text-slate-500 mb-6")

                                                with ui.row().classes("w-full justify-end gap-2"):

                                                    ui.button("取消", on_click=confirm_dialog.close).props("flat")

                                                    ui.button("确认更新", on_click=lambda: (confirm_dialog.close(), do_pull_update())).props("elevated color=positive")

                                            confirm_dialog.open()

                

                                        async def do_pull_update():

                                            pull_btn.disable()

                                            check_btn.disable()

                                            status_label.set_text("正在下载并应用更新...")

                                            try:

                                                success, msg = await asyncio.get_event_loop().run_in_executor(None, pull_updates)

                                                status_label.set_text(msg)

                                                if success:

                                                    ui.notify("系统更新成功！", color="positive", duration=None)

                                                    ui.label("更新已完成。请通过控制台重启应用以加载新版本。").classes("text-positive font-bold mt-4")

                                            except Exception as e_pull:

                                                status_label.set_text(f"更新失败: {e_pull}")

                                            finally:

                                                pull_btn.enable()

                                                check_btn.enable()

                

                                        check_btn.on_click(check_update)

                                        pull_btn.on_click(confirm_update)

                

                            # --- 系统维护 ---
            with ui.column().classes("w-full hidden") as sections["maintenance"]:
                ui.label("系统维护").classes("text-2xl font-bold mb-6")
                
                with ui.grid(columns=(1, 'md:2')).classes("w-full gap-6"):
                    # 数据库清理卡片
                    with ui.card().classes("p-6 shadow-sm border"):
                        with ui.row().classes("items-center mb-4"):
                            ui.icon("delete_sweep", color="warning", size="md").classes("mr-2")
                            ui.label("数据库清理").classes("text-xl font-bold")
                        ui.label("识别并删除数据库中不再使用的孤儿表。").classes("text-sm text-slate-500 mb-6")
                        
                        async def scan_and_clean_db():
                            if not state.db_connected: return
                            try:
                                from sqlalchemy import inspect, text
                                async with database.engine.connect() as conn:
                                    # 获取当前数据库中所有的表名
                                    def get_tables(connection):
                                        return inspect(connection).get_table_names()
                                    
                                    db_tables = await conn.run_sync(get_tables)
                                    # 获取模型中定义的表名
                                    model_tables = set(database.Base.metadata.tables.keys())
                                    
                                    orphan_tables = [t for t in db_tables if t not in model_tables]
                                    
                                    if not orphan_tables:
                                        ui.notify("未发现冗余表，数据库很干净。", color="positive")
                                        return
                                    
                                    with ui.dialog() as clean_confirm, ui.card().classes("p-6"):
                                        ui.label("发现冗余表").classes("text-h6 mb-2")
                                        ui.label(f"以下表不再被系统使用，确认删除吗？").classes("text-sm text-slate-500 mb-4")
                                        with ui.column().classes("bg-slate-100 p-2 rounded mb-6 w-full"):
                                            for ot in orphan_tables:
                                                ui.label(f"• {ot}").classes("text-xs font-mono text-negative")
                                        
                                        with ui.row().classes("w-full justify-end gap-2"):
                                            ui.button("取消", on_click=clean_confirm.close).props("flat")
                                            async def do_clean():
                                                async with database.engine.begin() as conn_del:
                                                    for ot in orphan_tables:
                                                        await conn_del.execute(text(f"DROP TABLE IF EXISTS `{ot}`"))
                                                ui.notify(f"已清理 {len(orphan_tables)} 个冗余表", color="positive")
                                                clean_confirm.close()
                                            ui.button("确认删除", on_click=do_clean).props("elevated color=negative")
                                    clean_confirm.open()
                            except Exception as e_clean:
                                ui.notify(f"扫描失败: {e_clean}", color="negative")

                        ui.button("扫描冗余表", icon="search", on_click=scan_and_clean_db).classes("w-full").props("outline")

                    # 日志清理卡片
                    with ui.card().classes("p-6 shadow-sm border"):
                        with ui.row().classes("items-center mb-4"):
                            ui.icon("history_toggle_off", color="info", size="md").classes("mr-2")
                            ui.label("日志管理").classes("text-xl font-bold")
                        ui.label("清空访客记录。这不会影响管理员账号或工具设置。").classes("text-sm text-slate-500 mb-6")
                        
                        async def clear_logs_action():
                            with ui.dialog() as log_confirm, ui.card().classes("p-6"):
                                ui.label("确认清空访问日志？").classes("text-h6 mb-2")
                                ui.label("此操作不可恢复。").classes("text-sm text-slate-500 mb-6")
                                with ui.row().classes("w-full justify-end gap-2"):
                                    ui.button("取消", on_click=log_confirm.close).props("flat")
                                    async def do_clear_logs():
                                        async with database.AsyncSessionLocal() as session:
                                            from sqlalchemy import delete
                                            await session.execute(delete(Guest))
                                            await session.commit()
                                        ui.notify("访问日志已清空", color="positive")
                                        log_confirm.close()
                                    ui.button("确认清空", on_click=do_clear_logs).props("elevated color=negative")
                            log_confirm.open()

                        ui.button("清空访客日志", icon="delete", on_click=clear_logs_action).classes("w-full").props("outline color=negative")

            # --- 队列监控 ---
            with ui.column().classes("w-full hidden") as sections["queue"]:
                from app.core.task_manager import global_task_manager
                ui.label("队列监控").classes("text-2xl font-bold mb-6")
                
                with ui.card().classes("w-full p-6 mb-6 shadow-sm border"):
                    ui.label("并发控制").classes("text-lg font-bold mb-4")
                    with ui.row().classes("items-center gap-4"):
                        ui.label("全局最大同时处理任务数:")
                        n_input = ui.number(value=global_task_manager.max_concurrent_tasks, min=1, max=10).props("outlined dense")
                        def update_max():
                            global_task_manager.max_concurrent_tasks = int(n_input.value)
                            ui.notify(f"已更新最大并发数为 {n_input.value}")
                        ui.button("保存", on_click=update_max).props("flat")

                @ui.refreshable
                def refresh_admin_queue():
                    with ui.card().classes("w-full p-6 shadow-sm border"):
                        ui.label("实时队列").classes("text-lg font-bold mb-4")
                        
                        active = list(global_task_manager.active_tasks.values())
                        waiting = global_task_manager.queue
                        
                        if not active and not waiting:
                            ui.label("当前无活跃任务").classes("text-slate-400 italic")
                            return

                        with ui.column().classes("w-full gap-4"):
                            if active:
                                ui.label(f"正在处理 ({len(active)})").classes("text-sm font-bold text-green-600")
                                for t in active:
                                    with ui.row().classes("w-full p-3 bg-green-50 rounded-lg items-center justify-between"):
                                        with ui.column():
                                            ui.label(t.name).classes("font-bold")
                                            ui.label(f"ID: {t.id} | IP: {t.ip}").classes("text-[10px] text-slate-500 font-mono")
                                        with ui.column().classes("items-end"):
                                            ui.label(t.filename or "无文件").classes("text-xs text-slate-600 truncate max-w-[200px]")
                                            ui.label("正在执行...").classes("text-[10px] text-green-500 animate-pulse")
                            
                            if waiting:
                                ui.label(f"等待中 ({len(waiting)})").classes("text-sm font-bold text-orange-600")
                                for i, t in enumerate(waiting):
                                    with ui.row().classes("w-full p-3 bg-slate-50 rounded-lg items-center justify-between"):
                                        with ui.row().classes("items-center"):
                                            ui.label(str(i+1)).classes("bg-orange-200 text-orange-800 rounded-full w-5 h-5 text-center text-[10px] leading-5 mr-3")
                                            with ui.column():
                                                ui.label(t.name).classes("font-bold text-slate-700")
                                                ui.label(f"ID: {t.id} | IP: {t.ip}").classes("text-[10px] text-slate-500 font-mono")
                                        ui.label(t.filename or "无文件").classes("text-xs text-slate-400")

                refresh_admin_queue()
                ui.timer(2.0, refresh_admin_queue.refresh)

            # --- 访问日志 ---

                

                            with ui.column().classes("w-full hidden") as sections["logs"]:

                

                                ui.label("最近访客").classes("text-2xl font-bold mb-6")

                

                                if state.db_connected:

                

                                    async with database.AsyncSessionLocal() as session:

                

                                        res = await session.execute(select(Guest).order_by(Guest.last_seen.desc()).limit(30))

                

                                        guests = res.scalars().all()

                

                                        

                

                                        if not guests:

                

                                            ui.label("尚无访问记录").classes("text-slate-400 italic")

                

                                        else:

                

                                            with ui.card().classes("w-full p-0 overflow-hidden border shadow-sm"):

                

                                                with ui.column().classes("w-full divide-y"):

                

                                                    for g in guests:

                

                                                        with ui.row().classes("w-full p-4 items-center justify-between hover:bg-slate-50 transition-colors"):

                

                                                            with ui.column().classes("gap-1"):

                

                                                                with ui.row().classes("items-center"):

                

                                                                    ui.icon("public", color="primary", size="xs").classes("mr-2")

                

                                                                    ui.label(g.ip_address).classes("font-mono font-bold text-slate-700")

                

                                                                

                

                                                                # 解析简单的 UA 信息

                

                                                                ua = "Unknown"

                

                                                                if g.metadata_json and isinstance(g.metadata_json, dict):

                

                                                                    ua = g.metadata_json.get("user_agent", "Unknown")

                

                                                                

                

                                                                def parse_ua(ua_str):

                

                                                                    if not ua_str or ua_str == "Unknown": return "未知设备"

                

                                                                    res_browser = "Other"

                

                                                                    if "Chrome" in ua_str: res_browser = "Chrome"

                

                                                                    if "Firefox" in ua_str: res_browser = "Firefox"

                

                                                                    if "Safari" in ua_str and "Chrome" not in ua_str: res_browser = "Safari"

                

                                                                    if "Edge" in ua_str: res_browser = "Edge"

                

                                                                    

                

                                                                    res_os = "Unknown OS"

                

                                                                    if "Windows" in ua_str: res_os = "Windows"

                

                                                                    if "Macintosh" in ua_str: res_os = "macOS"

                

                                                                    if "Android" in ua_str: res_os = "Android"

                

                                                                    if "iPhone" in ua_str: res_os = "iOS"

                

                                                                    if "Linux" in ua_str and "Android" not in ua_str: res_os = "Linux"

                

                                                                    

                

                                                                    return f"{res_browser} on {res_os}"

                

                

                

                                                                with ui.row().classes("items-center text-xs text-slate-500"):

                

                                                                    ui.icon("devices", size="xs").classes("mr-1")

                

                                                                    summary = ui.label(parse_ua(ua))

                

                                                                    with ui.tooltip(ua):

                

                                                                        ui.label(ua).classes("text-xs")

                

                                                            

                

                                                            with ui.column().classes("items-end"):

                

                                                                ui.label(g.last_seen.strftime('%Y-%m-%d')).classes("text-xs font-bold text-slate-600")

                

                                                                ui.label(g.last_seen.strftime('%H:%M:%S')).classes("text-[10px] text-slate-400")

                

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
                    r_user_input = ui.input("管理员用户名").classes("w-full").props('outlined dense')
                    r_code_input = ui.input("重置码").classes("w-full").props('outlined dense')
                    r_code_input.set_visibility(False)
                    
                    new_pwd_input = ui.input("新密码", password=True).classes("w-full").props('outlined dense')
                    new_pwd_input.set_visibility(False)

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
                        
                        print("\n" + "!" * 20 + " 重置验证 (第 1 步) " + "!" * 20, flush=True)
                        print(f"用户: {r_user_input.value} | IP: {client_ip}", flush=True)
                        print(f"验证码 1: {code}", flush=True)
                        print("!" * 60 + "\n", flush=True)
                        import logging
                        logging.getLogger("admin_reset").info(f"RESET_CODE_1: {code} for user {r_user_input.value}")
                        
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
                            print("\n" + "!" * 20 + " 重置验证 (第 2 步) " + "!" * 20, flush=True)
                            print(f"用户: {info['user']} | IP: {client_ip}", flush=True)
                            print(f"验证码 2: {new_code}", flush=True)
                            print("!" * 60 + "\n", flush=True)
                            import logging
                            logging.getLogger("admin_reset").info(f"RESET_CODE_2: {new_code} for user {info['user']}")
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

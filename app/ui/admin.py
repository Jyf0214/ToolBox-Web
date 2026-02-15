from nicegui import ui, app
from fastapi import Request
from sqlalchemy import select, func

from app.core import database
from app.models.models import User
from app.core.auth import is_authenticated
from app.ui.admin_parts.auth import render_login
from app.ui.admin_parts.dashboard import render_dashboard, render_settings, render_smtp
from app.ui.admin_parts.tools import render_tools
from app.ui.admin_parts.system import (
    render_system_status,
    render_maintenance,
    render_update,
    render_queue,
)
from app.ui.admin_parts.logs import render_logs


def create_admin_page(state, load_modules_func, sync_modules_func):
    @ui.page("/admin")
    async def admin_page(request: Request):
        client_ip = request.client.host
        request_host = request.headers.get("host", "")

        # --- 紧急强制校验: 确保不会在有管理员的情况下进入 setup ---
        if state.db_connected:
            try:
                async with database.AsyncSessionLocal() as session:
                    res = await session.execute(
                        select(func.count(User.id)).where(User.is_admin)
                    )
                    if res.scalar() > 0:
                        state.needs_setup = False
            except Exception:
                pass

        if state.needs_setup:
            ui.navigate.to("/setup")
            return

        # --- 管理员访问白名单检查 ---
        from app.core.settings_manager import get_setting

        allowed_hosts_str = await get_setting("admin_allowed_hosts", "")
        if allowed_hosts_str:
            allowed_hosts = [
                h.strip() for h in allowed_hosts_str.split(",") if h.strip()
            ]
            if client_ip not in allowed_hosts and request_host not in allowed_hosts:
                with ui.card().classes(
                    "absolute-center p-8 text-center shadow-lg border-t-4 border-red-500"
                ):
                    ui.icon("block", color="negative", size="xl").classes("mb-4")
                    ui.label("访问被拒绝").classes("text-h5 mb-2")
                    ui.label("您的站点/IP 未在管理员白名单中。").classes(
                        "text-slate-500 mb-4"
                    )
                    ui.label(f"当前 IP: {client_ip}").classes("text-[10px] font-mono")
                    ui.button("回到首页", on_click=lambda: ui.navigate.to("/")).props(
                        "flat"
                    )
                return

        # 如果未登录，直接渲染登录组件并返回
        if not is_authenticated():
            await render_login(client_ip, state, lambda: ui.navigate.to("/admin"))
            return

        # --- 页面内容骨架 (立即响应) ---
        # 使用 Header 和 Drawer 占位，内容通过异步加载

        with ui.header().classes("bg-slate-900 items-center justify-between px-4 py-2"):
            with ui.row().classes("items-center"):
                ui.button(on_click=lambda: left_drawer.toggle(), icon="menu").props(
                    "flat color=white"
                ).classes("sm:hidden")
                ui.label("ToolBox Admin").classes("text-xl font-bold text-white ml-2")

            def logout():
                app.storage.user.update({"authenticated": False})
                ui.navigate.to("/admin")

            ui.button("退出", icon="logout", on_click=logout).props(
                "flat color=white size=sm"
            )

        with ui.left_drawer(value=True).classes("bg-slate-50 border-r") as left_drawer:
            with ui.column().classes("w-full p-4 gap-2"):
                nav_dashboard = (
                    ui.button(
                        "控制面板",
                        icon="dashboard",
                        on_click=lambda: switch_to("dashboard"),
                    )
                    .props("flat align=left")
                    .classes("w-full rounded-lg")
                )
                nav_settings = (
                    ui.button(
                        "设置", icon="settings", on_click=lambda: switch_to("settings")
                    )
                    .props("flat align=left")
                    .classes("w-full rounded-lg")
                )
                nav_tools = (
                    ui.button(
                        "工具管理", icon="build", on_click=lambda: switch_to("tools")
                    )
                    .props("flat align=left")
                    .classes("w-full rounded-lg")
                )
                nav_update = (
                    ui.button(
                        "系统更新",
                        icon="system_update",
                        on_click=lambda: switch_to("update"),
                    )
                    .props("flat align=left")
                    .classes("w-full rounded-lg")
                )
                nav_maintenance = (
                    ui.button(
                        "系统维护",
                        icon="handyman",
                        on_click=lambda: switch_to("maintenance"),
                    )
                    .props("flat align=left")
                    .classes("w-full rounded-lg")
                )
                nav_queue = (
                    ui.button(
                        "队列监控", icon="reorder", on_click=lambda: switch_to("queue")
                    )
                    .props("flat align=left")
                    .classes("w-full rounded-lg")
                )
                nav_status = (
                    ui.button(
                        "运行状态",
                        icon="analytics",
                        on_click=lambda: switch_to("status"),
                    )
                    .props("flat align=left")
                    .classes("w-full rounded-lg")
                )
                nav_logs = (
                    ui.button(
                        "访问日志", icon="list_alt", on_click=lambda: switch_to("logs")
                    )
                    .props("flat align=left")
                    .classes("w-full rounded-lg")
                )

                ui.separator().classes("my-4")
                ui.button(
                    "回到首页", icon="home", on_click=lambda: ui.navigate.to("/")
                ).props("flat align=left").classes("w-full rounded-lg text-slate-600")

        sections = {}

        def switch_to(name):
            for k, v in sections.items():
                v.set_visibility(k == name)

            btns = {
                "dashboard": nav_dashboard,
                "settings": nav_settings,
                "tools": nav_tools,
                "update": nav_update,
                "maintenance": nav_maintenance,
                "queue": nav_queue,
                "status": nav_status,
                "logs": nav_logs,
            }
            for k, btn in btns.items():
                if k == name:
                    btn.classes(add="bg-primary text-white", remove="text-slate-600")
                else:
                    btn.classes(remove="bg-primary text-white", add="text-slate-600")

        # --- 内容容器 ---
        # 页面初始只创建容器，不运行耗时的 render 函数
        main_container = ui.column().classes("p-4 sm:p-8 w-full max-w-5xl mx-auto")
        with main_container:
            sections["dashboard"] = ui.column().classes("w-full")
            sections["settings"] = ui.column().classes("w-full hidden")
            sections["tools"] = ui.column().classes("w-full hidden")
            sections["update"] = ui.column().classes("w-full hidden")
            sections["maintenance"] = ui.column().classes("w-full hidden")
            sections["queue"] = ui.column().classes("w-full hidden")
            sections["status"] = ui.column().classes("w-full hidden")
            sections["logs"] = ui.column().classes("w-full hidden")

        # --- 异步加载数据 (解决 3s 超时) ---
        async def load_all_sections():
            with sections["dashboard"]:
                await render_dashboard(state)
            with sections["settings"]:
                await render_settings(state)
                ui.separator().classes("my-8")
                await render_smtp()
            with sections["tools"]:
                await render_tools(state, load_modules_func, sync_modules_func)
            with sections["update"]:
                await render_update()
            with sections["maintenance"]:
                await render_maintenance(state)
            with sections["queue"]:
                render_queue()
            with sections["status"]:
                await render_system_status(state)
            with sections["logs"]:
                await render_logs(state)

            # 加载完成后激活默认菜单样式
            switch_to("dashboard")

        # 启动后台加载任务，不阻塞页面返回
        ui.timer(0.1, load_all_sections, once=True)

from nicegui import ui, app
from fastapi import Request

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

        if state.needs_setup:
            ui.navigate.to("/setup")
            return

        @ui.refreshable
        async def render_content():
            if not is_authenticated():
                await render_login(client_ip, state, render_content.refresh)
                return

            # --- 侧边栏布局 ---
            with ui.header().classes(
                "bg-slate-900 items-center justify-between px-4 py-2"
            ):
                with ui.row().classes("items-center"):
                    ui.button(on_click=lambda: left_drawer.toggle(), icon="menu").props(
                        "flat color=white"
                    ).classes("sm:hidden")
                    ui.label("ToolBox Admin").classes(
                        "text-xl font-bold text-white ml-2"
                    )

                def logout():
                    app.storage.user.update({"authenticated": False})
                    render_content.refresh()

                ui.button("退出", icon="logout", on_click=logout).props(
                    "flat color=white size=sm"
                )

            with ui.left_drawer(value=True).classes(
                "bg-slate-50 border-r"
            ) as left_drawer:
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
                            "设置",
                            icon="settings",
                            on_click=lambda: switch_to("settings"),
                        )
                        .props("flat align=left")
                        .classes("w-full rounded-lg")
                    )
                    nav_tools = (
                        ui.button(
                            "工具管理",
                            icon="build",
                            on_click=lambda: switch_to("tools"),
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
                            "队列监控",
                            icon="reorder",
                            on_click=lambda: switch_to("queue"),
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
                            "访问日志",
                            icon="list_alt",
                            on_click=lambda: switch_to("logs"),
                        )
                        .props("flat align=left")
                        .classes("w-full rounded-lg")
                    )

                    ui.separator().classes("my-4")
                    ui.button(
                        "回到首页", icon="home", on_click=lambda: ui.navigate.to("/")
                    ).props("flat align=left").classes(
                        "w-full rounded-lg text-slate-600"
                    )

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
                        btn.classes(
                            add="bg-primary text-white", remove="text-slate-600"
                        )
                    else:
                        btn.classes(
                            remove="bg-primary text-white", add="text-slate-600"
                        )

            # --- 内容区域 ---
            with ui.column().classes("p-4 sm:p-8 w-full max-w-5xl mx-auto"):
                with ui.column().classes("w-full") as sections["dashboard"]:
                    await render_dashboard(state)

                with ui.column().classes("w-full hidden") as sections["settings"]:
                    await render_settings(state)
                    ui.separator().classes("my-8")
                    await render_smtp()

                with ui.column().classes("w-full hidden") as sections["tools"]:
                    await render_tools(state, load_modules_func, sync_modules_func)

                with ui.column().classes("w-full hidden") as sections["update"]:
                    await render_update()

                with ui.column().classes("w-full hidden") as sections["maintenance"]:
                    await render_maintenance(state)

                with ui.column().classes("w-full hidden") as sections["queue"]:
                    render_queue()

                with ui.column().classes("w-full hidden") as sections["status"]:
                    await render_system_status(state)

                with ui.column().classes("w-full hidden") as sections["logs"]:
                    await render_logs(state)

            switch_to("dashboard")

        await render_content()

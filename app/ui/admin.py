import asyncio
from nicegui import ui, app
from fastapi import Request
from sqlalchemy import select, func

from app.core import database
from app.core.auth import is_authenticated
from app.ui.auth import render_login
from app.ui.dashboard import render_dashboard, render_settings, render_smtp
from app.ui.tools import render_tools
from app.ui.system import (
    render_system_status,
    render_maintenance,
    render_update,
    render_queue,
)
from app.ui.logs import render_logs


def create_admin_page(state, load_modules_func, sync_modules_func):
    @ui.page("/admin")
    async def admin_page(request: Request):
        client_ip = request.client.host
        request_host = request.headers.get("host", "")

        if state.db_connected:
            try:
                async with database.AsyncSessionLocal() as session:
                    from app.models.models import AdminConfig

                    res = await session.execute(select(func.count(AdminConfig.id)))
                    if res.scalar() > 0:
                        state.needs_setup = False
            except Exception:
                pass

        if state.needs_setup:
            ui.navigate.to("/setup")
            return

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

        if not is_authenticated():
            await render_login(client_ip, state, lambda: ui.navigate.to("/admin"))
            return

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
        loading_spinner = None

        def switch_to(name):
            if not sections:
                return
            for k, v in sections.items():
                if v:
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

        main_container = ui.column().classes("p-4 sm:p-8 w-full max-w-5xl mx-auto")
        with main_container:
            loading_spinner = ui.row().classes("w-full justify-center p-12")
            with loading_spinner:
                ui.spinner(size="lg")
                ui.label("正在加载管理组件...").classes("text-slate-500 ml-4")

            sections["dashboard"] = ui.column().classes("w-full hidden")
            sections["settings"] = ui.column().classes("w-full hidden")
            sections["tools"] = ui.column().classes("w-full hidden")
            sections["update"] = ui.column().classes("w-full hidden")
            sections["maintenance"] = ui.column().classes("w-full hidden")
            sections["queue"] = ui.column().classes("w-full hidden")
            sections["status"] = ui.column().classes("w-full hidden")
            sections["logs"] = ui.column().classes("w-full hidden")

        async def load_all_sections():
            try:
                # 预加载所有组件内容
                async def run_section(name, func):
                    try:
                        with sections[name]:
                            await func() if asyncio.iscoroutinefunction(
                                func
                            ) else func()
                        return True
                    except RuntimeError as e:
                        if "parent slot" in str(e):
                            return False
                        raise
                    except Exception as e:
                        print(f"Error rendering {name}: {e}")
                        try:
                            with sections[name]:
                                ui.label(f"{name} 加载失败: {e}").classes(
                                    "text-negative"
                                )
                        except Exception:
                            pass
                        return True

                if not await run_section("dashboard", lambda: render_dashboard(state)):
                    return

                async def load_settings():
                    await render_settings(state)
                    ui.separator().classes("my-8")
                    await render_smtp()

                if not await run_section("settings", load_settings):
                    return

                if not await run_section(
                    "tools",
                    lambda: render_tools(state, load_modules_func, sync_modules_func),
                ):
                    return
                if not await run_section("update", render_update):
                    return
                if not await run_section(
                    "maintenance", lambda: render_maintenance(state)
                ):
                    return
                if not await run_section("queue", render_queue):
                    return
                if not await run_section("status", lambda: render_system_status(state)):
                    return
                if not await run_section("logs", lambda: render_logs(state)):
                    return

                # 加载完成后隐藏 loading，显示默认 dashboard
                loading_spinner.set_visibility(False)
                switch_to("dashboard")
            except Exception as e:
                print(f"Critical error in load_all_sections: {e}")
                try:
                    ui.notify("管理后台组件初始化发生严重错误", color="negative")
                except Exception:
                    pass

        ui.timer(0.1, load_all_sections, once=True)

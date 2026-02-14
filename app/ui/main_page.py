from fastapi import Request
from nicegui import ui
from sqlalchemy import select

from app.core import database
from app.models.models import Tool
from app.core.config import settings
from app.core.settings_manager import get_setting
from app.core.auth import is_authenticated


def create_main_page(state, modules):
    @ui.page("/")
    async def main_page(request: Request):
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

        with ui.header().classes(
            "items-center justify-between bg-slate-800 p-4 flex-wrap"
        ):
            with ui.row().classes("items-center"):
                ui.label(site_title).classes("text-2xl font-bold text-white")
                ui.label(f"v{settings.VERSION}").classes("text-xs text-slate-300 ml-2")
            if state.db_connected:
                ui.button(
                    icon="settings", on_click=lambda: ui.navigate.to("/admin")
                ).props("flat color=white")

        if not modules:
            ui.label("未加载任何模块。").classes("p-8 text-center w-full")
        else:
            enabled_modules = []
            if state.db_connected:
                async with database.AsyncSessionLocal() as session:
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
                enabled_modules = modules

            if not enabled_modules:
                ui.label("当前没有可用的工具。").classes("p-8 text-center w-full")
            else:
                with ui.tabs().classes("w-full overflow-x-auto") as tabs:
                    for m in enabled_modules:
                        ui.tab(m.name, icon=m.icon)
                with ui.tab_panels(tabs, value=enabled_modules[0].name).classes(
                    "w-full"
                ):
                    for m in enabled_modules:
                        with ui.tab_panel(m.name):
                            m.setup_ui()

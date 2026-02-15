from nicegui import ui
from sqlalchemy import select
from app.core import database
from app.models.models import Tool, Guest
from app.core.config import settings
from app.core.settings_manager import get_setting, set_setting


async def render_dashboard(state):
    ui.label("控制面板").classes("text-2xl font-bold mb-6")
    with ui.row().classes("w-full gap-4"):

        async def get_stats():
            if not state.db_connected:
                return 0, 0
            async with database.AsyncSessionLocal() as session:
                tc = len((await session.execute(select(Tool))).scalars().all())
                gc = len((await session.execute(select(Guest))).scalars().all())
                return tc, gc

        tc, gc = await get_stats()
        for val, label, color in [
            (tc, "总工具", "primary"),
            (gc, "历史访客", "secondary"),
        ]:
            with ui.card().classes("flex-1 p-6 items-center shadow-sm border"):
                ui.label(str(val)).classes(f"text-3xl font-bold text-{color}")
                ui.label(label).classes("text-slate-500 text-sm")


async def render_settings(state):
    ui.label("站点设置").classes("text-2xl font-bold mb-6")
    with ui.card().classes("w-full p-6 shadow-sm border"):
        curr_name = await get_setting("site_name", settings.SITE_NAME)
        name_in = (
            ui.input("站点名称", value=curr_name).classes("w-full").props("outlined")
        )

        async def save():
            await set_setting("site_name", name_in.value)
            ui.notify("已保存")

        if not state.db_connected:
            ui.button("保存", on_click=save).classes("mt-4").disable()
        else:
            ui.button("保存", on_click=save).classes("mt-4")


async def render_smtp():
    ui.label("邮件设置").classes("text-2xl font-bold mb-6")
    with ui.card().classes("w-full p-6"):
        smtp_enabled = await get_setting("smtp_enabled") == "true"
        en = ui.switch("启用通知", value=smtp_enabled)
        host = ui.input("SMTP 主机", value=await get_setting("smtp_host")).classes(
            "w-full"
        )
        user = ui.input("用户名", value=await get_setting("smtp_user")).classes(
            "w-full"
        )
        pwd = ui.input(
            "密码", password=True, value=await get_setting("smtp_password")
        ).classes("w-full")

        async def save_m():
            await set_setting("smtp_enabled", str(en.value).lower())
            await set_setting("smtp_host", host.value)
            await set_setting("smtp_user", user.value)
            await set_setting("smtp_password", pwd.value)
            ui.notify("设置已保存")

        ui.button("保存", on_click=save_m).classes("mt-4")

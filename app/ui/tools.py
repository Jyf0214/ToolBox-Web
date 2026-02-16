from nicegui import ui
from sqlalchemy import select, update
from app.core import database
from app.models.models import Tool


async def render_tools(state, load_modules_func, sync_modules_func):
    ui.label("工具管理").classes("text-2xl font-bold mb-6")

    @ui.refreshable
    async def tool_list():
        if not state.db_connected:
            return
        async with database.AsyncSessionLocal() as session:
            tools = (
                (await session.execute(select(Tool).order_by(Tool.id))).scalars().all()
            )
            with ui.grid(columns=(1, "md:2")).classes("w-full gap-4"):
                for t in tools:
                    with ui.card().classes("p-4 shadow-sm border"):
                        with ui.row().classes("w-full justify-between items-start"):
                            with ui.column():
                                ui.label(t.display_name).classes("font-bold")
                                if t.rate_limit_count > 0:
                                    ui.badge(
                                        f"{t.rate_limit_count}/{t.rate_limit_period}s",
                                        color="orange",
                                    )
                            with ui.column().classes("items-end"):

                                async def upd(field, value, name=t.name):
                                    async with database.AsyncSessionLocal() as s:
                                        await s.execute(
                                            update(Tool)
                                            .where(Tool.name == name)
                                            .values({field: value})
                                        )
                                        await s.commit()
                                    ui.notify("已更新")

                                ui.switch(
                                    "启用",
                                    value=t.is_enabled,
                                    on_change=lambda e, f="is_enabled": upd(f, e.value),
                                ).props("dense")
                                ui.button(
                                    icon="settings",
                                    on_click=lambda tobj=t: open_tool_settings(tobj),
                                ).props("flat dense size=sm")

    def open_tool_settings(t_obj):
        with ui.dialog() as d, ui.card().classes("p-6"):
            ui.label(f"配置 {t_obj.display_name}").classes("text-lg mb-4")
            cnt = ui.number("限制次数", value=t_obj.rate_limit_count).classes("w-full")
            per = ui.number("秒数", value=t_obj.rate_limit_period).classes("w-full")
            cap = ui.switch(
                "开启人机验证 (Cloudflare)", value=t_obj.requires_captcha
            ).classes("mt-2")

            async def sv():
                async with database.AsyncSessionLocal() as s:
                    await s.execute(
                        update(Tool)
                        .where(Tool.name == t_obj.name)
                        .values(
                            {
                                "rate_limit_count": int(cnt.value),
                                "rate_limit_period": int(per.value),
                                "requires_captcha": cap.value,
                            }
                        )
                    )
                    await s.commit()
                ui.notify("已保存")
                d.close()
                tool_list.refresh()

            ui.button("确定", on_click=sv)
        d.open()

    await tool_list()

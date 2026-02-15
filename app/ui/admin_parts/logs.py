from nicegui import ui
from sqlalchemy import select
from app.core import database
from app.models.models import Guest


async def render_logs(state):
    ui.label("最近访客").classes("text-2xl font-bold mb-6")
    if not state.db_connected:
        ui.label("数据库未连接").classes("text-negative")
        return

    async with database.AsyncSessionLocal() as session:
        gs = (
            (
                await session.execute(
                    select(Guest).order_by(Guest.last_seen.desc()).limit(30)
                )
            )
            .scalars()
            .all()
        )
        if not gs:
            ui.label("暂无访问记录").classes("text-slate-400 italic")
            return

        with ui.card().classes("w-full p-0 overflow-hidden border shadow-sm"):
            with ui.column().classes("w-full divide-y"):
                for g in gs:
                    with ui.row().classes(
                        "w-full p-4 items-center justify-between hover:bg-slate-50 transition-colors"
                    ):
                        with ui.column():
                            ui.label(g.ip_address).classes("font-mono font-bold")
                            if g.metadata_json and "user_agent" in g.metadata_json:
                                ua = g.metadata_json["user_agent"]
                                ui.label(
                                    ua[:60] + "..." if len(ua) > 60 else ua
                                ).classes("text-[10px] text-slate-400")
                        ui.label(g.last_seen.strftime("%m-%d %H:%M")).classes(
                            "text-xs text-slate-500"
                        )

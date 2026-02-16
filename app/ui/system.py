import asyncio
from nicegui import ui
from sqlalchemy import select, text
from app.core import database
from app.models.models import TaskHistory
from app.core.task_manager import global_task_manager
from app.core.updater import (
    check_for_updates,
    pull_updates,
    check_critical_changes,
    get_local_changelog,
    get_remote_changelog,
)


async def render_system_status(state):
    ui.label("系统状态").classes("text-2xl font-bold mb-6")
    with ui.grid(columns=(1, "md:3")).classes("w-full gap-4 mb-6"):
        c_lab = ui.label("CPU: -")
        m_lab = ui.label("MEM: -")

        async def update_stats():
            s = global_task_manager.get_system_stats()
            c_lab.set_text(f"CPU: {s['cpu_percent']}%")
            m_lab.set_text(
                f"MEM: {s['memory_percent']}% ({s['memory_available']}G Free)"
            )

        ui.timer(2.0, update_stats)

    @ui.refreshable
    async def history_list():
        if not state.db_connected:
            return
        async with database.AsyncSessionLocal() as s:
            tasks = (
                (
                    await s.execute(
                        select(TaskHistory)
                        .order_by(TaskHistory.completed_at.desc())
                        .limit(20)
                    )
                )
                .scalars()
                .all()
            )
            with ui.card().classes("w-full p-4 shadow-sm border"):
                ui.label("历史任务").classes("font-bold mb-2")
                for t in tasks:
                    ui.label(
                        f"{t.completed_at.strftime('%H:%M')} | {t.task_name} | {t.status}"
                    ).classes("text-xs border-b py-1")

    await history_list()
    ui.timer(5.0, history_list.refresh)


async def render_maintenance(state):
    ui.label("系统维护").classes("text-2xl font-bold mb-6")
    with ui.card().classes("p-4 w-full shadow-sm border"):
        ui.label("数据库清理").classes("font-bold mb-2")

        async def clean_db():
            from sqlalchemy import inspect

            async with database.engine.connect() as c:
                db_ts = await c.run_sync(lambda conn: inspect(conn).get_table_names())
                md_ts = set(database.Base.metadata.tables.keys())
                orphans = [t for t in db_ts if t not in md_ts]
                if not orphans:
                    ui.notify("数据库很干净")
                    return
                async with database.engine.begin() as cb:
                    for t in orphans:
                        await cb.execute(text(f"DROP TABLE `{t}`"))
                ui.notify(f"已清理 {len(orphans)} 张冗余表")

        ui.button("扫描并清理冗余表", on_click=clean_db).props("outline color=negative")


async def render_update():
    ui.label("系统更新").classes("text-2xl font-bold mb-6")
    with ui.card().classes("w-full p-8 shadow-sm border"):
        status_lab = ui.label("就绪").classes("text-lg mb-4 text-center w-full")
        warn_card = ui.card().classes("w-full mb-4 bg-orange-50 hidden")
        with warn_card:
            ui.label("⚠️ 检测到核心环境变动，建议重构镜像").classes(
                "p-4 text-orange-800 font-bold"
            )

        changelog_cont = ui.column().classes("w-full hidden")
        with changelog_cont:
            with ui.row().classes("w-full gap-4 h-64"):
                l_scroll = ui.scroll_area().classes("flex-1 border p-2 bg-slate-50")
                r_scroll = ui.scroll_area().classes("flex-1 border p-2 bg-blue-50")

        async def check():
            status_lab.set_text("同步中...")
            has_up, _, _, msg = await asyncio.get_event_loop().run_in_executor(
                None, check_for_updates
            )
            crit = await asyncio.get_event_loop().run_in_executor(
                None, check_critical_changes
            )
            warn_card.set_visibility(len(crit) > 0)

            _, ll = get_local_changelog()
            _, rl = await asyncio.get_event_loop().run_in_executor(
                None, get_remote_changelog
            )

            l_scroll.clear()
            r_scroll.clear()
            with l_scroll:
                ui.markdown(ll)
            with r_scroll:
                ui.markdown(rl)

            changelog_cont.set_visibility(True)
            status_lab.set_text(msg)
            pull_btn.set_visibility(has_up)

        with ui.row().classes("w-full justify-center gap-4"):
            ui.button("检查更新", on_click=check)
            pull_btn = (
                ui.button("开始更新", on_click=lambda: do_up())
                .classes("hidden")
                .props("color=positive")
            )

        async def do_up():
            await asyncio.get_event_loop().run_in_executor(None, pull_updates)
            ui.notify("更新成功")


def render_queue():
    ui.label("队列监控").classes("text-2xl font-bold mb-6")

    @ui.refreshable
    def q_list():
        active = list(global_task_manager.active_tasks.values())
        waiting = global_task_manager.queue
        with ui.card().classes("w-full p-4 shadow-sm border"):
            ui.label(f"活跃: {len(active)} | 等待: {len(waiting)}").classes(
                "font-bold mb-4"
            )
            for t in active:
                ui.label(f"● {t.name} ({t.id[:8]}) - 处理中").classes(
                    "text-green-600 text-sm"
                )
            for i, t in enumerate(waiting):
                ui.label(f"{i + 1}. {t.name} ({t.id[:8]}) - 等待中").classes(
                    "text-slate-500 text-sm"
                )

    q_list()
    ui.timer(2.0, q_list.refresh)

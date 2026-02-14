import asyncio
from nicegui import ui, app
from sqlalchemy import select, update

from app.core import database
from app.models.models import Tool, User, Guest
from app.core.config import settings
from app.core.settings_manager import get_setting, set_setting
from app.core.auth import is_authenticated, verify_password
from app.core.updater import check_for_updates, pull_updates


def create_admin_page(state, load_modules_func, sync_modules_func):
    @ui.page("/admin")
    async def admin_page():
        try:
            await asyncio.wait_for(state.initialized.wait(), timeout=10)
        except asyncio.TimeoutError:
            ui.notify("数据库连接超时。", color="negative")
            return

        if state.needs_setup:
            ui.navigate.to("/setup")
            return

        if not is_authenticated():
            with ui.card().classes("absolute-center w-[90vw] max-w-xs shadow-lg p-6"):
                ui.label("管理登录").classes("text-h6 mb-2")
                if not state.db_connected:
                    ui.label("注意：数据库当前未连接，登录将无法进行。").classes(
                        "text-negative text-xs mb-4"
                    )

                pwd = ui.input("密码", password=True).classes("w-full")

                async def login():
                    if not state.db_connected:
                        ui.notify(
                            "无法登录：数据库连接失败，请检查数据库配置。",
                            color="negative",
                        )
                        return

                    async with database.AsyncSessionLocal() as session:
                        result = await session.execute(
                            select(User).where(User.is_admin)
                        )
                        admin = result.scalars().first()
                        if admin and verify_password(pwd.value, admin.hashed_password):
                            app.storage.user.update({"authenticated": True})
                            ui.navigate.to("/admin")
                        else:
                            ui.notify("凭据无效", color="negative")

                ui.button("登录", on_click=login).classes("w-full mt-2")
            return

        # --- 管理界面头部 ---
        with ui.header().classes(
            "bg-slate-900 items-center justify-between p-4 flex-wrap"
        ):
            with ui.row().classes("items-center"):
                ui.label("管理后台").classes("text-xl text-white")
                ui.label(f"v{settings.VERSION}").classes("text-xs text-slate-400 ml-2")
            with ui.row().classes("items-center"):
                ui.button("首页", on_click=lambda: ui.navigate.to("/")).props(
                    "flat color=white"
                )
                ui.button(
                    "登出",
                    on_click=lambda: (
                        app.storage.user.update({"authenticated": False}),
                        ui.navigate.to("/"),
                    ),
                ).props("flat color=white")

        with ui.column().classes("p-4 sm:p-8 w-full max-w-2xl mx-auto"):
            # 站点设置
            ui.label("设置").classes("text-2xl mb-4")
            current_name = await get_setting("site_name", settings.SITE_NAME)

            name_input = ui.input("站点名称", value=current_name).classes("w-full")
            if not state.db_connected:
                name_input.disable()

            ui.button(
                "保存",
                on_click=lambda: (
                    set_setting("site_name", name_input.value),
                    ui.notify("已保存"),
                ),
            ).classes("mt-2").disable() if not state.db_connected else None

            ui.separator().classes("my-8")

            # 工具管理
            with ui.row().classes("w-full items-center justify-between mb-4"):
                ui.label("工具管理").classes("text-2xl")

                async def handle_refresh():
                    load_modules_func()
                    await sync_modules_func()
                    ui.notify("已重新扫描模块文件夹")
                    ui.navigate.to("/admin")

                ui.button("刷新工具列表", on_click=handle_refresh).props(
                    "flat icon=refresh"
                )

            if not state.db_connected:
                ui.label("工具管理不可用（数据库未连接）。").classes("text-negative")
            else:

                async def toggle_tool(tool_name, field, value):
                    async with database.AsyncSessionLocal() as session:
                        await session.execute(
                            update(Tool)
                            .where(Tool.name == tool_name)
                            .values({field: value})
                        )
                        await session.commit()
                    ui.notify(f"已更新 {tool_name}")

                async with database.AsyncSessionLocal() as session:
                    result = await session.execute(select(Tool).order_by(Tool.id))
                    tools = result.scalars().all()
                    for t in tools:
                        with ui.card().classes("w-full p-4 mb-4"):
                            with ui.row().classes(
                                "w-full items-center justify-between"
                            ):
                                with ui.column():
                                    ui.label(t.display_name).classes(
                                        "text-lg font-bold"
                                    )
                                    ui.label(f"ID: {t.name}").classes(
                                        "text-xs text-slate-500"
                                    )
                                with ui.row().classes("items-center gap-4"):
                                    ui.switch(
                                        "启用",
                                        value=t.is_enabled,
                                        on_change=lambda e, name=t.name: toggle_tool(
                                            name, "is_enabled", e.value
                                        ),
                                    )
                                    ui.switch(
                                        "游客可用",
                                        value=t.is_guest_allowed,
                                        on_change=lambda e, name=t.name: toggle_tool(
                                            name, "is_guest_allowed", e.value
                                        ),
                                    )

            # 系统更新
            ui.separator().classes("my-8")
            ui.label("系统更新").classes("text-2xl mb-4")
            status_label = ui.label("点击检查更新").classes("text-slate-600 mb-4")
            info_label = ui.label("").classes("text-sm text-slate-500 mb-4")
            update_btn = ui.button("检查更新")

            async def check_update():
                update_btn.disable()
                status_label.set_text("正在检查...")
                try:
                    (
                        has_up,
                        local,
                        remote,
                        msg,
                    ) = await asyncio.get_event_loop().run_in_executor(
                        None, check_for_updates
                    )
                    status_label.set_text(msg)
                    if has_up:
                        info_label.set_text(f"{local} -> {remote}")
                        update_btn.set_text("立即拉取")
                        update_btn.on_click(pull_update)
                except Exception as e:
                    status_label.set_text(f"错误: {e}")
                finally:
                    update_btn.enable()

            async def pull_update():
                update_btn.disable()
                status_label.set_text("拉取中...")
                try:
                    success, msg = await asyncio.get_event_loop().run_in_executor(
                        None, pull_updates
                    )
                    status_label.set_text(msg)
                    if success:
                        ui.notify("请重启应用")
                except Exception as e:
                    status_label.set_text(f"错误: {e}")
                finally:
                    update_btn.enable()

            update_btn.on_click(check_update)

            # 最近访客
            ui.separator().classes("my-8")
            ui.label("最近访客").classes("text-2xl mb-4")
            if state.db_connected:
                async with database.AsyncSessionLocal() as session:
                    res = await session.execute(
                        select(Guest).order_by(Guest.last_seen.desc()).limit(10)
                    )
                    for g in res.scalars().all():
                        ui.label(
                            f"{g.ip_address} - {g.last_seen.strftime('%Y-%m-%d %H:%M:%S')}"
                        ).classes("text-sm")

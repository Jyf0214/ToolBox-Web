import asyncio
from nicegui import ui, app
from sqlalchemy import select, update

from app.core import database
from app.models.models import Tool, User, Guest
from app.core.config import settings
from app.core.settings_manager import get_setting, set_setting
from app.core.auth import is_authenticated, verify_password
from app.core.updater import check_for_updates, pull_updates


import secrets
import string
import time
from fastapi import Request

from app.core.auth import get_password_hash

# 存储重置码及其过期时间、IP 频率限制
# 格式: {ip: {"code": str, "expires": float, "attempts": int, "last_request": float}}
reset_data = {}


def create_admin_page(state, load_modules_func, sync_modules_func):
    @ui.page("/admin")
    async def admin_page(request: Request):
        client_ip = request.client.host

        if state.needs_setup:
            ui.navigate.to("/setup")
            return

        if not is_authenticated():
            with ui.card().classes("absolute-center w-[90vw] max-w-sm shadow-lg p-6"):
                ui.label("管理登录").classes("text-h6 mb-2")
                if not state.db_connected:
                    ui.label("注意：数据库当前未连接，登录将无法进行。").classes(
                        "text-negative text-xs mb-4"
                    )

                user_input = ui.input("用户名").classes("w-full")
                pwd = ui.input("密码", password=True).classes("w-full")

                async def login():
                    if not state.db_connected:
                        ui.notify(
                            "无法登录：数据库连接失败，请检查数据库配置。",
                            color="negative",
                        )
                        return

                    if not user_input.value or not pwd.value:
                        ui.notify("用户名和密码不能为空", color="warning")
                        return

                    try:
                        async with database.AsyncSessionLocal() as session:
                            result = await session.execute(
                                select(User).where(
                                    User.username == user_input.value,
                                    User.is_admin,
                                )
                            )
                            admin = result.scalars().first()

                            if admin:
                                if verify_password(pwd.value, admin.hashed_password):
                                    app.storage.user.update({"authenticated": True})
                                    ui.notify("登录成功", color="positive")
                                    ui.navigate.to("/admin")
                                else:
                                    ui.notify("用户名或密码错误", color="negative")
                            else:
                                ui.notify("用户名或密码错误", color="negative")
                    except Exception as e:
                        ui.notify(f"登录过程出错: {e}", color="negative")

                pwd.on("keydown.enter", login)
                user_input.on("keydown.enter", login)
                ui.button("登录", on_click=login).classes("w-full mt-4")

                # --- 忘记密码逻辑 ---
                with ui.row().classes("w-full justify-center mt-2"):
                    ui.button(
                        "忘记密码？",
                        on_click=lambda: reset_dialog.open(),
                    ).props("flat size=sm color=grey")

                # 重置密码对话框
                with ui.dialog() as reset_dialog, ui.card().classes("w-full max-md"):
                    ui.label("重置管理员密码").classes("text-h6")
                    ui.label(
                        "出于安全考虑，点击下方按钮后，重置码将打印在服务器终端。"
                    ).classes("text-xs text-slate-500 mb-4")

                    with ui.column().classes("w-full gap-4"):
                        reset_user_input = ui.input("管理员用户名").classes("w-full")
                        code_input = ui.input("请输入 32 位重置码").classes("w-full")
                        new_pwd_input = ui.input("新密码", password=True).classes(
                            "w-full"
                        )

                        async def request_code():
                            if not reset_user_input.value:
                                ui.notify("请输入要重置的用户名", color="warning")
                                return

                            now = time.time()
                            ip_info = reset_data.get(client_ip, {"last_request": 0})

                            # 频率限制：每 60 秒只能请求一次
                            if now - ip_info["last_request"] < 60:
                                ui.notify("请求太频繁，请稍后再试", color="warning")
                                return

                            # 生成 32 位随机字符
                            alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                            code = "".join(secrets.choice(alphabet) for _ in range(32))

                            reset_data[client_ip] = {
                                "code": code,
                                "user": reset_user_input.value,
                                "expires": now + 600,  # 10 分钟有效
                                "last_request": now,
                            }

                            print("\n" + "=" * 50)
                            print(
                                f"管理员密码重置码 (用户: {reset_user_input.value}, 来自 IP: {client_ip}):"
                            )
                            print(f"CODE: {code}")
                            print("=" * 50 + "\n")

                            ui.notify("重置码已发送至终端", color="positive")

                        async def perform_reset():
                            info = reset_data.get(client_ip)
                            if (
                                not info
                                or info["code"] != code_input.value
                                or info["user"] != reset_user_input.value
                            ):
                                ui.notify("验证信息错误", color="negative")
                                return

                            if time.time() > info["expires"]:
                                ui.notify("重置码已过期", color="warning")
                                return

                            if not new_pwd_input.value:
                                ui.notify("请输入新密码", color="warning")
                                return

                            try:
                                async with database.AsyncSessionLocal() as session:
                                    # 验证用户是否存在且为管理员
                                    res = await session.execute(
                                        select(User).where(
                                            User.username == reset_user_input.value,
                                            User.is_admin,
                                        )
                                    )
                                    admin_user = res.scalars().first()
                                    if not admin_user:
                                        ui.notify(
                                            "指定用户不存在或非管理员", color="negative"
                                        )
                                        return

                                    await session.execute(
                                        update(User)
                                        .where(User.username == reset_user_input.value)
                                        .values(
                                            hashed_password=get_password_hash(
                                                new_pwd_input.value
                                            )
                                        )
                                    )
                                    await session.commit()

                                ui.notify("密码已成功重置，请登录", color="positive")
                                reset_dialog.close()
                                del reset_data[client_ip]
                            except Exception as e:
                                ui.notify(f"重置失败: {e}", color="negative")

                        with ui.row().classes("w-full justify-between mt-4"):
                            ui.button("获取重置码", on_click=request_code).props(
                                "outline"
                            )
                            ui.button("确认修改", on_click=perform_reset)
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

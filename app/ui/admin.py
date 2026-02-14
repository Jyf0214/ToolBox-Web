import asyncio
import secrets
import string
import time
from nicegui import ui, app
from fastapi import Request
from sqlalchemy import select, update

from app.core import database
from app.models.models import Tool, User, Guest
from app.core.config import settings
from app.core.settings_manager import get_setting, set_setting
from app.core.auth import is_authenticated, verify_password, get_password_hash
from app.core.updater import check_for_updates, pull_updates

# 存储重置数据
# 格式: {ip: {"code": str, "user": str, "expires": float, "step": int, "last_request": float}}
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
                        ui.notify("无法登录：数据库连接失败", color="negative")
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
                            if admin and verify_password(
                                pwd.value, admin.hashed_password
                            ):
                                app.storage.user.update({"authenticated": True})
                                ui.notify("登录成功", color="positive")
                                ui.navigate.to("/admin")
                            else:
                                ui.notify("用户名或密码错误", color="negative")
                    except Exception as e:
                        ui.notify(f"登录过程出错: {e}", color="negative")

                pwd.on("keydown.enter", login)
                user_input.on("keydown.enter", login)
                ui.button("登录", on_click=login).classes("w-full mt-4")

                with ui.row().classes("w-full justify-center mt-2"):
                    ui.button("忘记密码？", on_click=lambda: reset_dialog.open()).props(
                        "flat size=sm color=grey"
                    )

                # --- 重置密码/数据库对话框 ---
                with ui.dialog() as reset_dialog, ui.card().classes("w-full max-w-md"):
                    ui.label("安全验证与维护").classes("text-h6")
                    status_msg = ui.label("请输入管理员用户名以开始验证").classes(
                        "text-xs text-slate-500 mb-4"
                    )

                    with ui.column().classes("w-full gap-4"):
                        r_user_input = ui.input("管理员用户名").classes("w-full")
                        r_code_input = ui.input("重置码").classes("w-full hidden")
                        new_pwd_input = ui.input("新密码", password=True).classes(
                            "w-full hidden"
                        )

                        def generate_random_code():
                            alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
                            return "".join(secrets.choice(alphabet) for _ in range(32))

                        async def request_code():
                            if not r_user_input.value:
                                ui.notify("请输入用户名", color="warning")
                                return

                            now = time.time()
                            ip_info = reset_data.get(client_ip, {"last_request": 0})
                            if now - ip_info["last_request"] < 60:
                                ui.notify("请求太频繁", color="warning")
                                return

                            code = generate_random_code()
                            reset_data[client_ip] = {
                                "code": code,
                                "user": r_user_input.value,
                                "expires": now + 600,
                                "step": 1,
                                "last_request": now,
                            }

                            print("\n" + "!" * 20 + " 重置验证 (第 1 步) " + "!" * 20)
                            print(f"用户: {r_user_input.value} | IP: {client_ip}")
                            print(f"验证码 1: {code}")
                            print("!" * 60 + "\n")

                            r_code_input.set_visibility(True)
                            r_user_input.disable()
                            status_msg.set_text(
                                "第 1 次验证：请输入终端显示的 32 位重置码"
                            )
                            req_btn.set_visibility(False)
                            verify_btn.set_visibility(True)
                            ui.notify("验证码 1 已发送至终端", color="positive")

                        async def verify_step():
                            info = reset_data.get(client_ip)
                            if not info or time.time() > info["expires"]:
                                ui.notify("验证已超时，请重新开始", color="warning")
                                reset_dialog.close()
                                return

                            if r_code_input.value != info["code"]:
                                ui.notify("验证码错误", color="negative")
                                return

                            if info["step"] == 1:
                                # 进入第二步验证
                                new_code = generate_random_code()
                                info["code"] = new_code
                                info["step"] = 2
                                r_code_input.value = ""
                                status_msg.set_text(
                                    "第 2 次验证：请输入终端显示的【新】验证码"
                                )

                                print(
                                    "\n" + "!" * 20 + " 重置验证 (第 2 步) " + "!" * 20
                                )
                                print(f"用户: {info['user']} | IP: {client_ip}")
                                print(f"验证码 2: {new_code}")
                                print("!" * 60 + "\n")
                                ui.notify("验证码 2 已发送至终端", color="info")

                            elif info["step"] == 2:
                                # 验证全部通过
                                status_msg.set_text(
                                    "双重验证通过！您可以重置密码或清理数据库。"
                                )
                                r_code_input.set_visibility(False)
                                new_pwd_input.set_visibility(True)
                                verify_btn.set_visibility(False)
                                action_row.set_visibility(True)
                                ui.notify("身份确认成功", color="positive")

                        async def reset_password():
                            info = reset_data.get(client_ip)
                            if not new_pwd_input.value:
                                ui.notify("请输入新密码", color="warning")
                                return
                            try:
                                async with database.AsyncSessionLocal() as session:
                                    res = await session.execute(
                                        select(User).where(
                                            User.username == info["user"], User.is_admin
                                        )
                                    )
                                    admin_user = res.scalars().first()
                                    if not admin_user:
                                        ui.notify("权限验证失败", color="negative")
                                        return
                                    admin_user.hashed_password = get_password_hash(
                                        new_pwd_input.value
                                    )
                                    await session.commit()
                                ui.notify("密码已重置", color="positive")
                                reset_dialog.close()
                                del reset_data[client_ip]
                            except Exception as e:
                                ui.notify(f"重置失败: {e}", color="negative")

                        async def dangerous_reset_db():
                            try:
                                print(f"CRITICAL: IP {client_ip} 正在重置整个数据库！")
                                async with database.engine.begin() as conn:
                                    from app.core.database import Base

                                    await conn.run_sync(Base.metadata.drop_all)
                                    await conn.run_sync(Base.metadata.create_all)

                                ui.notify("数据库已彻底重置", color="positive")
                                state.needs_setup = True
                                del reset_data[client_ip]
                                reset_dialog.close()
                                await asyncio.sleep(1)
                                ui.navigate.to("/setup")
                            except Exception as e:
                                ui.notify(f"数据库重置失败: {e}", color="negative")

                        req_btn = ui.button(
                            "获取重置码", on_click=request_code
                        ).classes("w-full")
                        verify_btn = ui.button("验证", on_click=verify_step).classes(
                            "w-full hidden"
                        )

                        with ui.row().classes(
                            "w-full justify-between hidden"
                        ) as action_row:
                            ui.button("重置密码", on_click=reset_password).props(
                                "color=primary"
                            )
                            with ui.button("重置数据库", icon="warning").props(
                                "color=negative"
                            ):
                                with ui.menu():
                                    ui.menu_item(
                                        "确认彻底删除所有数据？",
                                        on_click=dangerous_reset_db,
                                    )

                        with ui.row().classes("w-full justify-end mt-4"):
                            ui.button("取消", on_click=reset_dialog.close).props("flat")
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

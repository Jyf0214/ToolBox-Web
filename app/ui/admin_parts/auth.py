import time
import secrets
import string
from nicegui import ui, app
from sqlalchemy import select
from app.core import database
from app.models.models import User
from app.core.auth import verify_password, verify_turnstile
from app.core.settings_manager import get_setting

# 登录限流配置
login_attempts = {}
MAX_ATTEMPTS = 5
LOCKOUT_TIME = 300
reset_data = {}


async def render_login(client_ip, state, on_success):
    # 获取配置
    site_key = await get_setting("cf_turnstile_site_key", "")
    secret_key = await get_setting("cf_turnstile_secret_key", "")

    # 注入 Cloudflare 脚本
    if site_key:
        ui.add_head_html(
            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>'
        )

    now = time.time()
    if client_ip in login_attempts:
        attempts = login_attempts[client_ip]
        if (
            attempts["count"] >= MAX_ATTEMPTS
            and now - attempts["last_attempt"] < LOCKOUT_TIME
        ):
            remaining = int(LOCKOUT_TIME - (now - attempts["last_attempt"]))
            with ui.card().classes(
                "absolute-center w-[90vw] max-w-sm shadow-xl p-8 text-center"
            ):
                ui.icon("lock", color="negative").classes("text-6xl mb-4")
                ui.label("访问受限").classes("text-h5 mb-2")
                ui.label(f"登录失败次数过多。请在 {remaining} 秒后再试。").classes(
                    "text-slate-500"
                )
            return

    with ui.card().classes(
        "absolute-center w-[90vw] max-w-sm shadow-2xl p-0 overflow-hidden border-t-4 border-primary"
    ):
        with ui.column().classes("p-8 w-full"):
            with ui.row().classes("w-full items-center justify-center mb-6"):
                ui.icon("admin_panel_settings", color="primary").classes(
                    "text-4xl mr-2"
                )
                ui.label("管理控制台").classes("text-h5 font-bold")

            if not state.db_connected:
                with ui.row().classes(
                    "w-full bg-red-50 p-3 rounded-lg mb-4 items-center"
                ):
                    ui.icon("error", color="negative").classes("text-lg mr-2")
                    ui.label("数据库未连接").classes("text-negative text-xs")

            user_input = (
                ui.input("用户名")
                .classes("w-full mb-2")
                .props('outlined dense prepend-icon="person"')
            )
            pwd = (
                ui.input("密码", password=True)
                .classes("w-full mb-6")
                .props('outlined dense prepend-icon="lock"')
            )

            # Cloudflare Turnstile 容器
            if site_key:
                with ui.element("div").classes("w-full flex justify-center mb-4"):
                    ui.html(
                        f'<div class="cf-turnstile" data-sitekey="{site_key}"></div>'
                    )

            async def login():
                if not state.db_connected:
                    ui.notify("数据库未连接", color="negative")
                    return
                if not user_input.value or not pwd.value:
                    ui.notify("请输入账号密码", color="warning")
                    return

                # 验证 CAPTCHA
                if site_key and secret_key:
                    # 从浏览器获取 turnstile 的响应 token
                    token = await ui.run_javascript(
                        'try { return turnstile.getResponse(); } catch(e) { return ""; }'
                    )
                    if not token:
                        ui.notify("请先完成人机验证", color="warning")
                        return
                    is_human = await verify_turnstile(token, secret_key)
                    if not is_human:
                        ui.notify("验证码验证失败，请重试", color="negative")
                        # 失败后重置验证码
                        await ui.run_javascript(
                            "try { turnstile.reset(); } catch(e) {}"
                        )
                        return

                if client_ip not in login_attempts:
                    login_attempts[client_ip] = {"count": 0, "last_attempt": 0}

                async with database.AsyncSessionLocal() as session:
                    res = await session.execute(
                        select(User).where(
                            User.username == user_input.value, User.is_admin
                        )
                    )
                    admin = res.scalars().first()
                    if admin and verify_password(pwd.value, admin.hashed_password):
                        login_attempts[client_ip] = {"count": 0, "last_attempt": 0}
                        app.storage.user["authenticated"] = True
                        ui.notify("登录成功", color="positive")
                        on_success()
                    else:
                        login_attempts[client_ip]["count"] += 1
                        login_attempts[client_ip]["last_attempt"] = time.time()
                        rem = MAX_ATTEMPTS - login_attempts[client_ip]["count"]
                        msg = "账号或密码错误"
                        if rem > 0:
                            msg += f"，还可尝试 {rem} 次"
                        else:
                            msg += "，IP 已锁定"
                        ui.notify(msg, color="negative")
                        if rem <= 0:
                            on_success()
                        # 登录失败重置验证码
                        if site_key:
                            await ui.run_javascript(
                                "try { turnstile.reset(); } catch(e) {}"
                            )

            pwd.on("keydown.enter", login)
            ui.button("进入系统", on_click=login).classes(
                "w-full h-12 text-lg shadow-md"
            )
            with ui.row().classes("w-full justify-center mt-4"):
                ui.button("找回权限", on_click=lambda: reset_dialog.open()).props(
                    "flat size=sm color=grey"
                )

    with ui.dialog() as reset_dialog, ui.card().classes("p-6"):
        ui.label("权限重置").classes("text-h6 mb-4")
        r_user = ui.input("用户名").classes("w-full")
        r_code = ui.input("验证码").classes("w-full")
        r_code.set_visibility(False)

        async def req_c():
            code = "".join(secrets.choice(string.digits) for _ in range(6))
            print(f"\n[Security] Reset Code for {r_user.value}: {code}\n", flush=True)
            reset_data[client_ip] = {"code": code, "user": r_user.value}
            r_code.set_visibility(True)
            ui.notify("验证码已发往终端")

        ui.button("发送验证码", on_click=req_c).classes("w-full")

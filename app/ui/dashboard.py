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
    ui.label("安全与站点设置").classes("text-2xl font-bold mb-6")

    # 站点基础设置
    with ui.card().classes("w-full p-6 shadow-sm border mb-6"):
        ui.label("基础设置").classes("text-lg font-bold mb-4")
        curr_name = await get_setting("site_name", settings.SITE_NAME)
        name_in = (
            ui.input("站点名称", value=curr_name).classes("w-full").props("outlined")
        )

        async def save_base():
            await set_setting("site_name", name_in.value)
            ui.notify("基础设置已保存")

        ui.button("保存基础设置", on_click=save_base).classes("mt-4")

    # 管理员访问白名单
    with ui.card().classes("w-full p-6 shadow-sm border mb-6"):
        ui.label("管理员安全限制").classes("text-lg font-bold mb-4")
        ui.markdown(
            "仅允许以下 IP 或域名访问管理页面。多个请用逗号分隔。留空则不限制。"
        ).classes("text-xs text-slate-500 mb-2")
        allowed_hosts = await get_setting("admin_allowed_hosts", "")
        hosts_in = (
            ui.input(
                "允许访问的站点/IP",
                value=allowed_hosts,
                placeholder="127.0.0.1, admin.example.com",
            )
            .classes("w-full")
            .props("outlined")
        )

        async def save_security():
            await set_setting("admin_allowed_hosts", hosts_in.value)
            ui.notify("安全设置已保存")

        ui.button("保存安全设置", on_click=save_security).classes("mt-4")

    # API 来源限制
    with ui.card().classes("w-full p-6 shadow-sm border mb-6"):
        ui.label("API 来源限制 (CORS/Origin)").classes("text-lg font-bold mb-4")
        ui.markdown(
            "仅允许以下域名发起的 API 请求。多个请用逗号分隔（例如 `https://example.com`）。留空则不限制（仅允许同源）。"
        ).classes("text-xs text-slate-500 mb-2")
        allowed_origins = await get_setting("api_allowed_origins", "")
        origins_in = (
            ui.input(
                "允许访问的站点链接",
                value=allowed_origins,
                placeholder="https://mysite.com, http://localhost:3000",
            )
            .classes("w-full")
            .props("outlined")
        )

        async def save_origins():
            await set_setting("api_allowed_origins", origins_in.value)
            ui.notify("API 来源设置已保存")

        ui.button("保存来源设置", on_click=save_origins).classes("mt-4")

    # Cloudflare Turnstile 设置
    with ui.card().classes("w-full p-6 shadow-sm border"):
        ui.label("Cloudflare Turnstile 验证码").classes("text-lg font-bold mb-4")
        ui.markdown("配置后将在管理员登录页面启用人机验证。").classes(
            "text-xs text-slate-500 mb-2"
        )

        cf_site_key = await get_setting("cf_turnstile_site_key", "")
        cf_secret_key = await get_setting("cf_turnstile_secret_key", "")

        sk_in = (
            ui.input("Site Key", value=cf_site_key)
            .classes("w-full")
            .props("outlined dense")
        )
        sec_in = (
            ui.input(
                "Secret Key",
                value=cf_secret_key,
                password=True,
                password_toggle_button=True,
            )
            .classes("w-full")
            .props("outlined dense")
        )

        async def save_cf():
            await set_setting("cf_turnstile_site_key", sk_in.value)
            await set_setting("cf_turnstile_secret_key", sec_in.value)
            ui.notify("Cloudflare 配置已保存")

        ui.button("保存验证码配置", on_click=save_cf).classes("mt-4")

    # 下载安全设置
    with ui.card().classes("w-full p-6 shadow-sm border mb-6"):
        ui.label("下载安全设置").classes("text-lg font-bold mb-4")
        ui.markdown(
            "配置文件下载的安全验证策略。Token V2 验证和 UA 验证为强制开启，其他可选。"
        ).classes("text-xs text-slate-500 mb-2")

        # 获取当前设置
        check_ip = await get_setting("download_check_ip", "false") == "true"
        check_expire = await get_setting("download_check_expire", "false") == "true"
        expire_time = await get_setting("download_expire_time", "3600")

        # IP 验证开关
        ip_switch = ui.switch("启用 IP 验证", value=check_ip).classes("w-full mb-2")

        # 过期验证开关
        expire_switch = ui.switch("启用链接过期验证", value=check_expire).classes(
            "w-full mb-2"
        )

        # 过期时间设置
        expire_input = (
            ui.input(
                "链接有效期（秒）",
                value=expire_time,
                placeholder="3600",
            )
            .classes("w-full mb-2")
            .props("outlined dense")
        )

        ui.markdown("说明：链接过期时间默认为3600秒（1小时）。").classes(
            "text-xs text-slate-400 mb-2"
        )

        async def save_download_security():
            await set_setting("download_check_ip", str(ip_switch.value).lower())
            await set_setting("download_check_expire", str(expire_switch.value).lower())
            await set_setting("download_expire_time", expire_input.value)
            ui.notify("下载安全设置已保存")

        ui.button("保存下载安全设置", on_click=save_download_security).classes("mt-4")


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

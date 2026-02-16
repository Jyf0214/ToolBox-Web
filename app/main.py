import asyncio
from fastapi import Request, Response
from nicegui import app, ui

from app.core.config import settings
from app.core.lifecycle import startup_handler, load_modules, sync_modules_with_db
from app.api.tracking import setup_tracking_api
from app.ui.setup import create_setup_page
from app.ui.main_page import create_main_page
from app.ui.admin import create_admin_page
from app.ui.licenses_page import create_licenses_page
from app.core.settings_manager import get_local_secret


@app.middleware("http")
async def api_security_middleware(request: Request, call_next):
    """
    API 安全防护中间件
    拦截直接通过脚本或逆向工具调用的 API 请求
    """
    path = request.url.path
    
    # 仅针对 API 和 下载路径进行深度校验
    if path.startswith("/api") or "/download/" in path:
        headers = request.headers
        
        # 1. 来源站校验 (Referer)
        referer = headers.get("referer", "")
        host = headers.get("host", "")
        
        # 允许没有 Referer 的情况（虽然少见），但如果有，必须包含当前 Host
        if referer and host not in referer:
            return Response(content="Invalid Referer", status_code=403)
            
        # 2. 现代浏览器安全头部校验 (Sec-Fetch-*)
        # 这些头部很难被脚本自动精准伪造（尤其是 same-origin 逻辑）
        fetch_site = headers.get("sec-fetch-site")
        if fetch_site and fetch_site != "same-origin":
            # 允许部分合法的跨站导航，但 API 请求必须是 same-origin
            if path.startswith("/api"):
                return Response(content="Direct API access forbidden", status_code=403)

        # 3. 校验 User-Agent (简单 Bot 过滤)
        ua = headers.get("user-agent", "").lower()
        if not ua or any(bot in ua for bot in ["python", "curl", "wget", "http-client", "postman"]):
            return Response(content="Automated access forbidden", status_code=403)

    return await call_next(request)


@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Cache-Control"] = (
        "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


class State:
    needs_setup = True
    initialized = asyncio.Event()
    db_connected = False


state = State()
modules = []
module_instances = {}


@app.on_startup
async def on_startup():
    await startup_handler(state, modules, module_instances)


def handle_exception(e: Exception):
    from app.core.updater import generate_emergency_token, pull_updates

    print(f"CRITICAL ERROR: {e}")

    try:
        from app.core.auth import is_authenticated

        authenticated = is_authenticated()
    except Exception:
        authenticated = False

    if authenticated:
        token = generate_emergency_token()

        async def emergency_repair():
            try:
                ui.notify("正在尝试紧急修复更新...", type="warning")
                success, msg = await asyncio.get_event_loop().run_in_executor(
                    None, pull_updates
                )
                if success:
                    ui.notify("修复成功，请手动重启应用", color="positive", duration=0)
                else:
                    ui.notify(f"修复失败: {msg}", color="negative")
            except Exception:
                pass

        try:
            with (
                ui.dialog() as dialog,
                ui.card().classes("p-6 border-2 border-negative"),
            ):
                ui.label("系统发生严重错误").classes("text-h6 text-negative mb-2")
                ui.label(f"错误详情: {str(e)[:200]}...").classes(
                    "text-xs text-slate-500 mb-4"
                )
                ui.label(f"安全令牌: {token}").classes(
                    "text-[10px] font-mono bg-slate-100 p-1 mb-4"
                )

                with ui.row().classes("w-full justify-end gap-2"):
                    ui.button("忽略", on_click=dialog.close).props("flat")
                    ui.button(
                        "执行紧急更新修复",
                        on_click=lambda: (dialog.close(), emergency_repair()),
                    ).props("elevated color=negative")
            dialog.open()
        except Exception:
            # Fallback to simple notification if dialog fails
            try:
                ui.notify("系统运行出错，请检查日志", color="negative")
            except Exception:
                pass
    else:
        try:
            ui.notify("系统运行出错，请联系管理员", color="negative")
        except Exception:
            pass


app.on_exception(handle_exception)

app.include_router(setup_tracking_api(state))

create_setup_page(state)
create_main_page(state, modules)
create_licenses_page()
create_admin_page(
    state,
    lambda: load_modules(modules, module_instances),
    lambda: sync_modules_with_db(state, modules),
)

ui.run(
    title=f"工具箱 v{settings.VERSION}",
    storage_secret=get_local_secret(),
    port=7860,
    viewport="width=device-width, initial-scale=1",
)

import os
import uuid
import asyncio
import secrets
import hashlib
import time
from pathlib import Path
from app.modules.base import BaseModule
from nicegui import ui, app
from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse


class DocxToPdfModule(BaseModule):
    def __init__(self):
        super().__init__()
        self.temp_dir = os.path.join(os.getcwd(), "temp_files")
        os.makedirs(self.temp_dir, exist_ok=True)
        self._download_tokens = {}
        self.setup_api()
        self._start_cleanup_timer()

    def _generate_token(self, ip: str, file_id: str) -> str:
        raw = f"{ip}:{file_id}:{secrets.randbelow(1000000)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def _start_cleanup_timer(self):
        from threading import Thread

        def cleanup():
            while True:
                time.sleep(3600)
                try:
                    current_time = time.time()
                    expired_keys = [
                        k
                        for k, v in self._download_tokens.items()
                        if current_time - v.get("created_at", 0) > 3600
                    ]
                    for k in expired_keys:
                        del self._download_tokens[k]
                except Exception:
                    pass

        Thread(target=cleanup, daemon=True).start()

    @property
    def name(self):
        return "Word 转 PDF"

    @property
    def icon(self):
        return "picture_as_pdf"

    def setup_api(self):
        @app.get(f"{self.router.prefix}/download/{{file_id}}/{{file_name}}")
        async def download_pdf(
            request: Request, file_id: str, file_name: str, token: str = None
        ):
            # 路径安全防护：强制仅提取文件名，防止穿越攻击
            safe_id = os.path.basename(file_id)
            safe_name = os.path.basename(file_name)
            file_path = os.path.join(self.temp_dir, safe_id, safe_name)

            if not os.path.exists(file_path):
                return JSONResponse(
                    status_code=404,
                    content={"error": "文件不存在或已过期", "reason": "file_not_found"},
                )

            # Token V2 验证
            token_key = f"{safe_id}:{safe_name}"
            token_info = self._download_tokens.get(token_key)

            if not token_info:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "无效的下载链接",
                        "reason": "download_link_invalid",
                    },
                )

            if token != token_info["token"]:
                return JSONResponse(
                    status_code=403,
                    content={"error": "下载Token无效", "reason": "token_invalid"},
                )

            # 强制 UA 验证
            user_agent = request.headers.get("user-agent", "").strip()
            if not user_agent:
                return JSONResponse(
                    status_code=403,
                    content={"error": "User-Agent无效", "reason": "ua_invalid"},
                )

            # 可选配置：IP 验证
            from app.core.settings_manager import get_setting

            check_ip = await get_setting("download_check_ip", "false")
            if check_ip == "true":
                client_ip = request.client.host
                if "x-forwarded-for" in request.headers:
                    client_ip = request.headers["x-forwarded-for"].split(",")[0]
                if token_info["ip"] != client_ip:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": "IP不匹配，请使用上传时的网络下载",
                            "reason": "ip_mismatch",
                        },
                    )

            # 可选配置：过期验证
            check_expire = await get_setting("download_check_expire", "false")
            if check_expire == "true":
                expire_time = int(await get_setting("download_expire_time", "3600"))
                if time.time() - token_info.get("created_at", 0) > expire_time:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": "下载链接已过期，请重新转换文件",
                            "reason": "link_expired",
                        },
                    )

            return FileResponse(
                file_path, media_type="application/pdf", filename=safe_name
            )

    def _get_pdf_info(self, pdf_path: str) -> dict:
        try:
            from pypdf import PdfReader

            reader = PdfReader(pdf_path)
            return {"pages": len(reader.pages)}
        except Exception as e:
            print(f"读取 PDF 信息出错: {e}")
            return {"pages": 0}

    def _add_blank_page_if_needed(self, pdf_path: str, add_blank_page: bool) -> bool:
        if not add_blank_page:
            return True
        try:
            import shutil
            from pypdf import PdfReader, PdfWriter

            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            if num_pages % 2 == 1:
                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)
                last_page = reader.pages[-1]
                width = float(last_page.mediabox.width)
                height = float(last_page.mediabox.height)

                from reportlab.pdfgen import canvas

                blank_pdf_path = pdf_path.replace(".pdf", "_blank.pdf")
                c = canvas.Canvas(blank_pdf_path, pagesize=(width, height))
                c.showPage()
                c.save()
                blank_reader = PdfReader(blank_pdf_path)
                writer.add_page(blank_reader.pages[0])
                temp_output = pdf_path.replace(".pdf", "_temp.pdf")
                with open(temp_output, "wb") as f:
                    writer.write(f)
                shutil.move(temp_output, pdf_path)
                if os.path.exists(blank_pdf_path):
                    os.remove(blank_pdf_path)
                return True
            return True
        except Exception as e:
            print(f"添加空白页时出错: {e}")
            return False

    def setup_ui(self):
        ui.label("Word 转 PDF 转换器").classes("text-h4 mb-4")
        ui.markdown(
            "上传 `.docx` 文件，将其转换为高质量的 PDF，支持页数统计与在线预览。"
        ).classes("mb-4 text-slate-500")

        # 定义一个内部函数来安全更新 UI，并打印非生命周期错误
        def safe_ui(func, *args, **kwargs):
            try:
                func(*args, **kwargs)
            except RuntimeError as e:
                # 忽略元素已删除的错误
                if (
                    "deleted" in str(e).lower()
                    or "parent slot" in str(e).lower()
                    or "client" in str(e).lower()
                ):
                    return
                print(f"UI Update Runtime Error: {e}")
            except Exception as e:
                print(f"UI Update Error: {e}")

        async def get_tool_security():
            from app.core import database
            from app.models.models import Tool
            from sqlalchemy import select

            async with database.AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Tool).where(Tool.name == "Word 转 PDF")
                )
                return res.scalars().first()

        security_state = {"site_key": "", "secret_key": "", "requires_captcha": False}

        async def init_security():
            from app.core.settings_manager import get_setting

            try:
                tool = await get_tool_security()
                if tool and tool.requires_captcha:
                    security_state["requires_captcha"] = True
                    security_state["site_key"] = await get_setting(
                        "cf_turnstile_site_key", ""
                    )
                    security_state["secret_key"] = await get_setting(
                        "cf_turnstile_secret_key", ""
                    )
                    if security_state["site_key"]:
                        ui.add_head_html(
                            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>'
                        )
                        captcha_container.set_visibility(True)
                        with captcha_container:
                            ui.html(
                                f'<div class="cf-turnstile" data-sitekey="{security_state["site_key"]}"></div>'
                            )
            except RuntimeError as e:
                if "parent slot" in str(e):
                    return
                raise

        with ui.dialog() as error_dialog, ui.card().classes("w-full max-w-2xl"):
            ui.label("详细错误日志").classes("text-h6")
            error_log_area = ui.textarea().classes("w-full h-64").props("readonly")
            with ui.row().classes("w-full justify-end mt-4"):
                ui.button("关闭", on_click=error_dialog.close).props("flat")
                ui.button(
                    "复制日志",
                    on_click=lambda: ui.run_javascript(
                        f"navigator.clipboard.writeText({repr(error_log_area.value)})"
                    ),
                ).props("icon=content_copy")

        with (
            ui.dialog() as preview_dialog,
            ui.card().classes("w-[90vw] h-[90vh] max-w-none"),
        ):
            preview_frame = ui.html().classes("w-full h-full")
            with (
                ui.button(icon="close", on_click=preview_dialog.close)
                .props("fab color=primary")
                .classes("absolute right-4 top-4")
            ):
                pass

        def show_error_report(msg: str):
            error_log_area.value = msg
            error_dialog.open()

        with ui.card().classes("w-full max-w-2xl p-6 shadow-md"):
            state = {"name": "", "content": None, "processing": False}

            # 使用自定义 HTML 元素构建进度条，解决组件显示冲突问题
            with (
                ui.element("div")
                .classes("w-full bg-slate-100 rounded-full h-3 mb-4 overflow-hidden")
                .style("display: none") as progress_container
            ):
                progress_bar_inner = (
                    ui.element("div")
                    .classes("bg-blue-500 h-full transition-all duration-300")
                    .style("width: 0%")
                )

            status_label = (
                ui.label("等待上传...")
                .classes("text-sm text-slate-500 mb-2")
                .style("display: none")
            )

            captcha_container = ui.element("div").classes(
                "w-full flex justify-center mb-4 hidden"
            )

            add_blank_page = ui.checkbox(
                "页数为奇数时自动添加空白页", value=True
            ).classes("mb-4")

            async def handle_upload(e):
                try:
                    file_name = getattr(
                        e.file, "filename", getattr(e.file, "name", "unknown.docx")
                    )
                    file_name = os.path.basename(file_name)
                    state["name"] = file_name

                    # 显示上传状态
                    safe_ui(status_label.style, "display: block")
                    safe_ui(status_label.set_text, f"上传完成: {file_name}")
                    safe_ui(progress_container.style, "display: block")
                    safe_ui(progress_bar_inner.style, "width: 100%")

                    content = e.file.read()
                    if hasattr(content, "__await__"):
                        state["content"] = await content
                    else:
                        state["content"] = content

                    ui.notify(f"文件已就绪: {file_name}", color="positive")
                    convert_btn.enable()
                except Exception as ex:
                    print(f"Upload Error: {ex}")
                    ui.notify(f"文件处理失败: {ex}", color="negative")

            ui.upload(
                label="选择或拖拽 .docx 文件",
                on_upload=handle_upload,
                auto_upload=True,
            ).props('accept=".docx" icon="upload_file"').classes("w-full mb-6")

            result_card = ui.card().classes(
                "w-full p-4 bg-slate-50 border-dashed border-2 border-slate-200 hidden mt-4"
            )

            async def convert():
                if not state["content"]:
                    return

                from app.core.task_manager import global_task_manager
                from app.core.auth import is_authenticated, verify_turnstile

                if (
                    security_state["requires_captcha"]
                    and security_state["site_key"]
                    and security_state["secret_key"]
                ):
                    token = await ui.run_javascript(
                        'try { return turnstile.getResponse(); } catch(e) { return ""; }'
                    )
                    if not token:
                        ui.notify("请先完成人机验证", color="warning")
                        return
                    is_human = await verify_turnstile(
                        token, security_state["secret_key"]
                    )
                    if not is_human:
                        ui.notify("验证码失效，请重试", color="negative")
                        await ui.run_javascript(
                            "try { turnstile.reset(); } catch(e) {}"
                        )
                        return

                client_ip = app.storage.browser.get("id", "Anonymous")

                try:
                    state["processing"] = True
                    safe_ui(convert_btn.disable)

                    task = await global_task_manager.add_task(
                        name="Word 转 PDF",
                        user_type="admin" if is_authenticated() else "guest",
                        ip=client_ip,
                        filename=state["name"],
                    )

                    # 显示进度条容器和状态标签
                    safe_ui(status_label.style, "display: block")
                    safe_ui(progress_container.style, "display: block")
                    safe_ui(progress_bar_inner.style, "width: 0%")
                    safe_ui(result_card.set_visibility, False)

                    async def simulate_fake_progress():
                        while state["processing"]:
                            try:
                                # 尝试解析当前百分比并模拟增长
                                current_style = progress_bar_inner.style.get(
                                    "width", "0%"
                                )
                                current_val = (
                                    float(current_style.replace("%", "")) / 100
                                )
                                if current_val < 0.95:
                                    # 进度越往后越慢
                                    increment = (0.98 - current_val) / 20
                                    new_p = (current_val + increment) * 100
                                    safe_ui(
                                        progress_bar_inner.style, f"width: {new_p}%"
                                    )
                            except Exception:
                                pass
                            await asyncio.sleep(0.8)

                    asyncio.create_task(simulate_fake_progress())

                    async def wait_for_start():
                        while True:
                            waiting_ids = [t.id for t in global_task_manager.queue]
                            if task.id in waiting_ids:
                                pos = waiting_ids.index(task.id) + 1
                                safe_ui(
                                    status_label.set_text,
                                    f"排队中: 前方有 {pos - 1} 个任务...",
                                )
                                safe_ui(progress_bar_inner.style, "width: 2%")
                            elif task.id in global_task_manager.active_tasks:
                                break
                            await asyncio.sleep(1.0)

                    # 启动状态监控并请求开始任务
                    monitor_task = asyncio.create_task(wait_for_start())
                    try:
                        await global_task_manager.start_task(task.id)
                    finally:
                        monitor_task.cancel()

                    safe_ui(status_label.set_text, "正在转换 (LibreOffice 渲染中)...")

                    file_id = str(uuid.uuid4())
                    work_dir = os.path.join(self.temp_dir, file_id)
                    os.makedirs(work_dir, exist_ok=True)

                    # 获取原文件名并构建输出路径
                    original_name = state["name"]
                    input_stem = Path(original_name).stem
                    output_name = f"{input_stem}.pdf"

                    input_path = os.path.join(work_dir, original_name)
                    output_path = os.path.join(work_dir, output_name)

                    with open(input_path, "wb") as f:
                        f.write(state["content"])

                    import shutil

                    libreoffice_path = (
                        shutil.which("libreoffice") or "/usr/bin/libreoffice"
                    )

                    process = await asyncio.create_subprocess_exec(
                        libreoffice_path,
                        "--headless",
                        "--convert-to",
                        "pdf",
                        input_path,
                        "--outdir",
                        work_dir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode == 0:
                        # 转换出的文件名可能不完全一致，确保它被重命名为原名.pdf
                        actual_output = input_path.replace(".docx", ".pdf")
                        if (
                            os.path.exists(actual_output)
                            and actual_output != output_path
                        ):
                            shutil.move(actual_output, output_path)

                        safe_ui(status_label.set_text, "后期处理中...")
                        if add_blank_page.value:
                            self._add_blank_page_if_needed(output_path, True)

                        info = self._get_pdf_info(output_path)
                        state["processing"] = False
                        safe_ui(progress_bar_inner.style, "width: 100%")
                        safe_ui(
                            progress_bar_inner.classes,
                            add="bg-green-500",
                            remove="bg-blue-500",
                        )
                        safe_ui(status_label.set_text, "转换完成！")
                        try:
                            ui.notify("转换成功！", color="positive")
                        except Exception:
                            pass

                        # 生成下载 token
                        download_token = self._generate_token(client_ip, file_id)
                        self._download_tokens[f"{file_id}:{output_name}"] = {
                            "token": download_token,
                            "ip": client_ip,
                            "created_at": time.time(),
                        }

                        download_url = f"{self.router.prefix}/download/{file_id}/{output_name}?token_dlDL={download_token}"

                        try:
                            result_card.clear()
                            result_card.set_visibility(True)
                            with result_card:
                                with ui.row().classes(
                                    "w-full items-center justify-between"
                                ):
                                    with ui.column():
                                        ui.label(output_name).classes(
                                            "font-bold text-lg"
                                        )
                                        ui.label(f"页数: {info['pages']} 页").classes(
                                            "text-sm text-slate-500"
                                        )

                                    with ui.row().classes("gap-2"):
                                        ui.button(
                                            "预览",
                                            icon="visibility",
                                            on_click=lambda: (
                                                preview_frame.set_content(
                                                    f'<iframe src="{download_url}" style="width:100%; height:100%; border:none;"></iframe>'
                                                ),
                                                preview_dialog.open(),
                                            ),
                                        ).props("outline")

                                        # 直接显示下载链接
                                        ui.html(
                                            f'<a href="{download_url}" download="{output_name}" '
                                            f'style="display:inline-flex;align-items:center;gap:8px;'
                                            f"padding:8px 16px;background:#1976d2;color:white;"
                                            f'text-decoration:none;border-radius:4px;font-weight:500;">'
                                            f'<span class="material-icons">download</span>'
                                            f"下载 PDF</a>"
                                        )
                        except Exception:
                            pass
                    else:
                        error_detail = f"LibreOffice Error:\n{stderr.decode()}"
                        try:
                            ui.notify("转换失败", color="negative")
                        except Exception:
                            pass
                        show_error_report(error_detail)
                except Exception as ex:
                    try:
                        ui.notify("程序出错", color="negative")
                    except Exception:
                        pass
                    show_error_report(str(ex))
                finally:
                    if "task" in locals():
                        await global_task_manager.complete_task(task.id)
                    state["processing"] = False
                    safe_ui(convert_btn.enable)
                    if input_path and os.path.exists(input_path):
                        os.remove(input_path)

            convert_btn = ui.button("开始转换", on_click=convert).classes(
                "w-full mt-2 py-4 text-lg"
            )
            convert_btn.disable()

        with ui.element("div"):
            ui.timer(0.1, init_security, once=True)

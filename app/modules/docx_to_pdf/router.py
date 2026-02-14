import os
import subprocess
import uuid
from app.modules.base import BaseModule
from nicegui import ui, app
from fastapi.responses import FileResponse


class DocxToPdfModule(BaseModule):
    def __init__(self):
        super().__init__()
        # 确保临时目录存在
        self.temp_dir = os.path.join(os.getcwd(), "temp_files")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.setup_api()

    @property
    def name(self):
        return "Word 转 PDF"

    @property
    def icon(self):
        return "picture_as_pdf"

    def setup_api(self):
        @app.get(f"{self.router.prefix}/download/{{file_id}}")
        async def download_pdf(file_id: str):
            file_path = os.path.join(self.temp_dir, f"{file_id}.pdf")
            if os.path.exists(file_path):
                return FileResponse(
                    file_path, media_type="application/pdf", filename="转换结果.pdf"
                )
            return {"error": "未找到文件"}

    def setup_ui(self):
        ui.label("Word 转 PDF 转换器").classes("text-h4 mb-4")
        ui.markdown(
            "上传 `.docx` 文件，使用 LibreOffice 将其转换为高质量的 PDF 文件。"
        ).classes("mb-4")

        with ui.card().classes("w-full max-w-xl p-6"):
            file_info = {"name": "", "content": None}

            async def handle_upload(e):
                file_info["name"] = e.name
                file_info["content"] = e.content
                ui.notify(f"已上传: {e.name}")
                convert_btn.enable()

            ui.upload(
                label="选择 .docx 文件",
                on_upload=handle_upload,
                auto_upload=True,
            ).props('accept=".docx"').classes("w-full")

            async def convert():
                if not file_info["content"]:
                    return

                processing_dialog = ui.dialog()
                with processing_dialog, ui.card():
                    ui.spinner(size="lg")
                    ui.label("正在转换中... 请稍候。")
                processing_dialog.open()

                try:
                    # 保存临时 docx
                    file_id = str(uuid.uuid4())
                    input_path = os.path.join(self.temp_dir, f"{file_id}.docx")

                    # 将上传的内容写入临时文件
                    content = file_info["content"].read()
                    with open(input_path, "wb") as f:
                        f.write(content)

                    # 调用 LibreOffice 进行转换
                    # --headless: 无界面模式
                    # --convert-to pdf: 目标格式
                    # --outdir: 输出目录
                    result = subprocess.run(
                        [
                            "libreoffice",
                            "--headless",
                            "--convert-to",
                            "pdf",
                            input_path,
                            "--outdir",
                            self.temp_dir,
                        ],
                        capture_output=True,
                        text=True,
                    )

                    if result.returncode == 0:
                        ui.notify("转换成功！", color="positive")
                        download_url = f"{self.router.prefix}/download/{file_id}"
                        with result_container:
                            ui.link("下载 PDF", download_url).classes(
                                "text-lg text-primary underline"
                            )
                    else:
                        ui.notify(f"转换失败: {result.stderr}", color="negative")
                except Exception as ex:
                    ui.notify(f"出错: {ex}", color="negative")
                finally:
                    processing_dialog.close()
                    if os.path.exists(input_path):
                        os.remove(input_path)

            convert_btn = ui.button("开始转换", on_click=convert).classes("w-full mt-4")
            convert_btn.disable()

            result_container = ui.row().classes("mt-4 w-full justify-center")

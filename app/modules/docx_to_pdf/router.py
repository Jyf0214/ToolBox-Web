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
        return "Word to PDF"

    @property
    def icon(self):
        return "picture_as_pdf"

    def setup_api(self):
        @app.get(f"{self.router.prefix}/download/{{file_id}}")
        async def download_pdf(file_id: str):
            file_path = os.path.join(self.temp_dir, f"{file_id}.pdf")
            if os.path.exists(file_path):
                return FileResponse(
                    file_path, media_type="application/pdf", filename="converted.pdf"
                )
            return {"error": "File not found"}

    def setup_ui(self):
        ui.label("Word to PDF Converter").classes("text-h4 mb-4")
        ui.markdown(
            "Upload a `.docx` file to convert it to a high-quality PDF using LibreOffice (Office-compatible)."
        ).classes("mb-4")

        with ui.card().classes("w-full max-w-xl p-6"):
            file_info = {"name": "", "content": None}

            async def handle_upload(e):
                file_info["name"] = e.name
                file_info["content"] = e.content
                ui.notify(f"Uploaded: {e.name}")
                convert_btn.enable()

            ui.upload(
                label="Choose .docx file",
                on_upload=handle_upload,
                auto_upload=True,
            ).props('accept=".docx"').classes("w-full")

            async def convert():
                if not file_info["content"]:
                    return

                processing_dialog = ui.dialog()
                with processing_dialog, ui.card():
                    ui.spinner(size="lg")
                    ui.label("Converting... please wait.")
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
                        ui.notify("Conversion successful!", color="positive")
                        download_url = f"{self.router.prefix}/download/{file_id}"
                        with result_container:
                            ui.link("Download PDF", download_url).classes(
                                "text-lg text-primary underline"
                            )
                    else:
                        ui.notify(
                            f"Conversion failed: {result.stderr}", color="negative"
                        )
                except Exception as ex:
                    ui.notify(f"Error: {ex}", color="negative")
                finally:
                    processing_dialog.close()
                    if os.path.exists(input_path):
                        os.remove(input_path)

            convert_btn = ui.button("Convert to PDF", on_click=convert).classes(
                "w-full mt-4"
            )
            convert_btn.disable()

            result_container = ui.row().classes("mt-4 w-full justify-center")

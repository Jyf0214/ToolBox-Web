from app.modules.base import BaseModule
from nicegui import ui
import base64


class ExampleModule(BaseModule):
    @property
    def name(self):
        return "Base64 编码/解码"

    @property
    def icon(self):
        return "code"

    def setup_ui(self):
        ui.label("Base64 编码/解码器").classes("text-h4 mb-4")

        with ui.column().classes("w-full max-w-xl"):
            input_text = ui.textarea("输入文本").classes("w-full")

            with ui.row():

                def encode():
                    try:
                        res = base64.b64encode(input_text.value.encode()).decode()
                        output_text.set_value(res)
                    except Exception as e:
                        ui.notify(f"错误: {e}")

                def decode():
                    try:
                        res = base64.b64decode(input_text.value.encode()).decode()
                        output_text.set_value(res)
                    except Exception as e:
                        ui.notify(f"错误: {e}")

                ui.button("编码", on_click=encode)
                ui.button("解码", on_click=decode, color="secondary")

            output_text = ui.textarea("结果").classes("w-full mt-4").props("readonly")

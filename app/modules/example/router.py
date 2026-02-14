from app.modules.base import BaseModule
from nicegui import ui
import base64

class ExampleModule(BaseModule):
    @property
    def name(self):
        return "Base64 Converter"

    @property
    def icon(self):
        return "code"

    def setup_ui(self):
        ui.label('Base64 Encoder/Decoder').classes('text-h4 mb-4')
        
        with ui.column().classes('w-full max-w-xl'):
            input_text = ui.textarea('Input Text').classes('w-full')
            
            with ui.row():
                def encode():
                    try:
                        res = base64.b64encode(input_text.value.encode()).decode()
                        output_text.set_value(res)
                    except Exception as e:
                        ui.notify(f"Error: {e}")

                def decode():
                    try:
                        res = base64.b64decode(input_text.value.encode()).decode()
                        output_text.set_value(res)
                    except Exception as e:
                        ui.notify(f"Error: {e}")

                ui.button('Encode', on_click=encode)
                ui.button('Decode', on_click=decode, color='secondary')

            output_text = ui.textarea('Result').classes('w-full mt-4').props('readonly')

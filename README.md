# ToolBox Web

一个模块化的 Python 在线工具服务平台。

## 快速开始

1. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```

2. **配置环境变量**:
   复制 `.env.example` 为 `.env` 并填写你的数据库 URL。
   ```bash
   cp .env.example .env
   ```

3. **运行程序**:
   ```bash
   python -m app.main
   ```

## 模块化开发

在 `app/modules/` 下创建一个新文件夹（如 `my_tool`），并在其中创建 `router.py`。
继承 `BaseModule` 类并实现 `setup_ui` 方法即可自动注册。

## 技术栈

- **UI/Server**: NiceGUI (FastAPI + Tailwind CSS)
- **ORM**: SQLAlchemy (Async)
- **Tracking**: FingerprintJS v3

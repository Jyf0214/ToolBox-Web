# Changelog

All notable changes to this project will be documented in this file.

## [0.2.0] - 2026-02-16

### Security
- 迁移数据库驱动从 `asyncmy` 到 `aiomysql` 以修复关键 SQL 注入漏洞 (CVE-2025-65896)。
- 升级 `cryptography` 至 46.0.5 以修复高危安全漏洞 (CVE-2023-0286)。
- 从 `PyPDF2` 迁移到 `pypdf` 5.3.1 以修复无限循环漏洞 (CVE-2023-36464)。
- 加固 Docker 镜像，使用非特权用户并限制 pip 访问。
- 集成 Cloudflare Turnstile CAPTCHA 验证，并实现管理员主机/IP 白名单安全策略。
- 完善文件下载安全，对 `file_id` 进行清理以防止路径遍历攻击。
- 增加下载 Token 验证和 IP 访问频率限制。
- 锁定安装页面，若管理员已存在则自动重定向至登录页。
- 移除所有 `bandit` 安全警告，使用更安全的替代方案替换 `subprocess` 调用。

### Added
- 新增 Markdown 转 PDF 模块。
- 启用压缩包文档（zip）转 PDF 工具，并支持批量上传。
- 新增系统状态页面，支持资源监控、任务历史记录及 SMTP 邮件配置。
- 实现全局任务队列系统，支持管理员监控及公共状态显示。
- 在管理后台新增详细的工具速率限制（Rate Limiting）配置。
- 新增系统维护功能，支持数据库清理和日志清除。
- 新增开源许可证页面，自动抓取并显示官方许可证文本。
- 管理后台支持追踪并显示访客的浏览器和操作系统信息。
- 增强系统更新功能，支持变更日志对比及确认对话框。
- 实现管理员密码重置功能（通过终端）及双重验证、数据库重置。
- 引入双阶段进度条，实时追踪文件上传和模拟转换进度。
- 支持自动同步模块到数据库功能。
- 支持主页手动选择进入登录或设置页面，取消自动重定向。

### Fixed
- 增强管理后台组件加载鲁棒性，修复侧边栏切换失效问题。
- 修复 `docx_to_pdf` 中的类型错误，并提高异常处理的健壮性。
- 实现启动时自动进行数据库模式迁移（自动添加缺失列）。
- 解决管理后台页面超时及布局嵌套错误。
- 优化管理员检测逻辑，改用专用 `admin_credentials` 表。
- 修复数据库连接时的 SSL 连接问题，支持 TOFU（首次使用信任）回退机制，确保在 TiDB Cloud 等环境下的稳定性。
- 解决 `docx_to_pdf` 模块中的语法问题，并完整集成工具级验证码。
- 修复安装过程中已存在管理员时的处理逻辑。
- 修复上传处理中的属性错误，并添加调试信息输出。
- 解决启动时数据库表初始化可能导致的 `AttributeError`。

### Changed
- 扁平化 UI 目录结构，将 `admin_parts` 移入 `ui` 目录。
- 优化管理员登录及后台的 UI/UX，提升响应式布局体验。
- 重构 `BaseModule` 和工具管理逻辑，引入 `Tool` 数据库模型。
- 优化内存使用，对重型库实施延迟加载。
- 简化更新程序，直接使用 `git pull` 并进行本地清理。
- 更新项目依赖，合并 Dependabot 的多个更新请求。
- 清理全项冗余及低质量注释，提升代码整洁度。

## [0.1.3] - 2026-02-14

### Fixed
- Fixed `sqlalchemy.exc.ObjectNotExecutableError: Not an executable object: 'SELECT 1'` by using `text('SELECT 1')`.

## [0.1.2] - 2026-02-14

### Fixed
- Fixed `AttributeError: type object 'URL' has no attribute 'create_from_string'` by replacing it with `sqlalchemy.engine.make_url`.

## [0.1.1] - 2026-02-14

### Fixed
- Automatically convert `mysql://` database URLs to `mysql+asyncmy://` for SQLAlchemy async engine compatibility.
- Aligned Ruff formatter version in pre-commit hooks to match local environment, resolving formatting conflicts.

### Added
- GitHub Actions cleanup job to automatically delete untagged container images from GHCR, with error tolerance.

### Changed
- Localized application UI and server-side messages to Chinese, including setup page, main dashboard, admin panel, and module UIs (Word to PDF, Base64 Converter).

## [0.1.0] - 2026-02-14

### Added
- Initial modular project structure with FastAPI and NiceGUI.
- Automatic application setup wizard on first run.
- Dynamic SECRET_KEY generation and storage.
- Guest tracking with FingerprintJS and IP.
- Base64 Converter as an example module.
- Docker support with optimized Dockerfile.
- GitHub Actions CI/CD with Ruff and Bandit security checks.
- Pre-commit hooks for local development quality control.

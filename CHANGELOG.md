# Changelog

All notable changes to this project will be documented in this file.

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

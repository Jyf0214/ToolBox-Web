import httpx
import asyncio
import os
import json

# 定义核心依赖及其官方许可证 RAW 链接
DEPENDENCIES = {
    "NiceGUI": {
        "repo": "https://github.com/zauberzeug/nicegui",
        "license_url": "https://raw.githubusercontent.com/zauberzeug/nicegui/main/LICENSE",
        "type": "MIT",
    },
    "SQLAlchemy": {
        "repo": "https://github.com/sqlalchemy/sqlalchemy",
        "license_url": "https://raw.githubusercontent.com/sqlalchemy/sqlalchemy/main/LICENSE",
        "type": "MIT",
    },
    "FastAPI": {
        "repo": "https://github.com/tiangolo/fastapi",
        "license_url": "https://raw.githubusercontent.com/tiangolo/fastapi/master/LICENSE",
        "type": "MIT",
    },
    "httpx": {
        "repo": "https://github.com/encode/httpx",
        "license_url": "https://raw.githubusercontent.com/encode/httpx/master/LICENSE.md",
        "type": "BSD-3-Clause",
    },
    "Pydantic": {
        "repo": "https://github.com/pydantic/pydantic",
        "license_url": "https://raw.githubusercontent.com/pydantic/pydantic/main/LICENSE",
        "type": "MIT",
    },
    "psutil": {
        "repo": "https://github.com/giampaolo/psutil",
        "license_url": "https://raw.githubusercontent.com/giampaolo/psutil/master/LICENSE",
        "type": "BSD-3-Clause",
    },
    "bcrypt": {
        "repo": "https://github.com/pyca/bcrypt",
        "license_url": "https://raw.githubusercontent.com/pyca/bcrypt/main/LICENSE",
        "type": "Apache-2.0",
    },
    "pypdf": {
        "repo": "https://github.com/py-pdf/pypdf",
        "license_url": "https://raw.githubusercontent.com/py-pdf/pypdf/main/LICENSE",
        "type": "BSD-3-Clause",
    },
    "ReportLab": {
        "repo": "https://github.com/MrBitBucket/reportlab-mirror",
        "license_url": "https://raw.githubusercontent.com/MrBitBucket/reportlab-mirror/master/LICENSE.txt",
        "type": "BSD-3-Clause",
    },
    "Ruff": {
        "repo": "https://github.com/astral-sh/ruff",
        "license_url": "https://raw.githubusercontent.com/astral-sh/ruff/main/LICENSE",
        "type": "MIT",
    },
    "markdown": {
        "repo": "https://github.com/Python-Markdown/markdown",
        "license_url": "https://raw.githubusercontent.com/Python-Markdown/markdown/master/LICENSE.md",
        "type": "BSD-3-Clause",
    },
    "LibreOffice": {
        "repo": "https://github.com/LibreOffice/core",
        "license_url": "https://raw.githubusercontent.com/LibreOffice/core/master/LICENSE",
        "type": "MPL-2.0 / LGPLv3",
    },
}


async def fetch_license(name, info):
    print(f"Fetching license for {name}...")
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(info["license_url"], timeout=10.0)
            if res.status_code == 200:
                return {
                    "name": name,
                    "repo": info["repo"],
                    "type": info["type"],
                    "text": res.text,
                }
    except Exception as e:
        print(f"Failed to fetch {name}: {e}")
    return None


async def main():
    results = []
    tasks = [fetch_license(n, i) for n, i in DEPENDENCIES.items()]
    fetched = await asyncio.gather(*tasks)

    for f in fetched:
        if f:
            results.append(f)

    os.makedirs("app/static", exist_ok=True)
    with open("app/static/licenses.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Licenses saved to app/static/licenses.json")


if __name__ == "__main__":
    asyncio.run(main())

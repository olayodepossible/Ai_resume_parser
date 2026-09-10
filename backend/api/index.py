"""Development entry point: `uv run main.py`.

For production use uvicorn (or gunicorn) directly:
    uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()

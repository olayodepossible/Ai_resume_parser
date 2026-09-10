"""Development entry point: `uv run uvicorn api.app.main:app --reload`.

For production use uvicorn (or gunicorn) directly:
    uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from app.main import app
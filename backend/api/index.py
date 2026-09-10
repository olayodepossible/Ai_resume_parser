"""
Application entry point.

Development from repository root:
    uv run uvicorn backend.api.app.main:app --reload

Vercel:
    backend/api/index.py
"""

from backend.api.app.main import app

__all__ = ["app"]
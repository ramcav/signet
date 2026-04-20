"""Entrypoint: `uv run fastapi dev src/main.py`."""
from signet.api.app import app

__all__ = ["app"]

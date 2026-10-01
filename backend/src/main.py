"""Entrypoint: `uv run fastapi dev src/main.py`."""
from signet.api.app import build_app

app = build_app()

__all__ = ["app"]

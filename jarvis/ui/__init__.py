"""Графический интерфейс Джарвиса."""

from __future__ import annotations

__all__ = ["run_hud"]


def run_hud(*args: object, **kwargs: object) -> int:
    """Запускает HUD; PySide6 импортируется только при реальном использовании."""
    from .app import run_hud as _run_hud

    return _run_hud(*args, **kwargs)  # type: ignore[arg-type]

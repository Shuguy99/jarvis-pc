"""Тесты навыков зрения, браузера и полного реестра."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jarvis.config import (
    BrowserConfig,
    Config,
    MemoryConfig,
    SkillsConfig,
    SpotifyConfig,
    VisionConfig,
)
from jarvis.skills import build_registry
from jarvis.skills import vision as vision_skills
from jarvis.skills.browser import INSTALL_HINT, BrowserSession


def _config(tmp_path: Path, **skills: Any) -> Config:
    """Конфиг с локальными путями, чтобы тесты не трогали домашний каталог."""
    base = SkillsConfig(
        screenshot_dir=str(tmp_path / "shots"),
        notes_file=str(tmp_path / "notes.md"),
        memory=MemoryConfig(backend="json", path=str(tmp_path / "memory")),
        browser=BrowserConfig(user_data_dir=str(tmp_path / "browser")),
        **skills,
    )
    return Config(skills=base)


def test_registry_contains_new_skills(tmp_path: Path) -> None:
    """Новые навыки видны модели, а Spotify появляется только при включении."""
    registry, services = build_registry(_config(tmp_path), lambda text: None)
    try:
        names = set(registry.names)
        assert {"analyze_screen", "read_screen_text"} <= names
        assert {"remember_fact", "recall_fact"} <= names
        assert {"browser_open", "browser_click", "browser_read"} <= names
        assert "spotify_play" not in names
    finally:
        services.shutdown()


def test_spotify_skills_appear_when_enabled(tmp_path: Path) -> None:
    """Включённый Spotify добавляет свои навыки."""
    config = _config(tmp_path, spotify=SpotifyConfig(enabled=True))
    registry, services = build_registry(config, lambda text: None)
    try:
        assert "spotify_play" in registry.names
    finally:
        services.shutdown()


def test_disabled_vision_answers_politely(tmp_path: Path) -> None:
    """Отключённое зрение не пытается снимать экран."""
    config = _config(tmp_path, vision=VisionConfig(enabled=False))
    assert "отключено" in vision_skills.analyze_screen(config)
    assert "отключено" in vision_skills.read_screen_text(config)


def test_vision_backend_requires_multimodal_model(tmp_path: Path) -> None:
    """Офлайн-мозг не умеет смотреть на экран, и об этом говорится честно."""
    config = _config(tmp_path)
    config.brain.backend = "offline"
    assert "мультимодальную модель" in vision_skills.analyze_screen(config)


def test_ocr_failure_is_reported(monkeypatch: Any, tmp_path: Path) -> None:
    """Без Tesseract навык объясняет, что нужно установить."""
    config = _config(tmp_path)
    monkeypatch.setitem(__import__("sys").modules, "pytesseract", None)
    monkeypatch.setattr(vision_skills, "capture_png", lambda cfg, region: b"png")
    assert "Tesseract" in vision_skills.read_screen_text(config)


def test_browser_without_playwright_explains_install(tmp_path: Path) -> None:
    """Без Playwright навык подсказывает команду установки."""
    session = BrowserSession(BrowserConfig(user_data_dir=str(tmp_path)))
    try:
        import playwright  # noqa: F401
    except ImportError:
        assert session.open("example.com") == INSTALL_HINT
    assert session.close() == "Браузер и так закрыт, сэр."
    session.shutdown()

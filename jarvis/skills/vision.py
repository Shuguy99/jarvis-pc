"""Навыки «зрения»: чтение текста с экрана (OCR) и анализ картинки моделью."""

from __future__ import annotations

import base64
import ctypes
import io
import logging
import platform
from typing import Any

from ..config import Config, VisionConfig

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment, misc]
from .clipboard import set_clipboard as write_clipboard
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_WINDOWS = platform.system() == "Windows"
REQUEST_TIMEOUT_S = 180
REGIONS = ("screen", "window")

DEFAULT_QUESTION = "Опиши, что происходит на экране, и что здесь главное."
VISION_PROMPT = (
    "Ты — Джарвис, ассистент, который смотрит на экран пользователя. "
    "Отвечай по-русски, кратко и по делу, без markdown. "
    "Если данных на изображении недостаточно, честно скажи об этом."
)


class VisionError(RuntimeError):
    """Понятная пользователю причина, почему «зрение» недоступно."""


def _active_window_box() -> dict[str, int] | None:
    """Границы активного окна Windows или None, если получить их нельзя."""
    if not IS_WINDOWS:
        return None
    # wintypes существует только в Windows, поэтому импортируем по месту.
    from ctypes import wintypes

    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    handle = user32.GetForegroundWindow()
    if not handle:
        return None
    rect = wintypes.RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    return {"left": rect.left, "top": rect.top, "width": width, "height": height}


def capture_png(config: VisionConfig, region: str = "screen") -> bytes:
    """Снимает экран или активное окно и возвращает PNG-байты."""
    try:
        import mss
        import mss.tools
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise VisionError("Модуль mss не установлен, сэр.") from exc
    box = _active_window_box() if region == "window" else None
    if region == "window" and box is None:
        log.info("Активное окно недоступно, снимаю весь экран")
    try:
        with mss.mss() as sct:
            shot = sct.grab(box or sct.monitors[0])
            png = mss.tools.to_png(shot.rgb, shot.size) or b""
    except Exception as exc:  # mss бросает свои исключения при недоступном дисплее
        raise VisionError(f"Не удалось снять экран: {exc}") from exc
    return _downscale(png, config.max_side_px)


def _downscale(png: bytes, max_side: int) -> bytes:
    """Уменьшает картинку, чтобы модель не задыхалась на 4K-снимках."""
    if max_side <= 0:
        return png
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - Pillow приходит с зависимостями
        return png
    image = Image.open(io.BytesIO(png))
    if max(image.size) <= max_side:
        return png
    scale = max_side / max(image.size)
    resized = image.resize(
        (max(1, int(image.width * scale)), max(1, int(image.height * scale))),
        Image.LANCZOS,
    )
    buffer = io.BytesIO()
    resized.save(buffer, format="PNG")
    return buffer.getvalue()


def ocr_png(config: VisionConfig, png: bytes) -> str:
    """Распознаёт текст на картинке через Tesseract."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise VisionError(
            "Для чтения текста нужен pytesseract и сам Tesseract OCR, сэр. "
            "Установите его и укажите skills.vision.tesseract_cmd."
        ) from exc
    if config.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
    try:
        text = pytesseract.image_to_string(Image.open(io.BytesIO(png)), lang=config.ocr_languages)
    except Exception as exc:  # pytesseract бросает свои исключения
        raise VisionError(f"Tesseract не смог прочитать экран: {exc}") from exc
    return " ".join(text.split())


def _resolve_backend(config: Config) -> str:
    """Определяет, какой мультимодальный бэкенд использовать."""
    backend = config.skills.vision.backend
    if backend == "auto":
        backend = config.brain.backend
    if backend == "openai" and not config.openai_api_key:
        raise VisionError("Для анализа экрана через OpenAI нужен OPENAI_API_KEY, сэр.")
    if backend not in {"ollama", "openai"}:
        raise VisionError(
            "Анализ экрана требует мультимодальную модель: "
            "задайте skills.vision.backend в ollama или openai, сэр."
        )
    return backend


def _ask_ollama(config: Config, png: bytes, question: str) -> str:
    """Спрашивает локальную мультимодальную модель Ollama о картинке."""
    vision = config.skills.vision
    payload: dict[str, Any] = {
        "model": vision.ollama_model,
        "messages": [
            {"role": "system", "content": VISION_PROMPT},
            {
                "role": "user",
                "content": question,
                "images": [base64.b64encode(png).decode("ascii")],
            },
        ],
        "stream": False,
        "options": {"temperature": config.brain.temperature},
    }
    if requests is None:
        raise VisionError("Модуль requests не установлен. Установите: pip install requests, сэр.")
    url = config.brain.ollama_host.rstrip("/") + "/api/chat"
    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_S)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise VisionError(
            f"Модель {vision.ollama_model} недоступна. Выполните: ollama pull {vision.ollama_model}"
        ) from exc
    return str(response.json().get("message", {}).get("content", "")).strip()


def _ask_openai(config: Config, png: bytes, question: str) -> str:
    """Спрашивает облачную модель OpenAI о картинке."""
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - зависит от окружения
        raise VisionError("Пакет openai не установлен, сэр.") from exc
    client = OpenAI(
        api_key=config.openai_api_key,
        base_url=config.brain.openai_base_url or None,
    )
    data_url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    completion = client.chat.completions.create(
        model=config.skills.vision.openai_model,
        temperature=config.brain.temperature,
        messages=[
            {"role": "system", "content": VISION_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": question},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
    )
    return (completion.choices[0].message.content or "").strip()


def analyze_screen(config: Config, question: str = "", region: str = "window") -> str:
    """Показывает экран мультимодальной модели и отвечает на вопрос о нём."""
    if not config.skills.vision.enabled:
        return "Зрение отключено в конфигурации, сэр."
    query = question.strip() or DEFAULT_QUESTION
    try:
        backend = _resolve_backend(config)
        png = capture_png(config.skills.vision, region)
        answer = (
            _ask_ollama(config, png, query)
            if backend == "ollama"
            else _ask_openai(config, png, query)
        )
    except VisionError as exc:
        return str(exc)
    return answer or "Я вижу экран, но описать его не получилось, сэр."


def read_screen_text(config: Config, region: str = "window", to_clipboard: bool = False) -> str:
    """Читает текст с экрана и при необходимости кладёт его в буфер обмена."""
    if not config.skills.vision.enabled:
        return "Зрение отключено в конфигурации, сэр."
    try:
        text = ocr_png(config.skills.vision, capture_png(config.skills.vision, region))
    except VisionError as exc:
        return str(exc)
    if not text:
        return "Текста на экране я не нашёл, сэр."
    if to_clipboard:
        write_clipboard(text)
        return f"Текст скопирован в буфер обмена, сэр. Начало: {text[:200]}"
    return f"На экране: {text[:1500]}"


def build_skills(config: Config) -> list[Skill]:
    """Создаёт навыки анализа экрана."""
    region_param = {
        "type": "string",
        "enum": list(REGIONS),
        "description": "window — активное окно, screen — весь экран",
    }
    return [
        Skill(
            name="analyze_screen",
            description=(
                "Посмотреть на экран пользователя мультимодальной моделью и ответить "
                "на вопрос о том, что там показано (таблица, страница, ошибка, перевод)."
            ),
            parameters=object_schema(
                {
                    "question": {
                        "type": "string",
                        "description": "Что нужно понять на экране",
                    },
                    "region": region_param,
                }
            ),
            handler=lambda question="", region="window": analyze_screen(config, question, region),
        ),
        Skill(
            name="read_screen_text",
            description=(
                "Распознать текст на экране через OCR: прочитать надпись, скопировать "
                "текст окна в буфер обмена."
            ),
            parameters=object_schema(
                {
                    "region": region_param,
                    "to_clipboard": {
                        "type": "boolean",
                        "description": "Скопировать распознанный текст в буфер обмена",
                    },
                }
            ),
            handler=lambda region="window", to_clipboard=False: read_screen_text(
                config, region, to_clipboard
            ),
        ),
    ]

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path

from ..config import ImageGenConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_OUTPUT_DIR = Path.home() / "Pictures" / "Jarvis" / "generated"


def _generate_openai(prompt: str, config: ImageGenConfig) -> str:
    """Генерирует через OpenAI DALL-E API."""
    api_key = os.environ.get("OPENAI_API_KEY", config.api_key)
    if not api_key:
        return "Не указан OPENAI_API_KEY, сэр."
    base_url = config.api_base or "https://api.openai.com/v1"
    url = f"{base_url}/images/generations"
    payload = json.dumps({
        "model": config.model,
        "prompt": prompt,
        "n": 1,
        "size": config.size,
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        image_url = result["data"][0]["url"]
        # Скачиваем
        return _download_image(image_url, prompt, config)
    except Exception as exc:
        return f"Ошибка генерации: {exc}, сэр."


def _generate_stable_diffusion(prompt: str, config: ImageGenConfig) -> str:
    """Генерирует через локальный Stable Diffusion WebUI API."""
    api_url = config.sd_url
    payload = json.dumps({
        "prompt": prompt,
        "steps": config.sd_steps,
        "width": 512, "height": 512,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{api_url}/sdapi/v1/txt2img",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        import base64
        img_data = base64.b64decode(result["images"][0])
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = _safe_filename(prompt)[:50] + ".png"
        out_path = _OUTPUT_DIR / filename
        out_path.write_bytes(img_data)
        return f"Картинка сохранена: {out_path}, сэр."
    except Exception as exc:
        return f"Ошибка Stable Diffusion: {exc}, сэр."


def _download_image(url: str, prompt: str, config: ImageGenConfig) -> str:
    """Скачивает сгенерированное изображение."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisAssistant/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = _safe_filename(prompt)[:50] + ".png"
        out_path = _OUTPUT_DIR / filename
        out_path.write_bytes(data)
        return f"Картинка сохранена: {out_path}, сэр."
    except Exception as exc:
        return f"Картинка сгенерирована, но не сохранена: {exc}, сэр."


def _safe_filename(text: str) -> str:
    """Безопасное имя файла из промпта."""
    import re
    name = re.sub(r'[^\w\s-]', '', text).strip()[:40]
    return name.replace(' ', '_') or "image"


def generate(config: ImageGenConfig, prompt: str) -> str:
    """Генерирует изображение по описанию."""
    if not prompt.strip():
        return "Пустой промпт, сэр."
    if config.backend == "openai":
        return _generate_openai(prompt, config)
    elif config.backend == "stable_diffusion":
        return _generate_stable_diffusion(prompt, config)
    # Auto: пробуем SD если доступен, иначе OpenAI
    if config.sd_url:
        return _generate_stable_diffusion(prompt, config)
    return _generate_openai(prompt, config)


def build_skills(config: ImageGenConfig) -> list[Skill]:
    return [
        Skill(
            name="generate_image",
            description="Сгенерировать изображение по текстовому описанию (DALL-E или Stable Diffusion).",
            parameters=object_schema(
                {"prompt": {"type": "string", "description": "Описание картинки"}},
                required=["prompt"],
            ),
            handler=lambda prompt: generate(config, prompt),
        ),
    ]

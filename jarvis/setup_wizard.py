"""Интерактивный мастер настройки Джарвиса.

Запуск: python -m jarvis setup
Проводит пользователя по шагам:
  1. Язык
  2. Мозг (Ollama / OpenAI / совместимый)
  3. Голос (TTS)
  4. Город для погоды
  5. Дополнительные навыки
Генерирует минимальный config.yaml с тем, что изменил пользователь.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import yaml


# ── Вспомогательные функции ─────────────────────────────────────────


def _ask(text: str, default: str = "") -> str:
    """Спрашивает у пользователя строку. Enter = default."""
    hint = f" [{default}]" if default else ""
    try:
        answer = input(f"  {text}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return answer or default


def _ask_choice(text: str, options: list[tuple[str, str]], default: str = "") -> str:
    """Спрашивает выбор из списка. Возвращает value первого элемента."""
    print(f"  {text}")
    for i, (key, label) in enumerate(options, 1):
        marker = " (по умолчанию)" if key == default else ""
        print(f"    {i}) {label}{marker}")
    while True:
        answer = _ask("Ваш выбор", default)
        # Позволяем вводить и номер, и ключ
        for i, (key, _) in enumerate(options, 1):
            if answer == str(i) or answer.lower() == key.lower():
                return key
        print(f"    Выберите число от 1 до {len(options)} или ключ: {', '.join(k for k, _ in options)}")


def _ask_yes(text: str, default: bool = True) -> bool:
    """Да/Нет вопрос."""
    hint = "Y/n" if default else "y/N"
    answer = _ask(f"{text} ({hint})", "да" if default else "нет")
    return answer.lower().startswith("д") or answer.lower().startswith("y") or (answer == "" and default)


def _check_ollama() -> bool:
    """Проверяет, доступен ли Ollama."""
    import subprocess
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _get_ollama_models() -> list[str]:
    """Возвращает список установленных моделей Ollama."""
    import subprocess
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return []
        lines = r.stdout.strip().split("\n")
        # Первая строка — заголовок
        return [line.split()[0] for line in lines[1:] if line.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _check_openai_key() -> bool:
    """Проверяет, задан ли OPENAI_API_KEY в окружении."""
    import os
    return bool(os.environ.get("OPENAI_API_KEY"))


# ── Шаги мастера ────────────────────────────────────────────────────


def _step_language() -> dict[str, str]:
    """Шаг 1: Язык."""
    print()
    print("── Язык ─────────────────────────────────────")
    lang = _ask_choice(
        "На каком языке Джарвис будет с вами общаться?",
        [
            ("ru", "Русский"),
            ("en", "English"),
        ],
        default="ru",
    )
    return {"lang": lang}


def _step_brain(lang: str) -> dict[str, Any]:
    """Шаг 2: Выбор мозга (LLM)."""
    from typing import Any

    print()
    print("── Мозг (LLM) ───────────────────────────────")
    print("  Джарвису нужна языковая модель для понимания команд.")
    print("  Ollama — бесплатная, работает локально (рекомендуется).")
    print("  OpenAI — платная, но работает без установки.")

    ollama_ok = _check_ollama()
    openai_ok = _check_openai_key()

    # Авто-определение лучшего варианта
    if ollama_ok and not openai_ok:
        recommended = "ollama"
    elif openai_ok and not ollama_ok:
        recommended = "openai"
    else:
        recommended = "ollama"

    backend = _ask_choice(
        "Что будете использовать?",
        [
            ("ollama", f"Ollama (локально) {'— установлен' if ollama_ok else '— НЕ установлен, нужно: ollama.com'}"),
            ("openai", f"OpenAI / совместимый {'— ключ есть' if openai_ok else '— нужен OPENAI_API_KEY'}"),
        ],
        default=recommended,
    )

    result: dict[str, Any] = {"backend": backend}

    if backend == "ollama":
        models = _get_ollama_models()
        if models:
            print(f"  Найдены модели: {', '.join(models)}")
            default_model = "qwen2.5:7b-instruct" if "qwen2.5:7b-instruct" in models else (models[0] if models else "")
            model = _ask("Какую модель использовать?", default_model)
        else:
            print("  Установленных моделей нет. Рекомендую:")
            print("    ollama pull qwen2.5:7b-instruct   # быстрая, хорошая по-русски")
            print("    ollama pull llama3.1:8b           # надежная")
            model = _ask("Модель (поставите позже через ollama pull)", "qwen2.5:7b-instruct")
        host = _ask("Адрес Ollama (если на этом ПК — Enter)", "http://127.0.0.1:11434")
        result.update({"ollama_model": model, "ollama_host": host})

    else:  # openai
        if not openai_ok:
            print()
            print("  ⚠  OPENAI_API_KEY не найден в переменных окружения.")
            print("  Задайте его ПЕРЕД запуском Джарвиса:")
            print("    Linux/Mac:  export OPENAI_API_KEY=sk-...")
            print("    Windows:    set OPENAI_API_KEY=sk-...")
            print()
        model = _ask("Модель", "gpt-4o-mini")
        base_url = _ask("Базовый URL (Enter для стандартного OpenAI, или OpenRouter/совместимый)", "")
        result.update({"openai_model": model, "openai_base_url": base_url})

    return result


def _step_voice(lang: str) -> dict[str, str]:
    """Шаг 3: Синтез речи (как Джарвис говорит)."""
    print()
    print("── Голос ────────────────────────────────────")

    import platform
    is_windows = platform.system() == "Windows"

    if is_windows:
        options = [
            ("sapi5", "Windows SAPI5 (офлайн, уже работает)"),
            ("edge", "Edge TTS (онлайн, звучит лучше, нужен интернет)"),
        ]
    else:
        options = [
            ("edge", "Edge TTS (онлайн, нейронный голос, нужен интернет)"),
        ]

    engine = _ask_choice("Какой движок озвучки?", options, default=options[0][0])
    result: dict[str, str] = {"tts_engine": engine}

    if engine == "edge":
        if lang == "ru":
            voice = _ask(
                "Голос Edge (Enter = по умолчанию)",
                "ru-RU-DmitryNeural",
            )
        else:
            voice = _ask(
                "Edge voice (Enter = default)",
                "en-US-AndrewNeural",
            )
        result["edge_voice"] = voice

    return result


def _step_weather(lang: str) -> dict[str, str]:
    """Шаг 4: Погода."""
    print()
    print("── Погода ───────────────────────────────────")
    if _ask_yes("Включить навык «погода»?", default=True):
        if lang == "ru":
            city = _ask("Ваш город", "Москва")
        else:
            city = _ask("Your city", "London")
        return {"weather_enabled": True, "weather_city": city}
    return {"weather_enabled": False}


def _step_skills() -> dict[str, bool]:
    """Шаг 5: Дополнительные навыки."""
    print()
    print("── Дополнительные навыки ────────────────────")
    print("  Остальные навыки уже включены по умолчанию.")
    print("  Здесь — те, которые требуют сторонних ключей или сервисов.")
    print()

    extras = [
        ("spotify", "Spotify (нужен аккаунт Spotify Developer)"),
        ("telegram", "Telegram бот (нужен бот от @BotFather)"),
        ("homeassistant", "Home Assistant / умный дом"),
        ("github", "GitHub (коммиты, issues, PR)"),
        ("image_gen", "Генерация картинок (DALL-E / Stable Diffusion)"),
        ("music_recognition", "Распознавание музыки (AudD API)"),
        ("passwords", "Менеджер паролей"),
    ]

    result: dict[str, bool] = {}
    for key, label in extras:
        if _ask_yes(f"  Включить «{label}»?", default=False):
            result[key] = True

    return result


def _step_api_keys(enabled_skills: dict[str, bool], lang: str) -> dict[str, str]:
    """Шаг 6: API ключи для выбранных навыков."""
    print()
    print("── API ключи ─────────────────────────────────")
    print("  Ключи хранятся в config.yaml. Для безопасности лучше"
          " использовать переменные окружения: ${VAR_NAME}")
    print()

    result: dict[str, str] = {}
    prompts: dict[str, tuple[str, str]] = {
        "telegram": ("Telegram бот-токен (от @BotFather)", "bot_token"),
        "homeassistant": ("Home Assistant токен (Long-lived access token)", "token"),
        "image_gen": ("API ключ для генерации картинок", "api_key"),
        "music_recognition": ("AudD API токен (audd.io)", "api_key"),
        "github": ("GitHub токен (или оставьте пустым — возьмётся из GITHUB_TOKEN)", "token"),
    }

    for skill_key, (prompt, field_name) in prompts.items():
        if enabled_skills.get(skill_key):
            val = _ask(f"  {prompt} (Enter чтобы задать позже)", "")
            if val:
                result[f"{skill_key}_{field_name}"] = val

    # Telegram: дополнительно нужен chat_id
    if enabled_skills.get("telegram"):
        if lang == "ru":
            cid = _ask("  Telegram chat ID (можно узнать у @userinfobot)", "")
        else:
            cid = _ask("  Telegram chat ID (check @userinfobot)", "")
        if cid:
            result["telegram_chat_id"] = cid

    return result


def _step_final() -> None:
    """Финальное сообщение."""
    print()
    print("════════════════════════════════════════════════")
    print("  Готово! Конфиг создан: config.yaml")
    print("════════════════════════════════════════════════")
    print()
    print("  Запуск:")
    print("    python -m jarvis              # голосовой режим")
    print("    python -m jarvis text         # текстовый режим")
    print("    python -m jarvis doctor       # проверка зависимостей")
    print()
    print("  Редактировать:  nano config.yaml  (или любой редактор)")
    print("  Все навыки:     https://github.com/Shuguy99/jarvis-pc#навыки")
    print()


# ── Генерация YAML ─────────────────────────────────────────────────


def _build_config(
    lang: str,
    brain: dict[str, Any],
    voice: dict[str, str],
    weather: dict[str, str],
    skills: dict[str, bool],
    api_keys: dict[str, str],
) -> dict[str, Any]:
    """Собирает словарь конфигурации из ответов мастера."""
    from typing import Any

    cfg: dict[str, Any] = {
        "log_level": "INFO",
        "greeting": "Все системы в норме, сэр." if lang == "ru" else "All systems nominal, sir.",
        "stt": {
            "language": "ru" if lang == "ru" else "en",
        },
        "brain": {},
        "skills": {
            "weather": {},
        },
    }

    # Мозг
    if brain["backend"] == "ollama":
        cfg["brain"] = {
            "backend": "ollama",
            "ollama_model": brain.get("ollama_model", "qwen2.5:7b-instruct"),
            "ollama_host": brain.get("ollama_host", "http://127.0.0.1:11434"),
        }
    else:
        brain_dict: dict[str, Any] = {
            "backend": "openai",
            "openai_model": brain.get("openai_model", "gpt-4o-mini"),
        }
        base_url = brain.get("openai_base_url", "")
        if base_url:
            brain_dict["openai_base_url"] = base_url
        cfg["brain"] = brain_dict

    # Голос
    if voice.get("tts_engine") == "edge":
        cfg["tts"] = {
            "engine": "edge",
            "edge_voice": voice.get("edge_voice", "ru-RU-DmitryNeural"),
        }

    # Погода
    if weather.get("weather_enabled"):
        cfg["skills"]["weather"] = {
            "enabled": True,
            "default_city": weather.get("weather_city", "Москва"),
        }
    else:
        cfg["skills"]["weather"] = {"enabled": False}

    # Дополнительные навыки
    for key, enabled in skills.items():
        if key == "github" and enabled:
            cfg["skills"][key] = {"enabled": True}
            if f"{key}_token" in api_keys:
                cfg["skills"][key]["token"] = api_keys[f"{key}_token"]
        elif key == "telegram" and enabled:
            cfg["skills"][key] = {"enabled": True}
            if f"{key}_bot_token" in api_keys:
                cfg["skills"][key]["bot_token"] = api_keys[f"{key}_bot_token"]
            if "telegram_chat_id" in api_keys:
                cfg["skills"][key]["chat_id"] = api_keys["telegram_chat_id"]
        elif key == "homeassistant" and enabled:
            cfg["skills"][key] = {"enabled": True}
            if f"{key}_token" in api_keys:
                cfg["skills"][key]["token"] = api_keys[f"{key}_token"]
        elif key == "image_gen" and enabled:
            cfg["skills"][key] = {"enabled": True, "backend": "openai"}
            if f"{key}_api_key" in api_keys:
                cfg["skills"][key]["api_key"] = api_keys[f"{key}_api_key"]
        elif key == "music_recognition" and enabled:
            cfg["skills"][key] = {"enabled": True}
            if f"{key}_api_key" in api_keys:
                cfg["skills"][key]["api_key"] = api_keys[f"{key}_api_key"]
        elif key == "passwords" and enabled:
            cfg["skills"][key] = {"enabled": True}
        elif key == "spotify" and enabled:
            cfg["skills"][key] = {"enabled": True}

    return cfg


def _save_config(data: dict[str, Any], path: Path) -> None:
    """Сохраняет конфиг в YAML с красивым форматированием."""
    from typing import Any

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Конфигурация Джарвиса (создана мастером настройки)\n"
        "# Редактируйте как угодно. Полный пример: config.example.yaml\n\n"
        + yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


# ── Точка входа ─────────────────────────────────────────────────────


def run_setup() -> int:
    """Запускает интерактивный мастер настройки."""
    from typing import Any

    print()
    print("╔═══════════════════════════════════════════════════╗")
    print("║  J.A.R.V.I.S. — Мастер настройки                 ║")
    print("║  Ответьте на несколько вопросов — и можно начать  ║")
    print("╚═══════════════════════════════════════════════════╝")

    # Проверяем нет ли уже config.yaml
    target = Path("config.yaml")
    if target.is_file():
        print()
        print(f"  ⚠  Файл {target} уже существует.")
        if not _ask_yes("Перезаписать? (старый конфиг будет потерян)", default=False):
            print("  Отменено.")
            return 0

    # Шаг 1: Язык
    lang_data = _step_language()
    lang = lang_data["lang"]

    # Шаг 2: Мозг
    brain_data = _step_brain(lang)

    # Шаг 3: Голос
    voice_data = _step_voice(lang)

    # Шаг 4: Погода
    weather_data = _step_weather(lang)

    # Шаг 5: Навыки
    skills_data = _step_skills()

    # Шаг 6: API ключи
    api_keys_data = _step_api_keys(skills_data, lang)

    # Генерация
    config_data = _build_config(lang, brain_data, voice_data, weather_data, skills_data, api_keys_data)
    _save_config(config_data, target)

    _step_final()
    return 0

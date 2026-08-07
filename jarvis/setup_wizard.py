"""Интерактивный мастер настройки Джарвиса.

Запуск: python -m jarvis setup
Проводит пользователя по ключевым шагам:
1. Проверка зависимостей
2. Выбор TTS-движка
3. Выбор LLM-бэкенда
4. Настройка голоса и микрофона
5. Включение/отключение UI
6. Создание config.yaml
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

import yaml


def _c(text: str, code: int = 0) -> str:
    """Цветной текст ANSI (0=reset, 1=bold, 31=red, 32=green, 33=yellow, 34=blue, 36=cyan)."""
    return f"\033[{code}m{text}\033[0m"


def _bold(text: str) -> str:
    return _c(text, 1)


def _green(text: str) -> str:
    return _c(text, 32)


def _yellow(text: str) -> str:
    return _c(text, 33)


def _cyan(text: str) -> str:
    return _c(text, 36)


def _red(text: str) -> str:
    return _c(text, 31)


def _input(prompt: str, default: str = "") -> str:
    """Ввод с подсказкой дефолта."""
    hint = f" [{_green(default)}]" if default else ""
    try:
        val = input(f"  {prompt}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val or default


def _choice(prompt: str, options: list[tuple[str, str]], default: int = 0) -> str:
    """Выбор из списка. Возвращает value первого элемента."""
    print(f"  {prompt}:")
    for i, (label, desc) in enumerate(options):
        marker = _bold("> ") if i == default else "  "
        print(f"    {marker}{_cyan(str(i + 1))}. {label} — {desc}")
    while True:
        try:
            val = input(f"  Ваш выбор [{_green(str(default + 1))}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not val:
            return options[default][0]
        try:
            idx = int(val) - 1
            if 0 <= idx < len(options):
                return options[idx][0]
        except ValueError:
            pass
        print(f"    {_yellow('Введите число от 1 до ' + str(len(options)))}")


def _yes_no(prompt: str, default: bool = True) -> bool:
    """Да/Нет вопрос."""
    hint = "[Y/n]" if default else "[y/N]"
    try:
        val = input(f"  {prompt} {hint}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    if not val:
        return default
    return val in ("y", "yes", "да", "д")


def _check_module(name: str) -> bool:
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _check_cmd(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None


def step_welcome() -> None:
    print()
    print(_bold("╔══════════════════════════════════════════════════╗"))
    print(_bold("║     Мастер настройки J.A.R.V.I.S.              ║"))
    print(_bold("║     Интерактивная настройка ассистента         ║"))
    print(_bold("╚══════════════════════════════════════════════════╝"))
    print()
    print(f"  {_yellow('Этот мастер поможет настроить Джарвиса за пару минут.')}")
    print(f"  {_yellow('Отвечайте на вопросы или нажимайте Enter для значений по умолчанию.')}")
    print()


def step_check_deps() -> list[str]:
    """Проверяет зависимости и возвращает список отсутствующих."""
    print(_bold("[1/6] Проверка зависимостей..."))
    print()
    checks = [
        ("sounddevice", "захват микрофона", True),
        ("webrtcvad", "детектор речи (VAD)", True),
        ("faster_whisper", "распознавание речи (STT)", True),
        ("edge_tts", "neural-голос (TTS)", False),
        ("pyttsx3", "офлайн-голос (TTS)", False),
        ("openwakeword", "пробуждение по слову", False),
        ("PySide6", "HUD-оверлей", False),
        ("playwright", "автоматизация браузера", False),
        ("psutil", "статус системы", False),
        ("chromadb", "долговременная память", False),
    ]
    missing: list[str] = []
    for module, purpose, critical in checks:
        ok = _check_module(module)
        if ok:
            print(f"    {_green('OK')}  {module:<18} — {purpose}")
        else:
            tag = _red("!!!") if critical else _yellow("... ")
            print(f"    {tag}  {module:<18} — {purpose}")
            missing.append(f"pip install {module.replace('_', '-')}")
    # Системные утилиты
    for cmd, purpose in [("mpv", "плеер для музыки"), ("yt-dlp", "загрузка с YouTube")]:
        ok = _check_cmd(cmd)
        if ok:
            print(f"    {_green('OK')}  {cmd:<18} — {purpose}")
        else:
            print(f"    {_yellow('... ')}  {cmd:<18} — {purpose}")
            if cmd == "mpv":
                missing.append("apt install mpv  (или скачайте с mpv.io)")
            else:
                missing.append("pip install yt-dlp")
    if missing:
        print()
        print(f"  {_yellow('Отсутствуют некоторые компоненты. Установите их позже:')}")
        for m in missing:
            print(f"    {m}")
    print()
    return missing


def step_tts() -> dict:
    """Выбор TTS-движка."""
    print(_bold("[2/6] Настройка голоса (TTS)"))
    print()
    has_edge = _check_module("edge_tts")
    has_sapi = _check_module("pyttsx3")
    if not has_edge and not has_sapi:
        print(f"  {_red('Ни один TTS-движок не установлен!')}")
        print(f"  {_yellow('Установите: pip install edge-tts')}")
        print()
        return {"tts": {"engine": "edge", "edge_voice": "ru-RU-DmitryNeural", "rate": 190, "volume": 1.0}}
    if has_edge:
        engine = _choice("Выберите TTS-движок", [
            ("edge", "Microsoft Edge Neural TTS (качественный, нужен интернет)"),
            ("sapi5", "pyttsx3 / SAPI5 (офлайн, Windows)"),
        ], default=0)
    else:
        engine = "sapi5"
        print(f"  {_yellow('edge-tts не установлен, используем pyttsx3')}")
    config: dict = {"tts": {"engine": engine, "rate": 190, "volume": 1.0}}
    if engine == "edge":
        print()
        print("  Доступные русские голоса Edge:")
        voices = [
            ("ru-RU-DmitryNeural", "Дмитрий (мужской, по умолчанию)"),
            ("ru-RU-SvetlanaNeural", "Светлана (женский)"),
        ]
        voice = _choice("Голос", voices, default=0)
        config["tts"]["edge_voice"] = voice
    else:
        voice_name = _input("Имя голоса SAPI (часть, например 'Irina' или 'David')", "")
        if voice_name:
            config["tts"]["voice"] = voice_name
    rate = _input("Скорость речи (50-450, по умолчанию 190)", "190")
    try:
        config["tts"]["rate"] = int(rate)
    except ValueError:
        pass
    print()
    return config


def step_brain() -> dict:
    """Выбор LLM-бэкенда."""
    print(_bold("[3/6] Настройка мозга (LLM)"))
    print()
    backend = _choice("Выберите бэкенд", [
        ("ollama", "Ollama (локальная модель, бесплатно, нужна установка)"),
        ("openai", "OpenAI / совместимое API (GPT-4o-mini и др.)"),
        ("offline", "Оффлайн-режим (только навыки, без LLM)"),
    ], default=0)
    config: dict = {"brain": {"backend": backend, "temperature": 0.4, "max_history": 20, "max_tool_iterations": 5}}
    if backend == "ollama":
        print()
        host = _input("Адрес Ollama", "http://127.0.0.1:11434")
        model = _input("Модель Ollama", "qwen2.5:7b-instruct")
        config["brain"]["ollama_host"] = host
        config["brain"]["ollama_model"] = model
        print(f"  {_yellow('Убедитесь что Ollama запущена и модель загружена:')}")
        print(f"    ollama serve && ollama pull {model}")
    elif backend == "openai":
        print()
        print(f"  {_yellow('API-ключ берётся из переменной окружения OPENAI_API_KEY.')}")
        base_url = _input("Базовый URL (пустой = api.openai.com)", "")
        model = _input("Модель", "gpt-4o-mini")
        if base_url:
            config["brain"]["openai_base_url"] = base_url
        config["brain"]["openai_model"] = model
    print()
    return config


def step_stt_mic() -> dict:
    """Настройка STT и микрофона."""
    print(_bold("[4/6] Настройка распознавания речи и микрофона"))
    print()
    config: dict = {
        "stt": {"model": "small", "language": "ru", "device": "auto", "compute_type": "int8"},
        "mic": {"sample_rate": 16000, "frame_ms": 30, "vad_aggressiveness": 2, "silence_ms": 800},
    }
    if not _check_module("faster_whisper"):
        print(f"  {_yellow('faster-whisper не установлен — распознавание речи не будет работать.')}")
        print(f"  Установите: pip install faster-whisper")
        print()
        return config
    print("  Модели STT (от быстрой к точной):")
    model = _choice("Модель Whisper", [
        ("tiny", "крошечная — супер быстро, много ошибок"),
        ("base", "базовая — быстро, неплохо для русского"),
        ("small", "маленькая — баланс скорости и качества (рекомендую)"),
        ("medium", "средняя — медленнее, точнее"),
        ("large-v3", "большая — самая точная, требует 10GB+ RAM"),
    ], default=2)
    config["stt"]["model"] = model
    lang = _choice("Основной язык", [
        ("ru", "Русский"),
        ("en", "English"),
        ("auto", "Автоопределение"),
    ], default=0)
    config["stt"]["language"] = lang
    if _check_module("sounddevice"):
        print()
        print(f"  {_cyan('Чтобы выбрать микрофон, запустите: python -m jarvis devices')}")
        dev = _input("Индекс микрофона (пустой = по умолчанию)", "")
        if dev:
            try:
                config["mic"]["device"] = int(dev)
            except ValueError:
                pass
    print()
    return config


def step_ui_wakeword() -> dict:
    """Настройка UI и слова пробуждения."""
    print(_bold("[5/6] Настройка интерфейса и пробуждения"))
    print()
    config: dict = {}
    # UI
    has_pyside6 = _check_module("PySide6")
    ui_on = False
    if has_pyside6:
        ui_on = _yes_no("Включить HUD-оверлей (прозрачное окно Джарвиса)?", default=False)
    else:
        print(f"  {_yellow('PySide6 не установлен — HUD отключён.')}")
    config["ui"] = {"enabled": ui_on, "opacity": 0.85, "accent": "#3fd0ff", "corner": "bottom-right"}
    # Wakeword
    has_www = _check_module("openwakeword")
    ww_on = False
    if has_www:
        ww_on = _yes_no("Включить пробуждение по слову 'Джарвис'? (openwakeword)", default=True)
    else:
        print(f"  {_yellow('openwakeword не установлен — пробуждение по слову отключено.')}")
        print(f"  Установите: pip install openwakeword")
    config["wake_word"] = {"enabled": ww_on, "threshold": 0.5, "fallback_phrases": ["джарвис", "jarvis"]}
    # Monitor
    mon_on = _yes_no("Включить фоновый мониторинг (батарея, память, диск)?", default=True)
    config["monitor"] = {"enabled": mon_on, "interval_s": 60, "battery_low": 20, "battery_critical": 10}
    # Hotkey
    system = platform.system()
    if system == "Linux":
        default_hotkey = "ctrl+alt+j"
    elif system == "Windows":
        default_hotkey = "ctrl+alt+j"
    else:
        default_hotkey = "cmd+alt+j"
    hotkey = _input(f"Горячая клавиша для активации", default_hotkey)
    config["hotkey"] = hotkey
    print()
    return config


def step_finish(config: dict) -> int:
    """Сохраняет config.yaml и показывает итог."""
    print(_bold("[6/6] Сохранение конфигурации"))
    print()
    # Определяем путь
    default_path = Path.home() / ".jarvis" / "config.yaml"
    use_home = _yes_no(f"Сохранить в {default_path}?", default=True)
    if use_home:
        target = default_path
    else:
        p = _input("Путь к файлу конфигурации", "config.yaml")
        target = Path(p).expanduser()
    if target.exists():
        if not _yes_no(f"Файл {target} существует. Перезаписать?", default=False):
            print(f"  {_yellow('Конфигурация не сохранена.')}")
            return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"  {_green(f'Конфигурация сохранена: {target}')}")
    print()
    print(_bold("══════════════════════════════════════════════════"))
    print(f"  {_green('Настройка завершена!')}")
    print()
    print(f"  Запустить Джарвиса:")
    print(f"    {_cyan('python -m jarvis voice')}       — голосовой режим")
    print(f"    {_cyan('python -m jarvis text')}        — текстовый режим")
    print(f"    {_cyan('python -m jarvis doctor')}      — диагностика")
    print()
    if target != Path("config.yaml"):
        print(f"  Указать путь к конфигу:")
        print(f"    {_cyan(f'python -m jarvis voice --config {target}')}")
        print()
    print(_bold("══════════════════════════════════════════════════"))
    return 0


def run_setup() -> int:
    """Запускает мастер настройки."""
    step_welcome()
    step_check_deps()
    config: dict = {
        "greeting": "Все системы в норме, сэр.",
        "log_level": "INFO",
    }
    config.update(step_tts())
    config.update(step_brain())
    config.update(step_stt_mic())
    config.update(step_ui_wakeword())
    return step_finish(config)

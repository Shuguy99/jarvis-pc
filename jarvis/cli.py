"""Точка входа: режимы запуска Джарвиса."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from .assistant import Assistant, Event, State
from .config import Config, load_config

log = logging.getLogger(__name__)

BANNER = r"""
   ___  ___    ___    _  __ __   __ ____  ____
  |_  || _ \  / _ \  | |/ / \ \ / /|_  _|/ ___|
   | || |_) || |_| | |   <   \ V /   ||  \___ \
  _| ||  _ < |  _  | | |\ \   | |    ||   ___) |
 |___||_| \_\|_| |_| |_| \_\  |_|  |____||____/
"""


def _setup_logging(level: str) -> None:
    """Настраивает единый формат логов."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_event(event: Event) -> None:
    """Печатает события ассистента в консоль."""
    if event.state is State.LISTENING:
        print("[слушаю...]")
    elif event.text and event.speaker == "jarvis":
        print(f"J.A.R.V.I.S.: {event.text}")


EXIT_WORDS = {"выход", "exit", "quit", "стоп"}


def _prompt_loop(assistant: Assistant) -> None:
    """Читает команды с клавиатуры, пока пользователь не завершит диалог."""
    print(BANNER)
    print(f"Мозг: {type(assistant.brain).__name__}, навыков: {len(assistant.skills)}")
    print("Введите команду или «выход».\n")
    assistant.monitor.start()
    while True:
        try:
            line = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if line.lower() in EXIT_WORDS:
            return
        if line:
            assistant.handle_text(line)


def run_text(config: Config) -> int:
    """Текстовый режим: команды вводятся с клавиатуры, HUD — если включён."""
    if config.ui.enabled:
        from .ui import run_hud

        return run_hud(config, _prompt_loop)
    assistant = Assistant(config, _print_event)
    try:
        _prompt_loop(assistant)
    finally:
        assistant.shutdown()
    return 0


def run_voice(config: Config) -> int:
    """Голосовой режим с HUD-оверлеем или без него."""
    if config.ui.enabled:
        from .ui import run_hud

        return run_hud(config)
    assistant = Assistant(config, _print_event)
    print(BANNER)
    try:
        assistant.listen_forever()
    except KeyboardInterrupt:
        pass
    finally:
        assistant.shutdown()
    return 0


def run_once(config: Config, command: str) -> int:
    """Выполняет одну команду и завершается."""
    assistant = Assistant(config, _print_event)
    try:
        reply = assistant.handle_text(command)
    finally:
        assistant.shutdown()
    print(reply)
    return 0


def list_devices() -> int:
    """Печатает доступные аудиоустройства."""
    try:
        import sounddevice as sd  # type: ignore[import-not-found]
    except ImportError:
        print("sounddevice не установлен")
        return 1
    print(sd.query_devices())
    return 0


def doctor(config: Config) -> int:
    """Проверяет наличие зависимостей и готовность подсистем."""
    checks: list[tuple[str, bool, str]] = []
    for module, purpose in (
        ("sounddevice", "захват микрофона"),
        ("webrtcvad", "детектор речи"),
        ("faster_whisper", "распознавание речи"),
        ("openwakeword", "пробуждение по слову «Джарвис»"),
        ("pyttsx3", "офлайн-голос Windows"),
        ("edge_tts", "neural-голос Edge"),
        ("PySide6", "HUD-оверлей"),
        ("psutil", "статус системы"),
        ("mss", "скриншоты"),
        ("pyperclip", "буфер обмена"),
        ("pygetwindow", "управление окнами"),
        ("pycaw", "точная громкость Windows"),
        ("PIL", "подготовка снимков для анализа"),
        ("pytesseract", "чтение текста с экрана (OCR)"),
        ("chromadb", "долговременная память"),
        ("playwright", "автоматизация браузера"),
        ("spotipy", "управление Spotify"),
    ):
        try:
            __import__(module)
            checks.append((module, True, purpose))
        except ImportError:
            checks.append((module, False, purpose))
    for module, ok, purpose in checks:
        print(f"{'[ok]  ' if ok else '[нет] '}{module:<16} — {purpose}")

    backend = config.brain.backend
    print(f"\nБэкенд мозга: {backend}")
    if backend == "openai":
        print("OPENAI_API_KEY:", "задан" if config.openai_api_key else "отсутствует")
    if backend == "ollama":
        from .brain.ollama_brain import OllamaBrain
        from .skills import build_registry

        skills, services = build_registry(config, lambda text: None)
        try:
            OllamaBrain(config.brain, skills).check()
            print("Ollama: доступна")
        except RuntimeError as exc:
            print(f"Ollama: {exc}")
        finally:
            services.shutdown()
    if config.skills.spotify.enabled:
        has_keys = bool(
            os.environ.get("SPOTIFY_CLIENT_ID") and os.environ.get("SPOTIFY_CLIENT_SECRET")
        )
        print("Spotify: ключи", "заданы" if has_keys else "отсутствуют")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Создаёт разбор аргументов командной строки."""
    parser = argparse.ArgumentParser(
        prog="jarvis", description="Голосовой ассистент Джарвис для ПК"
    )
    parser.add_argument("--config", help="путь к config.yaml")
    parser.add_argument("--log-level", help="уровень логирования")
    sub = parser.add_subparsers(dest="mode")
    sub.add_parser("voice", help="голосовой режим (по умолчанию)")
    sub.add_parser("text", help="текстовый режим в консоли")
    sub.add_parser("devices", help="список аудиоустройств")
    sub.add_parser("doctor", help="диагностика зависимостей")
    once = sub.add_parser("once", help="выполнить одну команду")
    once.add_argument("command", nargs="+", help="текст команды")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Запускает выбранный режим работы."""
    args = build_parser().parse_args(argv)
    if args.config and not Path(args.config).is_file():
        print(f"Файл конфига не найден: {args.config}", file=sys.stderr)
        return 2
    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(f"Ошибка в конфиге: {exc}", file=sys.stderr)
        return 2
    _setup_logging(args.log_level or config.log_level)
    mode = args.mode or "voice"
    if mode == "text":
        return run_text(config)
    if mode == "devices":
        return list_devices()
    if mode == "doctor":
        return doctor(config)
    if mode == "once":
        return run_once(config, " ".join(args.command))
    return run_voice(config)


if __name__ == "__main__":
    sys.exit(main())

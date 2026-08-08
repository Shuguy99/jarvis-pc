"""Файловый менеджер: поиск, копирование, перемещение файлов по голосу."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from ..config import FilesConfig
from .registry import Skill, _confirm_handler, object_schema

log = logging.getLogger(__name__)


def _human_size(size: int) -> str:
    """Форматированный размер файла."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.0f} TB"


def list_files(config: FilesConfig, directory: str = "", pattern: str = "") -> str:
    """Показывает файлы в директории, опционально фильтруя по шаблону."""
    base = directory or config.home_dir
    target = Path(base).expanduser()
    if not target.is_dir():
        return f"Директория {base} не найдена, сэр."
    entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    if pattern:
        try:
            entries = [e for e in entries if e.match(pattern)]
        except Exception:
            log.debug("files: ошибка (line 35)")
            entries = [e for e in entries if pattern.lower() in e.name.lower()]
    if not entries:
        filter_msg = f" по шаблону '{pattern}'" if pattern else ""
        return f"В {base} нет файлов{filter_msg}, сэр."
    lines = [f"Файлы в {base}:"]
    for entry in entries[:30]:
        kind = "[DIR] " if entry.is_dir() else ""
        suffix = ""
        if entry.is_file():
            try:
                suffix = f" ({_human_size(entry.stat().st_size)})"
            except OSError:
                pass
        lines.append(f"{kind}{entry.name}{suffix}")
    if len(entries) > 30:
        lines.append(f"... и ещё {len(entries) - 30} элементов.")
    return "\n".join(lines)


def search_files(config: FilesConfig, query: str, directory: str = "") -> str:
    """Рекурсивно ищет файлы по имени."""
    if not query.strip():
        return "Укажите что искать, сэр."
    base = directory or config.home_dir
    target = Path(base).expanduser()
    if not target.is_dir():
        return f"Директория {base} не найдена, сэр."
    query_lower = query.lower()
    found = []
    try:
        for entry in target.rglob("*"):
            if len(found) >= 20:
                break
            if query_lower in entry.name.lower():
                found.append(entry)
    except PermissionError:
        pass
    if not found:
        return f"По запросу '{query}' ничего не найдено в {base}, сэр."
    lines = [f"Найдено {len(found)} файлов по запросу '{query}':"]
    for entry in found:
        rel = entry.relative_to(target)
        lines.append(f"  {rel}")
    return "\n".join(lines)


def copy_file(config: FilesConfig, source: str, destination: str) -> str:
    """Копирует файл или директорию."""
    src = Path(source).expanduser()
    dst = Path(destination).expanduser()
    if not src.exists():
        return f"Источник {source} не найден, сэр."
    try:
        if src.is_dir():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
        return f"Скопировано: {source} -> {destination}."
    except Exception as exc:
        return f"Ошибка копирования: {exc}, сэр."


def move_file(config: FilesConfig, source: str, destination: str) -> str:
    """Перемещает файл или директорию."""
    src = Path(source).expanduser()
    dst = Path(destination).expanduser()
    if not src.exists():
        return f"Источник {source} не найден, сэр."
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Перемещено: {source} -> {destination}."
    except Exception as exc:
        return f"Ошибка перемещения: {exc}, сэр."


def delete_file(config: FilesConfig, path: str) -> str:
    """Удаляет файл или директорию."""
    target = Path(path).expanduser()
    if not target.exists():
        return f"{path} не найден, сэр."
    protected = {Path.home(), Path("/"), Path("/home")}
    try:
        if target.resolve() in {p.resolve() for p in protected}:
            return "Нет уж, сэр. Удалять системные каталоги я не буду."
    except (OSError, ValueError):
        pass
    try:
        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()
        return f"Удалено: {path}."
    except Exception as exc:
        return f"Ошибка удаления: {exc}, сэр."


def file_info(config: FilesConfig, path: str) -> str:
    """Показывает информацию о файле."""
    target = Path(path).expanduser()
    if not target.exists():
        return f"{path} не найден, сэр."
    try:
        stat = target.stat()
    except OSError as exc:
        return f"Не удалось получить информацию: {exc}, сэр."
    kind = "директория" if target.is_dir() else "файл"
    if target.is_file():
        size = _human_size(stat.st_size)
    else:
        try:
            size = f"{len(list(target.iterdir()))} элементов"
        except PermissionError:
            size = "нет доступа к содержимому"
    mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M")
    ext = target.suffix or "нет расширения"
    return f"{target.name}: {kind}, размер {size}, изменён {mtime}, расширение {ext}."


def create_directory(config: FilesConfig, path: str) -> str:
    """Создаёт директорию."""
    target = Path(path).expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True)
        return f"Директория создана: {path}."
    except Exception as exc:
        return f"Ошибка создания директории: {exc}, сэр."


def build_skills(config: FilesConfig) -> list[Skill]:
    """Создаёт навыки файлового менеджера."""
    return [
        Skill(
            name="list_files",
            description=(
                "Показать файлы в директории. Можно указать шаблон для фильтрации (glob: *.py). "
                "Без аргументов — показывает домашнюю директорию."
            ),
            parameters=object_schema(
                {
                    "directory": {"type": "string", "description": "Путь к директории (пустое = домашняя)"},
                    "pattern": {"type": "string", "description": "Шаблон имени файла, например *.txt"},
                },
            ),
            handler=lambda directory="", pattern="": list_files(config, directory, pattern),
        ),
        Skill(
            name="search_files",
            description="Рекурсивно найти файлы по имени в директории.",
            parameters=object_schema(
                {
                    "query": {"type": "string", "description": "Часть имени файла для поиска"},
                    "directory": {"type": "string", "description": "Где искать (пустое = домашняя директория)"},
                },
                required=["query"],
            ),
            handler=lambda query, directory="": search_files(config, query, directory),
        ),
        Skill(
            name="copy_file",
            description="Копировать файл или папку в другое место.",
            parameters=object_schema(
                {
                    "source": {"type": "string", "description": "Что копировать (путь)"},
                    "destination": {"type": "string", "description": "Куда копировать (путь)"},
                },
                required=["source", "destination"],
            ),
            handler=lambda source, destination: copy_file(config, source, destination),
        ),
        Skill(
            name="move_file",
            description="Переместить файл или папку.",
            parameters=object_schema(
                {
                    "source": {"type": "string", "description": "Что перемещать (путь)"},
                    "destination": {"type": "string", "description": "Куда переместить (путь)"},
                },
                required=["source", "destination"],
            ),
            handler=lambda source, destination: move_file(config, source, destination),
        ),
        Skill(
            name="delete_file",
            description="Удалить файл или директорию. Защита от удаления системных путей.",
            parameters=object_schema(
                {
                    "path": {"type": "string", "description": "Путь к файлу или папке"},
                },
                required=["path"],
            ),
            handler=_confirm_handler(lambda path: delete_file(config, path), "Удалить {path}?"),
        ),
        Skill(
            name="file_info",
            description="Показать информацию о файле: размер, дата, тип.",
            parameters=object_schema(
                {
                    "path": {"type": "string", "description": "Путь к файлу"},
                },
                required=["path"],
            ),
            handler=lambda path: file_info(config, path),
        ),
        Skill(
            name="create_directory",
            description="Создать новую директорию.",
            parameters=object_schema(
                {
                    "path": {"type": "string", "description": "Путь новой директории"},
                },
                required=["path"],
            ),
            handler=lambda path: create_directory(config, path),
        ),
    ]

"""Анализ диска: что занимает место."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from pathlib import Path

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"


def disk_usage(path: str = "~") -> str:
    """Общая статистика по дискам/разделам."""
    path = os.path.expanduser(path)
    if IS_WINDOWS:
        try:
            result = subprocess.run(
                ["wmic", "logicaldisk", "get", "size,freespace,caption"],
                capture_output=True, text=True, check=False, timeout=10,
            )
            lines = ["Диски:"]
            for line in result.stdout.strip().split("\n")[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    letter = parts[0]
                    free = int(parts[1]) // (1024**3)
                    total = int(parts[2]) // (1024**3)
                    used = total - free
                    pct = int(used / total * 100) if total else 0
                    lines.append(f"  {letter}: {used}/{total} ГБ занято ({pct}%)")
            return "\n".join(lines) if len(lines) > 1 else "Не удалось получить информацию, сэр."
        except Exception:
            log.debug("disk: wmic недоступен, используем fallback")
    # Linux / fallback через shutil
    p = Path(path)
    if not p.is_dir():
        return f"{path} не найден, сэр."
    try:
        usage = shutil.disk_usage(str(p))
    except Exception:
        log.debug("disk: не удалось получить статистику для %s", path)
        return f"Не удалось получить статистику для {path}, сэр."
    total_gb = usage.total / (1024**3)
    used_gb = usage.used / (1024**3)
    free_gb = usage.free / (1024**3)
    pct = int(usage.used / usage.total * 100) if usage.total else 0
    return (
        f"{path}: {used_gb:.1f}/{total_gb:.1f} ГБ занято ({pct}%), "
        f"свободно {free_gb:.1f} ГБ, сэр."
    )


def top_dirs(path: str = "~", count: int = 15) -> str:
    """Топ самых тяжёлых папок."""
    path = os.path.expanduser(path)
    p = Path(path)
    if not p.is_dir():
        return f"{path} не найден, сэр."
    # Собираем размеры
    sizes: list[tuple[int, str]] = []
    try:
        for entry in p.iterdir():
            if entry.is_dir() and not entry.is_symlink() and not entry.name.startswith("."):
                try:
                    total = sum(
                        f.stat().st_size for f in entry.rglob("*") if f.is_file()
                    )
                    sizes.append((total, entry.name))
                except (PermissionError, OSError):
                    continue
            elif entry.is_file():
                try:
                    sizes.append((entry.stat().st_size, entry.name))
                except OSError:
                    continue
    except PermissionError:
        return f"Нет доступа к {path}, сэр."
    if not sizes:
        return f"{path} пуст, сэр."
    sizes.sort(reverse=True)
    lines = [f"Топ {count} в {path}:"]
    for size, name in sizes[:count]:
        if size >= 1024**3:
            size_str = f"{size / (1024**3):.1f} ГБ"
        elif size >= 1024**2:
            size_str = f"{size / (1024**2):.1f} МБ"
        elif size >= 1024:
            size_str = f"{size / 1024:.1f} КБ"
        else:
            size_str = f"{size} Б"
        lines.append(f"  {name:<30} {size_str:>10}")
    return "\n".join(lines)


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="disk_usage",
            description="Статистика дискового пространства.",
            parameters=object_schema(
                {"path": {"type": "string", "description": "Путь (по умолчанию ~)"}}
            ),
            handler=lambda path="~": disk_usage(path),
        ),
        Skill(
            name="top_dirs",
            description="Топ самых тяжёлых папок/файлов в директории.",
            parameters=object_schema(
                {
                    "path": {"type": "string", "description": "Путь (по умолчанию ~)"},
                    "count": {"type": "integer", "description": "Сколько (по умолчанию 15)"},
                }
            ),
            handler=lambda path="~", count=15: top_dirs(path, count),
        ),
    ]

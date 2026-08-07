from __future__ import annotations

import logging
import os
import platform
import shutil
import signal
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"


def _parse_ps() -> list[dict[str, str]]:
    """Получает список процессов."""
    if IS_WINDOWS:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        procs = []
        for line in result.stdout.strip().split("\n"):
            parts = line.strip('"').split('","')
            if len(parts) >= 2:
                name = parts[0].split('\\')[-1]
                procs.append({"pid": parts[1], "name": name, "mem": parts[4] if len(parts) > 4 else "?"})
        return procs
    else:
        result = subprocess.run(
            ["ps", "aux", "--sort=-%cpu"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        procs = []
        for line in result.stdout.strip().split("\n")[1:]:
            parts = line.split(None, 10)
            if len(parts) >= 11:
                procs.append({
                    "user": parts[0], "pid": parts[1],
                    "cpu": parts[2], "mem": parts[3],
                    "name": parts[10][:50],
                })
        return procs


def top_cpu(count: int = 10) -> str:
    """Топ процессов по CPU."""
    procs = _parse_ps()
    if IS_LINUX:
        lines = [f"{'PID':>7} {'CPU%':>6} {'MEM%':>6}  Имя"]
        for p in procs[:count]:
            lines.append(f"{p['pid']:>7} {p['cpu']:>6} {p['mem']:>6}  {p['name']}")
    else:
        lines = [f"{'PID':>7}  Имя"]
        for p in procs[:count]:
            lines.append(f"{p['pid']:>7}  {p['name']}")
    return "\n".join(lines)


def top_mem(count: int = 10) -> str:
    """Топ процессов по памяти."""
    procs = _parse_ps()
    if IS_LINUX:
        procs.sort(key=lambda p: float(p.get("mem", 0)), reverse=True)
        lines = [f"{'PID':>7} {'CPU%':>6} {'MEM%':>6}  Имя"]
        for p in procs[:count]:
            lines.append(f"{p['pid']:>7} {p['cpu']:>6} {p['mem']:>6}  {p['name']}")
    else:
        lines = [f"{'PID':>7}  Память  Имя"]
        for p in procs[:count]:
            lines.append(f"{p['pid']:>7}  {p['mem']:>8}  {p['name']}")
    return "\n".join(lines)


def kill_process(target: str) -> str:
    """Убивает процесс по PID или имени."""
    try:
        pid = int(target)
        # По PID
        os.kill(pid, signal.SIGTERM)
        return f"Процесс {pid} завершён, сэр."
    except ValueError:
        pass  # Не PID — по имени
    except ProcessLookupError:
        return f"Процесс {target} не найден, сэр."
    except PermissionError:
        return f"Нет прав для завершения {target}, сэр."
    # По имени
    if IS_WINDOWS:
        result = subprocess.run(
            ["taskkill", "/F", "/IM", target],
            capture_output=True, text=True, check=False, timeout=10,
        )
    else:
        result = subprocess.run(
            ["pkill", "-f", target],
            capture_output=True, text=True, check=False, timeout=10,
        )
    if result.returncode == 0:
        return f"Процесс '{target}' завершён, сэр."
    return f"Не удалось завершить '{target}', сэр."


def proc_info(pid: str) -> str:
    """Информация о процессе."""
    try:
        pid_int = int(pid)
    except ValueError:
        return "PID должен быть числом, сэр."
    if IS_LINUX:
        result = subprocess.run(
            ["ps", "-p", pid, "-o", "pid,user,%cpu,%mem,etime,args"],
            capture_output=True, text=True, check=False, timeout=5,
        )
        return result.stdout.strip() or f"Процесс {pid} не найден, сэр."
    if IS_WINDOWS:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/V", "/FO", "LIST"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        return result.stdout.strip() or f"Процесс {pid} не найден, сэр."
    return f"Процесс {pid}: информация недоступна, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="top_cpu",
            description="Топ процессов по нагрузке на CPU.",
            parameters=object_schema(
                {"count": {"type": "integer", "description": "Сколько (по умолчанию 10)"}}
            ),
            handler=lambda count=10: top_cpu(count),
        ),
        Skill(
            name="top_mem",
            description="Топ процессов по потреблению памяти.",
            parameters=object_schema(
                {"count": {"type": "integer", "description": "Сколько (по умолчанию 10)"}}
            ),
            handler=lambda count=10: top_mem(count),
        ),
        Skill(
            name="kill_process",
            description="Завершить процесс по PID или имени.",
            parameters=object_schema(
                {"target": {"type": "string", "description": "PID или имя процесса"}},
                required=["target"],
            ),
            handler=lambda target: kill_process(target),
        ),
        Skill(
            name="proc_info",
            description="Подробная информация о процессе по PID.",
            parameters=object_schema(
                {"pid": {"type": "string", "description": "PID процесса"}},
                required=["pid"],
            ),
            handler=lambda pid: proc_info(pid),
        ),
    ]

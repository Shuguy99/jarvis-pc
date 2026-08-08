"""Сетевые утилиты: пинг, скорость, открытые порты."""

from __future__ import annotations

import logging
import platform
import re
import shutil
import socket
import subprocess

from .registry import Skill, object_schema

log = logging.getLogger(__name__)

IS_LINUX = platform.system() == "Linux"
IS_WINDOWS = platform.system() == "Windows"


def ping(host: str = "google.com", count: int = 4) -> str:
    """Пингует хост."""
    if IS_WINDOWS:
        cmd = ["ping", "-n", str(count), host]
    else:
        cmd = ["ping", "-c", str(count), "-W", "5", host]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=count * 6 + 5)
        output = result.stdout.strip()
        if not output:
            return f"Пинг {host} не удался, сэр."
        # Извлекаем среднее время
        if IS_WINDOWS:
            m = re.search(r"Среднее = (\d+)мс", output)
            if m:
                return f"{host}: среднее {m.group(1)} мс, сэр."
        else:
            m = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", output)
            if m:
                return f"{host}: среднее {m.group(1)} мс, сэр."
        # Fallback: возвращаем последние 3 строки
        lines = output.split("\n")[-3:]
        return f"{host}: " + "; ".join(lines).strip() + ", сэр."
    except subprocess.TimeoutExpired:
        return f"Пинг {host} превышен по таймауту, сэр."
    except Exception as exc:
        return f"Ошибка пинга: {exc}, сэр."


def speedtest() -> str:
    """Быстрый тест скорости через curl (загрузка файла)."""
    if not shutil.which("curl"):
        return "curl не найден. Установите curl, сэр."
    urls = [
        "http://speedtest.tele2.net/1MB.zip",
        "http://proof.ovh.net/files/1Mb.dat",
    ]
    for url in urls:
        try:
            result = subprocess.run(
                ["curl", "-o", "/dev/null", "-w", "%{speed_download}", url],
                capture_output=True, text=True, check=False, timeout=30,
            )
            speed = float(result.stdout.strip())
            mbps = speed * 8 / 1_000_000
            return f"Скорость загрузки: {mbps:.1f} Мбит/с, сэр."
        except Exception:
            log.debug("network: пропуск элемента (line 66)")
            continue
    return "Не удалось измерить скорость. Проверьте интернет, сэр."


def scan_ports(host: str = "localhost", ports: str = "") -> str:
    """Сканирует порты. ports: '80,443' или '80-100' или пусто (20 популярных)."""
    if not ports:
        port_list = [21, 22, 25, 53, 80, 110, 143, 443, 993, 995,
                    3306, 5432, 5900, 6379, 8080, 8443, 8888, 9090, 27017, 3000]
    else:
        port_list: list[int] = []
        for part in ports.split(","):
            part = part.strip()
            if "-" in part:
                try:
                    a, b = part.split("-")
                    port_list.extend(range(int(a), int(b) + 1))
                except ValueError:
                    pass
            else:
                try:
                    port_list.append(int(part))
                except ValueError:
                    pass
    if not port_list:
        return "Неверный формат портов, сэр."
    open_ports: list[int] = []
    for port in port_list[:100]:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                open_ports.append(port)
            sock.close()
        except Exception:
            log.debug("network: не критичная ошибка при sock.close()")
    if not open_ports:
        return f"На {host} нет открытых портов из проверенных ({len(port_list)}), сэр."
    port_str = ", ".join(str(p) for p in open_ports)
    return f"Открытые порты на {host}: {port_str} ({len(open_ports)}/{len(port_list)}), сэр."


def my_ip() -> str:
    """Узнать внешний IP."""
    try:
        result = subprocess.run(
            ["curl", "-s", "https://api.ipify.org"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        ip = result.stdout.strip()
        if ip and re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
            return f"Ваш IP: {ip}, сэр."
    except Exception:
        log.debug("network: не критичная ошибка при return f'Ваш IP: {ip}, сэр.'")
    return "Не удалось узнать IP, сэр."


def dns_lookup(domain: str) -> str:
    """DNS-запрос для домена."""
    try:
        ips = socket.getaddrinfo(domain, None, socket.AF_INET)
        if not ips:
            return f"Не удалось разрешить {domain}, сэр."
        unique_ips = list(dict.fromkeys(ip[4][0] for ip in ips))
        return f"{domain}: {', '.join(unique_ips)}, сэр."
    except socket.gaierror:
        return f"Не удалось разрешить {domain}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="ping",
            description="Пинговать хост (4 пакета по умолчанию).",
            parameters=object_schema(
                {
                    "host": {"type": "string", "description": "Хост (IP или домен)"},
                    "count": {"type": "integer", "description": "Количество пакетов"},
                }
            ),
            handler=lambda host="google.com", count=4: ping(host, count),
        ),
        Skill(
            name="speedtest",
            description="Быстрый тест скорости интернета (загрузка).",
            parameters=object_schema({}),
            handler=speedtest,
        ),
        Skill(
            name="scan_ports",
            description="Сканировать порты на хосте.",
            parameters=object_schema(
                {
                    "host": {"type": "string", "description": "Хост (по умолчанию localhost)"},
                    "ports": {"type": "string", "description": "Порты: '80,443' или '80-100' или пусто"},
                }
            ),
            handler=lambda host="localhost", ports="": scan_ports(host, ports),
        ),
        Skill(
            name="my_ip",
            description="Узнать внешний IP-адрес.",
            parameters=object_schema({}),
            handler=my_ip,
        ),
        Skill(
            name="dns_lookup",
            description="DNS-запрос для домена.",
            parameters=object_schema(
                {"domain": {"type": "string", "description": "Домен"}},
                required=["domain"],
            ),
            handler=lambda domain: dns_lookup(domain),
        ),
    ]

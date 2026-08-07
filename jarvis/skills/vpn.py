"""VPN контроль: включить/выключить WireGuard или OpenVPN туннель."""

from __future__ import annotations

import logging
import shutil
import subprocess

from ..config import VpnConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def _wg_available() -> bool:
    return shutil.which("wg-quick") is not None or shutil.which("wg") is not None


def _ovpn_available() -> bool:
    return shutil.which("openvpn") is not None


def vpn_status(config: VpnConfig) -> str:
    """Проверяет статус VPN подключений."""
    lines = []
    # WireGuard
    if config.backend in ("wireguard", "auto") and _wg_available():
        result = subprocess.run(
            ["wg", "show"], capture_output=True, text=True, check=False, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            interfaces = []
            for line in result.stdout.split("\n"):
                if line.startswith("interface:"):
                    interfaces.append(line.split(":")[1].strip())
            if interfaces:
                lines.append(f"WireGuard активен: {', '.join(interfaces)}")
            else:
                lines.append("WireGuard: нет активных туннелей")
        else:
            lines.append("WireGuard: отключён")
    # OpenVPN
    if config.backend in ("openvpn", "auto") and _ovpn_available():
        result = subprocess.run(
            ["pgrep", "-x", "openvpn"], capture_output=True, text=True, check=False, timeout=5,
        )
        if result.returncode == 0:
            pids = result.stdout.strip().split("\n")
            lines.append(f"OpenVPN активен (PID: {', '.join(pids[:3])})")
        else:
            lines.append("OpenVPN: отключён")
    if not lines:
        return "VPN не настроен. Установите WireGuard или OpenVPN, сэр."
    return "\n".join(lines)


def vpn_up(config: VpnConfig, name: str = "") -> str:
    """Включает VPN туннель."""
    conf = name or config.default_config
    if not conf:
        return "Укажите имя конфигурации или настройте default_config, сэр."
    # WireGuard
    if config.backend in ("wireguard", "auto") and _wg_available():
        try:
            result = subprocess.run(
                ["sudo", "wg-quick", "up", conf],
                capture_output=True, text=True, check=False, timeout=15,
            )
            if result.returncode == 0:
                return f"WireGuard {conf} включён, сэр."
            return f"Ошибка WireGuard: {result.stderr.strip() or result.stdout.strip()[:100]}, сэр."
        except Exception as exc:
            return f"Ошибка WireGuard: {exc}, сэр."
    # OpenVPN
    if config.backend in ("openvpn", "auto") and _ovpn_available():
        try:
            result = subprocess.run(
                ["sudo", "openvpn", "--config", conf, "--daemon"],
                capture_output=True, text=True, check=False, timeout=15,
            )
            if result.returncode == 0:
                return f"OpenVPN {conf} включён, сэр."
            return f"Ошибка OpenVPN: {result.stderr.strip()[:100]}, сэр."
        except Exception as exc:
            return f"Ошибка OpenVPN: {exc}, сэр."
    return "WireGuard или OpenVPN не установлены, сэр."


def vpn_down(config: VpnConfig, name: str = "") -> str:
    """Выключает VPN туннель."""
    conf = name or config.default_config
    if not conf:
        return "Укажите имя конфигурации, сэр."
    if config.backend in ("wireguard", "auto") and _wg_available():
        result = subprocess.run(
            ["sudo", "wg-quick", "down", conf],
            capture_output=True, text=True, check=False, timeout=15,
        )
        if result.returncode == 0:
            return f"WireGuard {conf} отключён, сэр."
        return f"Ошибка: {result.stderr.strip()[:100]}, сэр."
    if config.backend in ("openvpn", "auto") and _ovpn_available():
        result = subprocess.run(["sudo", "killall", "openvpn"], check=False, timeout=5, capture_output=True, text=True)
        if result.returncode == 0:
            return "OpenVPN отключён, сэр."
        return f"OpenVPN не был запущен или ошибка: {result.stderr.strip()[:80]}, сэр."
    return "VPN не настроен, сэр."


def vpn_list(config: VpnConfig) -> str:
    """Показывает доступные VPN конфигурации."""
    lines = []
    wg_dir = "/etc/wireguard"
    import os
    if os.path.isdir(wg_dir):
        from pathlib import Path
        confs = list(Path(wg_dir).glob("*.conf"))
        if confs:
            lines.append("WireGuard конфигурации:")
            for c in confs:
                lines.append(f"  {c.stem}")
    ovpn_dir = config.ovpn_dir
    if ovpn_dir:
        from pathlib import Path
        d = Path(ovpn_dir).expanduser()
        if d.is_dir():
            ovpn_files = list(d.glob("*.ovpn")) + list(d.glob("*.conf"))
            if ovpn_files:
                lines.append("OpenVPN конфигурации:")
                for f in ovpn_files:
                    lines.append(f"  {f.name}")
    if not lines:
        return "VPN конфигурации не найдены, сэр."
    return "\n".join(lines)


def build_skills(config: VpnConfig) -> list[Skill]:
    """Создаёт VPN навыки."""
    return [
        Skill(
            name="vpn_status",
            description="Показать статус VPN подключений.",
            parameters=object_schema({}),
            handler=lambda: vpn_status(config),
        ),
        Skill(
            name="vpn_up",
            description="Включить VPN туннель.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Имя конфигурации (пустое = по умолчанию)"}},
            ),
            handler=lambda name="": vpn_up(config, name),
        ),
        Skill(
            name="vpn_down",
            description="Выключить VPN туннель.",
            parameters=object_schema(
                {"name": {"type": "string", "description": "Имя конфигурации"}},
            ),
            handler=lambda name="": vpn_down(config, name),
        ),
        Skill(
            name="vpn_list",
            description="Показать доступные VPN конфигурации.",
            parameters=object_schema({}),
            handler=lambda: vpn_list(config),
        ),
    ]

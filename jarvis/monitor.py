"""Проактивный мониторинг: Джарвис сам предупреждает о проблемах с ПК."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import MonitorConfig

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Alert:
    """Одно предупреждение: ключ для антиспама и текст для озвучивания."""

    key: str
    text: str


def _battery_alerts(config: MonitorConfig, psutil: Any) -> list[Alert]:
    """Предупреждения о заряде батареи."""
    battery = getattr(psutil, "sensors_battery", lambda: None)()
    if battery is None or battery.power_plugged:
        return []
    percent = int(battery.percent)
    if percent <= config.battery_critical:
        return [
            Alert(
                "battery_critical",
                f"Сэр, заряд батареи критический — {percent} процентов. "
                "Подключите зарядное устройство немедленно.",
            )
        ]
    if percent <= config.battery_low:
        return [
            Alert(
                "battery_low",
                f"Сэр, батарея разряжена до {percent} процентов. "
                "Рекомендую подключить зарядное устройство.",
            )
        ]
    return []


class SystemMonitor:
    """Фоновый поток: следит за батареей, памятью, диском и процессором."""

    def __init__(self, config: MonitorConfig, notify: Callable[[str], None]) -> None:
        self.config = config
        self._notify = notify
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_sent: dict[str, float] = {}
        self._cpu_streak = 0

    def collect(self) -> list[Alert]:
        """Снимает метрики и возвращает актуальные предупреждения."""
        try:
            import psutil
        except ImportError:
            log.info("psutil не установлен, мониторинг отключён")
            return []
        alerts = _battery_alerts(self.config, psutil)
        memory = psutil.virtual_memory()
        if memory.percent >= self.config.memory_high:
            alerts.append(
                Alert(
                    "memory_high",
                    f"Сэр, память занята на {memory.percent:.0f} процентов. "
                    "Стоит закрыть лишние программы.",
                )
            )
        disk = psutil.disk_usage(str(Path.home().anchor or "/"))
        if disk.percent >= self.config.disk_high:
            alerts.append(
                Alert(
                    "disk_high",
                    f"Сэр, системный диск заполнен на {disk.percent:.0f} процентов.",
                )
            )
        cpu = psutil.cpu_percent(interval=None)
        # Всплеск загрузки — норма, поэтому реагируем только на серию замеров.
        self._cpu_streak = self._cpu_streak + 1 if cpu >= self.config.cpu_high else 0
        if self._cpu_streak >= max(1, self.config.cpu_samples):
            self._cpu_streak = 0
            alerts.append(
                Alert(
                    "cpu_high",
                    f"Сэр, процессор держит {cpu:.0f} процентов загрузки уже несколько минут.",
                )
            )
        return alerts

    def _should_send(self, alert: Alert, now: float) -> bool:
        """Не повторяет одно и то же предупреждение слишком часто."""
        previous = self._last_sent.get(alert.key)
        if previous is not None and now - previous < self.config.repeat_after_s:
            return False
        self._last_sent[alert.key] = now
        return True

    def tick(self) -> list[Alert]:
        """Один цикл проверки: возвращает то, что действительно отправлено."""
        now = time.monotonic()
        sent = [alert for alert in self.collect() if self._should_send(alert, now)]
        for alert in sent:
            self._notify(alert.text)
        return sent

    def _loop(self) -> None:
        """Периодически проверяет систему до остановки."""
        interval = max(5.0, self.config.interval_s)
        while not self._stop.wait(interval):
            try:
                self.tick()
            except Exception:  # монитор не должен ронять ассистента
                log.exception("Ошибка мониторинга системы")

    def start(self) -> None:
        """Запускает фоновый поток, если мониторинг включён."""
        if not self.config.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="monitor", daemon=True)
        self._thread.start()
        log.info("Мониторинг системы запущен, интервал %.0f с", self.config.interval_s)

    def shutdown(self) -> None:
        """Останавливает мониторинг."""
        self._stop.set()
        self._thread = None

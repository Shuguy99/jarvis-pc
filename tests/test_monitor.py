"""Тесты проактивного мониторинга состояния ПК."""

from __future__ import annotations

from typing import Any

from jarvis.config import MonitorConfig
from jarvis.monitor import SystemMonitor


class FakeMemory:
    """Заглушка psutil.virtual_memory()."""

    def __init__(self, percent: float) -> None:
        self.percent = percent


class FakeBattery:
    """Заглушка psutil.sensors_battery()."""

    def __init__(self, percent: float, plugged: bool) -> None:
        self.percent = percent
        self.power_plugged = plugged


class FakePsutil:
    """Минимальный psutil с управляемыми показаниями."""

    def __init__(
        self,
        cpu: float = 5.0,
        memory: float = 40.0,
        disk: float = 50.0,
        battery: FakeBattery | None = None,
    ) -> None:
        self._cpu = cpu
        self._memory = memory
        self._disk = disk
        self._battery = battery

    def cpu_percent(self, interval: float | None = None) -> float:
        return self._cpu

    def virtual_memory(self) -> FakeMemory:
        return FakeMemory(self._memory)

    def disk_usage(self, path: str) -> FakeMemory:
        return FakeMemory(self._disk)

    def sensors_battery(self) -> FakeBattery | None:
        return self._battery


def _monitor(
    psutil_stub: FakePsutil,
    monkeypatch: Any,
    config: MonitorConfig | None = None,
) -> tuple[SystemMonitor, list[str]]:
    """Монитор с подменённым psutil и собранными сообщениями."""
    monkeypatch.setitem(__import__("sys").modules, "psutil", psutil_stub)
    said: list[str] = []
    return SystemMonitor(config or MonitorConfig(), said.append), said


def test_low_battery_is_announced(monkeypatch: Any) -> None:
    """Разряженная батарея на питании от аккумулятора вызывает предупреждение."""
    stub = FakePsutil(battery=FakeBattery(15, plugged=False))
    monitor, said = _monitor(stub, monkeypatch)
    monitor.tick()
    assert said and "15 процентов" in said[0]


def test_charging_battery_is_silent(monkeypatch: Any) -> None:
    """При подключённой зарядке о заряде не сообщаем."""
    stub = FakePsutil(battery=FakeBattery(5, plugged=True))
    monitor, said = _monitor(stub, monkeypatch)
    monitor.tick()
    assert said == []


def test_alert_is_not_repeated_within_cooldown(monkeypatch: Any) -> None:
    """Одно и то же предупреждение не повторяется подряд."""
    stub = FakePsutil(memory=95.0)
    monitor, said = _monitor(stub, monkeypatch)
    monitor.tick()
    monitor.tick()
    assert len(said) == 1
    assert "память" in said[0].lower()


def test_cpu_spike_needs_several_samples(monkeypatch: Any) -> None:
    """Всплеск загрузки процессора не считается проблемой."""
    stub = FakePsutil(cpu=99.0)
    config = MonitorConfig(cpu_samples=3)
    monitor, said = _monitor(stub, monkeypatch, config)
    monitor.collect()
    monitor.collect()
    assert said == []
    alerts = monitor.collect()
    assert [alert.key for alert in alerts] == ["cpu_high"]


def test_disk_alert(monkeypatch: Any) -> None:
    """Переполненный диск попадает в предупреждения."""
    stub = FakePsutil(disk=99.0)
    monitor, _ = _monitor(stub, monkeypatch)
    assert [alert.key for alert in monitor.collect()] == ["disk_high"]


def test_missing_psutil_is_not_fatal(monkeypatch: Any) -> None:
    """Без psutil мониторинг просто молчит."""
    monkeypatch.setitem(__import__("sys").modules, "psutil", None)
    monitor = SystemMonitor(MonitorConfig(), lambda text: None)
    assert monitor.collect() == []

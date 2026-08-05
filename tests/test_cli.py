"""Проверки разбора аргументов и обработки ошибок конфигурации."""

from __future__ import annotations

from pathlib import Path

from jarvis.cli import main


def test_missing_config_reports_error(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Несуществующий путь к конфигу не подменяется значениями по умолчанию."""
    code = main(["--config", str(tmp_path / "nope.yaml"), "doctor"])
    assert code == 2
    assert "не найден" in capsys.readouterr().err


def test_broken_config_reports_error(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Некорректный конфиг завершается понятным сообщением, а не трейсбеком."""
    path = tmp_path / "config.yaml"
    path.write_text("- это список, а не словарь\n", encoding="utf-8")
    code = main(["--config", str(path), "doctor"])
    assert code == 2
    assert "Ошибка в конфиге" in capsys.readouterr().err

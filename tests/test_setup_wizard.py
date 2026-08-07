"""Тесты мастера настройки (без интерактивного ввода)."""

from jarvis.setup_wizard import _choice, _yes_no, _check_module, _c


def test_color_codes():
    assert '\033[0m' in _c('x', 0)
    assert '\033[1m' in _c('x', 1)
    assert '\033[32m' in _c('x', 32)


def test_check_module_true():
    assert _check_module('json') is True


def test_check_module_false():
    assert _check_module('totally_fake_module_xyz') is False

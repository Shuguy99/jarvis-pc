"""Тесты буфера обмена."""

from unittest.mock import patch
from jarvis.skills.clipboard import get_clipboard, set_clipboard, clear_clipboard, build_skills


def test_build_skills_count():
    skills = build_skills()
    assert len(skills) == 3
    names = {s.name for s in skills}
    assert "get_clipboard" in names
    assert "set_clipboard" in names
    assert "clear_clipboard" in names


@patch("pyperclip.paste", return_value="hello world")
def test_get_clipboard(mock_paste):
    result = get_clipboard()
    assert "hello world" in result


@patch("pyperclip.copy", return_value=True)
def test_set_clipboard(mock_copy):
    result = set_clipboard(text="test")
    assert "Скопировано" in result


@patch("pyperclip.copy", return_value=True)
def test_clear_clipboard(mock_copy):
    result = clear_clipboard()
    assert "очищен" in result

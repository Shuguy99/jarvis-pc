"""Тесты сниппетов кода."""

import pytest
from jarvis.skills import code_snippets


@pytest.fixture(autouse=True)
def _use_tmp(tmp_path, monkeypatch):
    """Перенаправляем хранилище во временный каталог."""
    monkeypatch.setattr(code_snippets, '_SNIPPETS_FILE', tmp_path / 'snippets.json')


def test_save_and_list():
    result = code_snippets.save_snippet(name='test', code="print('hello')", tags='python,test')
    assert 'сохранён' in result
    result = code_snippets.list_snippets()
    assert 'test' in result


def test_save_and_get():
    code_snippets.save_snippet(name='getme', code='x=1', tags='py')
    result = code_snippets.get_snippet(name='getme')
    assert 'x=1' in result


def test_search_by_tag():
    code_snippets.save_snippet(name='s1', code='a', tags='python')
    code_snippets.save_snippet(name='s2', code='b', tags='bash')
    result = code_snippets.search_snippets(query='python')
    assert 's1' in result


def test_get_nonexistent():
    result = code_snippets.get_snippet(name='nothere')
    assert 'не найден' in result

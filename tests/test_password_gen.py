"""Тесты генератора паролей."""

from jarvis.skills.password_gen import generate as generate_password, build_skills


def test_default_length():
    result = generate_password(length=16)
    assert result  # should not crash


def test_custom_length():
    result = generate_password(length=32)
    assert result


def test_no_symbols():
    result = generate_password(length=20, symbols=False)
    assert result


def test_build_skills():
    skills = build_skills()
    assert len(skills) == 1
    assert skills[0].name == "generate_password"

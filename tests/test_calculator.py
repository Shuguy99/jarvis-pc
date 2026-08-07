"""Тесты навыка калькулятор."""

from jarvis.skills.calculator import calculate, percentage, convert_temperature, build_skills


def test_calculate_basic():
    assert "6" in calculate("2+2*2")
    assert "10" in calculate("(2+3)*2")


def test_calculate_negative():
    assert "-5" in calculate("2-7")


def test_calculate_division():
    assert "2" in calculate("10/5")


def test_calculate_math_functions():
    result = calculate("sqrt(16)")
    assert "4" in result


def test_calculate_invalid():
    result = calculate("привет")
    assert result  # should not crash


def test_percentage_basic():
    assert "25" in percentage(value=100, percent=25)


def test_percentage_zero():
    result = percentage(value=0, percent=50)
    assert "0" in result


def test_convert_temperature_c_to_f():
    result = convert_temperature(value=100, from_unit="C", to_unit="F")
    assert "212" in result


def test_convert_temperature_f_to_c():
    result = convert_temperature(value=32, from_unit="F", to_unit="C")
    assert "0" in result


def test_convert_temperature_same_unit():
    result = convert_temperature(value=50, from_unit="C", to_unit="C")
    assert "50" in result


def test_build_skills_count():
    skills = build_skills()
    assert len(skills) == 3
    names = {s.name for s in skills}
    assert "calculate" in names
    assert "percentage" in names
    assert "convert_temperature" in names

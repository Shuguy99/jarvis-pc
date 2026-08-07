"""Тесты конвертера единиц."""

from jarvis.skills.unit_converter import convert as unit_convert, build_skills


def test_length_meters_to_feet():
    result = unit_convert(value=1, from_unit="m", to_unit="ft")
    assert result  # not empty


def test_weight_kg_to_lb():
    result = unit_convert(value=10, from_unit="kg", to_unit="lb")
    assert result


def test_speed_kmh_to_mph():
    result = unit_convert(value=100, from_unit="kmh", to_unit="mph")
    assert result


def test_data_mb_to_gb():
    result = unit_convert(value=1024, from_unit="MB", to_unit="GB")
    assert result


def test_same_unit():
    result = unit_convert(value=42, from_unit="m", to_unit="m")
    assert "42" in result


def test_unknown_unit():
    result = unit_convert(value=1, from_unit="xyz", to_unit="abc")
    assert result  # graceful error


def test_build_skills_count():
    skills = build_skills()
    assert len(skills) == 1
    assert skills[0].name == "unit_convert"

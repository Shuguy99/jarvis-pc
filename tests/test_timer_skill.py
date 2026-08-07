"""Тесты таймер-навыка."""

from jarvis.skills.timer_skill import TimerSkillService, build_skills


def test_build_skills():
    svc = TimerSkillService(notify=lambda t: None)
    skills = build_skills(svc)
    assert len(skills) == 3
    names = {s.name for s in skills}
    assert "timer_set" in names
    assert "timer_list" in names
    assert "timer_cancel" in names


def test_timer_set_and_list():
    svc = TimerSkillService(notify=lambda t: None)
    skills = build_skills(svc)
    set_skill = [s for s in skills if s.name == "timer_set"][0]
    list_skill = [s for s in skills if s.name == "timer_list"][0]

    set_skill.handler(seconds=1, label="test")
    result = list_skill.handler()
    assert "1" in result  # 1 active timer


def test_timer_cancel():
    svc = TimerSkillService(notify=lambda t: None)
    skills = build_skills(svc)
    set_skill = [s for s in skills if s.name == "timer_set"][0]
    cancel_skill = [s for s in skills if s.name == "timer_cancel"][0]

    set_skill.handler(seconds=10, label="cancelme")
    result = cancel_skill.handler()
    assert result  # graceful

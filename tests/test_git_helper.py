"""Тесты git-хелпера (без реального git)."""

from unittest.mock import patch, MagicMock
from jarvis.skills.git_helper import git_status, git_log, build_skills


def test_build_skills_count():
    skills = build_skills()
    assert len(skills) == 5
    names = {s.name for s in skills}
    assert "git_status" in names
    assert "git_commit" in names
    assert "git_push" in names
    assert "git_log" in names
    assert "git_branch" in names


@patch("jarvis.skills.git_helper.subprocess.run")
def test_git_status(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="On branch main\nnothing to commit")
    result = git_status()
    assert result


@patch("jarvis.skills.git_helper.subprocess.run")
def test_git_log(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="abc123 feat: add stuff")
    result = git_log(n=1)
    assert result

"""Тесты плагинной системы — манифест, install/uninstall/update/list, навыки."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from jarvis.config import Config
from jarvis.skills.plugins import (
    _parse_repo_name,
    _load_manifest,
    _save_manifest,
    _manifest_add,
    _manifest_remove,
    _manifest_update_skills,
    _load_plugin_file,
    _load_plugin_dir,
    load_plugins,
    load_github_plugins,
    _load_local_plugins,
    install_plugin,
    uninstall_plugin,
    update_plugin,
    list_installed_plugins,
    build_plugin_skills,
    GITHUB_PLUGINS_DIR,
    MANIFEST_PATH,
)


cfg = Config()


# ── _parse_repo_name ────────────────────────────────────────────────


class TestParseRepoName:
    def test_https(self):
        assert _parse_repo_name("https://github.com/user/jarvis-hello") == "jarvis-hello"

    def test_https_git(self):
        assert _parse_repo_name("https://github.com/user/jarvis-hello.git") == "jarvis-hello"

    def test_ssh(self):
        assert _parse_repo_name("git@github.com:user/jarvis-hello.git") == "jarvis-hello"

    def test_not_github(self):
        assert _parse_repo_name("https://gitlab.com/user/repo") is None

    def test_empty(self):
        assert _parse_repo_name("") is None


# ── Манифест ────────────────────────────────────────────────────────


class TestManifest:
    def test_load_missing(self, tmp_path):
        with patch("jarvis.skills.plugins.MANIFEST_PATH", tmp_path / "no.json"):
            assert _load_manifest() == {}

    def test_load_corrupt(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        with patch("jarvis.skills.plugins.MANIFEST_PATH", p):
            assert _load_manifest() == {}

    def test_save_and_load(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        plugins_dir = tmp_path / "plugins"
        with patch("jarvis.skills.plugins.MANIFEST_PATH", manifest_path), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", plugins_dir):
            _save_manifest({"test": {"url": "http://x", "skills": []}})
            result = _load_manifest()
            assert result["test"]["url"] == "http://x"

    def test_add_entry(self, tmp_path):
        manifest_path = tmp_path / "m.json"
        plugins_dir = tmp_path / "p"
        with patch("jarvis.skills.plugins.MANIFEST_PATH", manifest_path), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", plugins_dir):
            mock_skill = MagicMock()
            mock_skill.name = "hello"
            _manifest_add("http://github.com/u/r", "r", [mock_skill])
            data = _load_manifest()
            assert "r" in data
            assert data["r"]["skills"] == ["hello"]
            assert "installed_at" in data["r"]

    def test_remove_entry(self, tmp_path):
        manifest_path = tmp_path / "m.json"
        plugins_dir = tmp_path / "p"
        with patch("jarvis.skills.plugins.MANIFEST_PATH", manifest_path), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", plugins_dir):
            _save_manifest({"a": {}, "b": {}})
            _manifest_remove("a")
            assert "a" not in _load_manifest()
            assert "b" in _load_manifest()

    def test_update_skills(self, tmp_path):
        manifest_path = tmp_path / "m.json"
        plugins_dir = tmp_path / "p"
        with patch("jarvis.skills.plugins.MANIFEST_PATH", manifest_path), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", plugins_dir):
            _save_manifest({"p": {"url": "x", "skills": ["old"], "installed_at": "t"}})
            mock_skill = MagicMock()
            mock_skill.name = "new_skill"
            _manifest_update_skills("p", [mock_skill])
            data = _load_manifest()
            assert data["p"]["skills"] == ["new_skill"]
            assert "updated_at" in data["p"]


# ── load_plugin_file ────────────────────────────────────────────────


class TestLoadPluginFile:
    def test_valid_plugin(self, tmp_path):
        plugin_file = tmp_path / "hello.py"
        plugin_file.write_text(
            "from jarvis.skills.registry import Skill, object_schema\n"
            "def build_skills():\n"
            "    return [Skill(name='test', description='d', parameters=object_schema({}), handler=lambda: 'ok')]\n"
        )
        skills = _load_plugin_file(plugin_file, cfg)
        assert len(skills) == 1
        assert skills[0].name == "test"

    def test_no_build_skills(self, tmp_path):
        plugin_file = tmp_path / "bad.py"
        plugin_file.write_text("x = 1\n")
        skills = _load_plugin_file(plugin_file, cfg)
        assert skills == []

    def test_syntax_error(self, tmp_path):
        plugin_file = tmp_path / "err.py"
        plugin_file.write_text("def (")
        skills = _load_plugin_file(plugin_file, cfg)
        assert skills == []

    def test_build_skills_returns_non_list(self, tmp_path):
        plugin_file = tmp_path / "wrong.py"
        plugin_file.write_text("def build_skills(): return 'not a list'\n")
        skills = _load_plugin_file(plugin_file, cfg)
        assert skills == []

    def test_build_skills_with_config(self, tmp_path):
        plugin_file = tmp_path / "with_cfg.py"
        plugin_file.write_text(
            "from jarvis.skills.registry import Skill, object_schema\n"
            "def build_skills(config):\n"
            "    return [Skill(name='cfg_test', description='d', parameters=object_schema({}), handler=lambda: 'ok')]\n"
        )
        skills = _load_plugin_file(plugin_file, cfg)
        assert len(skills) == 1
        assert skills[0].name == "cfg_test"


# ── _load_plugin_dir ────────────────────────────────────────────────


class TestLoadPluginDir:
    def test_loads_valid_files(self, tmp_path):
        (tmp_path / "skill.py").write_text(
            "from jarvis.skills.registry import Skill, object_schema\n"
            "def build_skills():\n"
            "    return [Skill(name='s1', description='d', parameters=object_schema({}), handler=lambda: 'ok')]\n"
        )
        (tmp_path / "skill2.py").write_text(
            "from jarvis.skills.registry import Skill, object_schema\n"
            "def build_skills():\n"
            "    return [Skill(name='s2', description='d', parameters=object_schema({}), handler=lambda: 'ok')]\n"
        )
        # Файлы которые должны быть пропущены
        (tmp_path / "_init.py").write_text("")
        (tmp_path / ".hidden.py").write_text("")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_skill.py").write_text("")

        skills = _load_plugin_dir(tmp_path, cfg)
        assert len(skills) == 2
        names = {s.name for s in skills}
        assert names == {"s1", "s2"}


# ── uninstall_plugin ────────────────────────────────────────────────


class TestUninstall:
    def test_not_found(self, tmp_path):
        with patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", tmp_path), \
             patch("jarvis.skills.plugins._load_manifest", return_value={}):
            result = uninstall_plugin("ghost")
            assert "не найден" in result.lower()

    def test_success(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "skill.py").write_text("")
        manifest_path = tmp_path / "manifest.json"
        with patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", tmp_path), \
             patch("jarvis.skills.plugins.MANIFEST_PATH", manifest_path):
            _save_manifest({"my-plugin": {"url": "http://x", "skills": []}})
            result = uninstall_plugin("my-plugin")
            assert "удалён" in result
            assert not plugin_dir.exists()
            assert "my-plugin" not in _load_manifest()

    def test_fuzzy_match(self, tmp_path):
        plugin_dir = tmp_path / "jarvis-cool-skill"
        plugin_dir.mkdir()
        (plugin_dir / "skill.py").write_text("")
        with patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", tmp_path), \
             patch("jarvis.skills.plugins.MANIFEST_PATH", tmp_path / "m.json"):
            _save_manifest({"jarvis-cool-skill": {"url": "x", "skills": []}})
            result = uninstall_plugin("cool")
            assert "удалён" in result


# ── update_plugin ───────────────────────────────────────────────────


class TestUpdate:
    def test_no_plugins(self):
        with patch("jarvis.skills.plugins._load_manifest", return_value={}):
            assert "Нет установленных" in update_plugin("", cfg)

    def test_not_found(self):
        with patch("jarvis.skills.plugins._load_manifest", return_value={"a": {"url": "x"}}):
            result = update_plugin("ghost", cfg)
            assert "не найден" in result.lower()

    def test_update_all(self, tmp_path):
        manifest = {
            "p1": {"url": "http://github.com/u/p1", "skills": []},
            "p2": {"url": "http://github.com/u/p2", "skills": []},
        }
        (tmp_path / "p1").mkdir()
        (tmp_path / "p2").mkdir()
        with patch("jarvis.skills.plugins._load_manifest", return_value=manifest), \
             patch("jarvis.skills.plugins._clone_repo", return_value=True), \
             patch("jarvis.skills.plugins._load_plugin_dir", return_value=[]), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", tmp_path), \
             patch("jarvis.skills.plugins._manifest_update_skills"):
            result = update_plugin("", cfg)
            assert "обновлён" in result.lower()

    def test_update_specific(self, tmp_path):
        manifest = {"my-plugin": {"url": "http://github.com/u/p", "skills": ["old"]}}
        (tmp_path / "my-plugin").mkdir()
        with patch("jarvis.skills.plugins._load_manifest", return_value=manifest), \
             patch("jarvis.skills.plugins._clone_repo", return_value=True), \
             patch("jarvis.skills.plugins._load_plugin_dir", return_value=[]), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", tmp_path), \
             patch("jarvis.skills.plugins._manifest_update_skills") as mock_upd:
            result = update_plugin("my-plugin", cfg)
            assert "обновлён" in result.lower()
            mock_upd.assert_called_once()

    def test_missing_dir(self):
        manifest = {"ghost": {"url": "x", "skills": []}}
        with patch("jarvis.skills.plugins._load_manifest", return_value=manifest):
            result = update_plugin("ghost", cfg)
            assert "отсутствует" in result


# ── list_installed_plugins ────────────────────────────────────────────


class TestListPlugins:
    def test_empty(self):
        with patch("jarvis.skills.plugins._load_manifest", return_value={}):
            result = list_installed_plugins()
            assert "Нет" in result

    def test_with_plugins(self):
        manifest = {
            "hello": {"url": "http://github.com/u/hello", "skills": ["greet"], "installed_at": "2025-01-15T10:00:00"},
            "music": {"url": "http://github.com/u/music", "skills": ["play", "pause"], "installed_at": "2025-02-20T12:00:00"},
        }
        with patch("jarvis.skills.plugins._load_manifest", return_value=manifest):
            result = list_installed_plugins()
            assert "hello" in result
            assert "greet" in result
            assert "music" in result
            assert "play, pause" in result


# ── load_github_plugins ─────────────────────────────────────────────


class TestLoadGithubPlugins:
    def test_no_manifest(self, tmp_path):
        with patch("jarvis.skills.plugins._load_manifest", return_value={}):
            assert load_github_plugins(cfg) == []

    def test_loads_from_dirs(self, tmp_path):
        plugin_dir = tmp_path / "hello"
        plugin_dir.mkdir()
        (plugin_dir / "skill.py").write_text(
            "from jarvis.skills.registry import Skill, object_schema\n"
            "def build_skills():\n"
            "    return [Skill(name='gh_skill', description='d', parameters=object_schema({}), handler=lambda: 'ok')]\n"
        )
        manifest = {"hello": {"url": "x", "skills": []}}
        with patch("jarvis.skills.plugins._load_manifest", return_value=manifest), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", tmp_path):
            skills = load_github_plugins(cfg)
            assert len(skills) == 1
            assert skills[0].name == "gh_skill"

    def test_skips_missing_dir(self, tmp_path):
        manifest = {"ghost": {"url": "x", "skills": []}}
        with patch("jarvis.skills.plugins._load_manifest", return_value=manifest), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", tmp_path):
            skills = load_github_plugins(cfg)
            assert skills == []


# ── load_plugins (combined) ──────────────────────────────────────────


class TestLoadPluginsCombined:
    def test_loads_both_sources(self, tmp_path):
        # Локальный плагин
        local_dir = tmp_path / "skills"
        local_dir.mkdir()
        (local_dir / "local.py").write_text(
            "from jarvis.skills.registry import Skill, object_schema\n"
            "def build_skills():\n"
            "    return [Skill(name='local_s', description='d', parameters=object_schema({}), handler=lambda: 'ok')]\n"
        )
        # GitHub плагин
        gh_plugin = tmp_path / "gh_plugins" / "remote"
        gh_plugin.mkdir(parents=True)
        (gh_plugin / "skill.py").write_text(
            "from jarvis.skills.registry import Skill, object_schema\n"
            "def build_skills():\n"
            "    return [Skill(name='gh_s', description='d', parameters=object_schema({}), handler=lambda: 'ok')]\n"
        )
        with patch("jarvis.skills.plugins._load_manifest", return_value={"remote": {"url": "x", "skills": []}}), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", tmp_path / "gh_plugins"), \
             patch("jarvis.skills.plugins.PLUGINS_DIR_NAME", "skills"), \
             patch("jarvis.skills.plugins._load_local_plugins", wraps=lambda c: _load_local_plugins(c)) as mock_local:
            # Переопределяем _load_local_plugins чтобы он искал в tmp_path
            original = __import__("jarvis.skills.plugins", fromlist=["_load_local_plugins"])
            def patched_local(config):
                return original._load_local_plugins.__wrapped__(config) if hasattr(original._load_local_plugins, '__wrapped__') else []
            # Просто тестируем что load_plugins вызывает оба загрузчика
            with patch("jarvis.skills.plugins._load_local_plugins", return_value=[MagicMock(name='local_s')]), \
                 patch("jarvis.skills.plugins.load_github_plugins", return_value=[MagicMock(name='gh_s')]):
                skills = load_plugins(cfg)
                assert len(skills) == 2


# ── install_plugin ──────────────────────────────────────────────────


class TestInstallPlugin:
    def test_bad_url(self):
        with pytest.raises(ValueError, match="Не удалось извлечь"):
            install_plugin("https://gitlab.com/u/r", cfg)

    def test_clone_failure(self):
        with patch("jarvis.skills.plugins._parse_repo_name", return_value="test"), \
             patch("jarvis.skills.plugins._clone_repo", return_value=False), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", MagicMock()):
            with pytest.raises(RuntimeError, match="Не удалось клонировать"):
                install_plugin("https://github.com/u/r", cfg)

    def test_no_skills(self):
        with patch("jarvis.skills.plugins._parse_repo_name", return_value="empty"), \
             patch("jarvis.skills.plugins._clone_repo", return_value=True), \
             patch("jarvis.skills.plugins._load_plugin_dir", return_value=[]), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", MagicMock()), \
             patch("jarvis.skills.plugins._manifest_add"):
            with pytest.raises(RuntimeError, match="не содержит навыков"):
                install_plugin("https://github.com/u/empty", cfg)

    def test_success(self):
        mock_skill = MagicMock()
        mock_skill.name = "installed"
        with patch("jarvis.skills.plugins._parse_repo_name", return_value="good"), \
             patch("jarvis.skills.plugins._clone_repo", return_value=True), \
             patch("jarvis.skills.plugins._load_plugin_dir", return_value=[mock_skill]), \
             patch("jarvis.skills.plugins.GITHUB_PLUGINS_DIR", MagicMock()), \
             patch("jarvis.skills.plugins._manifest_add") as mock_add:
            skills = install_plugin("https://github.com/u/good", cfg)
            assert len(skills) == 1
            mock_add.assert_called_once()


# ── build_plugin_skills ─────────────────────────────────────────────


class TestBuildPluginSkills:
    def test_returns_4_skills(self):
        skills = build_plugin_skills(cfg)
        names = {s.name for s in skills}
        assert len(skills) == 4
        assert names == {"plugin_install", "plugin_uninstall", "plugin_list", "plugin_update"}

    def test_install_no_url(self):
        skills = build_plugin_skills(cfg)
        inst = next(s for s in skills if s.name == "plugin_install")
        result = inst.handler("")
        assert "URL" in result

    def test_uninstall_no_name(self):
        skills = build_plugin_skills(cfg)
        uninst = next(s for s in skills if s.name == "plugin_uninstall")
        result = uninst.handler("")
        assert "имя" in result.lower()

    def test_list_calls_list_installed(self):
        skills = build_plugin_skills(cfg)
        lst = next(s for s in skills if s.name == "plugin_list")
        with patch("jarvis.skills.plugins.list_installed_plugins", return_value="пусто"):
            assert lst.handler() == "пусто"

    def test_install_success(self):
        mock_skill = MagicMock()
        mock_skill.name = "new"
        skills = build_plugin_skills(cfg)
        inst = next(s for s in skills if s.name == "plugin_install")
        with patch("jarvis.skills.plugins.install_plugin", return_value=[mock_skill]):
            result = inst.handler("https://github.com/u/r")
            assert "установлен" in result.lower()

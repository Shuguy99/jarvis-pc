"""Тесты магазина плагинов — поиск, информация, установка, категории."""

import json
import base64
from unittest.mock import patch, MagicMock

import pytest

from jarvis.config import PluginStoreConfig
from jarvis.skills.plugin_store import (
    _gh_get,
    _get_token,
    _parse_repo_input,
    _fetch_manifest,
    _fetch_readme,
    _format_repo_info,
    _format_plugin_card,
    search_plugins,
    plugin_info,
    popular_plugins,
    plugins_by_category,
    store_install,
    build_skills,
)


cfg = PluginStoreConfig()
cfg_with_token = PluginStoreConfig(token="test_token")


# ── Вспомогательные данные ──────────────────────────────────────────


SAMPLE_REPO_ITEM = {
    "full_name": "user/jarvis-weather",
    "description": "Weather skill for Jarvis",
    "stargazers_count": 42,
    "forks_count": 5,
    "language": "Python",
    "updated_at": "2025-06-01T10:00:00Z",
    "topics": ["jarvis-skill", "weather"],
}


SAMPLE_REPO_ITEM_2 = {
    "full_name": "other/jarvis-music",
    "description": "Music player skill",
    "stargazers_count": 10,
    "forks_count": 2,
    "language": "Python",
    "updated_at": "2025-05-15T10:00:00Z",
    "topics": ["jarvis-skill", "music"],
}


SAMPLE_MANIFEST = {
    "name": "Погода",
    "description": "Подробный прогноз погоды",
    "version": "1.2.0",
    "author": "meteoman",
    "category": "погода",
    "tags": ["weather", "forecast"],
}


# ── _get_token ─────────────────────────────────────────────────────


class TestGetToken:
    def test_from_config(self):
        c = PluginStoreConfig(token="cfg_tok")
        assert _get_token(c) == "cfg_tok"

    def test_from_env(self):
        c = PluginStoreConfig(token="")
        with patch("jarvis.skills.plugin_store.os.environ.get", return_value="env_tok"):
            assert _get_token(c) == "env_tok"

    def test_empty(self):
        c = PluginStoreConfig(token="")
        with patch("jarvis.skills.plugin_store.os.environ.get", return_value=""):
            assert _get_token(c) == ""


# ── _parse_repo_input ──────────────────────────────────────────────


class TestParseRepoInput:
    def test_owner_repo(self):
        assert _parse_repo_input("user/repo") == ("user", "repo")

    def test_full_url(self):
        assert _parse_repo_input("https://github.com/user/repo") == ("user", "repo")

    def test_git_suffix(self):
        assert _parse_repo_input("user/repo.git") == ("user", "repo")

    def test_url_with_git(self):
        assert _parse_repo_input("https://github.com/user/repo.git") == ("user", "repo")

    def test_trailing_slash(self):
        assert _parse_repo_input("user/repo/") == ("user", "repo")

    def test_no_owner(self):
        assert _parse_repo_input("justname") == ("", "justname")


# ── _gh_get ─────────────────────────────────────────────────────────


class TestGhGet:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"key": "val"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            result = _gh_get("/test")
            assert result == {"key": "val"}
            mock_urlopen.assert_called_once()

    def test_404_returns_none(self):
        import urllib.error
        err = urllib.error.HTTPError(
            url="", code=404, msg="Not Found", hdrs=None, fp=None
        )
        with patch("urllib.request.urlopen", side_effect=err):
            assert _gh_get("/notfound") is None

    def test_500_returns_none(self):
        import urllib.error
        err = urllib.error.HTTPError(
            url="", code=500, msg="Server Error", hdrs=None, fp=None
        )
        err.read = MagicMock(return_value=b"server error")
        with patch("urllib.request.urlopen", side_effect=err):
            assert _gh_get("/fail") is None

    def test_with_token(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"[]"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
            _gh_get("/test", token="mytok")
            req = mock_urlopen.call_args[0][0]
            assert req.get_header("Authorization") == "token mytok"

    def test_network_error(self):
        with patch("urllib.request.urlopen", side_effect=OSError("network")):
            assert _gh_get("/test") is None


# ── _fetch_manifest ─────────────────────────────────────────────────


class TestFetchManifest:
    def test_main_branch(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(SAMPLE_MANIFEST).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = _fetch_manifest("user", "repo")
            assert result is not None
            assert result["name"] == "Погода"

    def test_master_fallback(self):
        """main не отвечает, manifest загружается из master."""
        call_count = 0
        def mock_urlopen(req, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise OSError("404")
            m = MagicMock()
            m.read.return_value = json.dumps(SAMPLE_MANIFEST).encode()
            m.__enter__ = lambda self: m
            m.__exit__ = lambda self, *a: False
            return m
        import jarvis.skills.plugin_store as ps
        original = ps.urllib.request.urlopen
        ps.urllib.request.urlopen = mock_urlopen
        try:
            result = _fetch_manifest("user", "repo")
            assert result is not None
            assert result["name"] == "Погода"
        finally:
            ps.urllib.request.urlopen = original

    def test_no_manifest(self):
        import urllib.error
        err = urllib.error.HTTPError("", 404, "Not Found", None, None)
        with patch("urllib.request.urlopen", side_effect=err):
            assert _fetch_manifest("user", "repo") is None

    def test_invalid_json(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not json"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            assert _fetch_manifest("user", "repo") is None


# ── _fetch_readme ───────────────────────────────────────────────────


class TestFetchReadme:
    def test_success(self):
        readme_text = "# My Plugin\n\nThis is a great plugin for Jarvis."
        b64 = base64.b64encode(readme_text.encode()).decode()
        api_resp = {"content": b64}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp):
            result = _fetch_readme("user", "repo")
            assert "great plugin" in result
            assert "#" not in result.split("\n")[0]  # заголовки убраны

    def test_no_readme(self):
        with patch("jarvis.skills.plugin_store._gh_get", return_value=None):
            assert _fetch_readme("user", "repo") == ""

    def test_empty_content(self):
        with patch("jarvis.skills.plugin_store._gh_get", return_value={"content": ""}):
            assert _fetch_readme("user", "repo") == ""


# ── _format_repo_info ───────────────────────────────────────────────


class TestFormatRepoInfo:
    def test_with_manifest(self):
        with patch("jarvis.skills.plugin_store._fetch_manifest", return_value=SAMPLE_MANIFEST):
            info = _format_repo_info(SAMPLE_REPO_ITEM, "")
            assert info["name"] == "Погода"
            assert info["description"] == "Подробный прогноз погоды"
            assert info["version"] == "1.2.0"
            assert info["author"] == "meteoman"
            assert info["category"] == "погода"
            assert info["stars"] == 42
            assert info["language"] == "Python"

    def test_without_manifest(self):
        with patch("jarvis.skills.plugin_store._fetch_manifest", return_value=None):
            info = _format_repo_info(SAMPLE_REPO_ITEM, "")
            assert info["name"] == "jarvis-weather"
            assert info["description"] == "Weather skill for Jarvis"
            assert info["version"] == ""
            assert info["category"] == ""
            assert info["tags"] == []

    def test_no_description(self):
        item = dict(SAMPLE_REPO_ITEM, description=None)
        with patch("jarvis.skills.plugin_store._fetch_manifest", return_value=None):
            info = _format_repo_info(item, "")
            assert info["description"] == ""


# ── _format_plugin_card ────────────────────────────────────────────


class TestFormatPluginCard:
    def test_full(self):
        info = {
            "name": "Погода", "full_name": "user/jarvis-weather",
            "description": "Подробный прогноз", "author": "meteoman",
            "category": "погода", "tags": ["weather"], "version": "1.0",
            "stars": 42, "forks": 5, "language": "Python", "updated": "2025-06-01",
        }
        card = _format_plugin_card(info)
        assert "Погода" in card
        assert "v1.0" in card
        assert "42" in card
        assert "погода" in card
        assert "meteoman" in card

    def test_minimal(self):
        info = {
            "name": "test", "full_name": "u/r",
            "description": "desc", "author": "", "category": "",
            "tags": [], "version": "", "stars": 0, "forks": 0,
            "language": "—", "updated": "2025-01-01",
        }
        card = _format_plugin_card(info)
        assert "test" in card
        assert "desc" in card
        # Без версии не должно быть 'v'
        assert "v" not in card.split("\n")[0]


# ── search_plugins ──────────────────────────────────────────────────


class TestSearchPlugins:
    def test_search_all(self):
        api_resp = {"total_count": 1, "items": [SAMPLE_REPO_ITEM]}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp), \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=None):
            result = search_plugins(cfg)
            assert "Найдено плагинов: 1" in result
            assert "jarvis-weather" in result

    def test_search_with_query(self):
        api_resp = {"total_count": 1, "items": [SAMPLE_REPO_ITEM]}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp) as mock_get, \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=None):
            search_plugins(cfg, "weather")
            args = mock_get.call_args
            assert "weather" in args[1]["params"]["q"]

    def test_empty_results(self):
        api_resp = {"total_count": 0, "items": []}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp):
            result = search_plugins(cfg)
            assert "пока нет" in result.lower()

    def test_empty_results_with_query(self):
        api_resp = {"total_count": 0, "items": []}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp):
            result = search_plugins(cfg, "nothing")
            assert "ничего не найдено" in result.lower()

    def test_api_failure(self):
        with patch("jarvis.skills.plugin_store._gh_get", return_value=None):
            result = search_plugins(cfg)
            assert "Не удалось" in result

    def test_uses_config_topic(self):
        custom_cfg = PluginStoreConfig(topic="my-custom-topic")
        api_resp = {"total_count": 0, "items": []}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp) as mock_get:
            search_plugins(custom_cfg)
            args = mock_get.call_args
            assert "my-custom-topic" in args[1]["params"]["q"]

    def test_with_manifest(self):
        api_resp = {"total_count": 1, "items": [SAMPLE_REPO_ITEM]}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp), \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=SAMPLE_MANIFEST):
            result = search_plugins(cfg)
            assert "Погода" in result
            assert "v1.2.0" in result


# ── plugin_info ─────────────────────────────────────────────────────


class TestPluginInfo:
    def test_success(self):
        with patch("jarvis.skills.plugin_store._gh_get", return_value=SAMPLE_REPO_ITEM), \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=SAMPLE_MANIFEST), \
             patch("jarvis.skills.plugin_store._fetch_readme", return_value="Great weather plugin."):
            result = plugin_info(cfg, "user/jarvis-weather")
            assert "Погода" in result
            assert "v1.2.0" in result
            assert "Great weather plugin" in result
            assert "установи из магазина" in result.lower()

    def test_no_repo(self):
        result = plugin_info(cfg, "")
        assert "Укажите" in result

    def test_invalid_format(self):
        result = plugin_info(cfg, "justname")
        assert "Некорректный" in result

    def test_not_found(self):
        with patch("jarvis.skills.plugin_store._gh_get", return_value=None):
            result = plugin_info(cfg, "user/nonexistent")
            assert "не найден" in result.lower()

    def test_no_readme(self):
        with patch("jarvis.skills.plugin_store._gh_get", return_value=SAMPLE_REPO_ITEM), \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=None), \
             patch("jarvis.skills.plugin_store._fetch_readme", return_value=""):
            result = plugin_info(cfg, "user/jarvis-weather")
            assert "jarvis-weather" in result
            assert "Описание" not in result


# ── popular_plugins ─────────────────────────────────────────────────


class TestPopularPlugins:
    def test_success(self):
        api_resp = {
            "total_count": 2,
            "items": [SAMPLE_REPO_ITEM, SAMPLE_REPO_ITEM_2],
        }
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp), \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=None):
            result = popular_plugins(cfg)
            assert "Популярные" in result
            assert "1." in result
            assert "2." in result
            assert "42" in result  # stars

    def test_empty(self):
        api_resp = {"total_count": 0, "items": []}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp):
            result = popular_plugins(cfg)
            assert "пока нет" in result.lower()

    def test_api_failure(self):
        with patch("jarvis.skills.plugin_store._gh_get", return_value=None):
            result = popular_plugins(cfg)
            assert "Не удалось" in result

    def test_sorted_by_stars(self):
        api_resp = {
            "total_count": 2,
            "items": [SAMPLE_REPO_ITEM_2, SAMPLE_REPO_ITEM],  # 10 before 42
        }
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp) as mock_get, \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=None):
            popular_plugins(cfg)
            args = mock_get.call_args
            assert args[1]["params"]["sort"] == "stars"


# ── plugins_by_category ─────────────────────────────────────────────


class TestPluginsByCategory:
    def test_no_category(self):
        result = plugins_by_category(cfg, "")
        assert "Укажите" in result

    def test_with_manifest_match(self):
        item_with_manifest = dict(SAMPLE_REPO_ITEM)
        api_resp = {"total_count": 1, "items": [item_with_manifest]}
        manifest_weather = dict(SAMPLE_MANIFEST, category="погода")
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp), \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=manifest_weather):
            result = plugins_by_category(cfg, "погода")
            assert "погода" in result.lower()
            assert "найдено" in result.lower()

    def test_with_tag_match(self):
        item = dict(SAMPLE_REPO_ITEM)
        api_resp = {"total_count": 1, "items": [item]}
        manifest_tags = dict(SAMPLE_MANIFEST, category="", tags=["sys", "system"])
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp), \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=manifest_tags):
            result = plugins_by_category(cfg, "sys")
            assert "найдено" in result.lower()

    def test_description_fallback(self):
        item = dict(SAMPLE_REPO_ITEM, description="Системный плагин для мониторинга")
        api_resp = {"total_count": 1, "items": [item]}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp), \
             patch("jarvis.skills.plugin_store._fetch_manifest", return_value=None):
            result = plugins_by_category(cfg, "система")
            # Описание содержит «системный» → частичное совпадение
            assert "Найдено" in result or "jarvis-weather" in result

    def test_no_results(self):
        api_resp = {"total_count": 0, "items": []}
        with patch("jarvis.skills.plugin_store._gh_get", return_value=api_resp):
            result = plugins_by_category(cfg, "космос")
            assert "ничего не найдено" in result.lower()

    def test_api_failure(self):
        with patch("jarvis.skills.plugin_store._gh_get", return_value=None):
            result = plugins_by_category(cfg, "погода")
            assert "Не удалось" in result


# ── store_install ───────────────────────────────────────────────────


class TestStoreInstall:
    def test_no_repo(self):
        result = store_install(cfg, "")
        assert "Укажите" in result

    def test_invalid_format(self):
        result = store_install(cfg, "justname")
        assert "Некорректный" in result

    def test_success(self):
        mock_skill = MagicMock()
        mock_skill.name = "installed_skill"
        with patch("jarvis.skills.plugin_store.install_plugin", return_value=[mock_skill]) as mock_inst:
            result = store_install(cfg, "user/repo")
            assert "установлен" in result.lower()
            assert "installed_skill" in result
            mock_inst.assert_called_once()
            call_args = mock_inst.call_args
            assert call_args[0][0] == "https://github.com/user/repo"
            from jarvis.config import Config as FullConfig
            assert isinstance(call_args[0][1], FullConfig)

    def test_no_skills(self):
        with patch("jarvis.skills.plugin_store.install_plugin", return_value=[]):
            result = store_install(cfg, "user/repo")
            assert "не содержит навыков" in result.lower()

    def test_value_error(self):
        with patch("jarvis.skills.plugin_store.install_plugin", side_effect=ValueError("bad url")):
            result = store_install(cfg, "user/repo")
            assert "bad url" in result

    def test_runtime_error(self):
        with patch("jarvis.skills.plugin_store.install_plugin", side_effect=RuntimeError("clone fail")):
            result = store_install(cfg, "user/repo")
            assert "clone fail" in result

    def test_generic_error(self):
        with patch("jarvis.skills.plugin_store.install_plugin", side_effect=Exception("unexpected")):
            result = store_install(cfg, "user/repo")
            assert "Ошибка" in result


# ── build_skills ────────────────────────────────────────────────────


class TestBuildSkills:
    def test_returns_5_skills(self):
        skills = build_skills(cfg)
        assert len(skills) == 5

    def test_skill_names(self):
        skills = build_skills(cfg)
        names = {s.name for s in skills}
        assert names == {"store_search", "store_info", "store_install", "store_popular", "store_category"}

    def test_all_have_descriptions(self):
        skills = build_skills(cfg)
        for s in skills:
            assert len(s.description) > 10

    def test_search_no_query(self):
        skills = build_skills(cfg)
        search = next(s for s in skills if s.name == "store_search")
        with patch("jarvis.skills.plugin_store.search_plugins", return_value="results"):
            assert search.handler("") == "results"

    def test_popular_no_args(self):
        skills = build_skills(cfg)
        pop = next(s for s in skills if s.name == "store_popular")
        with patch("jarvis.skills.plugin_store.popular_plugins", return_value="top"):
            assert pop.handler() == "top"

    def test_info_required_repo(self):
        skills = build_skills(cfg)
        info = next(s for s in skills if s.name == "store_info")
        params = info.parameters
        assert "repo" in params.get("required", [])

    def test_category_required(self):
        skills = build_skills(cfg)
        cat = next(s for s in skills if s.name == "store_category")
        params = cat.parameters
        assert "category" in params.get("required", [])

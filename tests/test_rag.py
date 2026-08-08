"""Тесты RAG: парсеры, чанкинг, JSON/ChromaDB хранилища, движок, BM25, HTML, CSV, URL, теги, статистика.

"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.config import RagConfig
from jarvis.skills.rag import (
    JsonRagStore,
    RagEngine,
    _HtmlTextExtractor,
    _compute_bm25_scores,
    _file_hash,
    _parse_html_from_string,
    _parse_tags,
    _source_id,
    _token_list,
    _tokens,
    chunk_text,
    fetch_url,
    parse_document,
    _SUPPORTED_EXTENSIONS,
    build_skills,
)


def _cfg(**overrides) -> RagConfig:
    defaults = {
        "enabled": True,
        "documents_dir": "~/.jarvis/documents",
        "chunk_size": 100,
        "chunk_overlap": 20,
        "top_k": 5,
        "backend": "json",
        "auto_ingest": False,
    }
    defaults.update(overrides)
    return RagConfig(**defaults)


def _tmp_cfg(tmp_path: Path) -> RagConfig:
    return _cfg(documents_dir=str(tmp_path / "rag_test"))


class TestTokens:
    def test_basic(self):
        assert "привет" in _tokens("Привет, мир!")

    def test_yo_replacement(self):
        t = _tokens("ёжик")
        assert "ежик" in t

    def test_empty(self):
        assert _tokens("") == set()

    def test_overlap(self):
        t1 = _tokens("красная машина")
        t2 = _tokens("машина едет")
        assert t1 & t2


class TestTokenList:
    def test_basic(self):
        result = _token_list("Привет мир привет")
        assert result == ["привет", "мир", "привет"]

    def test_empty(self):
        assert _token_list("") == []

    def test_counts(self):
        result = _token_list("тест тест тест")
        assert len(result) == 3


class TestChunkText:
    def test_empty(self):
        assert chunk_text("", 100, 20) == []

    def test_whitespace_only(self):
        assert chunk_text("   \n  ", 100, 20) == []

    def test_short_text(self):
        assert chunk_text("Короткий текст.", 100, 20) == []

    def test_single_chunk(self):
        text = "А" * 50
        chunks = chunk_text(text, 100, 20)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_multiple_paragraphs(self):
        p1 = "Первый абзац. " * 10
        p2 = "Второй абзац. " * 10
        text = f"{p1}\n\n{p2}"
        chunks = chunk_text(text, 100, 20)
        assert len(chunks) >= 2
        for c in chunks:
            assert len(c) >= 30

    def test_overlap(self):
        text = "Предложение один. Предложение два. Предложение три. " * 5
        chunks = chunk_text(text, 150, 50)
        assert len(chunks) >= 2

    def test_sentence_splitting(self):
        text = "Первое. Второе. Третье. " * 10
        chunks = chunk_text(text, 80, 20)
        assert len(chunks) >= 1
        for c in chunks:
            assert len(c) >= 30


class TestFileHash:
    def test_same_content(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same content")
        f2.write_text("same content")
        assert _file_hash(f1) == _file_hash(f2)

    def test_different_content(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("content a")
        f2.write_text("content b")
        assert _file_hash(f1) != _file_hash(f2)


class TestSourceId:
    def test_deterministic(self):
        sid1 = _source_id("test.pdf", "abc123")
        sid2 = _source_id("test.pdf", "abc123")
        assert sid1 == sid2

    def test_includes_hash(self):
        sid = _source_id("doc.txt", "deadbeef")
        assert "doc.txt" in sid
        assert "deadbeef" in sid


class TestParseTxt:
    def test_basic(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("Привет, мир!", encoding="utf-8")
        assert parse_document(f) == "Привет, мир!"

    def test_markdown(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("# Заголовок\n\nТекст", encoding="utf-8")
        assert "Заголовок" in parse_document(f)

    def test_unsupported_format(self, tmp_path):
        f = tmp_path / "test.xyz"
        f.write_text("test")
        with pytest.raises(ValueError, match="не поддерживается"):
            parse_document(f)


class TestParsePdf:
    def test_success(self, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 dummy")
        import jarvis.skills.rag as rag_mod
        original_parser = rag_mod._PARSERS[".pdf"]
        rag_mod._PARSERS[".pdf"] = lambda p: "PDF text content"
        try:
            result = parse_document(f)
            assert result == "PDF text content"
        finally:
            rag_mod._PARSERS[".pdf"] = original_parser


class TestParseDocx:
    def test_success(self, tmp_path):
        f = tmp_path / "test.docx"
        f.write_bytes(b"PK dummy")
        import jarvis.skills.rag as rag_mod
        original_parser = rag_mod._PARSERS[".docx"]
        rag_mod._PARSERS[".docx"] = lambda p: "DOCX text"
        try:
            result = parse_document(f)
            assert result == "DOCX text"
        finally:
            rag_mod._PARSERS[".docx"] = original_parser


class TestParseHtml:
    def test_from_string(self):
        html = "<html><head><title>Test</title></head>"
        html += "<body><h1>Заголовок</h1><p>Текст параграфа</p>"
        html += "<script>alert('x')</script>Скрыто</body></html>"
        result = _parse_html_from_string(html)
        assert "Заголовок" in result
        assert "Текст параграфа" in result
        assert "alert" not in result
        assert "Скрыто" in result

    def test_from_file(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text("<html><body><p>Hello</p></body></html>", encoding="utf-8")
        result = parse_document(f)
        assert "Hello" in result

    def test_strips_style(self):
        html = "<style>body{color:red}</style><p>Видимый</p>"
        result = _parse_html_from_string(html)
        assert "color" not in result
        assert "Видимый" in result


class TestParseCsv:
    def test_basic(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text(
            "имя,возраст,город\n"
            "Иван,25,Москва\n"
            "Мария,30,Питер\n",
            encoding="utf-8",
        )
        result = parse_document(f)
        assert "имя: Иван" in result
        assert "город: Москва" in result
        assert "Мария" in result

    def test_empty_rows_skipped(self, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_text(
            "col1,col2\n,,\nval1,val2\n",
            encoding="utf-8",
        )
        result = parse_document(f)
        assert "val1" in result

    def test_fallback_on_error(self, tmp_path):
        # Создаём файл который csv.reader сможет прочитать
        f = tmp_path / "ok.csv"
        f.write_text("a,b\n1,2", encoding="utf-8")
        result = parse_document(f)
        assert "1" in result


class TestHtmlTextExtractor:
    def test_basic(self):
        e = _HtmlTextExtractor()
        e.feed("<p>Hello <b>world</b></p>")
        assert "Hello" in e.get_text()
        assert "world" in e.get_text()

    def test_skips_script(self):
        e = _HtmlTextExtractor()
        e.feed("<script>var x = 1;</script><p>visible</p>")
        text = e.get_text()
        assert "var x" not in text
        assert "visible" in text

    def test_adds_newlines(self):
        e = _HtmlTextExtractor()
        e.feed("<p>first</p><p>second</p>")
        text = e.get_text()
        assert "\n" in text


class TestBM25:
    def test_basic_ranking(self):
        entries = [
            {"text": "API использует HTTP методы", "tokens": ["api", "использует", "http", "методы"]},
            {"text": "Рецепт пирога с яблоками", "tokens": ["рецепт", "пирога", "с", "яблоками"]},
            {"text": "REST API для разработчиков", "tokens": ["rest", "api", "для", "разработчиков"]},
        ]
        results = _compute_bm25_scores(["api", "http"], entries)
        assert len(results) >= 2
        # Первый результат должен быть про API+HTTP
        assert "API" in results[0][1]["text"] or "http" in results[0][1]["text"].lower()

    def test_empty_query(self):
        assert _compute_bm25_scores([], []) == []

    def test_no_match(self):
        entries = [{"text": "привет мир", "tokens": ["привет", "мир"]}]
        assert _compute_bm25_scores(["космос"], entries) == []

    def test_idf_boosts_rare_terms(self):
        entries = [
            {"text": "обычное слово частое", "tokens": ["обычное", "слово", "частое"]},
            {"text": "редкий термин спекифичный", "tokens": ["редкий", "термин", "спекифичный"]},
        ] * 10  # дублируем чтобы "частое" было частым
        results = _compute_bm25_scores(["редкий", "термин"], entries)
        assert len(results) > 0
        # Должны быть про редкий термин
        assert "редкий" in results[0][1]["text"]


class TestJsonRagStore:
    def test_add_and_search(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        count = store.add_chunks("src1", "doc.txt", ["Привет мир", "Пока мир"])
        assert count == 2
        results = store.search("привет", 5)
        assert len(results) == 1
        assert "Привет" in results[0]["text"]

    def test_search_with_score(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "doc.txt", ["Python программирование", "Java программирование"])
        results = store.search("Python", 5)
        assert len(results) == 1
        assert results[0]["score"] > 0

    def test_search_with_filename_filter(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "api.txt", ["REST API endpoint"])
        store.add_chunks("src2", "guide.txt", ["REST API tutorial"])
        results = store.search("API", 5, filename_filter="api.txt")
        assert len(results) == 1
        assert results[0]["filename"] == "api.txt"

    def test_search_filename_filter_no_match(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "a.txt", ["test data"])
        results = store.search("test", 5, filename_filter="other.txt")
        assert len(results) == 0

    def test_add_with_tags(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "doc.txt", ["content"], tags=["api", "docs"])
        results = store.search("content", 5)
        assert results[0]["tags"] == ["api", "docs"]

    def test_update_replaces(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "doc.txt", ["old content"], tags=["v1"])
        store.add_chunks("src1", "doc.txt", ["new content"], tags=["v2"])
        results = store.search("content", 5)
        assert len(results) == 1
        assert "new" in results[0]["text"]
        assert results[0]["tags"] == ["v2"]

    def test_list_sources(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "doc1.txt", ["chunk1"])
        store.add_chunks("src2", "doc2.txt", ["chunk2", "chunk3"])
        sources = store.list_sources()
        assert len(sources) == 2
        names = {s["filename"] for s in sources}
        assert "doc1.txt" in names
        assert "doc2.txt" in names

    def test_list_sources_with_tags(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "doc.txt", ["c"], tags=["api", "ref"])
        sources = store.list_sources()
        assert sources[0]["tags"] == ["api", "ref"]

    def test_delete_source(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "doc.txt", ["chunk1", "chunk2", "chunk3"])
        deleted = store.delete_source("src1")
        assert deleted == 3
        assert store.list_sources() == []

    def test_delete_nonexistent(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        deleted = store.delete_source("no_such")
        assert deleted == 0

    def test_search_empty_query(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "doc.txt", ["chunk1"])
        assert store.search("", 5) == []

    def test_search_no_match(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "doc.txt", ["Привет мир"])
        assert store.search("космонавт", 5) == []

    def test_persistence(self, tmp_path):
        rag_dir = tmp_path / "rag"
        store1 = JsonRagStore(rag_dir)
        store1.add_chunks("src1", "doc.txt", ["Данные для проверки проверки"])
        del store1
        store2 = JsonRagStore(rag_dir)
        results = store2.search("проверки", 5)
        assert len(results) == 1

    def test_corrupted_file(self, tmp_path):
        rag_dir = tmp_path / "rag"
        rag_dir.mkdir(parents=True)
        (rag_dir / "rag_index.json").write_text("not json{{{", encoding="utf-8")
        store = JsonRagStore(rag_dir)
        assert store.list_sources() == []

    def test_stats(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "big.txt", ["A" * 200], tags=["ref"])
        store.add_chunks("src2", "small.txt", ["B" * 50], tags=["api"])
        store.add_chunks("src3", "tagged.txt", ["C" * 100], tags=["ref", "api"])
        stats = store.stats()
        assert stats["total_chunks"] == 3
        assert stats["total_sources"] == 3
        assert stats["total_chars"] == 350
        assert len(stats["top_sources"]) <= 5
        assert "ref" in stats["tags"]
        assert "api" in stats["tags"]

    def test_stats_empty(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        stats = store.stats()
        assert stats["total_chunks"] == 0
        assert stats["top_sources"] == []
        assert stats["tags"] == {}


class TestRagEngine:
    def test_ingest_file(self, tmp_path):
        doc_file = tmp_path / "test.txt"
        doc_file.write_text("Это тестовый документ. " * 50, encoding="utf-8")
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_file(str(doc_file))
        assert "test.txt" in result
        assert "фрагмент" in result.lower()

    def test_ingest_not_found(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_file("/nonexistent/file.txt")
        assert "не найден" in result.lower()

    def test_ingest_unsupported(self, tmp_path):
        f = tmp_path / "test.xyz"
        f.write_text("test")
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_file(str(f))
        assert "не поддерживается" in result.lower()

    def test_ingest_empty(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("   ", encoding="utf-8")
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_file(str(f))
        assert "пуст" in result.lower()

    def test_ingest_with_tags(self, tmp_path):
        doc_file = tmp_path / "tagged.txt"
        doc_file.write_text("Документ с тегами. " * 50, encoding="utf-8")
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_file(str(doc_file), tags=["api", "ref"])
        assert "api" in result
        assert "ref" in result

    def test_ingest_directory(self, tmp_path):
        doc_dir = tmp_path / "docs"
        doc_dir.mkdir()
        (doc_dir / "a.txt").write_text("Документ А. " * 40, encoding="utf-8")
        (doc_dir / "b.md").write_text("Документ Б. " * 40, encoding="utf-8")
        (doc_dir / "c.xyz").write_text("skip me")
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_directory(str(doc_dir))
        assert "2 файлов" in result
        assert "a.txt" in result
        assert "b.md" in result

    def test_ingest_directory_with_tags(self, tmp_path):
        doc_dir = tmp_path / "docs2"
        doc_dir.mkdir()
        (doc_dir / "x.txt").write_text("Текст. " * 50, encoding="utf-8")
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_directory(str(doc_dir), tags=["docs"])
        assert "1 файлов" in result

    def test_ingest_directory_not_found(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_directory("/nonexistent")
        assert "не найдена" in result.lower()

    def test_ingest_html_file(self, tmp_path):
        f = tmp_path / "page.html"
        f.write_text(
            "<html><head><title>Test</title></head>"
            "<body><h1>Заголовок</h1><p>Содержимое страницы</p></body></html>",
            encoding="utf-8",
        )
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_file(str(f))
        assert "page.html" in result
        assert "фрагмент" in result.lower()

    def test_ingest_csv_file(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text(
            "name,value\nitem1,100\nitem2,200\n",
            encoding="utf-8",
        )
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_file(str(f))
        assert "data.csv" in result

    def test_ingest_url_success(self):
        engine = RagEngine(_cfg())
        html = "<html><body>" + "<p>Web content paragraph for testing. " * 5 + "</body></html>"
        with patch("jarvis.skills.rag.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = html.encode()
            mock_resp.headers = {"Content-Type": "text/html"}
            mock_resp.__enter__ = lambda self: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            result = engine.ingest_url("https://example.com")
            assert "example.com" in result
            assert "фрагмент" in result.lower()

    def test_ingest_url_error(self):
        engine = RagEngine(_cfg())
        with patch("jarvis.skills.rag.urllib.request.urlopen", side_effect=Exception("network error")):
            result = engine.ingest_url("https://example.com")
            assert "ошибка" in result.lower()

    def test_search(self, tmp_path):
        doc_file = tmp_path / "api.txt"
        doc_file.write_text(
            "REST API использует HTTP методы GET POST PUT DELETE. "
            "GET используется для получения данных. POST для создания. "
            "PUT для обновления. DELETE для удаления.",
            encoding="utf-8",
        )
        engine = RagEngine(_tmp_cfg(tmp_path))
        engine.ingest_file(str(doc_file))
        result = engine.search("HTTP методы")
        assert "Найдено" in result

    def test_search_with_tag_filter(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        f1 = tmp_path / "a.txt"
        f1.write_text("API documentation reference guide. " * 30, encoding="utf-8")
        f2 = tmp_path / "b.txt"
        f2.write_text("Cooking recipe ingredients list. " * 30, encoding="utf-8")
        engine.ingest_file(str(f1), tags=["api"])
        engine.ingest_file(str(f2), tags=["food"])
        result = engine.search("documentation", tag_filter="api")
        assert "a.txt" in result
        assert "b.txt" not in result

    def test_search_with_filename_filter(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        f1 = tmp_path / "api.txt"
        f1.write_text("API endpoint data. " * 30, encoding="utf-8")
        f2 = tmp_path / "guide.txt"
        f2.write_text("API tutorial data. " * 30, encoding="utf-8")
        engine.ingest_file(str(f1))
        engine.ingest_file(str(f2))
        result = engine.search("API", filename_filter="api.txt")
        assert "api.txt" in result

    def test_search_empty(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.search("")
        assert "Укажите" in result

    def test_search_shows_score(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        f = tmp_path / "score.txt"
        f.write_text("Python programming language. " * 30, encoding="utf-8")
        engine.ingest_file(str(f))
        result = engine.search("Python")
        assert "score=" in result

    def test_ask(self, tmp_path):
        doc_file = tmp_path / "vpn.txt"
        doc_file.write_text(
            "Для настройки VPN нужно создать конфигурационный файл. "
            "WireGuard использует ключи для шифрования. "
            "OpenVPN работает через сертификаты.",
            encoding="utf-8",
        )
        engine = RagEngine(_tmp_cfg(tmp_path))
        engine.ingest_file(str(doc_file))
        result = engine.ask("как настроить VPN")
        assert "Контекст" in result

    def test_list_sources_empty(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.list_sources()
        assert "пуста" in result.lower()

    def test_list_sources(self, tmp_path):
        doc_file = tmp_path / "guide.txt"
        doc_file.write_text("Руководство по Джарвису. " * 40, encoding="utf-8")
        engine = RagEngine(_tmp_cfg(tmp_path))
        engine.ingest_file(str(doc_file))
        result = engine.list_sources()
        assert "guide.txt" in result

    def test_list_sources_shows_tags(self, tmp_path):
        doc_file = tmp_path / "tagged.txt"
        doc_file.write_text("Content. " * 50, encoding="utf-8")
        engine = RagEngine(_tmp_cfg(tmp_path))
        engine.ingest_file(str(doc_file), tags=["ref", "v2"])
        result = engine.list_sources()
        assert "#ref" in result
        assert "#v2" in result

    def test_delete_source(self, tmp_path):
        doc_file = tmp_path / "temp.txt"
        doc_file.write_text("Временный документ. " * 40, encoding="utf-8")
        engine = RagEngine(_tmp_cfg(tmp_path))
        engine.ingest_file(str(doc_file))
        result = engine.delete_source("temp.txt")
        assert "Удалён" in result
        assert "temp.txt" in result

    def test_delete_nonexistent(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.delete_source("no_such.txt")
        assert "не найден" in result.lower()

    def test_delete_case_insensitive(self, tmp_path):
        doc_file = tmp_path / "Report.txt"
        doc_file.write_text("Отчёт. " * 40, encoding="utf-8")
        engine = RagEngine(_tmp_cfg(tmp_path))
        engine.ingest_file(str(doc_file))
        result = engine.delete_source("report.txt")
        assert "Удалён" in result

    def test_update_document(self, tmp_path):
        doc_file = tmp_path / "update_me.txt"
        doc_file.write_text("Версия 1. " * 40, encoding="utf-8")
        engine = RagEngine(_tmp_cfg(tmp_path))
        engine.ingest_file(str(doc_file))
        # Меняем содержимое
        doc_file.write_text("Версия 2 обновлённая. " * 40, encoding="utf-8")
        result = engine.update_document(str(doc_file))
        assert "обновлено" in result.lower()
        # Поиск должен находить новую версию
        search_result = engine.search("обновлённая")
        assert "Найдено" in search_result

    def test_update_not_found(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.update_document("/nonexistent/file.txt")
        assert "не найден" in result.lower()

    def test_stats(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        f1 = tmp_path / "big.txt"
        f1.write_text("Большой документ. " * 50, encoding="utf-8")
        f2 = tmp_path / "small.txt"
        f2.write_text("Маленький. " * 20, encoding="utf-8")
        engine.ingest_file(str(f1), tags=["ref"])
        engine.ingest_file(str(f2), tags=["api"])
        result = engine.stats()
        assert "2 источников" in result
        assert "фрагмент" in result
        assert "#ref" in result
        assert "#api" in result

    def test_stats_empty(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.stats()
        assert "пуста" in result.lower()

    def test_auto_ingest(self, tmp_path):
        doc_dir = tmp_path / "rag_test"
        doc_dir.mkdir()
        (doc_dir / "auto.txt").write_text("Автозагрузка. " * 50, encoding="utf-8")
        cfg = _cfg(documents_dir=str(doc_dir), auto_ingest=True)
        skills, engine = build_skills(cfg)
        # Документ должен быть загружен
        result = engine.search("Автозагрузка")
        assert "Найдено" in result

    def test_auto_ingest_disabled(self, tmp_path):
        doc_dir = tmp_path / "rag_test2"
        doc_dir.mkdir()
        (doc_dir / "skip.txt").write_text("Skip. " * 50, encoding="utf-8")
        cfg = _cfg(documents_dir=str(doc_dir), auto_ingest=False)
        skills, engine = build_skills(cfg)
        # Не должен быть загружен
        result = engine.search("Skip")
        assert "ничего не найдено" in result.lower()


class TestFetchUrl:
    def test_success_html(self):
        with patch("jarvis.skills.rag.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            html = "<html><body>" + "<p>Test content paragraph. " * 5 + "</body></html>"
            mock_resp.read.return_value = html.encode()
            mock_resp.headers = {"Content-Type": "text/html"}
            mock_resp.__enter__ = lambda self: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            result = fetch_url("https://example.com")
            assert "Test" in result

    def test_success_text(self):
        with patch("jarvis.skills.rag.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = b"Plain text content"
            mock_resp.headers = {"Content-Type": "text/plain"}
            mock_resp.__enter__ = lambda self: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            result = fetch_url("https://example.com/data.txt")
            assert "Plain text content" in result

    def test_error(self):
        with patch("jarvis.skills.rag.urllib.request.urlopen", side_effect=Exception("fail")):
            with pytest.raises(ValueError, match="Ошибка загрузки"):
                fetch_url("https://example.com")


class TestParseTags:
    def test_single(self):
        assert _parse_tags("api") == ["api"]

    def test_multiple(self):
        assert _parse_tags("api, docs, ref") == ["api", "docs", "ref"]

    def test_empty(self):
        assert _parse_tags("") == []

    def test_whitespace(self):
        assert _parse_tags("  ") == []

    def test_trims(self):
        assert _parse_tags("  api , docs  ") == ["api", "docs"]


class TestBuildSkills:
    def test_count(self):
        skills, _ = build_skills(_cfg(auto_ingest=False))
        assert len(skills) == 8

    def test_names(self):
        skills, _ = build_skills(_cfg(auto_ingest=False))
        names = {s.name for s in skills}
        expected = {
            "rag_ingest", "rag_ingest_url", "rag_search",
            "rag_ask", "rag_list", "rag_delete",
            "rag_update", "rag_stats",
        }
        assert names == expected

    def test_descriptions(self):
        skills, _ = build_skills(_cfg(auto_ingest=False))
        for s in skills:
            assert len(s.description) > 10

    def test_search_required(self):
        skills, _ = build_skills(_cfg(auto_ingest=False))
        rs = next(s for s in skills if s.name == "rag_search")
        props = rs.parameters.get("properties", rs.parameters)
        assert "query" in props

    def test_delete_required(self):
        skills, _ = build_skills(_cfg(auto_ingest=False))
        rd = next(s for s in skills if s.name == "rag_delete")
        props = rd.parameters.get("properties", rd.parameters)
        assert "filename" in props

    def test_ingest_no_params(self):
        skills, _ = build_skills(_cfg(auto_ingest=False))
        ri = next(s for s in skills if s.name == "rag_ingest")
        result = ri.handler(file_path="", directory="")
        assert "Укажите" in result

    def test_ingest_file_path(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Документ. " * 50, encoding="utf-8")
        skills, _ = build_skills(_tmp_cfg(tmp_path))
        ri = next(s for s in skills if s.name == "rag_ingest")
        result = ri.handler(file_path=str(f))
        assert "фрагмент" in result.lower()

    def test_ingest_directory_param(self, tmp_path):
        doc_dir = tmp_path / "docs"
        doc_dir.mkdir()
        (doc_dir / "a.txt").write_text("Текст. " * 50, encoding="utf-8")
        skills, _ = build_skills(_tmp_cfg(tmp_path))
        ri = next(s for s in skills if s.name == "rag_ingest")
        result = ri.handler(directory=str(doc_dir))
        assert "1 файлов" in result

    def test_ingest_with_tags_param(self, tmp_path):
        f = tmp_path / "t.txt"
        f.write_text("Tagged. " * 50, encoding="utf-8")
        skills, _ = build_skills(_tmp_cfg(tmp_path))
        ri = next(s for s in skills if s.name == "rag_ingest")
        result = ri.handler(file_path=str(f), tags="api, ref")
        assert "api" in result
        assert "ref" in result

    def test_ingest_url_handler(self):
        skills, _ = build_skills(_cfg(auto_ingest=False))
        riu = next(s for s in skills if s.name == "rag_ingest_url")
        with patch("jarvis.skills.rag.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            html = "<html><body>" + "<p>Web content for testing. " * 5 + "</body></html>"
            mock_resp.read.return_value = html.encode()
            mock_resp.headers = {"Content-Type": "text/html"}
            mock_resp.__enter__ = lambda self: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp
            result = riu.handler(url="https://example.com")
            assert "фрагмент" in result.lower()

    def test_search_with_tag_handler(self, tmp_path):
        f = tmp_path / "api_doc.txt"
        f.write_text("API reference. " * 40, encoding="utf-8")
        skills, _ = build_skills(_tmp_cfg(tmp_path))
        ri = next(s for s in skills if s.name == "rag_ingest")
        ri.handler(file_path=str(f), tags="api")
        rs = next(s for s in skills if s.name == "rag_search")
        result = rs.handler(query="API", tag="api")
        assert "Найдено" in result

    def test_update_handler(self, tmp_path):
        f = tmp_path / "upd.txt"
        f.write_text("Old. " * 40, encoding="utf-8")
        skills, _ = build_skills(_tmp_cfg(tmp_path))
        ri = next(s for s in skills if s.name == "rag_ingest")
        ri.handler(file_path=str(f))
        f.write_text("New updated. " * 40, encoding="utf-8")
        ru = next(s for s in skills if s.name == "rag_update")
        result = ru.handler(file_path=str(f))
        assert "обновлено" in result.lower()

    def test_stats_handler(self, tmp_path):
        f = tmp_path / "stat.txt"
        f.write_text("Stats doc. " * 40, encoding="utf-8")
        skills, _ = build_skills(_tmp_cfg(tmp_path))
        ri = next(s for s in skills if s.name == "rag_ingest")
        ri.handler(file_path=str(f), tags="test")
        rs = next(s for s in skills if s.name == "rag_stats")
        result = rs.handler()
        assert "1 источников" in result
        assert "#test" in result


class TestSupportedExtensions:
    def test_has_expected(self):
        assert ".txt" in _SUPPORTED_EXTENSIONS
        assert ".md" in _SUPPORTED_EXTENSIONS
        assert ".pdf" in _SUPPORTED_EXTENSIONS
        assert ".docx" in _SUPPORTED_EXTENSIONS
        assert ".html" in _SUPPORTED_EXTENSIONS
        assert ".csv" in _SUPPORTED_EXTENSIONS

    def test_no_unexpected(self):
        assert ".exe" not in _SUPPORTED_EXTENSIONS
        assert ".py" not in _SUPPORTED_EXTENSIONS

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.config import RagConfig
from jarvis.skills.rag import (
    JsonRagStore,
    RagEngine,
    _file_hash,
    _source_id,
    _tokens,
    chunk_text,
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


class TestJsonRagStore:
    def test_add_and_search(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        count = store.add_chunks("src1", "doc.txt", ["Привет мир", "Пока мир"])
        assert count == 2
        results = store.search("привет", 5)
        assert len(results) == 1
        assert "Привет" in results[0]["text"]

    def test_list_sources(self, tmp_path):
        store = JsonRagStore(tmp_path / "rag")
        store.add_chunks("src1", "doc1.txt", ["chunk1"])
        store.add_chunks("src2", "doc2.txt", ["chunk2", "chunk3"])
        sources = store.list_sources()
        assert len(sources) == 2
        names = {s["filename"] for s in sources}
        assert "doc1.txt" in names
        assert "doc2.txt" in names

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

    def test_ingest_directory_not_found(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.ingest_directory("/nonexistent")
        assert "не найдена" in result.lower()

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

    def test_search_empty(self, tmp_path):
        engine = RagEngine(_tmp_cfg(tmp_path))
        result = engine.search("")
        assert "Укажите" in result

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


class TestBuildSkills:
    def test_count(self):
        skills, _ = build_skills(_cfg())
        assert len(skills) == 5

    def test_names(self):
        skills, _ = build_skills(_cfg())
        names = {s.name for s in skills}
        assert names == {"rag_ingest", "rag_search", "rag_ask", "rag_list", "rag_delete"}

    def test_descriptions(self):
        skills, _ = build_skills(_cfg())
        for s in skills:
            assert len(s.description) > 10

    def test_search_required(self):
        skills, _ = build_skills(_cfg())
        rs = next(s for s in skills if s.name == "rag_search")
        assert "query" in rs.parameters.get("required", [])

    def test_delete_required(self):
        skills, _ = build_skills(_cfg())
        rd = next(s for s in skills if s.name == "rag_delete")
        assert "filename" in rd.parameters.get("required", [])

    def test_ingest_no_params(self):
        skills, _ = build_skills(_cfg())
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


class TestSupportedExtensions:
    def test_has_expected(self):
        assert ".txt" in _SUPPORTED_EXTENSIONS
        assert ".md" in _SUPPORTED_EXTENSIONS
        assert ".pdf" in _SUPPORTED_EXTENSIONS
        assert ".docx" in _SUPPORTED_EXTENSIONS

    def test_no_unexpected(self):
        assert ".exe" not in _SUPPORTED_EXTENSIONS
        assert ".py" not in _SUPPORTED_EXTENSIONS

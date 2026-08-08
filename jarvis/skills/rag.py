"""RAG (Retrieval-Augmented Generation): загрузка документов и поиск по ним.

Джарвис может загружать документы (TXT, MD, PDF, DOCX, HTML, CSV),
разбивать их на фрагменты и находить релевантные куски по запросу.

Возможности:
- Теги/категории для документов с фильтрацией при поиске
- TF-IDF взвешивание в JSON хранилище (BM25-подобный ранжирование)
- Авто-загрузка директории документов при старте
- Обновление документов (re-ingest заменяет старые чанки)
- HTML парсер (из файла или URL)
- CSV парсер (строки как записи)
- Статистика базы: размер, объём, топ документов
- Фильтрация по источнику при поиске

Голосовые команды:
  \"Джарвис, загрузи документ отчёт.pdf\"
  \"Джарвис, загрузи все документы\"
  \"Джарвис, загрузи страницу https://example.com\"
  \"Джарвис, найди в документах про API\"
  \"Джарвис, найди про API в отчёте.pdf\"
  \"Джарвис, спроси у документов как настроить VPN\"
  \"Джарвис, покажи загруженные документы\"
  \"Джарвис, удали документ отчёт.pdf из базы\"
  \"Джарвис, статистика базы документов\"
  \"Джарвис, обнови документ отчёт.pdf\"

Конфигурация в config.yaml::

  skills:
    rag:
      enabled: true
      documents_dir: \"~/.jarvis/documents\"
      chunk_size: 500
      chunk_overlap: 100
      top_k: 5
      auto_ingest: true
"""

from __future__ import annotations

import csv
import hashlib

import json
import logging
import math
import re
import urllib.request
import uuid
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Protocol

from ..config import RagConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

RAG_COLLECTION = "jarvis_rag"
WORD_RE = re.compile(r"\w+", re.UNICODE)

# Поддерживаемые форматы
_SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx", ".html", ".htm", ".csv"}


# ── Парсеры документов ──────────────────────────────────────────────


def _parse_txt(path: Path) -> str:
    """Читает TXT/MD файл."""
    return path.read_text(encoding="utf-8", errors="replace")


def _parse_pdf(path: Path) -> str:
    """Извлекает текст из PDF через PyMuPDF (fitz)."""
    import fitz
    doc = fitz.open(str(path))
    pages = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


def _parse_docx(path: Path) -> str:
    """Извлекает текст из DOCX через python-docx."""
    from docx import Document
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


class _HtmlTextExtractor(HTMLParser):
    """Извлекает видимый текст из HTML."""

    def __init__(self) -> None:
        super().__init__()
        self._text_parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "br"):
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._text_parts.append(data)

    def get_text(self) -> str:
        return "".join(self._text_parts)


def _parse_html_from_string(html_content: str) -> str:
    """Извлекает текст из HTML строки."""
    extractor = _HtmlTextExtractor()
    extractor.feed(html_content)
    text = extractor.get_text()
    # Нормализация whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_html(path: Path) -> str:
    """Извлекает текст из HTML файла."""
    html_content = path.read_text(encoding="utf-8", errors="replace")
    return _parse_html_from_string(html_content)


def _parse_csv(path: Path) -> str:
    """Извлекает текст из CSV файла (строки как записи)."""
    rows: list[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            headers = None
            for row in reader:
                if not any(cell.strip() for cell in row):
                    continue
                if headers is None:
                    headers = [c.strip() for c in row]
                    continue
                parts = []
                for i, cell in enumerate(row):
                    header = headers[i] if i < len(headers) else f"col{i}"
                    if cell.strip():
                        parts.append(f"{header}: {cell.strip()}")
                if parts:
                    rows.append(". ".join(parts))
    except Exception:
        # Fallback: просто читаем как текст
        return path.read_text(encoding="utf-8", errors="replace")
    return "\n\n".join(rows)


_PARSERS: dict[str, Any] = {
    ".txt": _parse_txt,
    ".md": _parse_txt,
    ".markdown": _parse_txt,
    ".pdf": _parse_pdf,
    ".docx": _parse_docx,
    ".html": _parse_html,
    ".htm": _parse_html,
    ".csv": _parse_csv,
}


def parse_document(path: Path) -> str:
    """Парсит документ по расширению. Возвращает полный текст."""
    ext = path.suffix.lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        raise ValueError(
            f"Формат {ext} не поддерживается. "
            f"Поддерживаемые: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )
    return parser(path)


def fetch_url(url: str, timeout_s: int = 15) -> str:
    """Скачивает URL и извлекает текст (HTML → plain text)."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; JarvisRAG/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(300_000).decode("utf-8", errors="replace")
        if "text/html" in content_type:
            return _parse_html_from_string(raw)
        # Для не-HTML: возвращаем как есть (может быть JSON, TXT и т.д.)
        return raw
    except Exception as exc:
        raise ValueError(f"Ошибка загрузки URL: {exc}") from exc


# ── Чанкинг ─────────────────────────────────────────────────────────


def _tokens(text: str) -> set[str]:
    """Нормализованные токены для поиска."""
    return {w.lower() for w in WORD_RE.findall(text.replace("ё", "е"))}


def _token_list(text: str) -> list[str]:
    """Список токенов (с повторами) для TF-IDF."""
    return [w.lower() for w in WORD_RE.findall(text.replace("ё", "е"))]


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Разбивает текст на перекрывающиеся чанки.

    Разбивает по абзацам, потом по предложениям. Если абзац/предложение
    длиннее chunk_size -- разбивает по словам.
    """
    if not text.strip():
        return []

    # Нормализация whitespace
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    chunks: list[str] = []
    # Разбиваем на абзацы
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    current = ""
    for para in paragraphs:
        if len(para) > chunk_size:
            if current.strip():
                chunks.append(current.strip())
                current = ""
            sentences = re.split(r"(?<=[.!?])\s+", para)
            # Если предложений не найдено (нет пунктуации) — разбиваем по словам
            if len(sentences) <= 1 and len(sentences[0]) > chunk_size:
                chunks.extend(_split_by_words(para, chunk_size, chunk_overlap))
                continue
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(current) + len(sent) + 1 > chunk_size and current.strip():
                    chunks.append(current.strip())
                    if chunk_overlap > 0 and len(current) > chunk_overlap:
                        words = current.split()
                        overlap_words = words[-max(1, chunk_overlap // 4):]
                        current = " ".join(overlap_words) + " " + sent
                    else:
                        current = sent
                else:
                    current = current + " " + sent if current else sent
        else:
            if len(current) + len(para) + 2 > chunk_size and current.strip():
                chunks.append(current.strip())
                if chunk_overlap > 0 and len(current) > chunk_overlap:
                    words = current.split()
                    overlap_words = words[-max(1, chunk_overlap // 4):]
                    current = " ".join(overlap_words) + " " + para
                else:
                    current = para
            else:
                current = current + "\n\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())

    # Фильтр слишком коротких чанков (меньше 30 символов)
    return [c for c in chunks if len(c) >= 30]


def _split_by_words(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Разбивает текст по словам, когда нет пунктуации для разделения."""
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    current_words: list[str] = []
    current_len = 0
    for word in words:
        word_len = len(word) + (1 if current_words else 0)  # +1 for space
        if current_len + word_len > chunk_size and current_words:
            chunks.append(" ".join(current_words))
            # Overlap: keep last N words
            if chunk_overlap > 0:
                overlap_count = max(1, chunk_overlap // 4)
                current_words = current_words[-overlap_count:]
                current_len = sum(len(w) for w in current_words) + len(current_words) - 1
            else:
                current_words = []
                current_len = 0
        current_words.append(word)
        current_len += word_len
    if current_words:
        chunks.append(" ".join(current_words))
    return [c for c in chunks if len(c) >= 30]


def _file_hash(path: Path) -> str:
    """SHA-256 хэш содержимого файла."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8192), b""):
            h.update(block)
    return h.hexdigest()[:16]


def _source_id(filename: str, file_hash: str) -> str:
    """Уникальный ID источника документа."""
    return f"{filename}_{file_hash}"


# ── TF-IDF для JSON хранилища ────────────────────────────────────


def _compute_bm25_scores(
    query_tokens: list[str],
    entries: list[dict[str, Any]],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[tuple[float, dict[str, Any]]]:
    """BM25-подобное ранжирование для JSON хранилища.

    Даёт более качественный ранкинг чем простое пересечение токенов.
    """
    if not query_tokens or not entries:
        return []

    N = len(entries)
    # Средняя длина документа (в токенах)
    avg_dl = sum(len(e.get("tokens", [])) for e in entries) / max(N, 1)

    # DF: в скольких документах встречается каждый термин
    df: Counter = Counter()
    for entry in entries:
        unique_tokens = set(entry.get("tokens", []))
        for t in unique_tokens:
            df[t] += 1

    # IDF
    idf: dict[str, float] = {}
    for t in set(query_tokens):
        df_t = df.get(t, 0)
        idf[t] = math.log((N - df_t + 0.5) / (df_t + 0.5) + 1)

    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in entries:
        entry_tokens = entry.get("tokens", [])
        dl = len(entry_tokens)
        tf_map = Counter(entry_tokens)
        score = 0.0
        for qt in query_tokens:
            if qt not in tf_map:
                continue
            tf = tf_map[qt]
            idf_val = idf.get(qt, 0)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / max(avg_dl, 1))
            score += idf_val * numerator / denominator
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


# ── Хранилище (Protocol) ───────────────────────────────────────────


class RagStore(Protocol):
    """Хранилище чанков документов с поиском."""

    def add_chunks(
        self, source_id: str, filename: str, chunks: list[str],
        tags: list[str] | None = None,
    ) -> int: ...

    def search(
        self, query: str, top_k: int,
        filename_filter: str = "",
    ) -> list[dict[str, Any]]: ...

    def list_sources(self) -> list[dict[str, Any]]: ...

    def delete_source(self, source_id: str) -> int: ...

    def stats(self) -> dict[str, Any]: ...


# ── JSON хранилище (fallback) ───────────────────────────────────────


class JsonRagStore:
    """JSON-файл хранилище с BM25-подобным ранжированием."""

    def __init__(self, path: Path) -> None:
        self._path = path / "rag_index.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            self._data = []
            return
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("RAG индекс повреждён, сбрасываю: %s", self._path)
            self._data = []

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8",
            )
        except OSError:
            log.exception("Ошибка сохранения RAG индекса")

    def add_chunks(
        self, source_id: str, filename: str, chunks: list[str],
        tags: list[str] | None = None,
    ) -> int:
        # Удаляем старые чанки этого источника (для обновления)
        self.delete_source(source_id)
        count = 0
        for i, chunk in enumerate(chunks):
            entry = {
                "id": uuid.uuid4().hex,
                "source_id": source_id,
                "filename": filename,
                "chunk_index": i,
                "text": chunk,
                "tokens": _token_list(chunk),
                "tags": tags or [],
            }
            self._data.append(entry)
            count += 1
        self._save()
        return count

    def search(
        self, query: str, top_k: int,
        filename_filter: str = "",
    ) -> list[dict[str, Any]]:
        wanted = _token_list(query)
        if not wanted:
            return []
        # Фильтр по файлу если указан
        entries = self._data
        if filename_filter:
            entries = [
                e for e in entries
                if e.get("filename", "").lower() == filename_filter.lower()
            ]
        if not entries:
            return []
        scored = _compute_bm25_scores(wanted, entries)
        return [
            {
                "text": e["text"],
                "filename": e["filename"],
                "chunk_index": e["chunk_index"],
                "tags": e.get("tags", []),
                "score": round(score, 3),
            }
            for score, e in scored[:top_k]
        ]

    def list_sources(self) -> list[dict[str, Any]]:
        sources: dict[str, dict[str, Any]] = {}
        for entry in self._data:
            sid = entry["source_id"]
            if sid not in sources:
                sources[sid] = {
                    "source_id": sid,
                    "filename": entry["filename"],
                    "chunks": 0,
                    "tags": entry.get("tags", []),
                }
            sources[sid]["chunks"] += 1
        return list(sources.values())

    def delete_source(self, source_id: str) -> int:
        before = len(self._data)
        self._data = [e for e in self._data if e["source_id"] != source_id]
        deleted = before - len(self._data)
        if deleted:
            self._save()
        return deleted

    def stats(self) -> dict[str, Any]:
        sources: dict[str, dict[str, Any]] = {}
        total_chars = 0
        for entry in self._data:
            sid = entry["source_id"]
            if sid not in sources:
                sources[sid] = {
                    "filename": entry["filename"],
                    "chunks": 0,
                    "chars": 0,
                    "tags": entry.get("tags", []),
                }
            sources[sid]["chunks"] += 1
            sources[sid]["chars"] += len(entry["text"])
            total_chars += len(entry["text"])
        # Топ по размеру
        top_sources = sorted(
            sources.values(), key=lambda x: x["chars"], reverse=True,
        )[:5]
        # Все теги
        all_tags: Counter = Counter()
        for info in sources.values():
            for t in info.get("tags", []):
                all_tags[t] += 1
        return {
            "total_chunks": len(self._data),
            "total_sources": len(sources),
            "total_chars": total_chars,
            "top_sources": [
                {
                    "filename": s["filename"],
                    "chunks": s["chunks"],
                    "chars": s["chars"],
                    "tags": s["tags"],
                }
                for s in top_sources
            ],
            "tags": dict(all_tags.most_common()),
        }


# ── ChromaDB хранилище ─────────────────────────────────────────────


class ChromaRagStore:
    """Векторное хранилище на ChromaDB с семантическим поиском."""

    def __init__(self, path: Path) -> None:
        import chromadb
        path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path / "chroma_rag"))
        self._collection = self._client.get_or_create_collection(RAG_COLLECTION)
        self._sources_path = path / "rag_sources.json"
        self._sources: dict[str, dict[str, Any]] = {}
        self._load_sources()

    def _load_sources(self) -> None:
        if self._sources_path.is_file():
            try:
                self._sources = json.loads(self._sources_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._sources = {}

    def _save_sources(self) -> None:
        try:
            self._sources_path.write_text(
                json.dumps(self._sources, ensure_ascii=False, indent=2), encoding="utf-8",
            )
        except OSError:
            log.exception("Ошибка сохранения RAG источников")

    def add_chunks(
        self, source_id: str, filename: str, chunks: list[str],
        tags: list[str] | None = None,
    ) -> int:
        if not chunks:
            return 0
        # Удаляем старые чанки (для обновления)
        self._delete_chunks(source_id)
        ids = [f"{source_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source_id": source_id,
                "filename": filename,
                "chunk_index": i,
                "tags": ",".join(tags) if tags else "",
            }
            for i in range(len(chunks))
        ]
        self._collection.add(ids=ids, documents=chunks, metadatas=metadatas)
        self._sources[source_id] = {
            "filename": filename,
            "chunks": len(chunks),
            "tags": tags or [],
        }
        self._save_sources()
        return len(chunks)

    def _delete_chunks(self, source_id: str) -> None:
        try:
            existing = self._collection.get(where={"source_id": source_id})
            if existing and existing.get("ids"):
                self._collection.delete(ids=existing["ids"])
        except Exception:
            log.warning("Ошибка удаления чанков %s из ChromaDB", source_id)

    def search(
        self, query: str, top_k: int,
        filename_filter: str = "",
    ) -> list[dict[str, Any]]:
        count = self._collection.count()
        if count == 0:
            return []
        actual_k = min(top_k, count)
        where = None
        if filename_filter:
            where = {"filename": filename_filter}
        kwargs: dict[str, Any] = {"query_texts": [query], "n_results": actual_k}
        if where:
            kwargs["where"] = where
        result = self._collection.query(**kwargs)
        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]
        results = []
        for doc, meta, dist in zip(documents[0], metadatas[0], distances[0]):
            tags_str = meta.get("tags", "")
            results.append({
                "text": str(doc),
                "filename": meta.get("filename", "?"),
                "chunk_index": meta.get("chunk_index", 0),
                "tags": [t.strip() for t in tags_str.split(",") if t.strip()],
                "score": round(1 - dist, 3) if dist is not None else 0,
            })
        return results

    def list_sources(self) -> list[dict[str, Any]]:
        return [
            {"source_id": sid, **info}
            for sid, info in self._sources.items()
        ]

    def delete_source(self, source_id: str) -> int:
        self._delete_chunks(source_id)
        chunks = self._sources.pop(source_id, {}).get("chunks", 0)
        self._save_sources()
        return chunks

    def stats(self) -> dict[str, Any]:
        total_chunks = self._collection.count()
        sources_info = []
        all_tags: Counter = Counter()
        total_chars = 0
        for sid, info in self._sources.items():
            chunks = info.get("chunks", 0)
            tags = info.get("tags", [])
            sources_info.append({
                "filename": info.get("filename", "?"),
                "chunks": chunks,
                "chars": 0,  # ChromaDB не хранит длину
                "tags": tags,
            })
            for t in tags:
                all_tags[t] += 1
        top_sources = sorted(
            sources_info, key=lambda x: x["chunks"], reverse=True,
        )[:5]
        return {
            "total_chunks": total_chunks,
            "total_sources": len(self._sources),
            "total_chars": total_chars,
            "top_sources": top_sources,
            "tags": dict(all_tags.most_common()),
        }


def _build_store(config: RagConfig) -> RagStore:
    """Создаёт хранилище: ChromaDB если доступна, иначе JSON."""
    path = Path(config.documents_dir)
    if config.backend in ("auto", "chroma"):
        try:
            return ChromaRagStore(path)  # type: ignore[return-value]
        except Exception as exc:
            if config.backend == "chroma":
                log.warning("ChromaDB недоступна (%s), RAG на JSON", exc)
            else:
                log.info("ChromaDB не используется (%s), RAG на JSON", exc)
    return JsonRagStore(path)


# ── RAG Engine ──────────────────────────────────────────────────────


class RagEngine:
    """Фасад RAG: загрузка документов, поиск, выдача контекста."""

    def __init__(self, config: RagConfig) -> None:
        self.config = config
        self._store: RagStore | None = None

    @property
    def store(self) -> RagStore:
        if self._store is None:
            self._store = _build_store(self.config)
        return self._store

    def ingest_file(self, file_path: str, tags: list[str] | None = None) -> str:
        """Загружает один документ в RAG базу."""
        p = Path(file_path).expanduser().resolve()
        if not p.is_file():
            return f"Файл {file_path} не найден, сэр."
        ext = p.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            return (
                f"Формат {ext} не поддерживается. "
                f"Поддерживаемые: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}, сэр."
            )
        try:
            text = parse_document(p)
        except Exception as exc:
            return f"Ошибка чтения {p.name}: {exc}, сэр."
        if not text.strip():
            return f"Документ {p.name} пуст, сэр."
        chunks = chunk_text(text, self.config.chunk_size, self.config.chunk_overlap)
        if not chunks:
            return f"Не удалось разбить {p.name} на чанки, сэр."
        file_hash = _file_hash(p)
        source_id = _source_id(p.name, file_hash)
        count = self.store.add_chunks(source_id, p.name, chunks, tags=tags)
        tag_str = f" [темы: {', '.join(tags)}]" if tags else ""
        return (
            f"Загружен {p.name}: {count} фрагментов "
            f"({len(text)} символов){tag_str}, сэр."
        )

    def ingest_url(self, url: str, tags: list[str] | None = None) -> str:
        """Загружает веб-страницу по URL в RAG базу."""
        try:
            text = fetch_url(url)
        except ValueError as exc:
            return str(exc) + ", сэр."
        if not text.strip():
            return f"Страница {url} пуста, сэр."
        chunks = chunk_text(text, self.config.chunk_size, self.config.chunk_overlap)
        if not chunks:
            return f"Не удалось разбить страницу {url} на чанки, сэр."
        # Генерируем имя из URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        filename = parsed.hostname or "web_page"
        filename = re.sub(r"[^\w.-]", "_", filename)
        filename = f"{filename}.html"
        source_id = _source_id(filename, hashlib.sha256(url.encode()).hexdigest()[:16])
        count = self.store.add_chunks(source_id, filename, chunks, tags=tags)
        tag_str = f" [темы: {', '.join(tags)}]" if tags else ""
        return (
            f"Загружена страница {url}: {count} фрагментов "
            f"({len(text)} символов){tag_str}, сэр."
        )

    def ingest_directory(self, directory: str = "", tags: list[str] | None = None) -> str:
        """Загружает все документы из директории."""
        dir_path = (
            Path(directory).expanduser()
            if directory
            else Path(self.config.documents_dir).expanduser()
        )
        if not dir_path.is_dir():
            return f"Директория {dir_path} не найдена, сэр."
        files = sorted(
            f for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS
        )
        if not files:
            return f"В {dir_path} нет поддерживаемых документов, сэр."
        results: list[str] = []
        total_chunks = 0
        for f in files:
            try:
                text = parse_document(f)
                if not text.strip():
                    results.append(f"  {f.name}: пуст")
                    continue
                chunks = chunk_text(text, self.config.chunk_size, self.config.chunk_overlap)
                if not chunks:
                    results.append(f"  {f.name}: не удалось разбить")
                    continue
                file_hash = _file_hash(f)
                source_id = _source_id(f.name, file_hash)
                count = self.store.add_chunks(source_id, f.name, chunks, tags=tags)
                total_chunks += count
                results.append(f"  {f.name}: {count} фрагментов")
            except Exception as exc:
                results.append(f"  {f.name}: ошибка ({exc})")
                log.warning("Ошибка загрузки %s: %s", f, exc)
        return (
            f"Загружено {len(files)} файлов, {total_chunks} фрагментов:\n"
            + "\n".join(results)
            + ", сэр."
        )

    def auto_ingest(self) -> str:
        """Автоматически загружает все документы из documents_dir."""
        dir_path = Path(self.config.documents_dir).expanduser()
        if not dir_path.is_dir():
            return ""
        files = sorted(
            f for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS
        )
        if not files:
            return ""
        total = 0
        for f in files:
            try:
                text = parse_document(f)
                if not text.strip():
                    continue
                chunks = chunk_text(text, self.config.chunk_size, self.config.chunk_overlap)
                if not chunks:
                    continue
                file_hash = _file_hash(f)
                source_id = _source_id(f.name, file_hash)
                count = self.store.add_chunks(source_id, f.name, chunks)
                total += count
            except Exception:
                pass
        if total > 0:
            log.info("RAG auto-ingest: %d файлов, %d фрагментов", len(files), total)
        return f"auto-ingested {total} chunks from {len(files)} files"

    def update_document(self, file_path: str) -> str:
        """Обновляет документ (удаляет старые чанки и загружает заново)."""
        p = Path(file_path).expanduser().resolve()
        if not p.is_file():
            return f"Файл {file_path} не найден, сэр."
        # Находим старый source_id по имени файла и удаляем
        sources = self.store.list_sources()
        old_count = 0
        for s in sources:
            if s.get("filename", "").lower() == p.name.lower():
                old_count += self.store.delete_source(s["source_id"])
        # Загружаем заново
        result = self.ingest_file(file_path)
        if old_count > 0:
            result += f" (обновлено, было {old_count} старых фрагментов)"
        return result

    def search(
        self, query: str, top_k: int = 0,
        filename_filter: str = "", tag_filter: str = "",
    ) -> str:
        """Ищет релевантные фрагменты по запросу."""
        if not query.strip():
            return "Укажите поисковый запрос, сэр."
        k = top_k if top_k > 0 else self.config.top_k
        results = self.store.search(query, k, filename_filter=filename_filter)

        # Пост-фильтрация по тегу
        if tag_filter and results:
            results = [
                r for r in results
                if tag_filter.lower() in [t.lower() for t in r.get("tags", [])]
            ]

        if not results:
            filter_info = ""
            if filename_filter:
                filter_info += f" в файле {filename_filter}"
            if tag_filter:
                filter_info += f" по теме {tag_filter}"
            return f"По запросу '{query}'{filter_info} ничего не найдено, сэр."
        lines = [f"Найдено {len(results)} фрагментов по '{query}':"]
        for r in results:
            fname = r.get("filename", "?")
            score = r.get("score", 0)
            text = r["text"][:300]
            tags = r.get("tags", [])
            tag_str = f" [#{', #'.join(tags)}]" if tags else ""
            lines.append(f"  [{fname}]{tag_str} (score={score}) {text}...")
        return "\n".join(lines) + ", сэр."

    def ask(self, question: str) -> str:
        """Ищет контекст и формирует ответ с выдержками из документов."""
        if not question.strip():
            return "Укажите вопрос, сэр."
        k = self.config.top_k
        results = self.store.search(question, k)
        if not results:
            return f"В загруженных документах нет информации по '{question}', сэр."
        lines = [f"Контекст из документов по вопросу '{question}':"]
        for i, r in enumerate(results, 1):
            fname = r.get("filename", "?")
            lines.append(f"  [{i}] ({fname}): {r['text'][:500]}")
        return "\n".join(lines) + ", сэр."

    def list_sources(self) -> str:
        """Показывает загруженные документы."""
        sources = self.store.list_sources()
        if not sources:
            return "База документов пуста, сэр. Загрузите документ командой rag_ingest."
        lines = [f"Загруженные документы ({len(sources)}):"]
        for s in sources:
            fname = s.get("filename", "?")
            chunks = s.get("chunks", "?")
            tags = s.get("tags", [])
            tag_str = f" [#{', #'.join(tags)}]" if tags else ""
            lines.append(f"  {fname} -- {chunks} фрагментов{tag_str}")
        return "\n".join(lines) + ", сэр."

    def delete_source(self, filename: str) -> str:
        """Удаляет документ из базы."""
        sources = self.store.list_sources()
        matching = [
            s for s in sources
            if s.get("filename", "").lower() == filename.lower()
        ]
        if not matching:
            matching = [
                s for s in sources
                if s.get("source_id", "") == filename
            ]
        if not matching:
            available = ", ".join(s.get("filename", "?") for s in sources) or "нет"
            return f"Документ '{filename}' не найден. Загруженные: {available}, сэр."
        deleted_total = 0
        for m in matching:
            sid = m["source_id"]
            deleted_total += self.store.delete_source(sid)
        return f"Удалён {filename}: {deleted_total} фрагментов, сэр."

    def stats(self) -> str:
        """Показывает статистику базы документов."""
        s = self.store.stats()
        total_chunks = s["total_chunks"]
        total_sources = s["total_sources"]
        total_chars = s["total_chars"]
        if total_sources == 0:
            return "База документов пуста, сэр."
        lines = [
            f"База документов: {total_sources} источников, "
            f"{total_chunks} фрагментов, {total_chars:,} символов.",
        ]
        # Теги
        tags = s.get("tags", {})
        if tags:
            tag_parts = [f"#{k} ({v})" for k, v in tags.items()]
            lines.append(f"Темы: {', '.join(tag_parts)}")
        # Топ документы
        top = s.get("top_sources", [])
        if top:
            lines.append("\nТоп по размеру:")
            for i, src in enumerate(top, 1):
                fname = src["filename"]
                chunks = src["chunks"]
                chars = src.get("chars", 0)
                src_tags = src.get("tags", [])
                tag_str = f" [#{', #'.join(src_tags)}]" if src_tags else ""
                char_info = f", {chars:,} символов" if chars else ""
                lines.append(f"  {i}. {fname}{tag_str} -- {chunks} фрагментов{char_info}")
        return "\n".join(lines) + ", сэр."


# ── Навыки ──────────────────────────────────────────────────────────


def build_skills(config: RagConfig) -> tuple[list[Skill], RagEngine]:
    """Создаёт RAG навыки и движок."""
    engine = RagEngine(config)
    skills = [
        Skill(
            name="rag_ingest",
            description=(
                "Загрузить документ в базу знаний RAG. "
                "Поддерживаются TXT, MD, PDF, DOCX, HTML, CSV. "
                "Если указать directory -- загрузит все документы из папки. "
                "tags -- список тем через запятую для фильтрации."
            ),
            parameters=object_schema(
                {
                    "file_path": {"type": "string", "description": "Путь к файлу документа"},
                    "directory": {"type": "string", "description": "Путь к папке с документами (вместо file_path)"},
                    "tags": {"type": "string", "description": "Темы через запятую (например: API,документация)"},
                },
            ),
            handler=lambda file_path="", directory="", tags="": (
                engine.ingest_directory(directory, tags=_parse_tags(tags))
                if directory
                else engine.ingest_file(file_path, tags=_parse_tags(tags))
                if file_path
                else "Укажите file_path или directory, сэр."
            ),
        ),
        Skill(
            name="rag_ingest_url",
            description=(
                "Загрузить веб-страницу по URL в базу знаний RAG. "
                "HTML автоматически конвертируется в текст. "
                "tags -- список тем для фильтрации."
            ),
            parameters=object_schema(
                {
                    "url": {"type": "string", "description": "URL веб-страницы"},
                    "tags": {"type": "string", "description": "Темы через запятую"},
                },
                required=["url"],
            ),
            handler=lambda url, tags="": engine.ingest_url(url, tags=_parse_tags(tags)),
        ),
        Skill(
            name="rag_search",
            description=(
                "Найти фрагменты в загруженных документах по смысловому запросу. "
                "Можно фильтровать по файлу (filename) и теме (tag)."
            ),
            parameters=object_schema(
                {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "top_k": {"type": "integer", "description": "Сколько фрагментов вернуть"},
                    "filename": {"type": "string", "description": "Фильтр по имени файла"},
                    "tag": {"type": "string", "description": "Фильтр по теме/тегу"},
                },
                required=["query"],
            ),
            handler=lambda query, top_k=0, filename="", tag="": engine.search(
                query, top_k, filename_filter=filename, tag_filter=tag,
            ),
        ),
        Skill(
            name="rag_ask",
            description=(
                "Задать вопрос документам -- извлечёт релевантные фрагменты как контекст. "
                "Результат можно передать в LLM для генерации ответа."
            ),
            parameters=object_schema(
                {"question": {"type": "string", "description": "Вопрос к документам"}},
                required=["question"],
            ),
            handler=lambda question: engine.ask(question),
        ),
        Skill(
            name="rag_list",
            description="Показать список загруженных документов в базе знаний RAG.",
            parameters=object_schema({}),
            handler=engine.list_sources,
        ),
        Skill(
            name="rag_delete",
            description="Удалить документ из базы знаний RAG по имени файла.",
            parameters=object_schema(
                {"filename": {"type": "string", "description": "Имя файла для удаления"}},
                required=["filename"],
            ),
            handler=lambda filename: engine.delete_source(filename),
        ),
        Skill(
            name="rag_update",
            description=(
                "Обновить документ в базе -- удалит старые чанки и загрузит заново. "
                "Полезно когда файл изменился."
            ),
            parameters=object_schema(
                {"file_path": {"type": "string", "description": "Путь к файлу"}},
                required=["file_path"],
            ),
            handler=lambda file_path: engine.update_document(file_path),
        ),
        Skill(
            name="rag_stats",
            description=(
                "Показать статистику базы документов RAG: "
                "количество источников, фрагментов, теги, топ документы."
            ),
            parameters=object_schema({}),
            handler=engine.stats,
        ),
    ]
    # Авто-загрузка
    if config.auto_ingest:
        try:
            engine.auto_ingest()
        except Exception:
            log.warning("RAG auto-ingest не удался", exc_info=True)
    return skills, engine


def _parse_tags(tags_str: str) -> list[str]:
    """Парсит строку тегов 'tag1, tag2' в список."""
    if not tags_str or not tags_str.strip():
        return []
    return [t.strip() for t in tags_str.split(",") if t.strip()]

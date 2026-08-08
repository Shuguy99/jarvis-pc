"""RAG (Retrieval-Augmented Generation): загрузка документов и поиск по ним.

Джарвис может загружать документы (TXT, MD, PDF, DOCX), разбивать их
на фрагменты и находить релевантные куски по запросу.

Голосовые команды:
  "Джарвис, загрузи документ отчёт.pdf"
  "Джарвис, загрузи все документы"
  "Джарвис, найди в документах про API"
  "Джарвис, спроси у документов как настроить VPN"
  "Джарвис, покажи загруженные документы"
  "Джарвис, удали документ отчёт.pdf из базы"

Конфигурация в config.yaml::

  skills:
    rag:
      enabled: true
      documents_dir: "~/.jarvis/documents"
      chunk_size: 500
      chunk_overlap: 100
      top_k: 5
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any, Protocol

from ..config import RagConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

RAG_COLLECTION = "jarvis_rag"
WORD_RE = re.compile(r"\w+", re.UNICODE)

# Поддерживаемые форматы
_SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf", ".docx"}


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


_PARSERS: dict[str, Any] = {
    ".txt": _parse_txt,
    ".md": _parse_txt,
    ".markdown": _parse_txt,
    ".pdf": _parse_pdf,
    ".docx": _parse_docx,
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


# ── Чанкинг ─────────────────────────────────────────────────────────


def _tokens(text: str) -> set[str]:
    """Нормализованные токены для поиска."""
    return {w.lower() for w in WORD_RE.findall(text.replace("ё", "е"))}


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


# ── Хранилище (Protocol) ───────────────────────────────────────────


class RagStore(Protocol):
    """Хранилище чанков документов с поиском."""

    def add_chunks(self, source_id: str, filename: str, chunks: list[str]) -> int: ...

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]: ...

    def list_sources(self) -> list[dict[str, Any]]: ...

    def delete_source(self, source_id: str) -> int: ...


# ── JSON хранилище (fallback) ───────────────────────────────────────


class JsonRagStore:
    """JSON-файл хранилище с ключевым поиском по пересечению токенов."""

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

    def add_chunks(self, source_id: str, filename: str, chunks: list[str]) -> int:
        count = 0
        for i, chunk in enumerate(chunks):
            entry = {
                "id": uuid.uuid4().hex,
                "source_id": source_id,
                "filename": filename,
                "chunk_index": i,
                "text": chunk,
                "tokens": list(_tokens(chunk)),
            }
            self._data.append(entry)
            count += 1
        self._save()
        return count

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        wanted = _tokens(query)
        if not wanted:
            return []
        scored: list[tuple[int, dict[str, Any]]] = []
        for entry in self._data:
            entry_tokens = set(entry.get("tokens", []))
            score = len(wanted & entry_tokens)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"text": e["text"], "filename": e["filename"], "chunk_index": e["chunk_index"]}
            for _, e in scored[:top_k]
        ]

    def list_sources(self) -> list[dict[str, Any]]:
        sources: dict[str, dict[str, Any]] = {}
        for entry in self._data:
            sid = entry["source_id"]
            if sid not in sources:
                sources[sid] = {"source_id": sid, "filename": entry["filename"], "chunks": 0}
            sources[sid]["chunks"] += 1
        return list(sources.values())

    def delete_source(self, source_id: str) -> int:
        before = len(self._data)
        self._data = [e for e in self._data if e["source_id"] != source_id]
        deleted = before - len(self._data)
        if deleted:
            self._save()
        return deleted


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

    def add_chunks(self, source_id: str, filename: str, chunks: list[str]) -> int:
        if not chunks:
            return 0
        ids = [f"{source_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {"source_id": source_id, "filename": filename, "chunk_index": i}
            for i in range(len(chunks))
        ]
        self._delete_chunks(source_id)
        self._collection.add(ids=ids, documents=chunks, metadatas=metadatas)
        self._sources[source_id] = {"filename": filename, "chunks": len(chunks)}
        self._save_sources()
        return len(chunks)

    def _delete_chunks(self, source_id: str) -> None:
        try:
            existing = self._collection.get(where={"source_id": source_id})
            if existing and existing.get("ids"):
                self._collection.delete(ids=existing["ids"])
        except Exception:
            pass

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        count = self._collection.count()
        if count == 0:
            return []
        actual_k = min(top_k, count)
        result = self._collection.query(query_texts=[query], n_results=actual_k)
        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        results = []
        for doc, meta in zip(documents[0], metadatas[0]):
            results.append({
                "text": str(doc),
                "filename": meta.get("filename", "?"),
                "chunk_index": meta.get("chunk_index", 0),
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

    def ingest_file(self, file_path: str) -> str:
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
        count = self.store.add_chunks(source_id, p.name, chunks)
        return f"Загружен {p.name}: {count} фрагментов ({len(text)} символов), сэр."

    def ingest_directory(self, directory: str = "") -> str:
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
                count = self.store.add_chunks(source_id, f.name, chunks)
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

    def search(self, query: str, top_k: int = 0) -> str:
        """Ищет релевантные фрагменты по запросу."""
        if not query.strip():
            return "Укажите поисковый запрос, сэр."
        k = top_k if top_k > 0 else self.config.top_k
        results = self.store.search(query, k)
        if not results:
            return f"По запросу '{query}' ничего не найдено, сэр."
        lines = [f"Найдено {len(results)} фрагментов по '{query}':"]
        for r in results:
            fname = r.get("filename", "?")
            text = r["text"][:300]
            lines.append(f"  [{fname}] {text}...")
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
            lines.append(f"  {fname} -- {chunks} фрагментов")
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


# ── Навыки ──────────────────────────────────────────────────────────


def build_skills(config: RagConfig) -> tuple[list[Skill], RagEngine]:
    """Создаёт RAG навыки и движок."""
    engine = RagEngine(config)
    skills = [
        Skill(
            name="rag_ingest",
            description=(
                "Загрузить документ в базу знаний RAG. "
                "Поддерживаются TXT, MD, PDF, DOCX. "
                "Если указать directory -- загрузит все документы из папки."
            ),
            parameters=object_schema(
                {
                    "file_path": {"type": "string", "description": "Путь к файлу документа"},
                    "directory": {"type": "string", "description": "Путь к папке с документами (вместо file_path)"},
                },
            ),
            handler=lambda file_path="", directory="": (
                engine.ingest_directory(directory)
                if directory
                else engine.ingest_file(file_path)
                if file_path
                else "Укажите file_path или directory, сэр."
            ),
        ),
        Skill(
            name="rag_search",
            description=(
                "Найти фрагменты в загруженных документах по смысловому запросу. "
                "Используй когда нужно найти конкретную информацию в документах."
            ),
            parameters=object_schema(
                {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "top_k": {"type": "integer", "description": "Сколько фрагментов вернуть"},
                },
                required=["query"],
            ),
            handler=lambda query, top_k=0: engine.search(query, top_k),
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
    ]
    return skills, engine

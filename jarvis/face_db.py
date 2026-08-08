"""База данных лиц: хранение, обучение, распознавание.

Использует face_recognition (dlib) для 128-мерных эмбеддингов.
Хранение: ~/.jarvis/faces/
  - faces.json     -- имена + пути к файлам эмбеддингов
  - encodings/     -- .npy файлы с векторами

Интеграция с профилями: лицо -> профиль Джарвиса.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

FACES_DIR = Path.home() / ".jarvis" / "faces"
FACES_DB = FACES_DIR / "faces.json"
ENCODINGS_DIR = FACES_DIR / "encodings"

# Порог совпадения (0.0 = идеально, 0.6 = мягкий).
DEFAULT_TOLERANCE = 0.5


def _ensure_dirs() -> None:
    FACES_DIR.mkdir(parents=True, exist_ok=True)
    ENCODINGS_DIR.mkdir(parents=True, exist_ok=True)


def _load_db() -> dict[str, dict[str, Any]]:
    """Загружает JSON-базу лиц."""
    if not FACES_DB.is_file():
        return {}
    try:
        data = json.loads(FACES_DB.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        log.warning("База лиц повреждена, начинаю заново")
        return {}


def _save_db(db: dict[str, dict[str, Any]]) -> None:
    """Сохраняет JSON-базу лиц."""
    try:
        _ensure_dirs()
        FACES_DB.write_text(
            json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError:
        log.exception("Не удалось сохранить базу лиц")


def get_encoding(frame: np.ndarray) -> np.ndarray | None:
    """Извлекает 128-мерный эмбеддинг лица из кадра.

    Возвращает None если лицо не найдено или библиотека недоступна.
    """
    try:
        import face_recognition  # type: ignore[import-not-found]
    except ImportError:
        log.warning("face_recognition не установлен")
        return None
    try:
        # Меняем BGR (OpenCV) -> RGB (face_recognition)
        rgb = frame[:, :, ::-1] if frame.ndim == 3 and frame.shape[2] == 3 else frame
        encodings = face_recognition.face_encodings(rgb)
        if not encodings:
            return None
        return encodings[0]
    except Exception:
        log.exception("Ошибка извлечения эмбеддинга")
        return None


def capture_frame(camera_index: int = 0) -> np.ndarray | None:
    """Захватывает один кадр с веб-камеры."""
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        log.warning("OpenCV не установлен")
        return None
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None
    try:
        ret, frame = cap.read()
        return frame if ret and frame is not None else None
    finally:
        cap.release()


def add_face(name: str, camera_index: int = 0, num_samples: int = 3) -> str:
    """Обучает на новом лице: делает несколько снимков, сохраняет средний эмбеддинг.

    Args:
        name: Имя человека.
        camera_index: Индекс камеры.
        num_samples: Сколько снимков для усреднения.

    Returns:
        Сообщение о результате.
    """
    try:
        import face_recognition  # type: ignore[import-not-found]
    except ImportError:
        return ("Библиотека face_recognition не установлена. "
                "Установите: pip install face_recognition")

    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return "OpenCV не установлен. Установите: pip install opencv-python"

    name = name.strip().title()
    if not name or len(name) < 2:
        return "Имя слишком короткое, нужно минимум 2 символа."

    _ensure_dirs()
    db = _load_db()

    encodings_collected: list[np.ndarray] = []
    for i in range(num_samples):
        frame = capture_frame(camera_index)
        if frame is None:
            return "Не удалось открыть камеру."
        enc = get_encoding(frame)
        if enc is not None:
            encodings_collected.append(enc)
        if i < num_samples - 1:
            import time
            time.sleep(0.5)  # пауза между снимками

    if not encodings_collected:
        return "Лицо не обнаружено на камере. Убедитесь что хорошо освещено."

    # Усредняем эмбеддинги для надёжности
    mean_encoding = np.mean(encodings_collected, axis=0)
    encoding_id = f"{name.lower()}_{len(encodings_collected)}"
    encoding_path = ENCODINGS_DIR / f"{encoding_id}.npy"
    np.save(str(encoding_path), mean_encoding)

    # Обновляем базу
    if name not in db:
        db[name] = {"encodings": [], "profile": "", "photo": ""}
    db[name]["encodings"].append(str(encoding_path))
    _save_db(db)

    return (
        f"Лицо {name} сохранено ({len(encodings_collected)} снимков). "
        f"Всего образцов: {len(db[name]['encodings'])}."
    )


def remove_face(name: str) -> str:
    """Удаляет лицо из базы."""
    name = name.strip().title()
    db = _load_db()
    if name not in db:
        return f"Лицо {name} не найдено в базе."

    # Удаляем файлы эмбеддингов
    for enc_path in db[name].get("encodings", []):
        try:
            Path(enc_path).unlink(missing_ok=True)
        except OSError:
            pass
    del db[name]
    _save_db(db)
    return f"Лицо {name} удалено из базы."


def recognize_face(
    camera_index: int = 0,
    tolerance: float = DEFAULT_TOLERANCE,
) -> tuple[str | None, float]:
    """Распознаёт лицо перед камерой.

    Returns:
        (имя, расстояние) или (None, 0.0) если не распознано.
    """
    try:
        import face_recognition  # type: ignore[import-not-found]
    except ImportError:
        return None, 0.0

    frame = capture_frame(camera_index)
    if frame is None:
        return None, 0.0

    encoding = get_encoding(frame)
    if encoding is None:
        return None, 0.0

    db = _load_db()
    if not db:
        return None, 0.0

    best_name: str | None = None
    best_distance = float("inf")

    for name, data in db.items():
        for enc_path_str in data.get("encodings", []):
            enc_path = Path(enc_path_str)
            if not enc_path.is_file():
                continue
            try:
                stored = np.load(str(enc_path))
                dist = float(np.linalg.norm(encoding - stored))
                if dist < best_distance:
                    best_distance = dist
                    best_name = name
            except Exception:
                log.debug("Ошибка загрузки эмбеддинга: %s", enc_path)

    if best_name is not None and best_distance <= tolerance:
        return best_name, best_distance
    return None, best_distance


def list_faces() -> list[dict[str, Any]]:
    """Возвращает список всех известных лиц."""
    db = _load_db()
    result = []
    for name, data in db.items():
        result.append({
            "name": name,
            "samples": len(data.get("encodings", [])),
            "profile": data.get("profile", ""),
        })
    return sorted(result, key=lambda x: x["name"])


def set_face_profile(name: str, profile_id: str) -> str:
    """Привязывает профиль Джарвиса к лицу."""
    name = name.strip().title()
    db = _load_db()
    if name not in db:
        return f"Лицо {name} не найдено. Сначала добавьте лицо."
    db[name]["profile"] = profile_id
    _save_db(db)
    return f"Лицу {name} привязан профиль {profile_id}."


def get_face_profile(name: str) -> str | None:
    """Возвращает привязанный профиль для лица."""
    db = _load_db()
    data = db.get(name.strip().title())
    if data:
        return data.get("profile") or None
    return None


def recognize_and_greet(
    camera_index: int = 0,
    tolerance: float = DEFAULT_TOLERANCE,
) -> str:
    """Распознаёт лицо и возвращает приветствие по имени."""
    name, distance = recognize_face(camera_index, tolerance)
    if name is None:
        return "Лицо не распознано."
    return f"Привет, {name}! (уверенность: {1 - distance:.0%})"
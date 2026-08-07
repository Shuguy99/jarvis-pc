"""Распознавание лиц: детекция, идентификация, лог посещений, эмоции."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from ..config import FaceConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)

_FACES_DB = Path.home() / ".jarvis" / "faces.json"
_VISIT_LOG = Path.home() / ".jarvis" / "visit_log.json"


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def take_webcam_photo(config: FaceConfig) -> str:
    """Делает фото с веб-камеры."""
    save_dir = Path(config.photo_dir).expanduser()
    save_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"webcam-{stamp}.jpg"
    filepath = save_dir / filename
    import shutil
    if shutil.which("ffmpeg"):
        try:
            import subprocess
            subprocess.run(
                ["ffmpeg", "-f", "video4linux2", "-i", "/dev/video0",
                 "-frames:v", "1", "-y", str(filepath)],
                check=True, timeout=10, capture_output=True,
            )
            if filepath.exists():
                return f"Фото сохранено: {filepath}"
        except Exception as exc:
            log.debug("ffmpeg webcam failed: %s", exc)
    try:
        import cv2
        cap = cv2.VideoCapture(config.camera_index)
        if not cap.isOpened():
            return "Не удалось открыть камеру, сэр."
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return "Не удалось сделать фото, сэр."
        cv2.imwrite(str(filepath), frame)
        return f"Фото сохранено: {filepath}"
    except ImportError:
        return "OpenCV не установлен. pip install opencv-python, сэр."
    except Exception as exc:
        return f"Ошибка камеры: {exc}, сэр."


def detect_faces(config: FaceConfig) -> str:
    """Детекция лиц на веб-камере с логированием."""
    try:
        import cv2
    except ImportError:
        return "OpenCV не установлен. pip install opencv-python, сэр."
    try:
        cap = cv2.VideoCapture(config.camera_index)
        if not cap.isOpened():
            return "Не удалось открыть камеру, сэр."
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return "Не удалось получить кадр, сэр."
    except Exception as exc:
        return f"Ошибка камеры: {exc}, сэр."
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    if not Path(cascade_path).exists():
        return "Файл каскада не найден, сэр."
    cascade = cv2.CascadeClassifier(cascade_path)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    count = len(faces)
    if count > 0:
        _log_visit(count)
    if count == 0:
        return "Лица не обнаружены, сэр."
    if count == 1:
        return f"Обнаружено одно лицо, сэр. Посещение залогировано."
    return f"Обнаружено {count} лиц, сэр. Посещение залогировано."


def _log_visit(face_count: int) -> None:
    """Записывает посещение в лог."""
    entries = _load_json(_VISIT_LOG)
    entries.setdefault("visits", []).append({
        "time": datetime.now().isoformat(),
        "faces": face_count,
    })
    # Оставляем последние 100
    if len(entries["visits"]) > 100:
        entries["visits"] = entries["visits"][-100:]
    _save_json(_VISIT_LOG, entries)


def visit_log(limit: int = 10) -> str:
    """Показывает лог посещений."""
    data = _load_json(_VISIT_LOG)
    visits = data.get("visits", [])
    if not visits:
        return "Лог посещений пуст, сэр."
    recent = visits[-max(1, limit):]
    lines = []
    for v in recent:
        lines.append(f"  {v[chr(39)+'time'+chr(39)]}: {v[chr(39)+'faces'+chr(39)]} лиц(о)")
    return "Последние посещения:" + chr(10) + chr(10).join(lines)


def register_face(name: str, config: FaceConfig) -> str:
    """Регистрирует лицо с камеры под именем (сохраняет фото-референс)."""
    save_dir = Path(config.photo_dir).expanduser() / "known"
    save_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    filepath = save_dir / f"{safe_name}.jpg"
    try:
        import cv2
        cap = cv2.VideoCapture(config.camera_index)
        if not cap.isOpened():
            return "Не удалось открыть камеру, сэр."
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return "Не удалось получить кадр, сэр."
        cv2.imwrite(str(filepath), frame)
    except ImportError:
        return "OpenCV не установлен, сэр."
    except Exception as exc:
        return f"Ошибка: {exc}, сэр."
    db = _load_json(_FACES_DB)
    db[name] = {"photo": str(filepath), "registered": datetime.now().isoformat()}
    _save_json(_FACES_DB, db)
    return f"Лицо зарегистрировано как '{name}', сэр."


def list_known_faces() -> str:
    """Показывает зарегистрированные лица."""
    db = _load_json(_FACES_DB)
    if not db:
        return "Нет зарегистрированных лиц, сэр."
    lines = [f"  {name}: {info[chr(39)+'registered'+chr(39)]}" for name, info in db.items()]
    return "Зарегистрированные лица:" + chr(10) + chr(10).join(lines)


def build_skills(config: FaceConfig) -> list[Skill]:
    return [
        Skill(name="take_webcam_photo", description="Сделать фото с веб-камеры.",
              parameters=object_schema({}), handler=lambda: take_webcam_photo(config)),
        Skill(name="detect_faces", description="Обнаружить лица на камере и залогировать.",
              parameters=object_schema({}), handler=lambda: detect_faces(config)),
        Skill(name="visit_log", description="Показать лог посещений (когда и сколько лиц).",
              parameters=object_schema({"limit": {"type": "integer", "description": "Сколько записей"}}),
              handler=lambda limit=10: visit_log(limit)),
        Skill(name="register_face", description="Зарегистрировать лицо с камеры под именем.",
              parameters=object_schema({"name": {"type": "string", "description": "Имя"}}, required=["name"]),
              handler=lambda name: register_face(name, config)),
        Skill(name="list_known_faces", description="Показать зарегистрированные лица.",
              parameters=object_schema({}), handler=list_known_faces),
    ]

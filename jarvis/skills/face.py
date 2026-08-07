"""Распознавание лиц: детекция, идентификация, эмоции, лог посещений.

Уровни функциональности (зависят от установленных пакетов):
- Базовый (opencv-python): детекция лиц, фото, лог
- Средний (+opencv-contrib-python): идентификация через LBPH
- Продвинутый (+deepface): анализ эмоций
"""

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
_UNKNOWN_DIR = Path.home() / ".jarvis" / "unknown_faces"


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


def _get_cascade():
    """Загружает Haar-каскад для детекции лиц."""
    import cv2
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    if not Path(cascade_path).exists():
        return None
    return cv2.CascadeClassifier(cascade_path)


def _capture_frame(camera_index: int):
    """Делает один кадр с веб-камеры. Возвращает (frame, error_msg)."""
    import cv2
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        return None, "Не удалось открыть камеру, сэр."
    try:
        ret, frame = cap.read()
    finally:
        cap.release()
    if not ret or frame is None:
        return None, "Не удалось получить кадр, сэр."
    return frame, None


def _detect_face_regions(frame) -> list:
    """Детекция лиц, возвращает список прямоугольников (x,y,w,h)."""
    import cv2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade = _get_cascade()
    if cascade is None:
        return []
    return cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))


def take_webcam_photo(config: FaceConfig) -> str:
    """Делает фото с веб-камеры."""
    save_dir = Path(config.photo_dir).expanduser()
    save_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filepath = save_dir / f"webcam-{stamp}.jpg"
    import shutil
    if shutil.which("ffmpeg"):
        try:
            import subprocess
            subprocess.run(
                ["ffmpeg", "-f", "video4linux2", "-i", f"/dev/video{config.camera_index}",
                 "-frames:v", "1", "-y", str(filepath)],
                check=True, timeout=10, capture_output=True,
            )
            if filepath.exists():
                return f"Фото сохранено: {filepath}"
        except Exception as exc:
            log.debug("ffmpeg webcam failed: %s", exc)
    try:
        import cv2
    except ImportError:
        return "OpenCV не установлен. pip install opencv-python, сэр."
    frame, err = _capture_frame(config.camera_index)
    if err:
        return err
    cv2.imwrite(str(filepath), frame)
    return f"Фото сохранено: {filepath}"


def detect_faces(config: FaceConfig) -> str:
    """Детекция лиц на веб-камере с логированием."""
    try:
        import cv2
    except ImportError:
        return "OpenCV не установлен. pip install opencv-python, сэр."
    frame, err = _capture_frame(config.camera_index)
    if err:
        return err
    faces = _detect_face_regions(frame)
    count = len(faces)
    if count > 0:
        _log_visit(count)
        _save_detection_photo(frame, faces, config)
    if count == 0:
        return "Лица не обнаружены, сэр."
    if count == 1:
        return "Обнаружено одно лицо, сэр. Посещение залогировано."
    return f"Обнаружено {count} лиц, сэр. Посещение залогировано."


def _save_detection_photo(frame, faces, config: FaceConfig) -> None:
    """Сохраняет фото с прямоугольниками вокруг лиц."""
    import cv2
    save_dir = Path(config.photo_dir).expanduser()
    save_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    annotated = frame.copy()
    for x, y, w, h in faces:
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (0, 255, 0), 2)
    filepath = save_dir / f"detection-{stamp}.jpg"
    cv2.imwrite(str(filepath), annotated)
    log.debug("Фото детекции сохранено: %s", filepath)


def _get_recognizer():
    """Создаёт и обучает LBPH распознаватель из известных лиц."""
    import cv2
    import numpy
    db = _load_json(_FACES_DB)
    if not db:
        return None, []
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    labels = []
    label_ids = []
    for idx, (name, info) in enumerate(db.items()):
        photo_path = Path(info.get("photo", ""))
        if not photo_path.is_file():
            continue
        img = cv2.imread(str(photo_path), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        cascade = _get_cascade()
        if cascade is not None:
            detected = cascade.detectMultiScale(img, scaleFactor=1.1, minNeighbors=3, minSize=(60, 60))
            if len(detected) > 0:
                x, y, w, h = detected[0]
                img = img[y:y+h, x:x+w]
        if img.size == 0:
            continue
        img = cv2.resize(img, (200, 200))
        labels.append(img)
        label_ids.append(idx)
    if not labels:
        return None, []
    recognizer.train(labels, numpy.array(label_ids))
    name_list = list(db.keys())
    return recognizer, name_list


def identify_face(config: FaceConfig) -> str:
    """Идентифицирует лицо на камере по базе зарегистрированных."""
    try:
        import cv2
        import numpy
    except ImportError:
        return "Нужен opencv-contrib-python для идентификации, сэр."
    frame, err = _capture_frame(config.camera_index)
    if err:
        return err
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = _detect_face_regions(frame)
    if len(faces) == 0:
        return "Лица не обнаружены, сэр."
    db = _load_json(_FACES_DB)
    if not db:
        return "Нет зарегистрированных лиц. Сначала вызовите register_face, сэр."
    recognizer, name_list = _get_recognizer()
    if recognizer is None:
        return "Не удалось обучить распознаватель. Проверьте фото в базе, сэр."
    results = []
    for x, y, w, h in faces:
        roi = cv2.resize(gray[y:y+h, x:x+w], (200, 200))
        label_id, confidence = recognizer.predict(roi)
        confidence_pct = 100 - confidence
        if confidence_pct > 40 and label_id < len(name_list):
            name = name_list[label_id]
            results.append(f"{name} (уверенность {confidence_pct:.0f}%)")
        else:
            results.append("неизвестное лицо")
            _save_unknown_face(frame[y:y+h, x:x+w])
    return "Обнаружены: " + ", ".join(results) + ", сэр."


def _save_unknown_face(face_crop) -> None:
    """Сохраняет фото незнакомого лица."""
    try:
        import cv2
        _UNKNOWN_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filepath = _UNKNOWN_DIR / f"unknown-{stamp}.jpg"
        cv2.imwrite(str(filepath), face_crop)
        log.info("Незнакомое лицо сохранено: %s", filepath)
    except Exception:
        pass


def detect_emotions(config: FaceConfig) -> str:
    """Анализ эмоций на лицах через DeepFace."""
    try:
        from deepface import DeepFace
    except ImportError:
        return "DeepFace не установлен. pip install deepface, сэр."
    frame, err = _capture_frame(config.camera_index)
    if err:
        return err
    faces = _detect_face_regions(frame)
    if len(faces) == 0:
        return "Лица не обнаружены, сэр."
    results = []
    for i, (x, y, w, h) in enumerate(faces):
        face_roi = frame[y:y+h, x:x+w]
        try:
            analysis = DeepFace.analyze(face_roi, actions=["emotion"], enforce_detection=False)
            if isinstance(analysis, list):
                analysis = analysis[0]
            emotions = analysis.get("dominant_emotion", "неизвестно")
            all_emotions = analysis.get("emotion", {})
            top3 = sorted(all_emotions.items(), key=lambda e: e[1], reverse=True)[:3]
            parts = [f"{em} {val:.0f}%" for em, val in top3]
            results.append(f"Лицо {i+1}: {emotions} ({', '.join(parts)})")
        except Exception as exc:
            results.append(f"Лицо {i+1}: ошибка анализа ({exc})")
    return "Эмоции: " + "; ".join(results) + ", сэр."


def _log_visit(face_count: int, identified: str = "") -> None:
    """Записывает посещение в лог."""
    entries = _load_json(_VISIT_LOG)
    visit = {
        "time": datetime.now().isoformat(),
        "faces": face_count,
    }
    if identified:
        visit["identified"] = identified
    entries.setdefault("visits", []).append(visit)
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
        time_str = v.get("time", "?")
        count = v.get("faces", 0)
        identified = v.get("identified", "")
        entry = f"  {time_str}: {count} лиц(о)"
        if identified:
            entry += f" ({identified})"
        lines.append(entry)
    return "Последние посещения:" + chr(10) + chr(10).join(lines)


def register_face(name: str, config: FaceConfig) -> str:
    """Регистрирует лицо с камеры под именем."""
    try:
        import cv2
    except ImportError:
        return "OpenCV не установлен, сэр."
    save_dir = Path(config.photo_dir).expanduser() / "known"
    save_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    filepath = save_dir / f"{safe_name}.jpg"
    frame, err = _capture_frame(config.camera_index)
    if err:
        return err
    faces = _detect_face_regions(frame)
    if len(faces) > 0:
        x, y, w, h = faces[0]
        face_crop = frame[y:y+h, x:x+w]
        cv2.imwrite(str(filepath), face_crop)
    else:
        cv2.imwrite(str(filepath), frame)
    db = _load_json(_FACES_DB)
    db[name] = {"photo": str(filepath), "registered": datetime.now().isoformat()}
    _save_json(_FACES_DB, db)
    return f"Лицо зарегистрировано как '{name}', сэр."


def unregister_face(name: str) -> str:
    """Удаляет лицо из базы."""
    db = _load_json(_FACES_DB)
    if name not in db:
        return f"Лицо '{name}' не найдено, сэр."
    info = db.pop(name)
    _save_json(_FACES_DB, db)
    photo = Path(info.get("photo", ""))
    if photo.is_file():
        try:
            photo.unlink()
        except OSError:
            pass
    return f"Лицо '{name}' удалено из базы, сэр."


def list_known_faces() -> str:
    """Показывает зарегистрированные лица."""
    db = _load_json(_FACES_DB)
    if not db:
        return "Нет зарегистрированных лиц, сэр."
    lines = []
    for name, info in db.items():
        registered = info.get("registered", "?")
        lines.append(f"  {name}: зарегистрирован {registered}")
    return "Зарегистрированные лица:" + chr(10) + chr(10).join(lines)


def build_skills(config: FaceConfig) -> list[Skill]:
    return [
        Skill(name="take_webcam_photo",
              description="Сделать фото с веб-камеры.",
              parameters=object_schema({}),
              handler=lambda: take_webcam_photo(config)),
        Skill(name="detect_faces",
              description="Обнаружить лица на камере и залогировать посещение.",
              parameters=object_schema({}),
              handler=lambda: detect_faces(config)),
        Skill(name="identify_face",
              description="Идентифицировать лицо на камере по базе. Нужен opencv-contrib-python.",
              parameters=object_schema({}),
              handler=lambda: identify_face(config)),
        Skill(name="detect_emotions",
              description="Анализ эмоций на лицах. Нужен deepface.",
              parameters=object_schema({}),
              handler=lambda: detect_emotions(config)),
        Skill(name="visit_log",
              description="Показать лог посещений.",
              parameters=object_schema({"limit": {"type": "integer", "description": "Записей"}}),
              handler=lambda limit=10: visit_log(limit)),
        Skill(name="register_face",
              description="Зарегистрировать лицо с камеры под именем.",
              parameters=object_schema({"name": {"type": "string", "description": "Имя"}},
                                     required=["name"]),
              handler=lambda name: register_face(name, config)),
        Skill(name="unregister_face",
              description="Удалить лицо из базы.",
              parameters=object_schema({"name": {"type": "string", "description": "Имя"}},
                                     required=["name"]),
              handler=unregister_face),
        Skill(name="list_known_faces",
              description="Показать зарегистрированные лица.",
              parameters=object_schema({}),
              handler=list_known_faces),
    ]

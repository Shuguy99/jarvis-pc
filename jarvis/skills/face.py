"""Распознавание лиц: детекция через OpenCV + webcam."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from ..config import FaceConfig
from .registry import Skill, object_schema

log = logging.getLogger(__name__)


def take_webcam_photo(config: FaceConfig) -> str:
    """Делает фото с веб-камеры."""
    save_dir = Path(config.photo_dir).expanduser()
    save_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"webcam-{stamp}.jpg"
    filepath = save_dir / filename

    # Пробуем ffmpeg (надёжно, кроссплатформенно)
    import shutil
    if shutil.which("ffmpeg"):
        try:
            subprocess.run(
                ["ffmpeg", "-f", "video4linux2", "-i", "/dev/video0",
                 "-frames:v", "1", "-y", str(filepath)],
                check=True, timeout=10, capture_output=True,
            )
            if filepath.exists():
                return f"Фото сохранено: {filepath}"
        except Exception as exc:
            log.debug("ffmpeg webcam не удался: %s", exc)

    # Fallback: OpenCV
    try:
        import cv2  # type: ignore[import-not-found]
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
        return "OpenCV не установлен. Установите: pip install opencv-python, сэр."
    except Exception as exc:
        return f"Ошибка камеры: {exc}, сэр."


def detect_faces(config: FaceConfig) -> str:
    """Детекция лиц на фото с веб-камеры."""
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        return "OpenCV не установлен. Установите: pip install opencv-python, сэр."
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

    # Загружаем каскад Хаара
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    if not Path(cascade_path).exists():
        return "Файл каскада не найден, сэр."
    cascade = cv2.CascadeClassifier(cascade_path)

    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
    count = len(faces)
    if count == 0:
        return "Лица не обнаружены, сэр."
    if count == 1:
        return f"Обнаружено одно лицо, сэр."
    return f"Обнаружено {count} лиц, сэр."


def build_skills(config: FaceConfig) -> list[Skill]:
    """Создаёт навыки распознавания лиц."""
    return [
        Skill(
            name="take_webcam_photo",
            description="Сделать фото с веб-камеры и сохранить в файл.",
            parameters=object_schema({}),
            handler=lambda: take_webcam_photo(config),
        ),
        Skill(
            name="detect_faces",
            description="Обнаружить лица на камере (количество лиц).",
            parameters=object_schema({}),
            handler=lambda: detect_faces(config),
        ),
    ]

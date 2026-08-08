"""Распознавание лиц: детекция, обучение, идентификация, привязка к профилям.

Зависимости (опционально):
  pip install opencv-python face_recognition

Голосовые команды:
  "Джарвис, добавь лицо Иван"    — обучение на новом человеке
  "Джарвис, кто перед камерой?"   — распознать и назвать
  "Джарвис, привяжи профиль casual к Ивану"
  "Джарвис, покажи все лица"       — список известных лиц
  "Джарвис, удали лицо Иван"      — удалить из базы
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..config import FaceConfig
from .registry import Skill, object_schema

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)


def _check_deps() -> str | None:
    """Проверяет зависимости. Возвращает ошибку или None."""
    missing = []
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        missing.append("opencv-python")
    try:
        import face_recognition  # type: ignore[import-not-found]
    except ImportError:
        missing.append("face_recognition")
    if missing:
        return (f"Не хватает библиотек: {', '.join(missing)}. "
                f"Установите: pip install {' '.join(missing)}")
    return None


def build_skills(config: FaceConfig) -> list[Skill]:
    """Создаёт навыки распознавания лиц."""
    cam = config.camera_index

    def add_face(name: str = "") -> str:
        """Добавляет новое лицо в базу — делает несколько снимков."""
        if not name:
            return "Укажите имя. Например: добавь лицо Иван."
        err = _check_deps()
        if err:
            return err
        from ..face_db import add_face as _add
        return _add(name, camera_index=cam)

    def recognize_face() -> str:
        """Распознаёт лицо перед камерой."""
        err = _check_deps()
        if err:
            return err
        from ..face_db import recognize_and_greet
        return recognize_and_greet(camera_index=cam)

    def list_faces() -> str:
        """Показывает все зарегистрированные лица."""
        from ..face_db import list_faces as _list
        faces = _list()
        if not faces:
            return 'База лиц пуста. Добавьте лицо: добавь лицо Имя.'
        lines = []
        for f in faces:
            profile_info = f" (профиль: {f['profile']})" if f["profile"] else ""
            lines.append(f"  {f['name']} — {f['samples']} образцов{profile_info}")
        return "Известные лица:\n" + "\n".join(lines)

    def remove_face(name: str = "") -> str:
        """Удаляет лицо из базы."""
        if not name:
            return "Укажите имя для удаления."
        from ..face_db import remove_face as _remove
        return _remove(name)

    def set_face_profile(name: str = "", profile_id: str = "") -> str:
        """Привязывает голосовой профиль Джарвиса к лицу."""
        if not name or not profile_id:
            return "Укажите имя и профиль. Например: привяжи профиль casual к Ивану."
        from ..face_db import set_face_profile as _set
        return _set(name, profile_id)

    def take_webcam_photo() -> str:
        """Делает фото с веб-камеры и сохраняет."""
        from pathlib import Path
        from datetime import datetime
        import shutil

        save_dir = Path(config.photo_dir).expanduser()
        save_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filepath = save_dir / f"webcam-{stamp}.jpg"

        # ffmpeg (надёжно, кроссплатформенно)
        if shutil.which("ffmpeg"):
            import subprocess
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
            cap = cv2.VideoCapture(cam)
            if not cap.isOpened():
                return "Не удалось открыть камеру."
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return "Не удалось сделать фото."
            cv2.imwrite(str(filepath), frame)
            return f"Фото сохранено: {filepath}"
        except ImportError:
            return "OpenCV не установлен. Установите: pip install opencv-python."
        except Exception as exc:
            return f"Ошибка камеры: {exc}."

    def detect_faces_count() -> str:
        """Считает количество лиц перед камерой."""
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError:
            return "OpenCV не установлен."
        try:
            cap = cv2.VideoCapture(cam)
            if not cap.isOpened():
                return "Не удалось открыть камеру."
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return "Не удалось получить кадр."
        except Exception as exc:
            return f"Ошибка камеры: {exc}."

        from pathlib import Path
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        if not Path(cascade_path).exists():
            return "Файл каскада не найден."
        cascade = cv2.CascadeClassifier(cascade_path)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        count = len(faces)
        if count == 0:
            return "Лица не обнаружены."
        if count == 1:
            return "Обнаружено одно лицо."
        return f"Обнаружено {count} лиц."

    return [
        Skill(
            name="add_face",
            description=(
                "Добавить новое лицо в базу для распознавания. "
                "Делает несколько снимков с камеры и сохраняет эмбеддинг."
            ),
            parameters=object_schema(
                {
                    "name": {
                        "type": "string",
                        "description": "Имя человека для добавления",
                    }
                },
                required=["name"],
            ),
            handler=add_face,
        ),
        Skill(
            name="recognize_face",
            description=(
                "Распознать лицо перед камерой и назвать человека. "
                "Сравнивает с базой известных лиц."
            ),
            parameters=object_schema({}),
            handler=recognize_face,
        ),
        Skill(
            name="list_known_faces",
            description="Показать все зарегистрированные в базе лица.",
            parameters=object_schema({}),
            handler=list_faces,
        ),
        Skill(
            name="remove_face",
            description="Удалить лицо из базы распознавания.",
            parameters=object_schema(
                {
                    "name": {
                        "type": "string",
                        "description": "Имя для удаления",
                    }
                },
                required=["name"],
            ),
            handler=remove_face,
        ),
        Skill(
            name="set_face_profile",
            description=(
                "Привязать голосовой профиль Джарвиса к конкретному лицу. "
                "Когда это лицо распознаётся, Джарвис автоматически переключается на его профиль."
            ),
            parameters=object_schema(
                {
                    "name": {
                        "type": "string",
                        "description": "Имя человека из базы лиц",
                    },
                    "profile_id": {
                        "type": "string",
                        "description": "ID профиля: default, casual, strict, pirate, или кастомный",
                    },
                },
                required=["name", "profile_id"],
            ),
            handler=set_face_profile,
        ),
        Skill(
            name="take_webcam_photo",
            description="Сделать фото с веб-камеры и сохранить в файл.",
            parameters=object_schema({}),
            handler=take_webcam_photo,
        ),
        Skill(
            name="detect_faces",
            description="Обнаружить и посчитать лица на камере.",
            parameters=object_schema({}),
            handler=detect_faces_count,
        ),
    ]

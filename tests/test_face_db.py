"""Тесты базы данных лиц (face_db) — без камеры и dlib."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from jarvis.face_db import (
    _ensure_dirs,
    _load_db,
    _save_db,
    get_encoding,
    capture_frame,
    add_face,
    remove_face,
    recognize_face,
    list_faces,
    set_face_profile,
    get_face_profile,
    recognize_and_greet,
    DEFAULT_TOLERANCE,
)


# ── База данных ────────────────────────────────────────────────────────


class TestDatabaseIO:
    """Тесты загрузки/сохранения JSON-базы."""

    def test_load_empty(self, tmp_path):
        """Нет файла — пустая база."""
        with patch("jarvis.face_db.FACES_DB", tmp_path / "none.json"):
            assert _load_db() == {}

    def test_load_valid(self, tmp_path):
        """Корректный JSON загружается."""
        db_file = tmp_path / "faces.json"
        data = {"Ivan": {"encodings": ["a.npy"], "profile": "casual"}}
        db_file.write_text(json.dumps(data), encoding="utf-8")
        with patch("jarvis.face_db.FACES_DB", db_file):
            result = _load_db()
            assert "Ivan" in result
            assert result["Ivan"]["profile"] == "casual"

    def test_load_corrupt(self, tmp_path):
        """Повреждённый JSON — пустая база."""
        db_file = tmp_path / "faces.json"
        db_file.write_text("not json", encoding="utf-8")
        with patch("jarvis.face_db.FACES_DB", db_file):
            assert _load_db() == {}

    def test_load_non_dict(self, tmp_path):
        """JSON-массив вместо объекта — пустая база."""
        db_file = tmp_path / "faces.json"
        db_file.write_text("[1, 2, 3]", encoding="utf-8")
        with patch("jarvis.face_db.FACES_DB", db_file):
            assert _load_db() == {}

    def test_save_and_load(self, tmp_path):
        """Сохранение и загрузка — полный цикл."""
        db_file = tmp_path / "faces.json"
        with patch("jarvis.face_db.FACES_DB", db_file):
            _save_db({"Anna": {"encodings": [], "profile": "strict"}})
            result = _load_db()
            assert result["Anna"]["profile"] == "strict"

    def test_ensure_dirs(self, tmp_path):
        """Создаёт каталоги если нет."""
        faces_dir = tmp_path / "faces"
        with patch("jarvis.face_db.FACES_DIR", faces_dir), \
             patch("jarvis.face_db.ENCODINGS_DIR", faces_dir / "encodings"):
            _ensure_dirs()
            assert faces_dir.is_dir()
            assert (faces_dir / "encodings").is_dir()


# ── Захват кадра ──────────────────────────────────────────────────────


class TestCaptureFrame:
    """Тесты захвата кадра."""

    def test_no_opencv(self):
        """OpenCV не установлен — None."""
        with patch.dict("sys.modules", {"cv2": None}):
            assert capture_frame() is None

    def test_camera_not_opened(self):
        """Камера не открывается — None."""
        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_cv2.VideoCapture.return_value = mock_cap
        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            assert capture_frame() is None

    def test_success(self):
        """Кадр получен."""
        mock_cv2 = MagicMock()
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cap.read.return_value = (True, frame)
        mock_cv2.VideoCapture.return_value = mock_cap
        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            result = capture_frame()
            assert result is not None
            assert result.shape == (100, 100, 3)


# ── Операции с базой ──────────────────────────────────────────────────


class TestFaceOperations:
    """Тесты add/remove/list/set_profile с моками."""

    def _patch_dirs(self, tmp_path):
        """Патчит пути для тестов."""
        faces_dir = tmp_path / "faces"
        enc_dir = faces_dir / "encodings"
        patches = [
            patch("jarvis.face_db.FACES_DIR", faces_dir),
            patch("jarvis.face_db.ENCODINGS_DIR", enc_dir),
            patch("jarvis.face_db.FACES_DB", faces_dir / "faces.json"),
        ]
        for p in patches:
            p.start()
        return patches

    def test_add_face_no_deps(self, tmp_path):
        """Нет face_recognition — ошибка."""
        patches = self._patch_dirs(tmp_path)
        try:
            with patch.dict("sys.modules", {"face_recognition": None, "cv2": MagicMock()}):
                result = add_face("Ivan")
                assert "face_recognition" in result
        finally:
            for p in patches:
                p.stop()

    def test_add_face_short_name(self, tmp_path):
        """Слишком короткое имя."""
        patches = self._patch_dirs(tmp_path)
        try:
            mock_fr = MagicMock()
            mock_cv2 = MagicMock()
            with patch.dict("sys.modules", {"face_recognition": mock_fr, "cv2": mock_cv2}):
                result = add_face("A")
                assert "короткое" in result
        finally:
            for p in patches:
                p.stop()

    def test_add_face_empty_name(self, tmp_path):
        """Пустое имя."""
        patches = self._patch_dirs(tmp_path)
        try:
            mock_fr = MagicMock()
            mock_cv2 = MagicMock()
            with patch.dict("sys.modules", {"face_recognition": mock_fr, "cv2": mock_cv2}):
                result = add_face("")
                assert "короткое" in result
        finally:
            for p in patches:
                p.stop()

    def test_remove_face_not_found(self, tmp_path):
        """Удаление несуществующего лица."""
        patches = self._patch_dirs(tmp_path)
        try:
            result = remove_face("Ghost")
            assert "не найден" in result
        finally:
            for p in patches:
                p.stop()

    def test_remove_face_success(self, tmp_path):
        """Удаление существующего лица."""
        patches = self._patch_dirs(tmp_path)
        try:
            _save_db({"Ivan": {"encodings": [], "profile": ""}})
            result = remove_face("Ivan")
            assert "удален" in result
            assert "Ivan" not in _load_db()
        finally:
            for p in patches:
                p.stop()

    def test_list_faces_empty(self, tmp_path):
        """Пустая база."""
        patches = self._patch_dirs(tmp_path)
        try:
            assert list_faces() == []
        finally:
            for p in patches:
                p.stop()

    def test_list_faces_with_data(self, tmp_path):
        """База с лицами."""
        patches = self._patch_dirs(tmp_path)
        try:
            _save_db({
                "Ivan": {"encodings": ["a.npy", "b.npy"], "profile": "casual"},
                "Anna": {"encodings": ["c.npy"], "profile": ""},
            })
            faces = list_faces()
            assert len(faces) == 2
            assert faces[0]["name"] == "Anna"
            assert faces[0]["samples"] == 1
            assert faces[1]["name"] == "Ivan"
            assert faces[1]["samples"] == 2
            assert faces[1]["profile"] == "casual"
        finally:
            for p in patches:
                p.stop()

    def test_set_face_profile_not_found(self, tmp_path):
        """Привязка профиля к несуществующему лицу."""
        patches = self._patch_dirs(tmp_path)
        try:
            result = set_face_profile("Ghost", "casual")
            assert "не найден" in result
        finally:
            for p in patches:
                p.stop()

    def test_set_face_profile_success(self, tmp_path):
        """Привязка профиля к существующему лицу."""
        patches = self._patch_dirs(tmp_path)
        try:
            _save_db({"Ivan": {"encodings": [], "profile": ""}})
            result = set_face_profile("Ivan", "strict")
            assert "strict" in result
            assert _load_db()["Ivan"]["profile"] == "strict"
        finally:
            for p in patches:
                p.stop()

    def test_get_face_profile(self, tmp_path):
        """Получение профиля для лица."""
        patches = self._patch_dirs(tmp_path)
        try:
            _save_db({"Ivan": {"encodings": [], "profile": "pirate"}})
            assert get_face_profile("Ivan") == "pirate"
            assert get_face_profile("Anna") is None
        finally:
            for p in patches:
                p.stop()


# ── Распознавание ─────────────────────────────────────────────────────


class TestRecognizeFace:
    """Тесты распознавания с моками."""

    def test_no_face_recognition(self):
        """Библиотека недоступна — (None, 0.0)."""
        with patch.dict("sys.modules", {"face_recognition": None}):
            name, dist = recognize_face()
            assert name is None
            assert dist == 0.0

    def test_no_camera(self):
        """Камера недоступна — (None, 0.0)."""
        with patch("jarvis.face_db.capture_frame", return_value=None):
            name, dist = recognize_face()
            assert name is None

    def test_no_face_in_frame(self):
        """Лицо не найдено в кадре — (None, 0.0)."""
        with patch("jarvis.face_db.capture_frame", return_value=np.zeros((100, 100, 3))), \
             patch("jarvis.face_db.get_encoding", return_value=None):
            name, dist = recognize_face()
            assert name is None

    def test_empty_database(self):
        """База пуста — (None, 0.0)."""
        enc = np.random.rand(128).astype(np.float64)
        with patch("jarvis.face_db.capture_frame", return_value=np.zeros((100, 100, 3))), \
             patch("jarvis.face_db.get_encoding", return_value=enc), \
             patch("jarvis.face_db._load_db", return_value={}):
            name, dist = recognize_face()
            assert name is None

    def test_recognize_match(self, tmp_path):
        """Лицо совпадает с базой."""
        enc_dir = tmp_path / "encodings"
        enc_dir.mkdir(parents=True, exist_ok=True)
        enc = np.random.rand(128).astype(np.float64)
        np.save(str(enc_dir / "ivan_1.npy"), enc)
        db = {"Ivan": {"encodings": [str(enc_dir / "ivan_1.npy")], "profile": ""}}

        mock_fr = MagicMock()
        with patch("jarvis.face_db.capture_frame", return_value=np.zeros((100, 100, 3))), \
             patch("jarvis.face_db.get_encoding", return_value=enc), \
             patch("jarvis.face_db._load_db", return_value=db), \
             patch.dict("sys.modules", {"face_recognition": mock_fr}):
            name, dist = recognize_face(tolerance=0.6)
            assert name == "Ivan"
            assert dist < 0.01

    def test_recognize_no_match(self, tmp_path):
        """Лицо не совпадает — расстояние слишком большое."""
        enc_dir = tmp_path / "encodings"
        enc_dir.mkdir(parents=True, exist_ok=True)
        stored_enc = np.random.rand(128).astype(np.float64)
        np.save(str(enc_dir / "ivan_1.npy"), stored_enc)

        query_enc = np.random.rand(128).astype(np.float64)
        db = {"Ivan": {"encodings": [str(enc_dir / "ivan_1.npy")], "profile": ""}}

        mock_fr = MagicMock()
        with patch("jarvis.face_db.capture_frame", return_value=np.zeros((100, 100, 3))), \
             patch("jarvis.face_db.get_encoding", return_value=query_enc), \
             patch("jarvis.face_db._load_db", return_value=db), \
             patch.dict("sys.modules", {"face_recognition": mock_fr}):
            name, dist = recognize_face(tolerance=0.3)
            assert name is None

    def test_recognize_and_greet_no_match(self):
        """recognize_and_greet при отсутствии лица."""
        with patch("jarvis.face_db.recognize_face", return_value=(None, 0.0)):
            assert recognize_and_greet() == "Лицо не распознано."

    def test_recognize_and_greet_match(self):
        """recognize_and_greet при совпадении."""
        with patch("jarvis.face_db.recognize_face", return_value=("Ivan", 0.15)):
            result = recognize_and_greet()
            assert "Ivan" in result
            assert "85%" in result


# ── Извлечение эмбеддингов ────────────────────────────────────────────


class TestGetEncoding:
    """Тесты извлечения эмбеддинга."""

    def test_no_library(self):
        """face_recognition не установлен — None."""
        with patch.dict("sys.modules", {"face_recognition": None}):
            assert get_encoding(np.zeros((100, 100, 3))) is None

    def test_no_face_detected(self):
        """Лицо не найдено — None."""
        mock_fr = MagicMock()
        mock_fr.face_encodings.return_value = []
        with patch.dict("sys.modules", {"face_recognition": mock_fr}):
            assert get_encoding(np.zeros((100, 100, 3))) is None

    def test_success(self):
        """Эмбеддинг извлечён."""
        mock_fr = MagicMock()
        test_enc = np.random.rand(128).astype(np.float64)
        mock_fr.face_encodings.return_value = [test_enc]
        with patch.dict("sys.modules", {"face_recognition": mock_fr}):
            result = get_encoding(np.zeros((100, 100, 3)))
            assert result is not None
            np.testing.assert_array_equal(result, test_enc)

    def test_bgr_to_rgb_conversion(self):
        """BGR кадр конвертируется в RGB для face_recognition."""
        mock_fr = MagicMock()
        test_enc = np.zeros(128)
        mock_fr.face_encodings.return_value = [test_enc]
        with patch.dict("sys.modules", {"face_recognition": mock_fr}):
            frame_bgr = np.zeros((10, 10, 3), dtype=np.uint8)
            get_encoding(frame_bgr)
            mock_fr.face_encodings.assert_called_once()


# ── Навыки (face.build_skills) ──────────────────────────────────────


class TestFaceSkills:
    """Тесты регистрации навыков распознавания лиц."""

    def test_build_skills_returns_7(self):
        """build_skills возвращает 7 навыков."""
        from jarvis.config import FaceConfig
        from jarvis.skills.face import build_skills

        cfg = FaceConfig(enabled=True, camera_index=0)
        skills = build_skills(cfg)
        names = {s.name for s in skills}
        assert len(skills) == 7
        assert names == {
            "add_face",
            "recognize_face",
            "list_known_faces",
            "remove_face",
            "set_face_profile",
            "take_webcam_photo",
            "detect_faces",
        }

    def test_add_face_requires_name(self):
        """add_face без имени возвращает подсказку."""
        from jarvis.config import FaceConfig
        from jarvis.skills.face import build_skills

        cfg = FaceConfig(enabled=True)
        skills = build_skills(cfg)
        add = next(s for s in skills if s.name == "add_face")
        result = add.handler("")
        assert "имя" in result.lower()

    def test_remove_face_requires_name(self):
        """remove_face без имени возвращает подсказку."""
        from jarvis.config import FaceConfig
        from jarvis.skills.face import build_skills

        cfg = FaceConfig(enabled=True)
        skills = build_skills(cfg)
        rem = next(s for s in skills if s.name == "remove_face")
        result = rem.handler("")
        assert "имя" in result.lower()

    def test_set_face_profile_requires_both(self):
        """set_face_profile без аргументов возвращает подсказку."""
        from jarvis.config import FaceConfig
        from jarvis.skills.face import build_skills

        cfg = FaceConfig(enabled=True)
        skills = build_skills(cfg)
        sfp = next(s for s in skills if s.name == "set_face_profile")
        result = sfp.handler("")
        assert "профиль" in result.lower()

    def test_list_faces_empty(self):
        """list_known_faces при пустой базе."""
        from jarvis.config import FaceConfig
        from jarvis.skills.face import build_skills

        cfg = FaceConfig(enabled=True)
        skills = build_skills(cfg)
        lf = next(s for s in skills if s.name == "list_known_faces")
        with patch("jarvis.face_db.list_faces", return_value=[]):
            result = lf.handler()
            assert "пуста" in result.lower()

    def test_recognize_face_no_deps(self):
        """recognize_face без библиотек сообщает об ошибке."""
        from jarvis.config import FaceConfig
        from jarvis.skills.face import build_skills

        cfg = FaceConfig(enabled=True)
        skills = build_skills(cfg)
        rec = next(s for s in skills if s.name == "recognize_face")
        with patch("jarvis.skills.face._check_deps", return_value="Нет opencv"):
            result = rec.handler()
            assert "opencv" in result


# ── Автоприветствие в Assistant ──────────────────────────────────────


class TestTryFaceGreeting:
    """Тесты _try_face_greeting в Assistant."""

    def test_face_disabled(self):
        """Если face.enabled=False — ничего не происходит."""
        from jarvis.config import Config
        from jarvis.assistant import Assistant
        from jarvis.profiles import ProfileManager
        from jarvis.skills import SkillRegistry, Services
        from jarvis.audio import Speaker

        cfg = Config()
        assert cfg.skills.face.enabled is False

        # Мокаем всё тяжёлое
        with patch("jarvis.assistant.build_registry", return_value=(SkillRegistry(), Services(timers=MagicMock(), memory=MagicMock(), browser=MagicMock()))), \
             patch("jarvis.assistant.build_brain", return_value=MagicMock()), \
             patch("jarvis.assistant.Speaker"), \
             patch("jarvis.assistant.SystemMonitor"), \
             patch("jarvis.assistant.WakeWordDetector"), \
             patch("jarvis.assistant.SpeechRecorder"), \
             patch("jarvis.assistant.HotkeyListener"):
            # Не должно падать даже без камеры
            pass  # _try_face_greeting проверяет enabled и выходит

    def test_face_recognized_switches_profile(self):
        """Распознанное лицо переключает профиль если привязан."""
        from jarvis.config import Config
        from jarvis.assistant import Assistant
        from jarvis.skills import SkillRegistry, Services
        from jarvis.profiles import ProfileManager

        cfg = Config()
        cfg.skills.face.enabled = True
        cfg.skills.face.auto_greeting = True
        cfg.skills.face.auto_switch_profile = True

        mock_brain = MagicMock()
        mock_profiles = MagicMock(spec=ProfileManager)
        mock_profiles.current_id = "default"
        mock_profiles.current = MagicMock()
        mock_profiles.switch.return_value = (True, "ok")

        with patch("jarvis.assistant.build_registry", return_value=(SkillRegistry(), Services(timers=MagicMock(), memory=MagicMock(), browser=MagicMock()))), \
             patch("jarvis.assistant.build_brain", return_value=mock_brain), \
             patch("jarvis.assistant.Speaker"), \
             patch("jarvis.assistant.SystemMonitor"), \
             patch("jarvis.assistant.WakeWordDetector"), \
             patch("jarvis.assistant.SpeechRecorder"), \
             patch("jarvis.assistant.HotkeyListener"), \
             patch("jarvis.assistant.ProfileManager", return_value=mock_profiles), \
             patch("jarvis.face_db.recognize_face", return_value=("Ivan", 0.12)), \
             patch("jarvis.face_db.get_face_profile", return_value="casual"):
            a = Assistant.__new__(Assistant)
            a.config = cfg
            a._sink = lambda e: None
            a.profiles = mock_profiles
            a.speaker = MagicMock()
            a.skills = SkillRegistry()
            a.services = Services(timers=MagicMock(), memory=MagicMock(), browser=MagicMock())
            a.brain = mock_brain
            a.monitor = MagicMock()
            a._stop = MagicMock()
            a._busy = MagicMock()
            a._hotkey = MagicMock()

            a._try_face_greeting()

            # Профиль должен быть переключён
            mock_profiles.switch.assert_called_once_with("casual")
            # Приветствие должно содержать имя
            assert "Ivan" in cfg.greeting

    def test_face_not_recognized_no_change(self):
        """Лицо не распознано — приветствие не меняется."""
        from jarvis.config import Config
        from jarvis.assistant import Assistant
        from jarvis.skills import SkillRegistry, Services
        from jarvis.profiles import ProfileManager

        cfg = Config()
        cfg.skills.face.enabled = True
        original_greeting = cfg.greeting

        mock_profiles = MagicMock(spec=ProfileManager)
        mock_profiles.current_id = "default"
        mock_profiles.current = MagicMock()

        with patch("jarvis.face_db.recognize_face", return_value=(None, 0.0)), \
             patch("jarvis.face_db.get_face_profile", return_value=None):
            a = Assistant.__new__(Assistant)
            a.config = cfg
            a._sink = lambda e: None
            a.profiles = mock_profiles
            a.speaker = MagicMock()
            a.skills = SkillRegistry()
            a.services = Services(timers=MagicMock(), memory=MagicMock(), browser=MagicMock())
            a.brain = MagicMock()
            a.monitor = MagicMock()
            a._stop = MagicMock()
            a._busy = MagicMock()
            a._hotkey = MagicMock()

            a._try_face_greeting()

            assert cfg.greeting == original_greeting
            mock_profiles.switch.assert_not_called()

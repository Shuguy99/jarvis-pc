"""Тесты навыков распознавания лиц."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jarvis.config import FaceConfig
from jarvis.skills.face import (
    _load_json,
    _save_json,
    build_skills,
    detect_emotions,
    detect_faces,
    identify_face,
    list_known_faces,
    register_face,
    take_webcam_photo,
    unregister_face,
    visit_log,
)


CFG = FaceConfig(enabled=True, photo_dir="/tmp/jarvis-test-faces")


# ── _load_json / _save_json ─────────────────────────────────────────


class TestJsonHelpers:
    def test_load_missing_returns_empty(self, tmp_path):
        assert _load_json(tmp_path / "nope.json") == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        p = tmp_path / "db.json"
        _save_json(p, {"a": 1})
        assert _load_json(p) == {"a": 1}

    def test_load_corrupted_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json", encoding="utf-8")
        assert _load_json(p) == {}


# ── take_webcam_photo ──────────────────────────────────────────────


class TestTakeWebcamPhoto:
    @patch("jarvis.skills.face._capture_frame", return_value=(None, "камера ошибка"))
    def test_camera_error(self, mock_cap):
        result = take_webcam_photo(CFG)
        assert "камера" in result.lower() or "ошибка" in result.lower()

    @patch("jarvis.skills.face._capture_frame")
    def test_success(self, mock_cap, tmp_path):
        import numpy as np
        fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_cap.return_value = (fake_frame, None)
        cfg = FaceConfig(photo_dir=str(tmp_path / "photos"))
        result = take_webcam_photo(cfg)
        assert "сохранено" in result.lower()


# ── detect_faces ────────────────────────────────────────────────────


class TestDetectFaces:
    @patch("jarvis.skills.face._detect_face_regions", return_value=[])
    @patch("jarvis.skills.face._capture_frame", return_value=(None, "ошибка"))
    def test_camera_error(self, mock_cap, mock_det):
        assert "ошибка" in detect_faces(CFG)

    @patch("jarvis.skills.face._log_visit")
    @patch("jarvis.skills.face._save_detection_photo")
    @patch("jarvis.skills.face._detect_face_regions", return_value=[])
    @patch("jarvis.skills.face._capture_frame")
    def test_no_faces(self, mock_cap, mock_det, mock_save, mock_log):
        import numpy as np
        mock_cap.return_value = (np.zeros((100, 100, 3), dtype=np.uint8), None)
        result = detect_faces(CFG)
        assert "не обнаружены" in result
        mock_log.assert_not_called()

    @patch("jarvis.skills.face._log_visit")
    @patch("jarvis.skills.face._save_detection_photo")
    @patch("jarvis.skills.face._detect_face_regions", return_value=[(10, 10, 50, 50)])
    @patch("jarvis.skills.face._capture_frame")
    def test_one_face(self, mock_cap, mock_det, mock_save, mock_log):
        import numpy as np
        mock_cap.return_value = (np.zeros((100, 100, 3), dtype=np.uint8), None)
        result = detect_faces(CFG)
        assert "одно лицо" in result
        mock_log.assert_called_once_with(1)
        mock_save.assert_called_once()

    @patch("jarvis.skills.face._log_visit")
    @patch("jarvis.skills.face._save_detection_photo")
    @patch("jarvis.skills.face._detect_face_regions", return_value=[(0,0,50,50), (60,60,50,50)])
    @patch("jarvis.skills.face._capture_frame")
    def test_two_faces(self, mock_cap, mock_det, mock_save, mock_log):
        import numpy as np
        mock_cap.return_value = (np.zeros((200, 200, 3), dtype=np.uint8), None)
        result = detect_faces(CFG)
        assert "2 лиц" in result
        mock_log.assert_called_once_with(2)


# ── identify_face ──────────────────────────────────────────────────


class TestIdentifyFace:
    @patch("jarvis.skills.face._capture_frame", return_value=(None, "ошибка"))
    def test_camera_error(self, mock_cap):
        assert "ошибка" in identify_face(CFG)

    @patch("jarvis.skills.face._detect_face_regions", return_value=[])
    @patch("jarvis.skills.face._capture_frame")
    def test_no_faces(self, mock_cap, mock_det):
        import numpy as np
        mock_cap.return_value = (np.zeros((100, 100, 3), dtype=np.uint8), None)
        result = identify_face(CFG)
        assert "не обнаружены" in result

    @patch("jarvis.skills.face._detect_face_regions", return_value=[(0,0,50,50)])
    @patch("jarvis.skills.face._capture_frame")
    def test_no_registered_faces(self, mock_cap, mock_det, tmp_path):
        import numpy as np
        mock_cap.return_value = (np.zeros((100, 100, 3), dtype=np.uint8), None)
        with patch("jarvis.skills.face._FACES_DB", tmp_path / "faces.json"):
            result = identify_face(CFG)
            assert "Нет зарегистрированных" in result


# ── detect_emotions ────────────────────────────────────────────────


class TestDetectEmotions:
    def test_deepface_not_installed(self):
        with patch("jarvis.skills.face._capture_frame", return_value=(None, "ошибка")):
            with patch.dict("sys.modules", {"deepface": None}):
                result = detect_emotions(CFG)
                assert "DeepFace не установлен" in result

    @patch("jarvis.skills.face._detect_face_regions", return_value=[])
    @patch("jarvis.skills.face._capture_frame")
    def test_no_faces(self, mock_cap, mock_det):
        import numpy as np
        mock_cap.return_value = (np.zeros((100, 100, 3), dtype=np.uint8), None)
        with patch.dict("sys.modules", {"deepface": MagicMock()}):
            result = detect_emotions(CFG)
            assert "не обнаружены" in result


# ── visit_log ──────────────────────────────────────────────────────


class TestVisitLog:
    def test_empty_log(self, tmp_path):
        with patch("jarvis.skills.face._VISIT_LOG", tmp_path / "log.json"):
            assert "пуст" in visit_log()

    def test_shows_visits(self, tmp_path):
        data = {"visits": [
            {"time": "2025-01-01T10:00", "faces": 1},
            {"time": "2025-01-01T11:00", "faces": 2, "identified": "Иван"},
        ]}
        p = tmp_path / "log.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with patch("jarvis.skills.face._VISIT_LOG", p):
            result = visit_log()
            assert "Иван" in result
            assert "2 лиц" in result

    def test_limit_works(self, tmp_path):
        visits = [{"time": f"2025-01-01T{i:02d}:00", "faces": 1} for i in range(20)]
        p = tmp_path / "log.json"
        p.write_text(json.dumps({"visits": visits}), encoding="utf-8")
        with patch("jarvis.skills.face._VISIT_LOG", p):
            result = visit_log(limit=5)
            # Should show only 5 entries
            assert result.count(chr(10) + "  ") == 5


# ── register_face / unregister_face / list_known_faces ─────────────


class TestRegisterFace:
    @patch("jarvis.skills.face._capture_frame", return_value=(None, "ошибка"))
    def test_camera_error(self, mock_cap):
        assert "ошибка" in register_face("test", CFG)

    @patch("jarvis.skills.face._detect_face_regions", return_value=[])
    @patch("jarvis.skills.face._capture_frame")
    def test_registers_without_face_detection(self, mock_cap, mock_det, tmp_path):
        import numpy as np
        mock_cap.return_value = (np.zeros((100, 100, 3), dtype=np.uint8), None)
        cfg = FaceConfig(photo_dir=str(tmp_path / "photos"))
        db_path = tmp_path / "faces.json"
        with patch("jarvis.skills.face._FACES_DB", db_path):
            result = register_face("testuser", cfg)
            assert "зарегистрировано" in result
            assert "testuser" in result
            db = _load_json(db_path)
            assert "testuser" in db


class TestUnregisterFace:
    def test_not_found(self, tmp_path):
        with patch("jarvis.skills.face._FACES_DB", tmp_path / "f.json"):
            assert "не найдено" in unregister_face("ghost")

    def test_removes_from_db(self, tmp_path):
        p = tmp_path / "f.json"
        _save_json(p, {"bob": {"photo": "/fake/path.jpg", "registered": "2025"}})
        with patch("jarvis.skills.face._FACES_DB", p):
            result = unregister_face("bob")
            assert "удалено" in result
            assert _load_json(p) == {}


class TestListKnownFaces:
    def test_empty(self, tmp_path):
        with patch("jarvis.skills.face._FACES_DB", tmp_path / "f.json"):
            assert "Нет зарегистрированных" in list_known_faces()

    def test_shows_registered(self, tmp_path):
        p = tmp_path / "f.json"
        _save_json(p, {"alice": {"registered": "2025-01-01"}})
        with patch("jarvis.skills.face._FACES_DB", p):
            result = list_known_faces()
            assert "alice" in result
            assert "2025-01-01" in result


# ── build_skills ────────────────────────────────────────────────────


class TestBuildSkills:
    def test_returns_eight_skills(self):
        skills = build_skills(CFG)
        assert len(skills) == 8

    def test_skill_names(self):
        names = {s.name for s in build_skills(CFG)}
        assert names == {
            "take_webcam_photo", "detect_faces", "identify_face",
            "detect_emotions", "visit_log", "register_face",
            "unregister_face", "list_known_faces",
        }

    def test_tool_specs_valid(self):
        for skill in build_skills(CFG):
            spec = skill.to_openai_tool()
            assert spec["type"] == "function"
            params = spec["function"]["parameters"]
            assert params["type"] == "object"
            for req in params.get("required", []):
                assert req in params["properties"]

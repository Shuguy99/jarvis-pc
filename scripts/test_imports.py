"""Проверка импорта каждого модуля навыков."""

import importlib
import traceback

skill_modules = [
    "jarvis.skills.registry",
    "jarvis.skills.system",
    "jarvis.skills.apps",
    "jarvis.skills.web",
    "jarvis.skills.personal",
    "jarvis.skills.vision",
    "jarvis.skills.memory",
    "jarvis.skills.browser",
    "jarvis.skills.spotify",
    "jarvis.skills.weather",
    "jarvis.skills.calendar",
    "jarvis.skills.desktop_notify",
    "jarvis.skills.translator",
    "jarvis.skills.env",
    "jarvis.skills.macros",
    "jarvis.skills.files",
    "jarvis.skills.youtube",
    "jarvis.skills.face",
    "jarvis.skills.github",
    "jarvis.skills.vpn",
    "jarvis.skills.sounds",
    "jarvis.skills.wifi",
    "jarvis.skills.pomodoro",
    "jarvis.skills.news",
    "jarvis.skills.currency",
    "jarvis.skills.homeassistant",
    "jarvis.skills.telegram_bot",
    "jarvis.skills.alarm",
    "jarvis.skills.passwords",
    "jarvis.skills.notes",
    "jarvis.skills.agenda",
    "jarvis.skills.habits",
    "jarvis.skills.expenses",
    "jarvis.skills.network",
    "jarvis.skills.windows_manager",
    "jarvis.skills.disk",
    "jarvis.skills.sysupdate",
    "jarvis.skills.processes",
    "jarvis.skills.music_recognition",
    "jarvis.skills.qr",
    "jarvis.skills.image_gen",
    "jarvis.skills.radio",
]

ok = 0
fail = 0
for mod in skill_modules:
    try:
        importlib.import_module(mod)
        print(f"  OK {mod}")
        ok += 1
    except Exception as e:
        print(f"  FAIL {mod}: {e}")
        traceback.print_exc()
        fail += 1

print(f"\nResult: {ok} OK, {fail} FAIL")
# J.A.R.V.I.S. — голосовой ИИ-ассистент для ПК

Локальный голосовой ассистент в духе Джарвиса Тони Старка. Просыпается по слову
«Джарвис», понимает свободную речь на русском, управляет компьютером и
показывает HUD-оверлей поверх всех окон.

**174 навыка** через function calling, работает на Linux, Windows и macOS.

```
Вы:  Джарвис, поставь громкость на 30 и открой блокнот
J.A.R.V.I.S.: Громкость установлена на 30 процентов. Запускаю блокнот, сэр.

Вы:  Какая погода в Москве?
J.A.R.V.I.S.: В Москве +22 градуса, переменная облачность, сэр.

J.A.R.V.I.S.: Сэр, батарея разряжена до 15 процентов, рекомендую подключить
              зарядное устройство.   (предупреждает сам, без вопроса)
```

## Возможности

### Ядро

| Подсистема | Реализация |
|---|---|
| Пробуждение | openWakeWord (`hey_jarvis`) + резерв по тексту |
| Слух | faster-whisper локально, VAD (WebRTC) |
| Мозг | Ollama (локально), OpenAI-совместимое API, офлайн-режим |
| Голос | SAPI5 (офлайн), Microsoft Edge Neural TTS |
| Зрение | OCR (Tesseract) или мультимодальная модель (llava / gpt-4o) |
| Память | ChromaDB с откатом на JSON |
| Инициатива | Фоновый мониторинг батареи, RAM, диска, CPU |
| Браузер | Playwright: открыть, клик, заполнить, прочитать |
| HUD | PySide6 оверлей: реактор, статус, команда/ответ |

### 174 навыка по категориям

**Система (17)**: `system_status`, `power_action`, `lock_workstation`, `take_screenshot`,
`screenshot_save`, `get_system_volume`, `system_volume`, `system_volume_up`,
`system_volume_down`, `system_toggle_mute`, `get_brightness`, `set_brightness`,
`battery_status`, `get_clipboard`, `set_clipboard`, `clear_clipboard`, `type_text`

**Приложения и окна (8)**: `open_app`, `close_app`, `list_windows`, `focus_window`,
`snap_left`, `snap_right`, `list_monitors`, `press_key`

**Процессы и диск (6)**: `kill_process`, `proc_info`, `top_cpu`, `top_mem`,
`disk_usage`, `top_dirs`

**Зрение и OCR (3)**: `analyze_screen`, `read_screen_text`, `face_detect`

**Память (5)**: `remember_fact`, `recall_fact`, `list_memory`, `forget_fact`,
`detect_language`

**Браузер (5)**: `browser_open`, `browser_click`, `browser_fill`,
`browser_press`, `browser_read`, `browser_close`

**Веб и поиск (4)**: `web_search`, `open_url`, `fetch_summary` (Википедия),
`open_in_browser`

**YouTube Music (8)**: `play_music`, `stop_music`, `yt_music_status`,
`yt_music_pause`, `yt_music_resume`, `yt_music_toggle`, `yt_music_seek`,
`yt_music_volume`

**Погода (3)**: `get_weather`, `get_forecast`, `weather_alert`

**Калькулятор и конвертеры (5)**: `calculate`, `percentage`, `convert_temperature`,
`unit_convert`, `convert_currency`

**Таймеры и будильники (7)**: `set_timer`, `list_timers`, `cancel_timer`,
`timer_set`, `timer_list`, `timer_cancel`, `set_alarm`, `list_alarms`, `cancel_alarm`

**Заметки и сниппеты (7)**: `add_note`, `read_notes`, `save_snippet`,
`search_snippets`, `list_snippets`, `get_snippet`, `dictaphone`

**Продуктивность (9)**: `pomodoro_start`, `pomodoro_status`, `pomodoro_cancel`,
`pomodoro_stats`, `today_agenda`, `upcoming_events`, `today_events`,
`habit_add`, `habit_check`, `habit_delete`, `habit_list`, `habit_stats`

**Расходы (5)**: `expense_add`, `expense_last`, `expense_summary`,
`expense_categories`, `expense_delete_last`

**Файловый менеджер (7)**: `list_files`, `search_files`, `file_info`,
`copy_file`, `delete_file`, `create_directory`, `get_path`

**Git (5)**: `git_status`, `git_commit`, `git_push`, `git_log`, `git_branch`

**GitHub (5)**: `repo_status`, `list_commits`, `list_issues`, `create_issue`,
`list_commits`

**Крипто и акции (3)**: `crypto_price`, `crypto_list`, `stock_price`

**Сеть (7)**: `speedtest`, `dns_lookup`, `scan_ports`, `wifi_status`,
`wifi_list`, `wifi_connect`, `wifi_disconnect`, `wifi_qr`

**Спotify (3)**: `spotify_play`, `spotify_control`, `spotify_now_playing`

**Радио (3)**: `radio_list`, `radio_play`, `radio_stop`

**Прочее**: `generate_password`, `generate_qr`, `read_qr`, `translate_text`,
`send_email`, `show_notification`, `play_sound`, `play_beep`,
`get_env`, `set_env`, `self_update`, `current_version`, `check_updates`,
`current_time`, `current_date`, `ping`

## Быстрый старт

### Мастер настройки (рекомендуется)

```bash
git clone https://github.com/Shuguy99/jarvis-pc.git
cd jarvis-pc
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m jarvis setup   # интерактивный визард за 2 минуты
python -m jarvis voice
```

### Ручная установка

1. **Python 3.10+** с галочкой «Add to PATH».
2. `pip install -r requirements.txt`
3. Создайте `config.yaml`:
   ```bash
   python -m jarvis config init   # копирует config.example.yaml
   ```
4. Выберите мозг в `config.yaml`:
   - **Локально** — установите [Ollama](https://ollama.com/download),
     `ollama pull qwen2.5:7b-instruct`, оставьте `backend: ollama`.
   - **Облако** — `backend: openai` + переменная `OPENAI_API_KEY`.
5. Запустите: `python -m jarvis voice`

## Режимы запуска

```bash
python -m jarvis voice              # голосовой режим + HUD
python -m jarvis text               # текстовый чат в консоли
python -m jarvis once "погода"      # одна команда
python -m jarvis doctor             # диагностика зависимостей
python -m jarvis devices            # список микрофонов
python -m jarvis setup              # мастер настройки
python -m jarvis config init        # создать config.yaml
```

Windows: `run.bat`, `run.bat text`, `run.bat doctor`

## Настройка

Все параметры — в [`config.yaml`](config.example.yaml). Ключевые:

| Параметр | По умолчанию | Описание |
|---|---|---|
| `brain.backend` | `ollama` | `ollama` / `openai` / `offline` |
| `brain.ollama_model` | `qwen2.5:7b-instruct` | Модель Ollama |
| `stt.model` | `small` | `tiny` (быстро) — `large-v3` (точно) |
| `tts.engine` | `sapi5` | `sapi5` (офлайн) / `edge` (neural) |
| `tts.edge_voice` | `ru-RU-DmitryNeural` | Голос Edge TTS |
| `ui.enabled` | `true` | HUD-оверлей (нужен PySide6) |
| `wake_word.enabled` | `true` | Пробуждение по слову (нужен openwakeword) |
| `monitor.enabled` | `true` | Фоновый мониторинг системы |
| `skills.allow_shutdown` | `false` | Разрешить голосовое выключение ПК |

## Как это устроено

```
jarvis/
  assistant.py      оркестратор: пробуждение → запись → STT → мозг → навыки → TTS
  audio/            микрофон + VAD, openWakeWord, faster-whisper, TTS
  brain/            function calling цикл + бэкенды ollama/openai/offline
  monitor.py        фоновый мониторинг и инициативные предупреждения
  skills/           59 модулей, 174 навыка
  ui/               HUD-оверлей на PySide6
  cli.py            режимы voice / text / once / doctor / devices / setup
  config.py         YAML-конфиг с валидацией и ${ENV_VAR} подстановкой
  setup_wizard.py   интерактивный мастер настройки
```

Один цикл: детектор слова → запись до тишины → Whisper → мозг выбирает навыки
→ выполнение → результат в модель → финальная фраза озвучивается и показывается
в HUD.

## Кроссплатформенность

Linux, Windows, macOS. Навыки автоматически адаптируются:
- Громкость: `pactl` / `amixer` (Linux), `pycaw` (Windows), `osascript` (macOS)
- Окна: `wmctrl`/`xdotool` (Linux), `pygetwindow` (Windows)
- Питание: `systemctl`/`shutdown` (Linux), `powershell` (Windows)

## Приватность

По умолчанию наружу не уходит ничего: пробуждение, распознавание и синтез
работают локально. Облако используется только при `brain.backend: openai`
или `tts.engine: edge`. Все данные (память, заметки, расходы) хранятся
в `~/.jarvis/`.

## Разработка

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q          # 180 тестов
.venv/bin/ruff check .                # линтер
.venv/bin/python -m jarvis doctor     # диагностика
```

### Добавить свой навык

Создайте файл `jarvis/skills/my_skill.py`:

```python
from .registry import Skill, object_schema

def my_handler(param: str) -> str:
    return f"Результат: {param}, сэр."

def build_skills() -> list[Skill]:
    return [
        Skill(
            name="my_skill",
            description="Описание для LLM",
            parameters=object_schema({"param": {"type": "string", "description": "Параметр"}}, required=["param"]),
            handler=my_handler,
        ),
    ]
```

Зарегистрируйте в `jarvis/skills/__init__.py` → `build_registry()`.

## Лицензия

MIT

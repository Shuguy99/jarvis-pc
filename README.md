<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/навыков-174-green" alt="Skills" />
  <img src="https://img.shields.io/badge/тестов-925-brightgreen" alt="Tests" />
  <img src="https://img.shields.io/badge/модулей-67-yellow" alt="Modules" />
  <img src="https://img.shields.io/badge/OS-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey" alt="Cross-platform" />
  <img src="https://img.shields.io/badge/License-MIT-orange" alt="License" />
</p>

<h1 align="center">J.A.R.V.I.S.</h1>

<p align="center">
  <b>Голосовой ИИ-ассистент для ПК</b><br>
  В духе Джарвиса Тони Старка. Локальный, приватный, расширяемый.
</p>

<p align="center">
  <a href="#быстрый-старт">Быстрый старт</a> &middot;
  <a href="#навыки">174 навыка</a> &middot;
  <a href="#безопасность">Безопасность</a> &middot;
  <a href="#как-это-устроено">Архитектура</a> &middot;
  <a href="#разработка">Разработка</a>
</p>

---

```
Вы:           Джарвис, поставь громкость на 30 и открой блокнот
J.A.R.V.I.S.: Громкость установлена на 30 процентов. Запускаю блокнот, сэр.

Вы:           Какая погода в Москве?
J.A.R.V.I.S.: В Москве +22 градуса, переменная облачность, сэр.

J.A.R.V.I.S.: Сэр, батарея разряжена до 15 процентов,
              рекомендую подключить зарядное устройство.
              (предупреждает сам, без вопроса)
```

## Почему J.A.R.V.I.S.

- **174 навыка** — от управления системой до умного дома, все через function calling
- **Локальный по умолчанию** — STT (Whisper), TTS (SAPI5), мозг (Ollama) работают без интернета
- **Облако по желанию** — OpenAI, OpenRouter, Edge Neural TTS для лучших результатов
- **Кроссплатформенный** — Linux, Windows, macOS с автоадаптацией команд
- **Расширяемый** — плагинная архитектура, написать навык = 10 строк кода
- **Приватный** — данные в `~/.jarvis/`, наружу ничего не уходит без вашего разрешения
- **С инициативой** — сам следит за батареей, CPU, RAM и предупреждает о проблемах
- **Безопасный** — подтверждение опасных операций, защита путей, валидация URL, rate limiting

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
   - **Локально (бесплатно)** — установите [Ollama](https://ollama.com/download),
     `ollama pull qwen2.5:7b-instruct`, оставьте `backend: ollama`.
   - **Облако** — `backend: openai` + переменная `OPENAI_API_KEY`.
5. Запустите: `python -m jarvis voice`

## Режимы запуска

```bash
python -m jarvis voice              # голосовой режим + HUD
python -m jarvis text               # текстовый чат в консоли
python -m jarvis once "погода"      # одна команда без запуска цикла
python -m jarvis doctor             # диагностика зависимостей
python -m jarvis devices            # список микрофонов
python -m jarvis setup              # мастер настройки
python -m jarvis config init        # создать config.yaml из шаблона
```

Windows: `run.bat`, `run.bat text`, `run.bat doctor`

## Навыки

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

<details>
<summary><b>Система (17)</b></summary>

`system_status` `power_action` `lock_workstation` `take_screenshot`
`screenshot_save` `get_system_volume` `system_volume` `system_volume_up`
`system_volume_down` `system_toggle_mute` `get_brightness` `set_brightness`
`battery_status` `get_clipboard` `set_clipboard` `clear_clipboard` `type_text`
</details>

<details>
<summary><b>Приложения и окна (8)</b></summary>

`open_app` `close_app` `list_windows` `focus_window`
`snap_left` `snap_right` `list_monitors` `press_key`
</details>

<details>
<summary><b>Процессы и диск (6)</b></summary>

`kill_process` `proc_info` `top_cpu` `top_mem` `disk_usage` `top_dirs`
</details>

<details>
<summary><b>Зрение и OCR (3)</b></summary>

`analyze_screen` `read_screen_text` `face_detect`
</details>

<details>
<summary><b>Память (5)</b></summary>

`remember_fact` `recall_fact` `list_memory` `forget_fact` `detect_language`
</details>

<details>
<summary><b>Браузер (6)</b></summary>

`browser_open` `browser_click` `browser_fill` `browser_press` `browser_read` `browser_close`
</details>

<details>
<summary><b>Веб и поиск (4)</b></summary>

`web_search` `open_url` `fetch_summary` `open_in_browser`
</details>

<details>
<summary><b>YouTube Music (8)</b></summary>

`play_music` `stop_music` `yt_music_status` `yt_music_pause` `yt_music_resume`
`yt_music_toggle` `yt_music_seek` `yt_music_volume`
</details>

<details>
<summary><b>Погода (3)</b></summary>

`get_weather` `get_forecast` `weather_alert`
</details>

<details>
<summary><b>Калькулятор и конвертеры (5)</b></summary>

`calculate` `percentage` `convert_temperature` `unit_convert` `convert_currency`
</details>

<details>
<summary><b>Таймеры и будильники (9)</b></summary>

`set_timer` `list_timers` `cancel_timer` `timer_set` `timer_list` `timer_cancel`
`set_alarm` `list_alarms` `cancel_alarm`
</details>

<details>
<summary><b>Заметки и сниппеты (7)</b></summary>

`add_note` `read_notes` `save_snippet` `search_snippets` `list_snippets` `get_snippet` `dictaphone`
</details>

<details>
<summary><b>Продуктивность (12)</b></summary>

`pomodoro_start` `pomodoro_status` `pomodoro_cancel` `pomodoro_stats`
`today_agenda` `upcoming_events` `today_events`
`habit_add` `habit_check` `habit_delete` `habit_list` `habit_stats`
</details>

<details>
<summary><b>Расходы (5)</b></summary>

`expense_add` `expense_last` `expense_summary` `expense_categories` `expense_delete_last`
</details>

<details>
<summary><b>Файловый менеджер (7)</b></summary>

`list_files` `search_files` `file_info` `copy_file` `delete_file` `create_directory` `get_path`
</details>

<details>
<summary><b>Git и GitHub (10)</b></summary>

`git_status` `git_commit` `git_push` `git_log` `git_branch`
`repo_status` `list_commits` `list_issues` `create_issue`
</details>

<details>
<summary><b>Сеть, Wi-Fi, VPN (8)</b></summary>

`speedtest` `dns_lookup` `scan_ports` `wifi_status` `wifi_list` `wifi_connect` `wifi_disconnect` `wifi_qr`
</details>

<details>
<summary><b>Умный дом — Home Assistant (11)</b></summary>

`ha_toggle` `ha_turn_on` `ha_turn_off` `ha_state` `ha_list`
`ha_call_service` `ha_list_devices` `ha_toggle_device` `ha_set_light`
`ha_get_state` `ha_run_script`
</details>

<details>
<summary><b>Сцены / автоматизации (2)</b></summary>

`run_scene` `list_scenes` — предустановленные: `morning`, `work`, `evening`, `focus`
</details>

<details>
<summary><b>Спotify, радио, музыка (6)</b></summary>

`spotify_play` `spotify_control` `spotify_now_playing` `radio_list` `radio_play` `radio_stop`
</details>

<details>
<summary><b>Прочее</b></summary>

`generate_password` `generate_qr` `read_qr` `translate_text`
`send_email` `show_notification` `play_sound` `play_beep`
`get_env` `set_env` `self_update` `current_version` `check_updates`
`current_time` `current_date` `ping` `crypto_price` `crypto_list`
`stock_price` `image_gen` `recognize_music` `telegram_send`
`notion_add_task` `notion_list_tasks` `browser_close`
</details>

## Настройка

Все параметры — в [`config.yaml`](config.example.yaml). Ключевые:

| Параметр | По умолчанию | Описание |
|---|---|---|
| `brain.backend` | `ollama` | `ollama` / `openai` / `offline` |
| `brain.ollama_model` | `qwen2.5:7b-instruct` | Модель Ollama |
| `brain.temperature` | `0.4` | 0.0–2.0, ниже = точнее |
| `stt.model` | `small` | `tiny` (быстро) — `large-v3` (точно) |
| `tts.engine` | `sapi5` | `sapi5` (офлайн) / `edge` (neural) |
| `tts.edge_voice` | `ru-RU-DmitryNeural` | Голос Edge TTS |
| `ui.enabled` | `true` | HUD-оверлей (нужен PySide6) |
| `wake_word.enabled` | `true` | Пробуждение по слову (нужен openwakeword) |
| `monitor.enabled` | `true` | Фоновый мониторинг системы |
| `skills.allow_shutdown` | `false` | Разрешить голосовое выключение ПК |
| `rate_limit.enabled` | `true` | Rate limiting для внешних вызовов |
| `rate_limit.per_second` | `1.0` | Минимальный интервал между вызовами (с) |
| `rate_limit.burst` | `3` | Количество вызовов подряд без throttling |

### Алиасы

Сокращения для частых команд (в `config.yaml`):

```yaml
skills:
  aliases:
    тихо: "установи громкость на 20 процентов"
    громко: "установи громкость на 80 процентов"
    музыка: "открой приложение Spotify"
    погода: "какая сейчас погода"
```

## Как это устроено

```
jarvis/
  assistant.py      оркестратор: пробуждение → запись → STT → мозг → навыки → TTS
  audio/            микрофон + VAD, openWakeWord, faster-whisper, TTS
  brain/            function calling цикл + бэкенды ollama/openai/offline
  monitor.py        фоновый мониторинг и инициативные предупреждения
  skills/           67 модулей, 174 навыка
  ui/               HUD-оверлей на PySide6
  cli.py            режимы voice / text / once / doctor / devices / setup
  config.py         YAML-конфиг с валидацией и ${ENV_VAR} подстановкой
  setup_wizard.py   интерактивный мастер настройки (6 шагов)
tests/             925 тестов (pytest)
```

### Цикл обработки

```
Микрофон → VAD (детекция речи) → openWakeWord ("Джарвис")
  → Whisper (STT) → LLM + function calling → навыки
  → LLM (финальный ответ) → TTS → Динамики + HUD
```

Мозг получает все 174 навыка как OpenAI tool definitions. Модель сама решает,
какие вызвать, в каком порядке и с какими аргументами. Результат выполнения
навыка возвращается обратно в модель для формулировки ответа.

### Кроссплатформенность

Навыки автоматически адаптируются к ОС:
- Громкость: `pactl` / `amixer` (Linux), `pycaw` (Windows), `osascript` (macOS)
- Окна: `wmctrl`/`xdotool` (Linux), `pygetwindow` (Windows)
- Питание: `shutdown` (Linux/macOS), `powershell` (Windows)
- MPV IPC: UNIX socket (Linux/macOS), named pipe (Windows)

## Безопасность

### Подтверждение опасных операций

Удаление файлов, закрытие приложений, git push/commit, системные обновления,
перезагрузка и выключение — требуют подтверждения пользователя через LLM.
При повторном вызове с теми же аргументами выполнение проходит без повторного вопроса.

### Защита путей и URL

- **Удаление** блокируется для `/`, `/home`, `%USERPROFILE%` и их подкаталогов
- **URL** отклоняются если схема — `javascript:`, `file:`, `data:`
- **Shell-команды** отклоняются при наличии `|`, `` ` ``, `;`, `$()``
- **Выключение/перезагрузка** заблокированы пока явно не разрешены в конфиге

### Rate limiting

Внешние вызовы (веб-поиск, Telegram API, HTTP-запросы) ограничены
token-bucket алгоритмом с настраиваемым `per_second` и `burst`.
Каждая группа вызовов (например, `web_search`) имеет независимый bucket.

### Логирование ошибок

Все исключения логируются через `log.debug()` / `log.warning()` —
никаких тихих `except Exception: pass`, которые скрывают баги.

## Приватность

По умолчанию наружу не уходит ничего: пробуждение, распознавание и синтез
работают локально. Облако используется только при `brain.backend: openai`
или `tts.engine: edge`. Все данные (память, заметки, расходы) хранятся
в `~/.jarvis/`.

## Разработка

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q          # 925 тестов
.venv/bin/ruff check .                # линтер
.venv/bin/python -m jarvis doctor     # диагностика зависимостей
```

### Добавить свой навык

1. Создайте файл `jarvis/skills/my_skill.py`:

```python
from .registry import Skill, object_schema


def my_handler(param: str) -> str:
    return f"Результат: {param}, сэр."


def build_skills() -> list[Skill]:
    return [
        Skill(
            name="my_skill",
            description="Описание для LLM — модель видит это",
            parameters=object_schema(
                {"param": {"type": "string", "description": "Параметр"}},
                required=["param"],
            ),
            handler=my_handler,
        ),
    ]
```

2. Зарегистрируйте в `jarvis/skills/__init__.py` → `build_registry()`.
3. Готово — навык автоматически появится в tool definitions и будет доступен голосом.

### Если навыку нужна конфигурация

```python
def build_skills(config: SomeConfig) -> list[Skill]:
    return [
        Skill(
            name="my_skill",
            description="...",
            parameters=object_schema({}),
            handler=lambda: do_something(config.api_key),
        ),
    ]
```

`build_registry()` в `__init__.py` уже передаёт конфиг нужным модулям.

## Стек

| Слой | Технология |
|---|---|
| STT | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| TTS | [edge-tts](https://github.com/rany2/edge-tts), [pyttsx3](https://github.com/nateshmbhat/pyttsx3) |
| LLM (local) | [Ollama](https://ollama.com) + Qwen / Llama / Mistral |
| LLM (cloud) | OpenAI API, OpenRouter, любой совместимый endpoint |
| Wake word | [openWakeWord](https://github.com/dscripka/openWakeWord) |
| VAD | [WebRTC VAD](https://github.com/wiseman/py-webrtcvad) |
| Browser | [Playwright](https://playwright.dev/python/) |
| Memory | [ChromaDB](https://www.trychroma.com/) |
| Vision | Tesseract OCR, multimodal LLM |
| HUD | [PySide6](https://wiki.qt.io/PySide6) |
| Smart home | Home Assistant REST API |

## Лицензия

MIT
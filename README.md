# J.A.R.V.I.S. — голосовой ассистент для ПК

Локальный голосовой ассистент в духе Джарвиса Тони Старка: просыпается на слово
«Джарвис», понимает свободную речь, реально управляет Windows и показывает
HUD-оверлей с «реактором» поверх всех окон.

```
Вы:  Джарвис, поставь громкость на 30 и открой блокнот
J.A.R.V.I.S.: Громкость установлена на 30 процентов. Запускаю блокнот, сэр.
```

## Что умеет

| Подсистема | Реализация |
|---|---|
| Пробуждение | openWakeWord, предобученная модель `hey_jarvis`; резерв — поиск слова «Джарвис» в распознанном тексте |
| Слух | faster-whisper локально (без интернета), VAD от WebRTC определяет конец фразы |
| Мозг | Ollama (локально), OpenAI-совместимое API или офлайн-режим на правилах |
| Голос | SAPI5 (офлайн, Windows) или neural-голоса Microsoft Edge |
| Интерфейс | HUD-оверлей PySide6: реактор, состояние, последняя команда и ответ |

24 навыка, которые модель вызывает через function calling:

- **Приложения и окна**: `open_app`, `close_app`, `list_windows`, `focus_window`
- **Система**: `set_volume`, `change_volume`, `media_control`, `take_screenshot`,
  `system_status`, `lock_workstation`, `power_action`
- **Веб**: `web_search`, `open_url`, `weather`, `fetch_summary` (Википедия)
- **Личное**: `current_time`, `current_date`, `set_timer`, `list_timers`,
  `cancel_timer`, `add_note`, `read_notes`, `read_clipboard`, `write_clipboard`

Своё приложение добавляется одной строкой в `config.yaml` — например
`музыка: "C:\\...\\Spotify.lnk"`, после чего работает «Джарвис, включи музыку».

## Установка (Windows)

1. Поставьте [Python 3.10+](https://www.python.org/downloads/windows/)
   (галочка «Add python.exe to PATH»).
2. Запустите `install.bat` — он создаст `.venv`, поставит зависимости,
   скопирует `config.example.yaml` в `config.yaml` и покажет диагностику.
3. Выберите мозг в `config.yaml`:
   - **Локально, без ключей** — установите [Ollama](https://ollama.com/download),
     затем `ollama pull qwen2.5:7b-instruct` и оставьте `backend: ollama`.
   - **Облако** — `backend: openai` и переменная окружения `OPENAI_API_KEY`
     (`setx OPENAI_API_KEY sk-...`, затем перезапустите терминал).
4. `run.bat` — Джарвис запускается, здоровается и слушает.

Первый запуск скачивает модель Whisper (`small` ≈ 500 МБ) и модель пробуждения.

## Режимы запуска

```bat
run.bat                    :: голос + HUD-оверлей
run.bat text               :: текстовый режим в консоли, без микрофона
run.bat once "сделай скриншот"
run.bat doctor             :: что установлено, доступна ли Ollama
run.bat devices            :: индексы микрофонов для mic.device
```

На Linux/macOS то же самое: `python -m jarvis text`. Навыки, специфичные для
Windows (громкость, окна, питание), честно сообщают, что недоступны.

## Настройка

Все параметры — в `config.yaml` (шаблон с комментариями:
[`config.example.yaml`](config.example.yaml)). Частые правки:

- `stt.model: tiny` — быстрее, но грубее; `medium` — точнее и тяжелее.
- `stt.device: cuda` — распознавание на видеокарте (нужен CUDA-совместимый torch).
- `tts.engine: edge` — живой neural-голос вместо системного.
- `mic.silence_ms` — пауза, после которой фраза считается законченной.
- `skills.allow_shutdown: true` — разрешить голосовое выключение ПК
  (по умолчанию запрещено).
- `ui.enabled: false` — работать без оверлея.

## Как это устроено

```
jarvis/
  assistant.py      оркестратор: пробуждение → запись → STT → мозг → навыки → TTS
  audio/            микрофон + VAD, openWakeWord, faster-whisper, синтез речи
  brain/            общий цикл function calling + бэкенды ollama/openai/offline
  skills/           реестр навыков и их реализации
  ui/               HUD-оверлей на PySide6
  cli.py            режимы voice / text / once / doctor / devices
```

Один цикл: детектор ключевого слова → запись до тишины → Whisper → мозг решает,
какие навыки вызвать → результаты навыков возвращаются в модель → финальная
фраза озвучивается и выводится в HUD.

Мозг подменяем: `Brain` реализует историю и цикл инструментов, бэкенду остаётся
один метод `_chat`. Если выбранный бэкенд недоступен (нет ключа, не запущена
Ollama), ассистент не падает, а переходит в офлайн-режим на регулярных
выражениях и продолжает выполнять прямые команды.

## Приватность

По умолчанию наружу не уходит ничего, кроме явных запросов навыков (поиск,
погода, Википедия): пробуждение, распознавание и синтез работают локально.
Облако используется только при `brain.backend: openai` или `tts.engine: edge`.

## Разработка

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m mypy jarvis
```

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
| Зрение | Снимок активного окна → OCR (Tesseract) или мультимодальная модель (`llava` в Ollama / `gpt-4o-mini`) |
| Память | Долговременная память фактов: ChromaDB с автоматическим откатом на JSON |
| Инициатива | Фоновый мониторинг батареи, памяти, диска и процессора: Джарвис предупреждает сам |
| Браузер | Playwright с постоянным профилем: открыть, заполнить, нажать, прочитать |
| Интерфейс | HUD-оверлей PySide6: реактор, состояние, последняя команда и ответ |

39 навыков, которые модель вызывает через function calling:

- **Приложения и окна**: `open_app`, `close_app`, `list_windows`, `focus_window`
- **Система**: `set_volume`, `change_volume`, `media_control`, `take_screenshot`,
  `system_status`, `lock_workstation`, `power_action`
- **Зрение**: `analyze_screen`, `read_screen_text`
- **Память**: `remember_fact`, `recall_fact`, `list_memory`, `forget_fact`
- **Браузер**: `browser_open`, `browser_click`, `browser_fill`, `browser_press`,
  `browser_read`, `browser_close`
- **Музыка**: `spotify_play`, `spotify_control`, `spotify_now_playing`
- **Веб**: `web_search`, `open_url`, `weather`, `fetch_summary` (Википедия)
- **Личное**: `current_time`, `current_date`, `set_timer`, `list_timers`,
  `cancel_timer`, `add_note`, `read_notes`, `read_clipboard`, `write_clipboard`

```
Вы:  Джарвис, какая сумма в столбце B?
J.A.R.V.I.S.: (смотрит на активное окно) В столбце B сумма 128 400 рублей, сэр.

Вы:  Джарвис, запомни, что мой номер заказа 7788-АА
J.A.R.V.I.S.: Запомнил, сэр.

J.A.R.V.I.S.: Сэр, батарея разряжена до 15 процентов, рекомендую подключить
              зарядное устройство.   (сам, без вопроса)
```

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

Дополнительно, по желанию:

- **Чтение текста с экрана (OCR)** — поставьте
  [Tesseract OCR для Windows](https://github.com/UB-Mannheim/tesseract/wiki)
  с русским языком и укажите путь в `skills.vision.tesseract_cmd`
  (обычно `C:\Program Files\Tesseract-OCR\tesseract.exe`).
- **Анализ экрана моделью** — локально: `ollama pull llava:7b`; в облаке:
  `skills.vision.backend: openai` и `OPENAI_API_KEY`.
- **Автоматизация браузера** — `install.bat` сам ставит Chromium для Playwright;
  профиль браузера живёт в `~/.jarvis/browser`, логины не сбрасываются.
- **Spotify** — зарегистрируйте приложение в
  [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) с
  redirect URI `http://127.0.0.1:8888/callback`, задайте `SPOTIFY_CLIENT_ID`
  и `SPOTIFY_CLIENT_SECRET` в переменные окружения и включите
  `skills.spotify.enabled: true`. Управление воспроизведением через Web API
  требует Spotify Premium.

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
- `monitor.battery_low`, `monitor.memory_high`, `monitor.disk_high` — пороги
  инициативных предупреждений; `monitor.enabled: false` — молчать.
- `skills.vision.backend` — `auto` (как у мозга), `ollama` или `openai`.
- `skills.memory.backend: json` — память без ChromaDB, простым файлом.
- `skills.browser.headless: true` — браузер без окна.

## Как это устроено

```
jarvis/
  assistant.py      оркестратор: пробуждение → запись → STT → мозг → навыки → TTS
  audio/            микрофон + VAD, openWakeWord, faster-whisper, синтез речи
  brain/            общий цикл function calling + бэкенды ollama/openai/offline
  monitor.py        фоновый мониторинг ПК и инициативные предупреждения
  skills/           реестр навыков: system, apps, web, personal, vision, memory,
                    browser, spotify
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

Зрение и память тоже могут быть полностью локальными: OCR выполняет Tesseract
на вашем ПК, снимки экрана уходят только в выбранную вами модель (с `llava`
в Ollama — никуда не уходят), факты памяти лежат в `~/.jarvis/memory`. При
`skills.vision.backend: openai` изображение экрана отправляется в OpenAI —
для чувствительных данных выбирайте Ollama.

## Разработка

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m mypy jarvis
```

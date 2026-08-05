@echo off
rem Установка Джарвиса: создаёт виртуальное окружение и ставит зависимости.
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python не найден. Установите Python 3.10+ с python.org и повторите.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/4] Создаю виртуальное окружение...
    py -3 -m venv .venv || goto :error
)

echo [2/4] Обновляю pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error

echo [3/4] Ставлю зависимости (это займёт несколько минут)...
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error

if not exist "config.yaml" (
    echo [4/4] Создаю config.yaml из шаблона...
    copy /y config.example.yaml config.yaml >nul
) else (
    echo [4/4] config.yaml уже есть, оставляю как есть.
)

echo.
echo Готово. Проверка окружения:
".venv\Scripts\python.exe" -m jarvis doctor
echo.
echo Запуск: run.bat  (текстовый режим: run.bat text)
pause
exit /b 0

:error
echo.
echo Установка прервана из-за ошибки.
pause
exit /b 1

@echo off
rem Запуск Джарвиса. Примеры: run.bat | run.bat text | run.bat doctor
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Окружение не найдено. Сначала запустите install.bat
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m jarvis %*
exit /b %errorlevel%

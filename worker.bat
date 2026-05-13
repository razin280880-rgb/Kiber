@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv" (
    echo Сначала запусти start.bat — он установит зависимости.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

echo === ИгроВАН Worker ===
echo Проверяет завершённые сессии и отправляет родителям сообщения через 1 час.
echo Запуск в непрерывном режиме. Ctrl+C — стоп.
echo.

python -m src.worker

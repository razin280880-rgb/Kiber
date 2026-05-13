@echo off
chcp 65001 >nul
echo === KIBERone IgroVAN - Trial Lesson Server ===
echo.

cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Python not found. Install Python 3.10+ from python.org
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -q -r requirements.txt

if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo .env created from template. Edit it if you need to change BASE_URL or password.
    echo.
)

echo.
echo Starting server on http://localhost:5000
echo Admin panel: http://localhost:5000/admin
echo Press Ctrl+C to stop.
echo.

python -m waitress --host=0.0.0.0 --port=5000 src.app:app

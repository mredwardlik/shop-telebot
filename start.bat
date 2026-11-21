@echo off
rem Makes a virtual environment in .env on the first run, then starts the bot
if not exist .env\Scripts\activate.bat (
    python -m venv .env
    call .env\Scripts\activate.bat
    pip install -e .
) else (
    call .env\Scripts\activate.bat
)
python -m shop_telebot
pause

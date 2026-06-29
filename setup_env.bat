@echo off
echo ==========================================
echo   MT5 Trading Bot — Environment Setup
echo ==========================================

:: Create virtual environment if not exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    echo Done.
) else (
    echo Virtual environment already exists.
)

:: Activate
echo Activating virtual environment...
call venv\Scripts\activate.bat

:: Upgrade pip silently
python -m pip install --upgrade pip --quiet

:: Install dependencies
echo Installing dependencies...
pip install MetaTrader5 pandas numpy

echo.
echo ==========================================
echo   Setup complete. venv is now active.
echo   To activate later: call venv\Scripts\activate.bat
echo   To run the bot:    python bot.py
echo   To run backtest:   python backtest.py EURUSD H1 M5 1
echo ==========================================

cmd /k

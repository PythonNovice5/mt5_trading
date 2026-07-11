@echo off
REM Auto-start launcher for the ORB bot. Runs at logon (via Startup folder).
cd /d C:\Users\Administrator\projects\mt5_trading
call venv\Scripts\activate.bat
python launch_orb.py NDX100

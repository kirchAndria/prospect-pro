@echo off
title CRM Prospection Pro
cd /d "%~dp0"
echo ==========================================
echo   CRM PROSPECTION PRO v4.5
echo ==========================================
echo Demarrage de l'application dans votre navigateur...
echo.

if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

streamlit run prospection_app.py
pause

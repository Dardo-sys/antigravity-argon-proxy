@echo off
chcp 65001 >nul
title Argon Antigravity HTTP Proxy (Port 8000)
cd /d "%~dp0"
echo ========================================================
echo   ARGON ANTIGRAVITY HTTP PROXY (gemini-4-argon)
echo   Local URL:       http://127.0.0.1:8000
echo   OpenAI Endpoint: http://127.0.0.1:8000/v1/chat/completions
echo   Native Endpoint: http://127.0.0.1:8000/api/argon
echo ========================================================
echo.
python argon_antigravity_proxy.py --mode http --port 8000
pause

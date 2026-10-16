@echo off
chcp 65001 >nul
title Consultar Gemini 4 Argon
cd /d "%~dp0"
echo ========================================================
echo   CONSULTA DIRECTA A GEMINI 4 ARGON (gemini-4-argon)
echo ========================================================
echo.
:loop
set /p PROMPT_TEXT="Escribe tu consulta para Argon (o escribe 'salir'): "
if /i "%PROMPT_TEXT%"=="salir" goto fin
if "%PROMPT_TEXT%"=="" goto loop
echo.
echo Consultando a Gemini 4 Argon (thinking_level=medium)...
echo.
python argon_antigravity_proxy.py --prompt "%PROMPT_TEXT%" --thinking-level medium
echo.
echo --------------------------------------------------------
goto loop
:fin
exit

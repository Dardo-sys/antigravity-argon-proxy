@echo off
chcp 65001 >nul
title Telemetria y Saldo Gemini 4 Argon
cd /d "%~dp0"
echo ========================================================
echo   CONSUMO Y SALDO DE CREDITO (ARGON TELEMETRY)
echo ========================================================
echo.
python -c "import json, pathlib; p=pathlib.Path.home()/'.gemini'/'argon-telemetry.json'; data=json.loads(p.read_text(encoding='utf-8')) if p.exists() else []; cost=sum(x.get('cost_usd',0) for x in data); print(f'Total llamadas registradas: {len(data)}\nCosto acumulado: ${cost:.5f} USD\nSaldo restante del credito de $10 USD: ${max(0.0, 10.0 - cost):.4f} USD')"
echo.
pause

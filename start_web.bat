@echo off
chcp 65001 > nul
echo.
echo  MermaOps -- Arrancando para pruebas web
echo  =========================================

:: Matar procesos anteriores en 8001 y 3030
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8001 " ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":3030 " ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1
timeout /t 1 /nobreak > nul

:: Backend
echo  [1/2] Arrancando backend (puerto 8001)...
start "MermaOps Backend" cmd /k "cd /d %~dp0 && python -m uvicorn backend.main:app --port 8001 --reload"
timeout /t 8 /nobreak > nul

:: Flutter web -- SIEMPRE desde app\build\web
echo  [2/2] Arrancando app web (puerto 3030)...
start "MermaOps Web" cmd /k "cd /d %~dp0app\build\web && python -m http.server 3030"
timeout /t 2 /nobreak > nul

:: Abrir Chrome
echo  Abriendo Chrome...
start chrome http://localhost:3030

echo.
echo  App:      http://localhost:3030
echo  Backend:  http://localhost:8001
echo  Telegram: @ChuwiMermaOpsBot
echo.
echo  Usuarios:
echo    Encargado: encargado@mermaops.es / Encargado2024!
echo    Staff:     demo@mermaops.es / Demo2024!
echo    Admin:     admin@mermaops.es / Admin2024!
echo.

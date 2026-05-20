@echo off
chcp 65001 > nul
echo.
echo =====================================================
echo   MermaOps -- Arranque completo
echo =====================================================

:: Cargar variables del .env
for /f "tokens=1,2 delims==" %%A in ('type .env ^| findstr /v "^#" ^| findstr "="') do (
    set "%%A=%%B"
)

:: Arrancar backend si no está corriendo
curl -s http://127.0.0.1:%APP_PORT%/health > nul 2>&1
if %errorlevel% neq 0 (
    echo   Arrancando backend en puerto %APP_PORT%...
    start /B python -m uvicorn backend.main:app --host 0.0.0.0 --port %APP_PORT% --no-access-log
    timeout /t 4 /nobreak > nul
    echo   Backend OK
) else (
    echo   Backend ya activo en puerto %APP_PORT%
)

:: Detectar dispositivo: emulador o móvil real
echo.
echo   Dispositivos disponibles:
cd app
"C:\scr\flutter\bin\flutter.bat" devices 2>nul | findstr /i "android\|emulator"
echo.

:: Preguntar tipo de dispositivo
set DEVICE_TYPE=emulator
set /p DEVICE_TYPE="   Tipo de dispositivo [emulator/phone] (Enter=emulator): "

if /i "%DEVICE_TYPE%"=="phone" (
    :: Móvil real: necesita IP local del PC en la misma red WiFi
    echo.
    echo   Para movil real: el movil y el PC deben estar en la misma WiFi.
    echo   IP local del PC:
    ipconfig | findstr "IPv4"
    echo.
    set /p LOCAL_IP="   Introduce la IP local del PC (ej: 192.168.1.50): "
    set API_HOST=!LOCAL_IP!
    set DEVICE_ARG=
    echo   Usando API_URL=http://!LOCAL_IP!:%APP_PORT%/api/v1
) else (
    :: Emulador Android: usa 10.0.2.2 para acceder al host
    set API_HOST=10.0.2.2
    set DEVICE_ARG=-d emulator-5554
    echo   Usando API_URL=http://10.0.2.2:%APP_PORT%/api/v1
)

echo.
echo   Lanzando app Flutter...
echo   Supabase: %SUPABASE_URL%
echo.

setlocal enabledelayedexpansion
"C:\scr\flutter\bin\flutter.bat" run %DEVICE_ARG% ^
  --dart-define=SUPABASE_URL=%SUPABASE_URL% ^
  --dart-define=SUPABASE_ANON_KEY=%SUPABASE_ANON_KEY% ^
  "--dart-define=API_URL=http://!API_HOST!:%APP_PORT%/api/v1"
endlocal

cd ..

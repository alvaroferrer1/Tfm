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

:: Lanzar app Flutter en emulador
echo   Lanzando app en emulador...
echo   Supabase: %SUPABASE_URL%
echo   API:      http://10.0.2.2:%APP_PORT%/api/v1
echo.

cd app
flutter run -d emulator-5554 ^
  --dart-define=SUPABASE_URL=%SUPABASE_URL% ^
  --dart-define=SUPABASE_ANON_KEY=%SUPABASE_ANON_KEY% ^
  "--dart-define=API_URL=http://10.0.2.2:%APP_PORT%/api/v1"

cd ..

@echo off
setlocal EnableExtensions
title Sesame Companion Launcher
cd /d "%~dp0"

REM 8GB RAM safeguards so Ollama only keeps 1 compact model in memory
set "OLLAMA_NUM_PARALLEL=1"
set "OLLAMA_MAX_LOADED_MODELS=1"

REM Defaults if not set in .env
set "SESAME_ROBOT_IP=192.168.1.1"
set "AI_PROVIDER=auto"
set "OLLAMA_MODEL=qwen2.5:0.5b"

REM Read fresh settings from .env every launch (supports Wi-Fi / Hotspot IP updates)
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
        if /i "%%A"=="SESAME_ROBOT_IP" set "SESAME_ROBOT_IP=%%B"
        if /i "%%A"=="AI_PROVIDER" set "AI_PROVIDER=%%B"
        if /i "%%A"=="OLLAMA_MODEL" set "OLLAMA_MODEL=%%B"
    )
)

echo ============================================================
echo   Sesame Robot Companion — Exhibition Launcher
echo ============================================================
echo   Robot Wi-Fi IP (.env) : %SESAME_ROBOT_IP%
echo   AI Brain Mode         : %AI_PROVIDER%
echo   Offline Ollama Model  : %OLLAMA_MODEL%
echo ============================================================
echo.

REM Locate Ollama CLI (works even before Windows refreshes PATH after winget install)
set "OLLAMA_EXE="
where ollama >nul 2>nul && set "OLLAMA_EXE=ollama"
if "%OLLAMA_EXE%"=="" (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
)
if "%OLLAMA_EXE%"=="" (
    if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_EXE=%ProgramFiles%\Ollama\ollama.exe"
)

if /i not "%AI_PROVIDER%"=="groq" (
    if not "%OLLAMA_EXE%"=="" (
        echo [Local AI] Checking Ollama service...
        powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"
        if errorlevel 1 (
            echo [Local AI] Starting Ollama background server...
            start "" /min "%OLLAMA_EXE%" serve
            timeout /t 3 /nobreak >nul
        )

        "%OLLAMA_EXE%" list | findstr /i /c:"%OLLAMA_MODEL%" >nul 2>nul
        if errorlevel 1 (
            echo [Local AI] Pulling compact offline model %OLLAMA_MODEL% ^(one-time ~397 MB download^)...
            "%OLLAMA_EXE%" pull %OLLAMA_MODEL%
        ) else (
            echo [Local AI] Offline model %OLLAMA_MODEL% is ready!
        )
    ) else (
        echo [Note] Ollama is not installed yet — cloud / keyword fallback remains active.
    )
)

echo.
echo [Launch] Starting Sesame Companion App...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" app.py
) else (
    python app.py
)

if errorlevel 1 (
    echo.
    echo [Error] Sesame exited unexpectedly. Press any key to close.
    pause >nul
)


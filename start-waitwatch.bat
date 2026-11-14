@echo off
setlocal

title WaitWatch Startup

:: ============================================================================
:: WaitWatch - One-Click Windows Startup Script
::
:: This script safely checks Docker Desktop and launches the WaitWatch stack:
:: - PostgreSQL (PostGIS) database with existing persistent volume
:: - FastAPI backend service
:: - React + Vite frontend application
::
:: Safety guarantee: This script only runs 'docker compose up -d'. It never
:: deletes, prunes, or recreates persistent volumes or database data.
:: ============================================================================

:: 1. Navigate to the WaitWatch directory regardless of where the batch file is invoked from
cd /d "%~dp0"

echo ======================================================================
echo                  WaitWatch - Starting Application
echo ======================================================================
echo.

:: 2. Check whether Docker CLI is available in PATH or known install locations
where docker >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe" (
        set "PATH=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin;%PATH%"
    ) else if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" (
        set "PATH=%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
    )
)

where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI was not found in your PATH or standard install folders.
    echo Please verify that Docker Desktop is installed on this system.
    echo.
    goto :fail
)

:: 3. Check whether the Docker Engine is running
echo [1/4] Checking Docker Engine status...
docker info >nul 2>&1
if not errorlevel 1 (
    echo [OK] Docker Engine is already running.
    goto :docker_ready
)

:: 4. If Docker Engine is not running, attempt to launch Docker Desktop
echo [INFO] Docker Engine is not running. Attempting to start Docker Desktop...

set "DOCKER_DESKTOP_EXE="
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe" (
    set "DOCKER_DESKTOP_EXE=%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
) else if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
    set "DOCKER_DESKTOP_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
)

if not defined DOCKER_DESKTOP_EXE (
    echo [ERROR] Could not find Docker Desktop executable.
    echo Expected location: "%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe"
    echo Please start Docker Desktop manually and run this script again.
    echo.
    goto :fail
)

echo Starting Docker Desktop from:
echo   "%DOCKER_DESKTOP_EXE%"
start "" "%DOCKER_DESKTOP_EXE%"

echo Waiting for Docker Engine to become ready (timeout: ~120s)...
set /a ELAPSED=0
set /a TIMEOUT=120
set /a INTERVAL=3

:wait_for_docker
timeout /t %INTERVAL% /nobreak >nul 2>&1 || ping -n 4 127.0.0.1 >nul
set /a ELAPSED+=%INTERVAL%

docker info >nul 2>&1
if not errorlevel 1 (
    echo [OK] Docker Engine is ready! (took ~%ELAPSED%s)
    goto :docker_ready
)

if %ELAPSED% geq %TIMEOUT% (
    echo.
    echo [ERROR] Timed out waiting for Docker Engine to start (%TIMEOUT%s elapsed).
    echo Docker Desktop may still be initializing or require manual attention.
    echo Please open Docker Desktop manually, ensure it shows "Engine running",
    echo and then re-run this script.
    echo.
    goto :fail
)

echo ... waiting for Docker daemon (%ELAPSED%s / %TIMEOUT%s)
goto :wait_for_docker

:docker_ready
echo.
:: 5. Execute docker compose up -d (starts existing containers without volume loss)
echo [2/4] Starting WaitWatch containers (docker compose up -d)...
docker compose up -d
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start Docker Compose services.
    echo Please check the error messages above.
    echo.
    goto :fail
)

:: 6. Check the status of Compose services
echo.
echo [3/4] Current container status:
docker compose ps
echo.

:: 7. Wait briefly for application readiness
echo [4/4] Verifying application readiness...
echo Waiting for backend API (http://localhost:8000/api/health) and frontend (http://localhost:3000)...

set /a HEALTH_ELAPSED=0
set /a HEALTH_TIMEOUT=45
set /a HEALTH_INTERVAL=2

:check_health
set "BACKEND_OK=0"
set "FRONTEND_OK=0"

where curl >nul 2>&1
if not errorlevel 1 (
    curl.exe -s -f http://localhost:8000/api/health >nul 2>&1
    if not errorlevel 1 set "BACKEND_OK=1"
    curl.exe -s -f http://localhost:3000 >nul 2>&1
    if not errorlevel 1 set "FRONTEND_OK=1"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $h = Invoke-RestMethod -Uri 'http://localhost:8000/api/health' -TimeoutSec 2 -ErrorAction Stop; if ($h.status -eq 'healthy') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 set "BACKEND_OK=1"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $w = Invoke-WebRequest -Uri 'http://localhost:3000' -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop; if ($w.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 set "FRONTEND_OK=1"
)

if "%BACKEND_OK%"=="1" if "%FRONTEND_OK%"=="1" (
    echo [OK] Backend API is healthy and Frontend is accessible!
    goto :app_ready
)

if %HEALTH_ELAPSED% geq %HEALTH_TIMEOUT% (
    echo [WARNING] Application started, but readiness verification timed out.
    echo The services may still be finishing initialization in the background.
    goto :app_ready
)

timeout /t %HEALTH_INTERVAL% /nobreak >nul 2>&1 || ping -n 3 127.0.0.1 >nul
set /a HEALTH_ELAPSED+=%HEALTH_INTERVAL%
echo ... waiting for services (%HEALTH_ELAPSED%s / %HEALTH_TIMEOUT%s)
goto :check_health

:app_ready
echo.
echo ======================================================================
echo                  WaitWatch is Ready!
echo ======================================================================
echo.
echo   Frontend Web Application:  http://localhost:3000
echo   Backend API Health Check:  http://localhost:8000/api/health
echo   Interactive API Docs:      http://localhost:8000/docs
echo.
echo Opening WaitWatch in your default web browser...
start http://localhost:3000

echo.
echo Press any key to close this window (WaitWatch containers will keep running).
pause >nul
exit /b 0

:fail
echo.
echo ======================================================================
echo                  Startup Failed
echo ======================================================================
echo.
echo Please review the error details above.
echo.
pause
exit /b 1

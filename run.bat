@echo off
setlocal enabledelayedexpansion

echo ===================================================
echo     Aileron - Touchless Input Controller (v0.1.0-rc1)
echo     Platforms: Windows 10/11 & Linux
echo ===================================================
echo.

:: Check for uv runner
where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [INFO] Using uv runner...
    if "%~1"=="" (
        echo [INFO] Starting in safe dry-run mode (--backend null --debug)...
        echo [INFO] Pass --live to engage OS mouse/keyboard, or --gamepad-test for axis monitor.
        uv run aileron --backend null --debug
    ) else if "%~1"=="--live" (
        echo [WARNING] Arming live input backend! Starts DISARMED. Hold open palm to arm.
        shift
        uv run aileron %*
    ) else (
        uv run aileron %*
    )
    goto :end
)

:: Fallback to python
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo [INFO] uv not found, using python...
    if "%~1"=="" (
        python -m aileron --backend null --debug
    ) else if "%~1"=="--live" (
        shift
        python -m aileron %*
    ) else (
        python -m aileron %*
    )
    goto :end
)

echo [ERROR] Neither 'uv' nor 'python' was found in PATH.
echo Please install Python 3.11+ or uv (https://astral.sh/uv).
pause
exit /b 1

:end
endlocal

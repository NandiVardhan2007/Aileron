@echo off
setlocal

echo ===================================================
echo     Aileron - Touchless Input Controller (v0.1.0-rc1)
echo     Platform: Windows 10/11 (64-bit)
echo ===================================================
echo.

if "%~1"=="" (
    echo [INFO] Launching safe preview mode (NullBackend).
    echo [INFO] To arm live input, run: run.bat --live
    uv run aileron --backend null --debug
    goto :end
)

if /i "%~1"=="--live" (
    echo [WARNING] Arming live input backend! Starts DISARMED. Hold open palm to arm.
    shift
    uv run aileron --backend auto %*
    goto :end
)

uv run aileron %*

:end
endlocal

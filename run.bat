@echo off
setlocal

echo ===================================================
echo     Aileron - Touchless Input Controller v0.1.0-rc1
echo     Platform: Windows 10/11 64-bit
echo ===================================================
echo.

if "%~1"=="" goto :dry_run
if /i "%~1"=="--live" goto :live_run

uv run aileron %*
goto :end

:dry_run
echo [INFO] Launching safe preview mode with NullBackend
echo [INFO] To arm live input, run: run.bat --live
uv run aileron --backend null --debug
goto :end

:live_run
echo [WARNING] Arming live input backend! Starts DISARMED. Hold open palm to arm.
shift
uv run aileron --backend auto %*
goto :end

:end
endlocal

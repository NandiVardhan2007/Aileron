#!/usr/bin/env bash
# ==============================================================================
# Aileron — Touchless Air-Mouse and Simulator Flight-Deck Launcher (Linux)
# ==============================================================================
set -euo pipefail

echo "==================================================="
echo "    Aileron - Touchless Input Controller (v0.1.0-rc1)"
echo "    Target: Linux (X11 / Wayland via uinput)"
echo "==================================================="
echo ""

# Check for /dev/uinput write permissions for gamepad/mouse emulation
if [ -e /dev/uinput ] && [ ! -w /dev/uinput ]; then
    echo "[NOTICE] /dev/uinput exists but is not writable by current user ($USER)."
    echo "         To enable live input emulation without root, configure udev rules:"
    echo "         echo 'KERNEL==\"uinput\", MODE=\"0660\", GROUP=\"input\"' | sudo tee /etc/udev/rules.d/99-uinput.rules"
    echo "         sudo usermod -aG input \$USER"
    echo "         (Running with --backend null or keyboard fallback remains fully functional)"
    echo ""
fi

# Detect runner
if command -v uv >/dev/null 2>&1; then
    if [ $# -eq 0 ]; then
        echo "[INFO] Starting safe dry-run mode (--backend null --debug)..."
        echo "[INFO] Pass --live to engage OS mouse/keyboard, or --gamepad-test for axis viewer."
        exec uv run aileron --backend null --debug
    elif [ "$1" = "--live" ]; then
        echo "[WARNING] Arming live input backend! Starts DISARMED. Hold open palm to arm."
        shift
        exec uv run aileron "$@"
    else
        exec uv run aileron "$@"
    fi
elif command -v python3 >/dev/null 2>&1; then
    if [ $# -eq 0 ]; then
        echo "[INFO] Starting safe dry-run mode (--backend null --debug)..."
        exec python3 -m aileron --backend null --debug
    elif [ "$1" = "--live" ]; then
        shift
        exec python3 -m aileron "$@"
    else
        exec python3 -m aileron "$@"
    fi
else
    echo "[ERROR] Neither 'uv' nor 'python3' was found in PATH."
    echo "Please install Python 3.11+ or uv (https://astral.sh/uv)."
    exit 1
fi

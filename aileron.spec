# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for Aileron (M7).

Bundles:
- Core executable entry point: aileron.__main__
- Default configuration: config/defaults.toml
- Computer vision assets: models/hand_landmarker.task (if present)
- Output backend plugins and dependencies
"""

import os
from pathlib import Path

block_cipher = None

repo_root = Path(os.path.abspath(".")).resolve()

datas = [
    (str(repo_root / "config" / "defaults.toml"), "config"),
]

model_path = repo_root / "models" / "hand_landmarker.task"
if model_path.exists():
    datas.append((str(model_path), "models"))

hidden_imports = [
    "cv2",
    "numpy",
    "pydantic",
    "pynput",
    "aileron",
    "aileron.capture",
    "aileron.control",
    "aileron.features.extraction",
    "aileron.gestures.dwell",
    "aileron.gestures.engine",
    "aileron.gestures.pinch",
    "aileron.gestures.scroll",
    "aileron.gestures.zoom",
    "aileron.modes.cockpit",
    "aileron.modes.handlebar",
    "aileron.modes.manager",
    "aileron.modes.session",
    "aileron.modes.yoke",
    "aileron.output.base",
    "aileron.output.gamepad",
    "aileron.output.null",
    "aileron.output.windows",
    "aileron.plugins",
    "aileron.profiles",
    "aileron.safety.blackbox",
    "aileron.safety.gate",
    "aileron.safety.kill_switch",
    "aileron.safety.ledger",
    "aileron.safety.watchdog",
    "aileron.ui.hud",
]

a = Analysis(
    [str(repo_root / "src" / "aileron" / "__main__.py")],
    pathex=[str(repo_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="aileron",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="aileron",
)

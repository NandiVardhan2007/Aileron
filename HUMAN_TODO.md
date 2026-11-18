# HUMAN_TODO.md — Human Verification & Hardware Checklists

> Items that require a human operator, physical devices, user studies, or external administrative actions.
> Do NOT mark these complete in automated CI or mock runs.

## 1. Physical Hardware & Safety Sign-Off (SAFETY §8)
Before arming real OS mouse/keyboard or virtual gamepad output on production machines, perform these checks:
- [ ] **Kill Switch Verification:** Press `Ctrl+Alt+Esc` while moving hands vigorously; verify all cursor motion stops within 1 frame and inputs are disarmed.
- [ ] **Kill Switch Under CPU Load:** Run synthetic CPU stress test (100% core load); verify `Ctrl+Alt+Esc` fires reliably.
- [ ] **Physical Camera Disconnect:** Unplug USB webcam mid-drag and mid-throttle; assert cursor freezes, drag releases, and gamepad axes return to 0 within 160 ms.
- [ ] **Process Termination (`taskkill /F /IM python.exe`):** Terminate process mid-drag; verify OS does not retain stuck mouse button.
- [ ] **Camera Occlusion:** Cover webcam lens with palm; verify state switches to neutralized/searching within 150 ms.
- [ ] **Multi-Person Interference:** Introduce a second person into camera frame; verify primary hand lock persists and does not jump.
- [ ] **Display Geometry Changes:** Connect/disconnect external monitor or change display scaling (DPI); verify virtual desktop mapping recalculates cleanly.

## 2. Driver & Environment Setup
- [ ] **Virtual Gamepad Driver Choice & Installation:** Review ViGEmBus status (PRD R4, ADR-005) or install Nefarius ViGEmBus driver on Windows with Administrator privileges.
- [ ] **OS Permissions:**
  - macOS: Grant Accessibility (for CGEvent) and Input Monitoring (for global hotkey).
  - Linux: Set udev rules for `/dev/uinput` to allow non-root input injection.

## 3. Real-World Calibration & Demographic Testing
- [ ] **Varied Lighting Conditions:** Test in low light (<50 lux), fluorescent office lighting, and direct sunlight/backlit windows.
- [ ] **Demographic & Ergonomic Diversity:** Test with diverse skin tones, hand sizes, jewelry, and eyeglasses.
- [ ] **Ergonomic Fatigue Evaluation:** Conduct 15-minute usage test; collect Borg CR10 perceived exertion score (target ≤ 5/10).

## 4. User Studies (TESTING §7)
- [ ] **ISO 9241-9 Fitts' Law Pointing Test:** Run `tools/fitts_test.py` with 12+ participants (target throughput ≥ 2.0 bits/s).
- [ ] **Accidental Action Audit:** Conduct 15-minute productivity task (target ≤ 1 accidental click/drag per 10 min).
- [ ] **Simulator Lap Benchmark:** Drive reference lap in racing sim (Assetto Corsa / Live for Speed / Forza) comparing Aileron Yoke vs physical Xbox controller (target within 120% of baseline lap time).
- [ ] **First-Time User Onboarding:** Test onboarding wizard with novice users (target ≤ 5 min to first successful click).

## 5. Release & Legal Preparation
- [ ] **Code Signing Certificate:** Obtain code-signing certificate for Windows installer and PyInstaller binaries.
- [ ] **Trademark & Name Clearance:** Check "Aileron" trademark in relevant software/input device classes (BRANDING.md).
- [ ] **License Selection:** Finalize open-source license (MIT vs Apache-2.0).

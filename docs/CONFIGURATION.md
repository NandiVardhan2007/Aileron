# Configuration Reference — Aileron

Settings are TOML. Layers (later wins): **`config/defaults.toml` → user profile (`config/profiles/<name>.toml`) → CLI flags**.
Validation is done by Pydantic models at startup; invalid values fail fast with a message naming the key and range
(`CFG-02`). `schema_version` enables migrations (`CFG-03`).

`config/defaults.toml` is the **single source of truth** for default values; this table explains meaning and
safe ranges. CI verifies they match (`DOC-03`).

## Sections

| Section | Key | Meaning | Range / options |
|---------|-----|---------|-----------------|
| camera | `fps`, `width`, `height` | Requested capture format | 15–120, 640–1920 |
| camera | `mirror` | Mirror once at capture | true recommended |
| tracking | `hand_lost_ms` | Time without a valid hand before neutralizing | 80–500 (safety-relevant, do not exceed 300 without warning) |
| tracking | `min_hand_conf` | Minimum confidence to accept a hand | 0.3–0.95 |
| tracking | `primary_hand` | Which hand may control the pointer | either/left/right |
| loop | `tick_hz` | Control loop rate | 60–240 |
| filters.* | `min_cutoff`, `beta`, `d_cutoff` | One Euro params per channel | Lower `min_cutoff` = smoother/laggier; higher `beta` = less lag when moving fast |
| pointer | `mode` | Absolute or trackpad-like relative | absolute/relative |
| pointer | `region_*` | Camera area mapped to the screen | w,h 0.3–0.9 |
| pointer | `gamma` | Edge/center gain curve | 0.8–2.0 |
| click | `pinch_on/off` | Hysteresis thresholds in palm sizes | on < off; gap ≥ 0.06 |
| click | `tap_ms`, `dbl_ms` | Tap/hold and double-click windows | 150–600 |
| click | `max_clicks_per_s` | Rate limit (safety) | 2–15 |
| scroll | `deadzone`, `gain`, `power`, `max_lines_per_s` | Displacement → scroll rate shape | |
| zoom | `step_fraction`, `method` | Sensitivity and key mapping | 0.03–0.15 |
| fingers | `theta_*`, `ext_*` | Finger extension mapping and hysteresis | ext_on > ext_off |
| session | `start_armed` | Start armed (not recommended) | false by default |
| session | `*_ms` | Dwell times for gestures | 200–1500 |
| session | `kill_switch_hotkey` | Global stop | any chord |
| cockpit | `profile`, `on_loss`, `neutral_hold_ms`, `ramp_in_ms` | Cockpit behavior and safety | |
| cockpit.yoke / handlebar | `steer_*`, `*_source`, `trigger_*` | Axis shaping and sources | |
| cockpit.buttons | gear/handbrake/horn | Pinch combo bindings | |
| ui | `hud`, `hud_mode`, `reduced_motion`, `audio_cues` | HUD behavior | |
| accessibility | `stability_mode`, `dwell_click` | Tremor/pinch-free options | |
| blackbox | `enabled`, `seconds`, `dump_on_fault` | Landmark ring buffer | opt-in |
| privacy | `network` | Must stay false | |

## Profiles
A profile contains only overrides plus calibration results:

```toml
# config/profiles/arjun.toml
schema_version = 1
[pointer]
region_w = 0.55
[click]
pinch_on = 0.22
pinch_off = 0.32
[cockpit.yoke]
steer_max_deg = 52.0
[calibration]
theta_neutral_deg = -1.4
right_index_ext_min = 0.12
right_index_ext_max = 0.93
left_index_ext_min = 0.10
left_index_ext_max = 0.90
```

## CLI flags (selection)
`--backend {auto,null,mouse,gamepad}` · `--profile NAME` · `--debug` · `--replay FILE` · `--record FILE` ·
`--no-hud` · `--gamepad-test` · `--panic` · `--print-config`

## Environment variables
`AILERON_CONFIG_DIR`, `AILERON_LOG_LEVEL`, `AILERON_MODEL_PATH`.

## Changing defaults
A default change is a behavior change: update `defaults.toml`, this file, `CHANGELOG.md`, and re-run replay tests.

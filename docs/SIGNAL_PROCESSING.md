# Signal Processing and Math — Aileron

All formulas operate on MediaPipe landmarks (`Lm` indices). Values in **bold** are config parameters.

## 1. Normalization

**Palm size** (scale unit):
`palm_size = ½ · (‖L0 − L9‖ + ‖L5 − L17‖)` using image-normalized x,y (aspect-corrected: multiply x by `width/height`).

Every distance threshold is expressed in `palm_size` units so behavior is constant at any distance from the
camera. If `palm_size < `**`min_palm_size`** (hand too far) the hand is flagged `valid=False` and the HUD shows "move closer".

## 2. Finger extension

Use **world landmarks** (metric 3D) to avoid foreshortening. For a joint B with neighbors A and C:

```
θ(A,B,C) = arccos( (A−B)·(C−B) / (‖A−B‖·‖C−B‖) )
```

For each finger take the PIP and DIP joint angles (`θ_pip`, `θ_dip`), average them, then map to 0..1:

```
ext = clamp( (θ̄ − θ_curled) / (θ_straight − θ_curled), 0, 1 )
```

Defaults: `θ_curled = 70°`, `θ_straight = 170°` (replaced by calibrated per-user values, `GEST-08`).
A finger is **extended** when `ext > ext_on (0.75)` and **curled** when `ext < ext_off (0.35)` (hysteresis).
Thumb uses the angle at MCP/IP plus distance from the thumb tip to the index MCP (in palm sizes).

## 3. Pinch ratios

```
pinch_index  = ‖L4 − L8‖  / palm_size
pinch_middle = ‖L4 − L12‖ / palm_size
pinch_ring   = ‖L4 − L16‖ / palm_size
pinch_pinky  = ‖L4 − L20‖ / palm_size
```
Pinch **on** at `< 0.25`, **off** at `> 0.35` (defaults). Use 3D world distance when available; fall back to 2D.

## 4. Cursor pipeline (Pointer mode)

1. **Anchor:** `a = ½ (L5 + L9)` (image-normalized).
2. **Active region** (**region_w=0.6, region_h=0.5, region_cx=0.5, region_cy=0.55**): `u = clamp((a.x − x0)/region_w, 0, 1)`, `v` likewise. Frames are already mirrored, so no extra x-flip.
3. **Filter** `u, v` with One Euro (§5).
4. **Optional gain curve:** `u' = 0.5 + sign(u−0.5)·|2(u−0.5)|^γ / 2` with **gamma** (1.0 = linear; >1 gives finer control near the center, fast at the edges).
5. **Absolute mode:** map to the virtual desktop `(X, Y) = (vx + u'·vw, vy + v'·vh)` in physical pixels (DPI-aware, multi-monitor via virtual screen bounds).
   **Relative mode:** `ΔX = k · Δu'`, with `k = `**relative_gain** and a speed-dependent acceleration `k(s) = k0·(1 + **accel**·s)`; the region re-centers on re-engage.
6. **Click freeze:** between pinch-down and release (or drag threshold), hold the output at the pre-pinch position (or damp by **freeze_damping**).
7. **Clamp** to desktop bounds and emit `MoveTo` / `MoveBy` only when the change exceeds **min_move_px** (default 1 px).

## 5. One Euro filter

Adaptive low-pass: heavy smoothing when slow (kills jitter), light smoothing when fast (kills lag).

```
Te      = t − t_prev                      (seconds, from timestamps)
α(fc)   = 1 / (1 + τ/Te),  τ = 1/(2π·fc)
dx̂      = α(d_cutoff)·(Δx/Te) + (1 − α(d_cutoff))·dx̂_prev
fc      = min_cutoff + beta·|dx̂|
x̂       = α(fc)·x + (1 − α(fc))·x̂_prev
```

Starting points for normalized coordinates (speed in units/s): **min_cutoff = 1.2 Hz, beta = 8.0, d_cutoff = 1.0 Hz**.
Tune with `tools/tune_filters.py` (plots lag vs. jitter on recorded sessions). Separate parameter sets for
cursor, scroll anchor, steering, trigger channels. The filter **resets on hand loss** to avoid a smeared jump
when the hand reappears.

Do not use fixed-window moving averages for the cursor (constant lag, `rules.md` SIG-05).

## 6. Scroll (V-sign)

Joystick-style, not swipe-style: on gesture start store the anchor `a0`. Displacement `d = a − a0` (in palm sizes)
drives the rate:

```
rate_lines_per_s = sign(d) · gain · curve(max(|d| − deadzone, 0))
curve(x) = x^p          (p ≈ 1.5 default: slow start, fast when pushed)
```
Parameters: **scroll_deadzone=0.15, scroll_gain=40, scroll_power=1.5, scroll_max=60 lines/s**. Moving back to `a0` stops
scrolling, so no repeated swiping is needed. Horizontal scroll uses the x component with its own gain.

## 7. Zoom (two hands pinching)

Both hands in pinch-index state. Let `D` = distance between the two pinch midpoints (in the larger `palm_size` units).
At zoom start store `D0`. Emit one `Zoom(±1)` per **zoom_step (6%)** change of `D/D0`; then rebase `D0 ← D`.
Direction: spreading = zoom in. Sent as Ctrl + wheel up/down (app-dependent; configurable alternative: Ctrl +/−).

## 8. Steering angle (Cockpit / Yoke)

With both hands tracked: `P_L = L9 of left hand`, `P_R = L9 of right hand` in image coordinates (y down).

```
θ_wheel = atan2(P_R.y − P_L.y,  (P_R.x − P_L.x)·aspect) in degrees      # + = clockwise as the user sees it
θ_adj   = θ_wheel − θ_neutral                                         # from pre-flight calibration
steer   = curve_expo( deadzone(θ_adj, **steer_dz=3°**) / **steer_max=45°**, **steer_expo=0.35** )   → [-1, 1]
```
`curve_expo(x) = (1−e)·x + e·x³` (e in 0..1; higher = softer near center). Clamp to ±1 and filter with the One Euro
steering profile (lower `min_cutoff`, small `beta`).

**Hand-height fallback:** when only one hand is visible, Yoke profile holds the last steer value for 150 ms, then
neutralizes (`SAFE-02`); it does not guess.

## 9. Handlebar roll (single hand)

```
v      = world[L9] − world[L0]                    # wrist → middle knuckle (3D)
roll   = atan2(v.x, −v.y) in degrees               # 0 = fingers up, + = tilted right
```
Then the same neutral/deadzone/expo steps as §8 with **handlebar_max=35°**.

## 10. Throttle and brake (trigger fingers)

```
throttle = curve( clamp((ext_index − ext_min) / (ext_max − ext_min), 0, 1), **trigger_curve** )
```
`ext_min/ext_max` are the user's calibrated curled/extended values for that finger. Filter with a **fast** One Euro
profile (triggers need low lag) and apply a small **trigger_deadzone=0.05** so a relaxed hand is exactly zero.

## 11. Confidence and validity gating
- Frame accepted if `hand.score ≥ `**min_hand_conf (0.6)** and `palm_size ≥ min_palm_size` and all values finite.
- Rejected frames count as "no hand" for the `hand_lost_ms` timer (`SAFE-02`); they are **never** used as degraded data.
- **Primary hand selection:** when multiple hands are present in Pointer mode, lock to the hand that first engaged (sticky) until it is lost for > `hand_lost_ms`; ties broken by larger `palm_size`.

## 12. Timing rules
- All durations/velocities use timestamps, never frame counts (`SIG-07`).
- Filters compute `Te` from actual timestamps and clamp it to `[1 ms, 100 ms]` to survive stalls.
- Gesture dwell timers pause (not reset) for up to **dwell_grace_ms=100** of lost frames, then reset.

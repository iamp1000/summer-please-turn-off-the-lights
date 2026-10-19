# Tapo L930 Firmware Effect Lab Findings & Calibration Report

This document records the reverse-engineered parameters, hardware behaviors, and exact firmware schemas supported by the **Tapo L930 (50-zone addressable WRGBIC)** onboard microcontroller.

---

## 1. Executive Summary

The Tapo L930 onboard microcontroller has a built-in animation engine capable of running complex multi-zone effects autonomously in firmware.
* **Firmware Loops**: Once uploaded, the microcontroller loops sequences or pseudorandom patterns indefinitely. It requires **zero network traffic** and does not burden the PC, Wi-Fi link, or device processor.
* **Network Flooding Protection**: Rapid streaming commands flood the micro-controller's TCP buffer and can knock the strip offline. Replacing repeating animations with native firmware loops guarantees buttery-smooth 60+ FPS hardware rendering while eliminating connection drops.

---

## 2. Firmware Parameter Mapping & Behavior on 50 Segments

From automated testing with `src/effect_lab.py` and direct hardware interrogation:

### Sequence Effects (`type: "sequence"`)
1. **Sequence Array (`sequence`)**:
   * Accepts **up to 16 HSV color stops**: `[[H, S, V], ...]`.
   * $H \in [0, 360]$, $S \in [0, 100]$, $V \in [0, 100]$.
   * If more than 16 colors are provided, the firmware discards or truncates the sequence.
2. **Spread (`spread`)**:
   * Defines the **spatial wavelength (zone width)** of each color stop across the 50 addressable segments.
   * `spread = 1`: Each color occupies 1 segment (dense, rapid repetition).
   * `spread = 7`: Ideal wave width (7 segments per color stop, giving ~7 complete color cycles across 50 zones).
   * `spread = 12..16`: Broad oceanic or aurora gradient curtains spanning 1/3 to 1/2 of the backboard.
3. **Direction (`direction`)**:
   * `direction = 1`: Left to Right ($\to$ forward motion).
   * `direction = 2`: Right to Left ($\leftarrow$ reverse motion).
   * `direction = 3`: Center Outward ($\leftarrow \text{Center} \to$ symmetrical expansion).
   * `direction = 4`: Edges Inward ($\to \text{Center} \leftarrow$ inward collapse).
4. **Transition (`transition`)**:
   * Speed of color interpolation between adjacent segments in milliseconds: `0 <= transition <= 6000`.
   * `transition = 100..400`: Fast, energetic motion (chases, sweeps, pulses).
   * `transition = 1000..2000`: Flowing natural currents (waves, aurora).
   * `transition = 4000..6000`: Ultra-slow, serene ambient glides (Drift, Tide).
5. **Repeat Times (`repeat_times`)**:
   * `repeat_times = 0`: Continuous, infinite loop.
   * `repeat_times > 0`: Finite run count (used for Sunrise / Sunset alarm sequences).
6. **Expansion Strategy (`expansion_strategy`)**:
   * `1`: Smooth spatial wrapping and linear interpolation across the segment boundaries.
   * `2`: Phased pulse/dilation wave.

---

### Random Effects (`type: "random"`)
1. **Target Segments (`segments`)**:
   * `segments = [0]`: Applies random algorithm uniformly across all zones.
   * `segments = [...]`: Pinpoints specific zones (e.g. Lightning strikes or spark positions).
2. **Hue & Saturation Ranges**:
   * `hue_range = [min_h, max_h]`: Constrains generated hues (e.g. `[180, 240]` for cool stars; `[15, 35]` for warm embers).
   * `saturation_range = [min_s, max_s]`: Controls pastel vs vivid coloration.
   * `brightness_range = [min_b, max_b]`: Sets twinkle depth (e.g. `[0, 80]` allows LEDs to completely extinguish between flashes).
3. **Fadeoff & Transitions**:
   * `fadeoff`: Decay/falloff duration in ms before the LED fades back to baseline.
   * `transition_range = [min_t, max_t]`: Randomizes attack and swell speeds across different zones.
4. **Random Seed (`random_seed`)**:
   * Valid range: `1 <= seed <= 600`.
   * Governs the pseudo-random number generator sequence on the microcontroller. Different seeds produce distinct spatial twinkle patterns.

---

## 3. Native Preset Templates Extracted from Hardware

The following exact JSON payloads were retrieved directly from the L930 hardware:

| Preset Name | Type | Direction | Spread | Transition (ms) | Sequence / Ranges |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Rainbow** | `sequence` | `1` | `12` | `1500` | `[[0,100,100], [100,100,100], [200,100,100], [300,100,100]]` |
| **Aurora** | `sequence` | `4` | `7` | `1500` | `[[120,100,100], [240,100,100], [260,100,100], [280,100,100]]` |
| **Ocean** | `sequence` | `3` | `16` | `2000` | `[[198,84,30], [198,70,30], [198,10,30]]` |
| **Lightning** | `random` | - | - | `50` | `hue:[240,240], sat:[10,11], bright:[90,100], seed:600, fadeoff:150` |
| **Raindrop** | `random` | - | - | `1000` | `hue:[200,200], sat:[10,20], bright:[10,30], seed:24, fadeoff:1000` |
| **Flicker** | `random` | - | - | `375..500` | `hue:[30,40], sat:[100,100], bright:[50,100], seed:1` |
| **Candy Cane** | `sequence` | `1` | `1` | `500` | Peppermint red and white 16-zone repeating pattern |
| **Haunted Mansion** | `random` | - | - | `50..1500`| `hue:[45,45], sat:[10,10], bright:[0,80], seed:1, fadeoff:200` |
| **Icicle** | `sequence` | `4` | `3` | `400` | `[[190,100,70], [190,100,70], [190,30,50], [190,100,70]]` |

---

## 4. Effect Architecture Rules

Every effect in the system is strictly classified into one of three execution categories:

1. **`firmware`**:
   * Uploaded **once** when selected or when the user changes a parameter (speed, brightness, palette).
   * Loops on the strip's internal microcontroller with **zero continuous PC network traffic**.
   * Streaming sender thread is completely paused/idle.
   * Parameter updates are throttled to at most once per 2 seconds.
2. **`streamed_slow`**:
   * For complex procedural models requiring algorithmic calculations (e.g., Lava Lamp metaballs, Fire2012 fluid simulation, Dusk circadian drift).
   * Streamed at $\le 2$ updates/s with `transition_ms` roughly matching the update interval so the hardware LED driver handles the inter-frame fading.
3. **`live`**:
   * Music and Movie modes only. Operates at the safety rate cap with instant hardware transitions.

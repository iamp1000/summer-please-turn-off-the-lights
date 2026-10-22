# Effect Catalog: Motion Models and GUI Behavior

This document records intentional differences between effects so new modes do not become near-duplicates.

## L930 effect models

| Effect | Execution | Visual behavior |
|---|---|---|
| Tide | Firmware sequence | Deliberate traveling, layered ocean wave |
| Drift | Firmware random | Low-energy per-IC changes with slow independent fades |
| Deep Ocean | Firmware random | Deep blue/green shimmer at low brightness with long transitions |
| Flicker | Native firmware random | Warm candle/fire micro-fluctuation, not a traveling effect |
| Starfield | Firmware random | Sparse cool-white twinkles over a near-black background |
| Embers | Firmware random | Slow amber points with long fades |
| Fireflies | Firmware random | Independent green/gold pulses |
| Prism Sparks | Firmware random | Brief high-saturation sparkles with short fades |
| Lava Lamp | Procedural stream | Four color-distinct moving metaballs with different thermal weights and dark gaps |
| Meteor Shower | Procedural stream | Three staggered moving heads with narrow white-blue cores and asymmetric tails |
| Oil Slick | Procedural stream | Iridescent interference bands in cyan, indigo, rose and amber, drifting at independent speeds |
| Silk Ribbons | Procedural stream | Broad satin-like color ribbons glide in counterflow with soft halos and no point-like chase |
| Nebula Bloom | Procedural stream | Violet, indigo, fuchsia and blue gas clouds slowly overlap and breathe over a deep-space floor |
| Holographic Moiré | Procedural stream | Two spectral lattices slide against each other to create a living interference field |

Firmware-random modes are classified as `firmware`: their builders return native `LightEffect(type="random")` payloads, and the strip evolves without per-frame network updates. Procedural effects are classified as `streamed_slow` and must be routed explicitly in both worker and preview computation.

## UI improvements

- Web and desktop catalogs search by effect name, group and (on L930) description.
- The web catalog distinguishes on-device effects from procedural streaming.
- Search keeps its query while the effects grid updates and shows filtered counts.
- Seasonal entries remain collapsed by default, but search reveals matching items.
- Physical hardware testing is still required for color calibration, perceived flicker and transition behavior.


## Original L930 designs

The following four effects are original procedural models, not aliases of firmware presets or older catalog entries:

- **Oil Slick** uses multiple incommensurate spatial and temporal waves to create continuous iridescent interference rather than a rainbow sweep.
- **Silk Ribbons** models four wide, independently moving ribbon fields with Gaussian edges, counterflow and overlapping color blends.
- **Nebula Bloom** uses slowly moving, breathing chromatic cloud fields with a dark floor; it deliberately avoids flashes and isolated strobe-like points.
- **Holographic Moiré** combines two different spectral lattices, creating a slow interference pattern that changes shape as their phases drift.

All four are `streamed_slow` and inherit the L930 safety cadence: no more than two updates per second, hardware transition duration matched to the actual interval, and any slower controller pacing respected. Preview output and live output must call the same renderer so the effect shown in the catalog matches the physical animation.

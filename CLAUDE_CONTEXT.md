# FullControl Project Context

## What this repo is
A personal fork of the [FullControl](https://github.com/FullControlXYZ/fullcontrol) toolpath programming library for 3D printing. The upstream library is used as-is; all personal work lives in dedicated folders that don't touch the upstream codebase.

- **Fork:** https://github.com/vsuley/fullcontrol
- **Local path:** `~/src/fullcontrol`
- **Remotes:** `origin` → personal fork, `fork` → upstream FullControlXYZ

---

## Printer: Tuchanka

A **Prusa XL 5-tool** printer. All Tuchanka-specific code lives in:

```
fullcontrol/devices/personal/tuchanka/
├── setup.py            # startup, shutdown, profile loading, output naming
├── start_gcode.gcode   # reference: original PrusaSlicer start gcode (unmodified)
└── profiles/
    ├── petg.json               # PETG, 0.4mm nozzle
    ├── petg_0.8.json           # PETG, 0.8mm nozzle
    └── jessie_silky_pla_0.8.json  # Jessie Silky PLA, 0.8mm nozzle
```

### Key functions in setup.py

| Function | Purpose |
|---|---|
| `load_profile(name)` | Load a material profile by name from profiles/ |
| `starting_steps(...)` | Full XL startup sequence (checks → disable unused tools → home XY → pick up tool → heat → MBL → purge) |
| `ending_steps(...)` | Shutdown sequence (retract → park → cool all → present print → disable steppers) |
| `base_settings(...)` | Returns initialization_data dict for GcodeControls. **Does NOT include nozzle_temp or bed_temp** — FullControl auto-injects heat commands for those which causes a preheat error on the XL before any tool is picked up. Tuchanka's startup sequence handles all heating. |
| `next_output_path(design_name, output_dir)` | Returns next sequential output path, e.g. my_design_01, my_design_02 |

### Important startup sequence notes
- Unused tools (not in `tools_used`) are explicitly set to S0 at startup
- Initial tool is picked up **before** any heat commands are issued
- A `P0 S1 L2 D0` park is issued before pickup in case a tool is already loaded
- `heat_soak` and `nozzle_clean` both default to `False` — pass `True` to enable
- Prusa XL uses **zero-based tool indexing**: T0–T4
- Currently only tools 1 (T0) and 4 (T3) have filament loaded

---

## Notebooks

Personal design notebooks live in `personal_models/`. Gcode output goes to `personal_models/gcode/` (gitignored).

```
personal_models/
├── tuchanka_design.ipynb       # H letter design (single layer outline), first test print
├── nonplanar_spacer.ipynb      # Non-planar spacer adapted from FullControl example
├── gcode/                      # Gitignored gcode output
│   └── .gitignore
└── fullcontrol_geometry_reference.md  # Summary of all FC geometry primitives
```

### Notebook structure (consistent across all notebooks)
1. Imports (fc + tuchanka setup functions)
2. Printer/startup parameters (`load_profile`, `starting_steps`)
3. Design parameters (EW, EH, print_speed pulled from profile)
4. Design steps (geometry)
5. Preview (`fc.transform(..., 'plot', ...)`)
6. Gcode export (`startup + design_steps + shutdown`, `next_output_path`, `include_date=False`)

---

## Material profiles

JSON files in `profiles/`. Load with `load_profile('name')`. Keys:

```json
{
  "material": "...",
  "nozzle_diameter": 0.4,
  "first_layer_temps": [215.0, 215.0, 215.0, 215.0, 215.0],
  "idle_temps":        [70.0,  70.0,  70.0,  70.0,  70.0],
  "mbl_temp":          170.0,
  "bed_temp":          60.0,
  "print_speed":       1000,
  "travel_speed":      8000,
  "extrusion_width":   0.4,
  "extrusion_height":  0.2,
  "zhop":              2.0
}
```

---

## Useful FullControl geometry primitives

See `personal_models/fullcontrol_geometry_reference.md` for the full list. Most relevant for decorative/art-deco style designs:

- **Shapes:** `circleXY`, `ellipseXY`, `polygonXY`, `spiralXY`, `helixZ`
- **Curves:** `bezier`, `catmull_rom_spline`, `arcXY`
- **Transforms:** `move`, `rotate` (with `copy=True` for radial repeat), `reflectXY`
- **Path ops:** `offset_path`, `segmented_path`
- **Waves:** `sinewaveXYpolar`, `arc_sinewaveXY`

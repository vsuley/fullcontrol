"""
Tuchanka - Prusa XL 5-Tool startup procedure for FullControl.

Use with printer_name='custom' and no_primer. Prepend the result of
starting_steps() to your design steps, and pass base_settings() output
to GcodeControls initialization_data.

Example:
    import fullcontrol as fc
    from fullcontrol.devices.personal.tuchanka.setup import starting_steps, base_settings

    design_steps = [...]  # your FullControl design

    steps = starting_steps(
        initial_tool=0,
        tools_used=[0, 1],
        first_layer_temps=[215, 220, 0, 0, 0],
        bed_temp=60,
        print_area=(20, 20, 180, 180),
    ) + design_steps

    gcode_controls = fc.GcodeControls(
        printer_name='custom',
        initialization_data=base_settings(travel_speed=8000, nozzle_temp=215, bed_temp=60),
    )
    fc.transform(steps, 'gcode', gcode_controls)

Notes:
    - travel_speed is in mm/min (FC convention), not mm/s (PrusaSlicer convention).
      8000 mm/min ≈ 133 mm/s.
    - All temperatures are in °C.
    - print_area is (x_min, y_min, x_max, y_max) in mm. Used for M555 and MBL probe width.
"""

import json
from pathlib import Path

from fullcontrol.gcode import ManualGcode

_PROFILES_DIR = Path(__file__).parent / 'profiles'


def next_output_path(design_name: str, output_dir: str = '.') -> str:
    """
    Returns the next sequential output path for a design, e.g.:
        'my_design_01', 'my_design_02', ...

    Pass the result as save_as to GcodeControls (with include_date=False).
    FullControl will append .gcode automatically.

    Args:
        design_name: Base name for the design (no path, no extension).
        output_dir:  Directory to scan and write into. Defaults to current dir.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = list(output_dir.glob(f'{design_name}_*.gcode'))
    numbers = []
    for f in existing:
        stem = f.stem  # e.g. 'my_design_03'
        suffix = stem[len(design_name) + 1:]  # e.g. '03'
        if suffix.isdigit():
            numbers.append(int(suffix))
    next_n = max(numbers, default=0) + 1
    return str(output_dir / f'{design_name}_{next_n:02d}')


def load_profile(name: str) -> dict:
    """
    Load a material profile by name from the profiles/ directory.

    Example:
        profile = load_profile('petg')
        startup = starting_steps(**{k: profile[k] for k in
                      ('first_layer_temps', 'idle_temps', 'mbl_temp',
                       'bed_temp', 'travel_speed', 'zhop')})
        gcode_controls = fc.GcodeControls(
            printer_name='custom',
            initialization_data=base_settings(
                print_speed=profile['print_speed'],
                extrusion_width=profile['extrusion_width'],
                extrusion_height=profile['extrusion_height'],
                nozzle_temp=profile['first_layer_temps'][0],
                bed_temp=profile['bed_temp'],
            ),
        )
    """
    path = _PROFILES_DIR / f'{name}.json'
    if not path.exists():
        available = [p.stem for p in _PROFILES_DIR.glob('*.json')]
        raise FileNotFoundError(
            f"Profile '{name}' not found. Available profiles: {available}"
        )
    with path.open() as f:
        return json.load(f)

# Per-tool purge zone on the XL bed (fixed by physical layout).
# Each entry: (start_x, direction, purge_y)
# direction: +1 = purge moves right (increasing X), -1 = left (decreasing X)
# Purge sequence per tool: move dir*10mm (extrude), dir*30mm (extrude+wipe), dir*3mm (wipe low), dir*3mm (wipe up)
_PURGE_CONFIG = {
    0: (30,  +1, -7.0),
    1: (150, -1, -7.0),
    2: (210, +1, -7.0),
    3: (330, -1, -7.0),
    4: (330, -1, -4.5),
}


def base_settings(
    travel_speed: float = 8000,
    print_speed: float = 1000,
    nozzle_temp: float = 215,
    bed_temp: float = 60,
    extrusion_width: float = 0.4,
    extrusion_height: float = 0.2,
) -> dict:
    """
    Returns an initialization_data dict for GcodeControls.

    These values drive FullControl's extrusion math and are used as defaults
    throughout the print. Override any of them to match your material/setup.
    """
    return {
        'print_speed': print_speed,
        'travel_speed': travel_speed,
        'extrusion_width': extrusion_width,
        'extrusion_height': extrusion_height,
        'nozzle_temp': nozzle_temp,
        'bed_temp': bed_temp,
        'relative_e': True,
        'primer': 'no_primer',
    }


def starting_steps(
    initial_tool: int = 0,
    tools_used: list = None,
    first_layer_temps: list = None,
    idle_temps: list = None,
    mbl_temp: float = 170.0,
    bed_temp: float = 60.0,
    travel_speed: float = 8000,
    zhop: float = 2.0,
    print_area: tuple = (0, 0, 360, 360),
    nozzle_diameters: list = None,
    heat_soak: bool = False,
    nozzle_clean: bool = False,
) -> list:
    """
    Returns a list of FullControl steps for Tuchanka's full startup sequence:
    printer checks → thermal prep → homing → MBL → per-tool purge lines.

    Args:
        initial_tool:      Tool index (0–4) active at print start.
        tools_used:        Tool indices used in this print. Defaults to all 5.
        first_layer_temps: Per-tool first-layer nozzle temps (°C). Defaults to 215 for all.
        idle_temps:        Per-tool standby temps between use (°C). Defaults to 70 for all.
        mbl_temp:          Nozzle temp during mesh bed leveling (°C). Defaults to 170.
                           The original PrusaSlicer logic varied this by filament type;
                           override here as needed for your material.
        bed_temp:          Bed temperature (°C). Defaults to 60.
        travel_speed:      Travel speed in mm/min. Defaults to 8000 (~133 mm/s).
        zhop:              Z hop for toolchanges in mm. Clamped to minimum 2.0.
        print_area:        (x_min, y_min, x_max, y_max) in mm. Used for M555 and MBL
                           probe width calculation.
        nozzle_diameters:  Per-tool nozzle diameter in mm. Defaults to 0.4 for all.
        heat_soak:         If True, pause for heat absorption (G29 G) after bed reaches
                           temp. Defaults to False.
        nozzle_clean:      If True, wipe nozzle on silicone brush before MBL probing.
                           Defaults to False.
    """
    if tools_used is None:
        tools_used = [0, 1, 2, 3, 4]
    if first_layer_temps is None:
        first_layer_temps = [215.0] * 5
    if idle_temps is None:
        idle_temps = [70.0] * 5
    if nozzle_diameters is None:
        nozzle_diameters = [0.4] * 5

    x_min, y_min, x_max, y_max = print_area
    zhop = max(zhop, 2.0)
    f = int(travel_speed)  # F value for manual gcode moves (mm/min)

    # MBL probe width: cover the X range of all active tools' purge zones.
    # XL probes near the purge area before the print starts.
    if any(t >= 2 for t in tools_used):
        mbl_probe_w = 300
    elif 1 in tools_used:
        mbl_probe_w = 130
    else:
        mbl_probe_w = 50

    steps = []

    # -------------------------------------------------------------------------
    # 1. Printer checks & coordinate mode
    # -------------------------------------------------------------------------
    steps.append(ManualGcode(text='\n; === Tuchanka startup (FullControl) ==='))
    steps.append(ManualGcode(text='M17 ; enable steppers'))
    steps.append(ManualGcode(text='M862.3 P "XL" ; printer model check'))
    steps.append(ManualGcode(text='M862.5 P2 ; g-code level check'))
    steps.append(ManualGcode(text='M862.6 P"Input shaper" ; FW feature check'))
    steps.append(ManualGcode(text='G90 ; absolute coordinates'))
    steps.append(ManualGcode(text='M83 ; extruder relative mode'))
    steps.append(ManualGcode(text=f'M555 X{x_min} Y{y_min} W{x_max - x_min} H{y_max - y_min} ; set print area'))

    # Report nozzle specs for each active tool
    for t in tools_used:
        steps.append(ManualGcode(text=f'M862.1 T{t} P{nozzle_diameters[t]} ; nozzle diameter tool {t}'))

    # -------------------------------------------------------------------------
    # 2. Thermal prep for MBL (reduced temp — not full print temp)
    # -------------------------------------------------------------------------
    steps.append(ManualGcode(text=f'\n; --- thermal prep for MBL ---'))
    steps.append(ManualGcode(text=f'M217 Z{zhop:.1f} ; toolchange z hop'))
    steps.append(ManualGcode(text=f'M140 S{bed_temp} ; set bed temp (no wait)'))
    steps.append(ManualGcode(text='G0 Z5 ; Z clearance'))
    steps.append(ManualGcode(text=f'M109 T{initial_tool} S{mbl_temp} ; heat tool {initial_tool} to MBL temp'))

    # -------------------------------------------------------------------------
    # 3. Home XY, pick up all used tools (dock verification), select initial tool
    # -------------------------------------------------------------------------
    steps.append(ManualGcode(text=f'\n; --- homing & dock verification ---'))
    steps.append(ManualGcode(text='G28 XY ; home XY'))
    steps.append(ManualGcode(text=f'G1 F{f}'))
    for t in tools_used:
        if t != initial_tool:
            steps.append(ManualGcode(text=f'T{t} S1 L0 D0 ; pick tool {t} (dock verify)'))
    steps.append(ManualGcode(text=f'T{initial_tool} S1 L0 D0 ; select initial tool'))

    # -------------------------------------------------------------------------
    # 4. Home Z, wait for bed, re-heat to MBL temp
    # -------------------------------------------------------------------------
    steps.append(ManualGcode(text=f'\n; --- home Z & wait for bed ---'))
    steps.append(ManualGcode(text='M84 E ; turn off E motor'))
    steps.append(ManualGcode(text='G28 Z ; home Z'))
    steps.append(ManualGcode(text='G0 Z5 ; Z clearance'))
    steps.append(ManualGcode(text=f'M104 T{initial_tool} S{idle_temps[initial_tool]} ; drop to idle temp while bed heats'))
    steps.append(ManualGcode(text=f'M190 S{bed_temp} ; wait for bed temp'))
    if heat_soak:
        steps.append(ManualGcode(text='G29 G ; absorb heat'))
    steps.append(ManualGcode(text=f'M109 T{initial_tool} S{mbl_temp} ; reheat to MBL temp'))

    # -------------------------------------------------------------------------
    # 5. Nozzle cleanup (wipe on silicone brush before probing)
    # -------------------------------------------------------------------------
    if nozzle_clean:
        cleanup_x0 = min(x_min, x_max - 32)  # left edge of the 32mm brush zone
        cleanup_y = y_min - 7                 # 7mm in front of print area
        steps.append(ManualGcode(text=f'\n; --- nozzle cleanup ---'))
        steps.append(ManualGcode(text=f'G1 X{cleanup_x0 + 32} Y{cleanup_y} Z5 F{f} ; approach cleanup zone'))
        steps.append(ManualGcode(text='M302 S155 ; lower cold extrusion limit to 155C'))
        steps.append(ManualGcode(text='G1 E-2 F2400 ; retract'))
        steps.append(ManualGcode(text='M84 E ; turn off E motor'))
        steps.append(ManualGcode(text=f'G29 P9 X{cleanup_x0} Y{cleanup_y} W32 H7 ; wipe nozzle'))
        steps.append(ManualGcode(text='G0 Z5 F480 ; lift away'))
        steps.append(ManualGcode(text='M107 ; fan off'))

    # -------------------------------------------------------------------------
    # 6. Mesh Bed Leveling
    # -------------------------------------------------------------------------
    steps.append(ManualGcode(text=f'\n; --- mesh bed leveling ---'))
    steps.append(ManualGcode(text='M84 E ; turn off E motor'))
    steps.append(ManualGcode(text='G29 P1 ; invalidate existing MBL & probe print area'))
    steps.append(ManualGcode(text=f'G29 P1 X30 Y0 W{mbl_probe_w} H20 C ; probe near purge area'))
    steps.append(ManualGcode(text='G29 P3.2 ; interpolate probes'))
    steps.append(ManualGcode(text='G29 P3.13 ; extrapolate outside probe area'))
    steps.append(ManualGcode(text='G29 A ; activate MBL'))
    steps.append(ManualGcode(text='G1 Z10 F720'))
    steps.append(ManualGcode(text=f'G1 F{f}'))
    steps.append(ManualGcode(text='P0 S1 L1 D0 ; park tool'))

    # -------------------------------------------------------------------------
    # 7. Start heating all tools to first-layer temp
    # -------------------------------------------------------------------------
    steps.append(ManualGcode(text=f'\n; --- preheat all active tools ---'))
    for t in tools_used:
        steps.append(ManualGcode(text=f'M104 T{t} S{first_layer_temps[t]} ; preheat tool {t}'))

    # -------------------------------------------------------------------------
    # 8. Purge lines — non-initial tools first, then initial tool
    # -------------------------------------------------------------------------
    purge_order = [t for t in tools_used if t != initial_tool] + [initial_tool]

    for i, t in enumerate(purge_order):
        is_last = (i == len(purge_order) - 1)  # True for the initial tool
        steps.extend(_purge_tool(t, first_layer_temps[t], idle_temps[t], f, keep_hot=is_last))

    steps.append(ManualGcode(text=f'\nG92 E0 ; reset extruder position'))
    steps.append(ManualGcode(text=f'; === Tuchanka startup complete — T{initial_tool} active, ready to print ===\n'))

    return steps


def ending_steps(
    travel_speed: float = 8000,
    present_print: bool = True,
    present_y: float = 365.0,
) -> list:
    """
    Returns a list of FullControl steps for Tuchanka's shutdown sequence:
    retract, park tool, cool all heaters, optionally present the print, disable steppers.

    Args:
        travel_speed:  Travel speed in mm/min. Defaults to 8000 (~133 mm/s).
        present_print: If True, move the bed forward to present the finished print.
                       Defaults to True.
        present_y:     Y position (mm) to move to when presenting the print.
                       Defaults to 365 (near the front of the XL bed).
    """
    f = int(travel_speed)
    steps = []

    steps.append(ManualGcode(text='\n; === Tuchanka shutdown (FullControl) ==='))

    # Retract and lift
    steps.append(ManualGcode(text='G1 E-2 F2400 ; retract'))
    steps.append(ManualGcode(text='G91 ; relative positioning'))
    steps.append(ManualGcode(text='G1 Z10 F720 ; lift nozzle'))
    steps.append(ManualGcode(text='G90 ; absolute positioning'))

    # Park tool and cool all heaters
    steps.append(ManualGcode(text='P0 S1 L2 D0 ; park tool'))
    steps.append(ManualGcode(text='M104 T0 S0 ; cool tool 0'))
    steps.append(ManualGcode(text='M104 T1 S0 ; cool tool 1'))
    steps.append(ManualGcode(text='M104 T2 S0 ; cool tool 2'))
    steps.append(ManualGcode(text='M104 T3 S0 ; cool tool 3'))
    steps.append(ManualGcode(text='M104 T4 S0 ; cool tool 4'))
    steps.append(ManualGcode(text='M140 S0 ; cool bed'))
    steps.append(ManualGcode(text='M107 ; fan off'))

    # Present print
    if present_print:
        steps.append(ManualGcode(text=f'G1 Y{present_y} F{f} ; present print'))

    # Disable steppers
    steps.append(ManualGcode(text='M84 ; disable steppers'))

    steps.append(ManualGcode(text='; === Tuchanka shutdown complete ===\n'))

    return steps


def _purge_tool(
    tool: int,
    first_layer_temp: float,
    idle_temp: float,
    f: int,
    keep_hot: bool = False,
) -> list:
    """
    Generates purge line steps for a single tool.

    Picks the tool, extrudes a purge line along its designated X zone at the
    front of the bed, wipes the nozzle, retracts, and either drops to idle
    temp (non-initial tools) or stays hot (initial tool, keep_hot=True).
    """
    start_x, direction, purge_y = _PURGE_CONFIG[tool]
    d = direction  # +1 or -1

    steps = []
    steps.append(ManualGcode(text=f'\n; --- purge tool {tool} ---'))
    steps.append(ManualGcode(text='P0 S1 L2 D0 ; park current tool'))
    steps.append(ManualGcode(text=f'M109 T{tool} S{first_layer_temp} ; wait for tool {tool}'))
    steps.append(ManualGcode(text=f'T{tool} S1 L0 D0 ; pick tool {tool}'))
    steps.append(ManualGcode(text='G92 E0 ; reset extruder'))
    steps.append(ManualGcode(text=f'G0 X{start_x} Y{purge_y} Z10 F{f} ; approach purge zone'))
    steps.append(ManualGcode(text=f'G0 E10 X{start_x + d*10} Z0.2 F500 ; purge while descending'))
    steps.append(ManualGcode(text=f'G0 X{start_x + d*40} E9 F800 ; continue purge and wipe'))
    steps.append(ManualGcode(text=f'G0 X{start_x + d*43} Z0.05 F8000 ; wipe close to bed'))
    steps.append(ManualGcode(text=f'G0 X{start_x + d*46} Z0.2 F8000 ; wipe away from bed'))
    steps.append(ManualGcode(text='G1 E-2 F2400 ; retract'))
    steps.append(ManualGcode(text='G92 E0 ; reset extruder'))

    if not keep_hot:
        steps.append(ManualGcode(text=f'M104 T{tool} S{idle_temp} ; drop tool {tool} to idle temp'))

    return steps

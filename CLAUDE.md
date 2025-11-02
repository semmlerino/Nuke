# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a **Nuke Python automation toolkit** for VFX pipeline operations. The scripts automate creating Read/Write nodes for renders, plates, lens distortion, and playblasts in Foundry Nuke (version 16.0+, Python 3.11.7).

**Key Context:** This runs **inside Nuke's Python environment**, not as standalone scripts. All scripts are imported and executed via Nuke's Script Editor or menu.py hotkeys.

## Architecture

### Centralized Configuration Pattern

All pipeline paths are managed through `pipeline_config.py`:

```python
# Single source of truth for all VFX pipeline paths
PipelineConfig.get_renders_root(show, seq, shot, user)  # Maya renders
PipelineConfig.get_plate_root(show, seq, shot)          # Turnover plates
PipelineConfig.get_ld_root(show, seq, shot, user)       # 3DE lens distortion
PipelineConfig.get_altplates_output(show, seq, shot)    # Nuke outputs
```

**Path Structure Convention:**
```
/shows/{show}/shots/{seq}/{shot}/user/{user}/...
```

All scripts parse this structure from `nuke.root().name()` to infer show/shot context.

### Script Categories

1. **Read Node Creators** - Create Read nodes for latest versions:
   - `mm_geo_read.py` - Geometry renders from Maya
   - `mm_plate_read.py` - RAW plates with intelligent plate ID detection
   - `mm_playblast_read.py` - Maya playblasts (sequences or movies), category-based
   - `mm_cone_read.py` - Cones playblasts (wrapper for playblast_read with category="Cones")
   - Note: Wireframe (Ctrl+Alt+B) uses playblast_read directly, Cones (Ctrl+Alt+C) uses cone_read wrapper

2. **Import/Paste Scripts**:
   - `mm_ld_import.py` - Pastes 3DE lens distortion .nk files with scoring system

3. **Write Node Creators**:
   - `mm_write_altplates.py` - Creates Write nodes with ACES/OCIO settings

4. **Menu Registration**:
   - `menu.py` - Registers hotkeys with deduplication pattern

### Auto-Connection Pattern

**Critical Pattern:** Scripts that accept selected nodes will auto-connect:

```python
# Save selection before operations that clear it
selected_node = nuke.selectedNodes()[0] if nuke.selectedNodes() else None

# After creating/pasting nodes
if selected_node:
    new_node.setInput(0, selected_node)
```

Examples:
- `mm_write_altplates.py` - Connects Write to selected node
- `mm_ld_import.py` - Connects pasted LD group to selected node (typically a Read)

## Nuke-Specific Development Patterns

### Node Creation
Always use `nuke.nodes.ClassName()` for batch operations (NOT `nuke.createNode()`):

```python
# Correct - batch/scripting
r = nuke.nodes.Read()
r["file"].fromUserText("/path/to/file.####.exr")

# Wrong - interactive only
r = nuke.createNode("Read")  # Opens dialog, breaks automation
```

### Knob Manipulation Best Practices

```python
# Loading sequences - always load a real frame first
r["file"].fromUserText("/path/to/file.1001.exr")  # Real frame
r["file"].fromUserText("/path/to/file.####.exr")  # Then hash pattern

# Setting values - wrap in try/except (knobs vary by Nuke version)
try:
    r["colorspace"].setValue("linear")
except Exception:
    pass  # Knob might not exist in this Nuke version
```

### Context Parsing Pattern

All scripts use this pattern to infer shot context:

```python
nk_path = nuke.root().name()
parts = Path(nk_path).parts
show = parts[parts.index("shows") + 1]
seq = parts[parts.index("shots") + 1]
shot = parts[parts.index("shots") + 2]
user = parts[parts.index("user") + 1]
```

## File Scanning & Version Detection

### Version Directory Pattern

All scripts look for versioned directories (`v001`, `v002`, etc.) and scan in **reverse order** (latest first):

```python
vdirs = [d for d in parent.iterdir() if re.match(r"v\d+$", d.name, re.IGNORECASE)]
vdirs.sort(key=lambda d: _version_num(d.name), reverse=True)  # v003, v002, v001

def _version_num(vname: str) -> int:
    m = re.match(r"v(\d+)$", vname, re.IGNORECASE)
    return int(m.group(1)) if m else -1
```

### Image Sequence Scanning

Standard pattern for detecting frame sequences:

```python
# Match: shot_scene_anything_v001.1001.exr
pattern = re.compile(rf"^{re.escape(shot)}_scene_.*_v{vnum}\\.(\\d+)\\.([A-Za-z0-9]+)$")

# Group by extension, find min/max frames, determine padding
files = [(path, frame_num, padding, extension), ...]
```

## Plate ID Detection System

`mm_plate_read.py` and `mm_ld_import.py` use intelligent plate ID detection with **preference order**:

1. From existing Read nodes in script (highest priority)
2. From .nk filename/path segments
3. From `scene/` subdirectories (FG01, BG01, MG02, etc.)

**Plate ID Pattern:** `[A-Z]{2}\d{2}` (e.g., FG01, BG01, MG02)

Normalization ensures consistent format:
```python
"fg1" → "FG01"
"BG2" → "BG02"
```

## 3DE Lens Distortion Scoring System

`mm_ld_import.py` uses a scoring system to select the best .nk file:

- **+6 points:** Filename exactly matches `{shot}_mm_default_{plate}_LD_v{version}.nk`
- **+3 points:** Parent folder matches turnover context pattern
- **+1 point:** Path contains plate token
- **-∞ (skip):** Path contains directory with dot in name (e.g., `IMG_1241.JPG/`)

Highest scoring file from the latest version wins.

## Testing in Nuke

Since these run inside Nuke, testing workflow:

1. **Script Editor Test:**
   ```python
   import importlib, mm_geo_read
   importlib.reload(mm_geo_read)
   mm_geo_read.run()
   ```

2. **Hotkey Test:**
   - Open a shot .nk file: `/shows/{show}/shots/{seq}/{shot}/user/{user}/scene/comp.nk`
   - Press registered hotkey (e.g., Ctrl+Alt+G for geo, Ctrl+Alt+P for plate)
   - Verify Read node created with correct path

3. **Connection Test:**
   - Select a node
   - Run script (e.g., Ctrl+Alt+W for Write, Ctrl+Alt+L for LD import)
   - Verify auto-connection

## Code Quality Standards

All code follows these standards (enforced in recent updates):

1. **Type Annotations:** Full Python 3.11+ type hints on all functions
2. **Docstrings:** Comprehensive docstrings with Args, Returns, Raises, Examples
3. **Module Docstrings:** Explain purpose, path structure, filename patterns, usage
4. **Error Handling:** Use `_err()` helper to show user message + raise RuntimeError

Example:
```python
def create_latest_geo_read_hash() -> nuke.Node:
    """
    Create a Read node for the latest geometry render sequence.

    Returns:
        Created Nuke Read node

    Raises:
        RuntimeError: If script not saved or no geo renders found
    """
```

## Menu Integration (menu.py)

Hotkey registration uses singleton pattern to prevent duplicates:

```python
# Stored on nuke module to persist across reloads
if not hasattr(nuke, "_bb_hotkeys_bound"):
    nuke._bb_hotkeys_bound: Set[Tuple[str, str]] = set()

def add_hidden_hotkey_once(label: str, command: str, shortcut: str) -> None:
    key = (label, shortcut)
    if key in nuke._bb_hotkeys_bound:
        return
    nuke.menu("Nuke").addCommand(f"@BlueBolt/{label}", command, shortcut, shortcutContext=2)
    nuke._bb_hotkeys_bound.add(key)
```

**shortcutContext=2** means DAG (Node Graph) only, not Script Editor.

## Registered Hotkeys

- **Ctrl+Alt+C:** Latest Cones playblast Read node
- **Ctrl+Alt+G:** Latest Geo render Read node
- **Ctrl+Alt+P:** Latest Plate Read node
- **Ctrl+Alt+L:** Import 3DE lens distortion .nk (connects to selected node)
- **Ctrl+Alt+B:** Latest Wireframe playblast Read node
- **Ctrl+Alt+W:** Create AltPlates Write node (connects to selected node)

## Write Node Configuration Standard

All Write nodes for AltPlates use this configuration:

```python
file: /shows/{show}/shots/{seq}/{shot}/user/gabriel-h/mm/nuke/outputs/AltPlates/{name}.#.exr
file_type: exr
first_part: rgba
raw: True
create_directories: True
ocioColorspace: scene_linear
display: ACES
view: "Client3DLUT + grade"
```

Note: `user/gabriel-h` is hardcoded for centralized output location.

## When Modifying Pipeline Paths

**Always update `pipeline_config.py` first**, then update dependent scripts:

1. Add/modify path template in `PipelineConfig`
2. Add/modify helper method (e.g., `get_<type>_root()`)
3. Update scripts that use old hardcoded paths
4. Test in Nuke with actual shot paths

## Important Nuke Python Details

- **Image sequence notation:** Use single `#` (e.g., `file.#.exr`), not `####`
- **fromUserText() for sequences:** Always load real frame first, then hash pattern
- **nuke.tprint():** Use for logging (appears in Script Editor)
- **nuke.message():** Use for user-facing errors (modal dialog)
- **Path parsing:** Always use `Path.parts` tuple, not string manipulation

## Reference Documentation

See `NUKE_PYTHON_BEST_PRACTICES.md` for comprehensive Nuke Python patterns and `IMPROVEMENTS_SUMMARY.md` for recent changes/improvements.

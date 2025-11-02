"""
menu.py

Nuke menu customization and keyboard shortcut bindings.

This file registers hotkeys for custom tools, implementing a singleton pattern
to prevent duplicate bindings across sessions. All bindings are for the DAG
(Node Graph) context.

Registered Hotkeys:
    Ctrl+Alt+C: Create Read node for latest Cones playblast
    Ctrl+Alt+G: Create Read node for latest Geo render
    Ctrl+Alt+P: Create Read node for latest Plate
    Ctrl+Alt+L: Import 3DE lens distortion .nk file
    Ctrl+Alt+B: Create Read node for latest Wireframe playblast
    Ctrl+Alt+W: Create Write node for alternate plates

Required Scripts:
    - mm_cone_read.py
    - mm_geo_read.py
    - mm_plate_read.py
    - mm_ld_import.py
    - mm_playblast_read.py
    - mm_write_altplates.py

Usage:
    Place this file at ~/.nuke/menu.py
    Nuke will load it automatically on startup
"""

import nuke
from typing import Set, Tuple

# Command strings for hotkeys
# Each imports the module, reloads it (for development), and runs it
cmd_cone: str = (
    "import importlib, mm_cone_read; "
    "importlib.reload(mm_cone_read); "
    "mm_cone_read.run()"
)
cmd_geo: str = (
    "import importlib, mm_geo_read; "
    "importlib.reload(mm_geo_read); "
    "mm_geo_read.run()"
)
cmd_plate: str = (
    "import importlib, mm_plate_read; "
    "importlib.reload(mm_plate_read); "
    "mm_plate_read.run()"
)
cmd_ld: str = (
    "import importlib, mm_ld_import; "
    "importlib.reload(mm_ld_import); "
    "mm_ld_import.run()"
)
cmd_playblast: str = (
    "import importlib, mm_playblast_read; "
    "importlib.reload(mm_playblast_read); "
    "mm_playblast_read.run()"
)
cmd_write_alt: str = (
    "import importlib, mm_write_altplates; "
    "importlib.reload(mm_write_altplates); "
    "mm_write_altplates.run()"
)

# Initialize hotkey tracking on nuke module (persists across reloads)
if not hasattr(nuke, "_bb_hotkeys_bound"):
    nuke._bb_hotkeys_bound: Set[Tuple[str, str]] = set()


def add_hidden_hotkey_once(label: str, command: str, shortcut: str) -> None:
    """
    Register a hotkey binding only once per session.

    Uses a set stored on the nuke module to track which hotkeys have been
    bound, preventing duplicate registrations if menu.py is reloaded.

    The hotkey is registered in the DAG (Node Graph) context, meaning it
    only triggers when the user is working in the node graph, not in the
    Script Editor or other panels.

    Args:
        label: Menu label for the command (appears under @BlueBolt/ in menu)
        command: Python code to execute when hotkey is pressed
        shortcut: Keyboard shortcut string (e.g., "ctrl+alt+g")

    Example:
        >>> add_hidden_hotkey_once("My Tool", "my_module.run()", "ctrl+alt+m")
        # Registers once, subsequent calls with same label/shortcut are ignored
    """
    key = (label, shortcut)
    if key in nuke._bb_hotkeys_bound:
        return

    nuke.menu("Nuke").addCommand(
        f"@BlueBolt/{label}",
        command,
        shortcut,
        shortcutContext=2  # 2 = DAG (Node Graph) context
    )
    nuke._bb_hotkeys_bound.add(key)


# Register all hotkeys
add_hidden_hotkey_once("Latest Cones Read", cmd_cone, "ctrl+alt+c")
add_hidden_hotkey_once("Latest Geo  Read", cmd_geo, "ctrl+alt+g")
add_hidden_hotkey_once("Latest Plate Read", cmd_plate, "ctrl+alt+p")
add_hidden_hotkey_once("Import 3DE LD .nk", cmd_ld, "ctrl+alt+l")
add_hidden_hotkey_once("Latest Wireframe Read", cmd_playblast, "ctrl+alt+b")
add_hidden_hotkey_once("Write AltPlates", cmd_write_alt, "ctrl+alt+w")

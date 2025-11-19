"""
mm_write_altplates.py

Create Write nodes for alternate plate outputs.

This script creates a Write node configured to output to the centralized
AltPlates directory under user gabriel-h. The filename is based on the
currently selected node, or defaults to "Graded" if nothing is selected.
The Write node is automatically connected to the selected node.

Path structure:
    /shows/<show>/shots/<seq>/<shot>/user/gabriel-h/mm/nuke/outputs/AltPlates/

Output format:
    <selected_node_name>.#.exr
    Default: Graded.#.exr

Features:
    - Automatically connects to selected node
    - Automatically creates output directories
    - EXR format with RGBA, raw enabled
    - OCIO colorspace: scene_linear
    - Display: ACES
    - View: "Client3DLUT + grade"

Usage:
    import mm_write_altplates
    mm_write_altplates.run()  # Creates Write node connected to selected node
"""

import re
from pathlib import Path
from typing import NoReturn

import nuke

from pipeline_config import PipelineConfig


def _err(msg: str) -> NoReturn:
    """
    Display error message to user and raise RuntimeError.

    Args:
        msg: Error message to display

    Raises:
        RuntimeError: Always raised after showing message
    """
    nuke.message(msg)
    raise RuntimeError(msg)


def _find_index(parts: tuple[str, ...], name: str) -> int:
    """
    Find index of a string in a tuple, returning -1 if not found.

    Args:
        parts: Tuple of strings to search
        name: String to find

    Returns:
        Index of name in parts, or -1 if not found
    """
    try:
        return parts.index(name)
    except ValueError:
        return -1


def _sanitize_name(name: str) -> str:
    """
    Sanitize node name for use in filename.

    Removes or replaces characters that are problematic in filenames.

    Args:
        name: Node name to sanitize

    Returns:
        Sanitized name safe for use in filenames

    Example:
        >>> _sanitize_name("My Node! (v2)")
        "My_Node_v2"
    """
    # Replace spaces and special characters with underscores
    name = re.sub(r'[^\w\-.]', '_', name)
    # Remove consecutive underscores
    name = re.sub(r'_+', '_', name)
    # Remove leading/trailing underscores
    name = name.strip('_')
    return name if name else "Graded"


def _get_selected_node() -> nuke.Node | None:
    """
    Get the currently selected node.

    Returns:
        First selected node, or None if nothing selected

    Example:
        If "Grade1" is selected, returns the Grade1 node object
        If nothing is selected, returns None
    """
    selected = nuke.selectedNodes()
    return selected[0] if selected else None


def _get_selected_node_name() -> str:
    """
    Get the name of the currently selected node.

    Returns:
        Sanitized name of selected node, or "Graded" if nothing selected

    Example:
        If "Grade1" is selected, returns "Grade1"
        If nothing is selected, returns "Graded"
    """
    node = _get_selected_node()
    if not node:
        return "Graded"

    node_name = node.name()
    return _sanitize_name(node_name)


def create_altplates_write() -> nuke.Node:
    """
    Create a Write node for alternate plate outputs.

    Parses the current Nuke script path to determine show/seq/shot context,
    then creates a Write node configured to output to the AltPlates directory
    under user gabriel-h. Automatically connects to the currently selected node.

    The output filename is based on the currently selected node's name,
    or defaults to "Graded" if nothing is selected.

    Configuration:
    - Path: /shows/{show}/shots/{seq}/{shot}/user/gabriel-h/mm/nuke/outputs/AltPlates/
    - Format: <name>.#.exr
    - File type: exr
    - First part: rgba
    - Raw: True
    - Create directories: True
    - OCIO colorspace: scene_linear
    - Display: ACES
    - View: "Client3DLUT + grade"
    - Auto-connects to selected node

    Returns:
        Created Nuke Write node

    Raises:
        RuntimeError: If script not saved or path doesn't match expected structure

    Example:
        With selected node "Grade1" in shot DD_230_0360:
        Creates Write node with file:
        /shows/jack_ryan/shots/DD_230/DD_230_0360/user/gabriel-h/mm/nuke/outputs/AltPlates/Grade1.#.exr
        And connects the Write node's input to Grade1

        With no selection:
        Uses default filename "Graded.#.exr" with no input connection
    """
    # Parse context from current .nk file
    nk_path = nuke.root().name()
    if not nk_path or nk_path == "Root":
        _err("Please save the Nuke script first so I can infer the shot path.")

    p = Path(nk_path)
    parts = p.parts
    i_shows = _find_index(parts, "shows")
    i_shots = _find_index(parts, "shots")

    if min(i_shows, i_shots) < 0:
        _err(
            "Couldn't parse show/shot from the Nuke script path.\n"
            "Expected /shows/<show>/shots/<seq>/<shot>/..."
        )

    try:
        show = parts[i_shows + 1]
        seq = parts[i_shots + 1]
        shot = parts[i_shots + 2]
    except IndexError:
        _err("Path didn't have enough segments after /shows or /shots.")

    # Get output directory using config
    output_dir = PipelineConfig.get_altplates_output(show, seq, shot)

    # Get selected node (for filename and connection)
    selected_node = _get_selected_node()
    base_name = _get_selected_node_name()

    # Build full output path with hash pattern (single # for Nuke)
    output_file = output_dir / f"{base_name}.#.exr"

    # Create Write node
    w = nuke.nodes.Write()
    w["name"].setValue(f"Write_AltPlates_{base_name}")

    # Set file path
    w["file"].fromUserText(str(output_file))

    # Set EXR format
    try:
        w["file_type"].setValue("exr")
    except Exception:
        pass

    # Set first_part to rgba
    try:
        w["first_part"].setValue("rgba")
    except Exception:
        pass

    # Enable raw
    try:
        w["raw"].setValue(True)
    except Exception:
        pass

    # Enable create directories
    try:
        w["create_directories"].setValue(True)
    except Exception:
        pass

    # Set OCIO colorspace to scene_linear
    try:
        w["ocioColorspace"].setValue("scene_linear")
    except Exception:
        pass

    # Set display to ACES
    try:
        w["display"].setValue("ACES")
    except Exception:
        pass

    # Set view to "Client3DLUT + grade"
    try:
        w["view"].setValue("Client3DLUT + grade")
    except Exception:
        pass

    # Note: If you have a custom before_render() callback function,
    # you can add it here with:
    # try:
    #     w["beforeRender"].setValue("before_render()")
    # except Exception:
    #     pass

    # Connect to selected node if there is one
    if selected_node:
        try:
            w.setInput(0, selected_node)
            nuke.tprint(f"[AltPlates] Connected to: {selected_node.name()}")
        except Exception as e:
            nuke.tprint(f"[AltPlates] Warning: Could not connect to {selected_node.name()}: {e}")

    nuke.tprint(f"[AltPlates] Created Write node: {output_file}")
    nuke.tprint(f"[AltPlates] Output name: {base_name}")
    nuke.tprint(f"[AltPlates] Directory: {output_dir}")

    return w


def run() -> nuke.Node:
    """
    Stable entry point for menus and hotkeys.

    Creates Write node for AltPlates output based on selected node.

    Returns:
        Created Nuke Write node

    Example:
        # From menu.py or Script Editor:
        import mm_write_altplates
        mm_write_altplates.run()
    """
    return create_altplates_write()

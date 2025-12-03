"""
mm_wireframe_export_setup.py

Create a complete node tree for playblast export with lens distortion.

This script automates the setup of a full export pipeline including:
- Playblast Read (PNG/movie from playblast/{category}/v###/)
- Transform (scale 1.1, center 2156 1152)
- 3DE lens distortion group (pasted from LD .nk file)
- Raw plate Read (EXR from plate/input_plate/{PLATE}/v###/)
- Merge (A=Plate, B=Playblast+LD)
- WriteTank (farm export configured for Camera Elements)

Path structures:
    Playblast: /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/maya/playblast/{category}/v###/
    Plate: /shows/<show>/shots/<seq>/<shot>/publish/turnover/plate/input_plate/<PLATE>/v###/exr/
    LD: /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/3de/mm-default/exports/scene/<PLATE>/nuke_lens_distortion/v###/

Usage:
    import mm_wireframe_export_setup
    mm_wireframe_export_setup.run()  # Creates Wireframe export tree

    # Or for Cones:
    mm_wireframe_export_setup.create_playblast_export_setup(category="Cones")
"""

from pathlib import Path

import nuke

from export_utils import (
    detect_plate_from_nkpath,
    detect_plate_from_reads,
    err,
    find_latest_ld,
    find_latest_plate,
    find_latest_playblast,
    infer_context_from_nk,
)


def create_playblast_export_setup(category: str = "Wireframe") -> dict[str, nuke.Node]:
    """
    Create a complete node tree for playblast export with lens distortion.

    Creates an independent 6-node export pipeline:
    1. Read node for playblast (PNG/movie)
    2. Transform node (scale 1.1, center 2156 1152)
    3. LD_3DE lens distortion group (pasted from .nk)
    4. Read node for raw plate (EXR)
    5. Merge node (A=Plate, B=Playblast+LD)
    6. WriteTank node (configured for Camera Elements export)

    This creates a standalone node tree, not connected to any existing nodes.

    Args:
        category: Playblast category to use (default: "Wireframe")
            Common values: "Wireframe", "Cones"

    Returns:
        Dictionary of created nodes:
            {
                "playblast_read": Read node,
                "transform": Transform node,
                "ld_group": LD group node,
                "plate_read": Read node,
                "merge": Merge node,
                "write_tank": WriteTank node
            }

    Raises:
        RuntimeError: If script not saved, or any required files not found

    Example:
        >>> nodes = create_playblast_export_setup(category="Wireframe")
        >>> # Creates complete export tree for Wireframe playblast
    """
    nuke.tprint(f"[Export Setup] Creating {category} export pipeline...")

    # Parse context
    show, seq, shot, user = infer_context_from_nk()
    nk_parts = Path(nuke.root().name()).parts

    # Detect plate ID
    plate_id = detect_plate_from_reads()
    if not plate_id:
        plate_id = detect_plate_from_nkpath(tuple(s.lower() for s in nk_parts))

    nuke.tprint(f"[Export Setup] Detected plate ID: {plate_id or '(auto-detect from available plates)'}")

    # Find latest playblast
    nuke.tprint(f"[Export Setup] Finding latest {category} playblast...")
    playblast_data, playblast_v = find_latest_playblast(show, seq, shot, user, category)

    # Find latest plate
    nuke.tprint("[Export Setup] Finding latest plate...")
    plate_prefix, plate_ext, plate_fmin, plate_fmax, plate_pad, plate_v, plate_bg = find_latest_plate(
        show, seq, shot, plate_id
    )

    # Find latest LD
    nuke.tprint("[Export Setup] Finding latest LD file...")
    ld_file, ld_v, ld_plate = find_latest_ld(show, seq, shot, user, plate_bg)

    # Clear selection
    for n in nuke.selectedNodes():
        n.setSelected(False)

    # ========================================================================
    # 1. CREATE PLAYBLAST READ NODE
    # ========================================================================
    nuke.tprint(f"[Export Setup] Creating {category} Read node...")

    if playblast_data["type"] == "sequence":
        best_prefix = playblast_data["best_prefix"]
        ext = playblast_data["ext"]
        fmin = playblast_data["fmin"]
        fmax = playblast_data["fmax"]
        pad = playblast_data["pad"]

        hashes = "#" * pad
        hash_pattern = f"{best_prefix}.{hashes}.{ext}"
        first_frame_path = f"{best_prefix}.{str(fmin).zfill(pad)}.{ext}"

        playblast_read = nuke.nodes.Read()
        playblast_read["name"].setValue(f"Read_playblast_{category}_v{playblast_v}")

        # Load real frame first, then hash pattern
        playblast_read["file"].fromUserText(first_frame_path)
        playblast_read["file"].fromUserText(hash_pattern)

        # Set frame range
        for knob, val in (("first", fmin), ("last", fmax), ("origfirst", fmin), ("origlast", fmax)):
            try:
                playblast_read[knob].setValue(int(val))
            except Exception:
                pass

        # PNG/JPG: leave colorspace to project defaults; EXR: set raw/linear
        if ext.lower() == "exr":
            for k, v in (("file_type", "exr"), ("colorspace", "linear")):
                try:
                    playblast_read[k].setValue(v)
                except Exception:
                    pass
            try:
                playblast_read["raw"].setValue(True)
            except Exception:
                pass

        try:
            playblast_read["reload"].execute()
        except Exception:
            pass

    elif playblast_data["type"] == "movie":
        movie_path = playblast_data["path"]

        playblast_read = nuke.nodes.Read()
        playblast_read["name"].setValue(f"Read_playblast_{category}_v{playblast_v}")
        playblast_read["file"].fromUserText(movie_path)

        try:
            playblast_read["reload"].execute()
        except Exception:
            pass

    else:
        err("Internal error: unknown playblast type.")

    # ========================================================================
    # 2. CREATE TRANSFORM NODE
    # ========================================================================
    nuke.tprint("[Export Setup] Creating Transform node...")

    transform = nuke.nodes.Transform()
    transform["name"].setValue("Transform_WireframeScale")
    try:
        transform["scale"].setValue(1.1)
    except Exception:
        pass
    try:
        transform["center"].setValue([2156, 1152])
    except Exception:
        pass

    # Connect to playblast
    transform.setInput(0, playblast_read)

    # ========================================================================
    # 3. PASTE LD .NK FILE
    # ========================================================================
    nuke.tprint(f"[Export Setup] Pasting LD file: {ld_file.name}")

    for n in nuke.selectedNodes():
        n.setSelected(False)

    nuke.nodePaste(str(ld_file))
    pasted = nuke.selectedNodes()

    # Find the primary Group/LiveGroup
    ld_group: nuke.Node | None = None
    for n in pasted:
        if n.Class() in ("Group", "LiveGroup"):
            ld_group = n
            break

    if not ld_group:
        err(f"No Group/LiveGroup found in pasted LD file:\n{ld_file}")

    # Rename LD group
    try:
        ld_group.setName(f"LD_3DE_{ld_plate}_v{ld_v}", unique=False)
    except Exception:
        pass

    # Connect to transform
    ld_group.setInput(0, transform)

    # ========================================================================
    # 4. CREATE PLATE READ NODE
    # ========================================================================
    nuke.tprint("[Export Setup] Creating plate Read node...")

    plate_hashes = "#" * plate_pad
    plate_hash_pattern = f"{plate_prefix}.{plate_hashes}.{plate_ext}"
    plate_first_frame_path = f"{plate_prefix}.{str(plate_fmin).zfill(plate_pad)}.{plate_ext}"

    plate_read = nuke.nodes.Read()
    plate_read["name"].setValue(f"Read_rawPlate_{plate_bg}_v{plate_v}")

    # Load real frame first, then hash pattern
    plate_read["file"].fromUserText(plate_first_frame_path)
    plate_read["file"].fromUserText(plate_hash_pattern)

    # Set EXR-specific settings
    if plate_ext.lower() == "exr":
        try:
            plate_read["file_type"].setValue("exr")
        except Exception:
            pass
        try:
            plate_read["colorspace"].setValue("linear")
        except Exception:
            pass
        try:
            plate_read["raw"].setValue(True)
        except Exception:
            pass

    # Set frame range
    for knob, val in (("first", plate_fmin), ("last", plate_fmax), ("origfirst", plate_fmin), ("origlast", plate_fmax)):
        try:
            plate_read[knob].setValue(int(val))
        except Exception:
            pass

    try:
        plate_read["reload"].execute()
    except Exception:
        pass

    # ========================================================================
    # 5. CREATE MERGE NODE
    # ========================================================================
    nuke.tprint("[Export Setup] Creating Merge node...")

    merge = nuke.nodes.Merge2()
    merge["name"].setValue("Merge_WireframePlate")

    # Connect inputs: A=Plate (foreground), B=Wireframe+LD (background)
    merge.setInput(0, ld_group)  # B input (background)
    merge.setInput(1, plate_read)  # A input (foreground)

    # ========================================================================
    # 6. CREATE WRITETANK NODE
    # ========================================================================
    nuke.tprint("[Export Setup] Creating WriteTank node...")

    # Check if WriteTank exists
    try:
        write_tank = nuke.nodes.WriteTank()
    except Exception:
        err("WriteTank node type not found.\nThis node requires Shotgun/Flow toolkit integration.")

    write_tank["name"].setValue("WriteTank_WireframeExport")

    # Connect to merge
    write_tank.setInput(0, merge)

    # Configure WriteTank - match example settings
    try:
        write_tank["profile_name"].setValue("Camera Elements")
    except Exception:
        pass

    try:
        write_tank["custom_knob_camera_element"].setValue("lineupGeo")
    except Exception:
        pass

    # Colorspace settings
    try:
        write_tank["colorspace"].setValue("lin_sgamut3cine")
    except Exception:
        pass

    # File type
    try:
        write_tank["file_type"].setValue("exr")
    except Exception:
        pass

    # Channels
    try:
        write_tank["channels"].setValue("rgb")
    except Exception:
        pass

    nuke.tprint("[Export Setup] ✓ Complete! Created 6-node export pipeline")
    nuke.tprint(f"[Export Setup]   • Playblast: {category} v{playblast_v}")
    nuke.tprint(f"[Export Setup]   • Plate: {plate_bg} v{plate_v}")
    nuke.tprint(f"[Export Setup]   • LD: {ld_plate} v{ld_v}")

    return {
        "playblast_read": playblast_read,
        "transform": transform,
        "ld_group": ld_group,
        "plate_read": plate_read,
        "merge": merge,
        "write_tank": write_tank,
    }


def run() -> dict[str, nuke.Node]:
    """
    Stable entry point for menus and hotkeys.

    Creates Wireframe playblast export setup by default.

    Returns:
        Dictionary of created nodes

    Example:
        # From menu.py or Script Editor:
        import mm_wireframe_export_setup
        mm_wireframe_export_setup.run()  # Creates Wireframe export tree

        # For Cones:
        import mm_wireframe_export_setup
        mm_wireframe_export_setup.create_playblast_export_setup(category="Cones")
    """
    return create_playblast_export_setup(category="Wireframe")

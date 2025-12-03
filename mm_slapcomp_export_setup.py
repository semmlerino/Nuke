"""
mm_slapcomp_export_setup.py

Create dual-export slap comp setup with Cones and Wireframe playblast pipelines.

This script automates the setup of TWO complete export pipelines sharing a single plate:
- Shared: Raw plate Read node (EXR)
- Cones pipeline: Playblast Read → Transform → LD → Merge → Crop → WriteTank
- Wireframe pipeline: Playblast Read → Transform → LD → Merge → Crop → WriteTank

Path structures:
    Playblast: /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/maya/playblast/{category}/v###/
    Plate: /shows/<show>/shots/<seq>/<shot>/publish/turnover/plate/input_plate/<PLATE>/v###/exr/
    LD: /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/3de/mm-default/exports/scene/<PLATE>/nuke_lens_distortion/v###/

Usage:
    import mm_slapcomp_export_setup
    mm_slapcomp_export_setup.run()  # Creates both Cones + Wireframe export trees

Hotkey:
    Ctrl+Alt+Shift+S (registered in menu.py)
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


def create_slapcomp_export_setup() -> dict[str, dict[str, nuke.Node]]:
    """
    Create dual-export slap comp setup (Cones + Wireframe) sharing one plate.

    Creates a shared raw plate Read node that feeds into TWO complete export pipelines:

    Architecture:
        [Shared Plate Read (EXR)]
              ↓         ↓
        [Cones Pipeline] [Wireframe Pipeline]

    Each pipeline consists of:
    1. Read node for playblast (PNG/movie)
    2. Transform node (scale 1.1, center 2156 1152)
    3. LD_3DE lens distortion group (pasted from .nk)
    4. Merge node (A=Shared Plate, B=Playblast+LD)
    5. Crop node
    6. WriteTank node (configured for Camera Elements export)

    Returns:
        Dictionary of created nodes:
            {
                "shared": {
                    "plate_read": Read node
                },
                "Cones": {
                    "playblast_read": Read node,
                    "transform": Transform node,
                    "ld_group": LD group node,
                    "merge": Merge node,
                    "crop": Crop node,
                    "write_tank": WriteTank node
                },
                "Wireframe": {
                    "playblast_read": Read node,
                    "transform": Transform node,
                    "ld_group": LD group node,
                    "merge": Merge node,
                    "crop": Crop node,
                    "write_tank": WriteTank node
                }
            }

    Raises:
        RuntimeError: If script not saved, or any required files not found

    Example:
        >>> nodes = create_slapcomp_export_setup()
        >>> # Creates complete dual-export tree (Cones + Wireframe)
    """
    nuke.tprint("[Slap Comp] Creating dual-export setup (Cones + Wireframe)...")

    # Parse context
    show, seq, shot, user = infer_context_from_nk()
    nk_parts = Path(nuke.root().name()).parts

    # Detect plate ID
    plate_id = detect_plate_from_reads()
    if not plate_id:
        plate_id = detect_plate_from_nkpath(tuple(s.lower() for s in nk_parts))

    nuke.tprint(f"[Slap Comp] Detected plate ID: {plate_id or '(auto-detect from available plates)'}")

    # Find latest plate (shared resource)
    nuke.tprint("[Slap Comp] Finding latest plate...")
    plate_prefix, plate_ext, plate_fmin, plate_fmax, plate_pad, plate_v, plate_bg = find_latest_plate(
        show, seq, shot, plate_id
    )

    # Find latest LD (shared detection, pasted separately for each pipeline)
    nuke.tprint("[Slap Comp] Finding latest LD file...")
    ld_file, ld_v, ld_plate = find_latest_ld(show, seq, shot, user, plate_bg)

    # Clear selection
    for n in nuke.selectedNodes():
        n.setSelected(False)

    # ========================================================================
    # CREATE SHARED PLATE READ NODE
    # ========================================================================
    nuke.tprint("[Slap Comp] Creating shared plate Read node...")

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

    # Position plate Read node
    plate_read.setXYpos(200, -200)

    # ========================================================================
    # CREATE DUAL EXPORT PIPELINES
    # ========================================================================

    categories = ["Cones", "Wireframe"]
    category_element_map = {
        "Cones": "cones",
        "Wireframe": "lineupGeo"
    }

    # Position offsets for each pipeline
    category_x_offset = {
        "Cones": -200,  # Left side
        "Wireframe": 400  # Right side
    }

    results: dict[str, dict[str, nuke.Node]] = {
        "shared": {"plate_read": plate_read}
    }

    for category in categories:
        nuke.tprint(f"[Slap Comp] Creating {category} pipeline...")

        # Find latest playblast for this category
        playblast_data, playblast_v = find_latest_playblast(show, seq, shot, user, category)

        # Get position offset
        x_offset = category_x_offset[category]

        # ====================================================================
        # 1. CREATE PLAYBLAST READ NODE
        # ====================================================================

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

        # Position playblast Read
        playblast_read.setXYpos(x_offset, -300)

        # ====================================================================
        # 2. CREATE TRANSFORM NODE
        # ====================================================================

        transform = nuke.nodes.Transform()
        transform["name"].setValue(f"Transform_{category}Scale")
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

        # Position Transform
        transform.setXYpos(x_offset, -200)

        # ====================================================================
        # 3. PASTE LD .NK FILE
        # ====================================================================

        # Clear selection before paste
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
            ld_group.setName(f"LD_3DE_{ld_plate}_{category}_v{ld_v}", unique=False)
        except Exception:
            pass

        # Connect to transform
        ld_group.setInput(0, transform)

        # Position LD group
        ld_group.setXYpos(x_offset, -100)

        # ====================================================================
        # 4. CREATE MERGE NODE
        # ====================================================================

        merge = nuke.nodes.Merge2()
        merge["name"].setValue(f"Merge_{category}Plate")

        # Connect inputs: A=Plate (foreground), B=Playblast+LD (background)
        merge.setInput(0, ld_group)      # B input (background)
        merge.setInput(1, plate_read)    # A input (foreground)

        # Position Merge
        merge.setXYpos(x_offset, 0)

        # ====================================================================
        # 5. CREATE CROP NODE
        # ====================================================================

        crop = nuke.nodes.Crop()
        crop["name"].setValue(f"Crop_{category}")

        # Set crop box to full frame
        try:
            crop["box"].setValue([0, 0, nuke.root().width(), nuke.root().height()])
        except Exception:
            pass

        # Connect to merge
        crop.setInput(0, merge)

        # Position Crop
        crop.setXYpos(x_offset, 50)

        # ====================================================================
        # 6. CREATE WRITETANK NODE
        # ====================================================================

        # Check if WriteTank exists
        try:
            write_tank = nuke.nodes.WriteTank()
        except Exception:
            err("WriteTank node type not found.\nThis node requires Shotgun/Flow toolkit integration.")

        write_tank["name"].setValue(f"WriteTank_{category}Export")

        # Connect to crop
        write_tank.setInput(0, crop)

        # Configure WriteTank - match example settings
        try:
            write_tank["profile_name"].setValue("Camera Elements")
        except Exception:
            pass

        # Set category-specific camera_element value
        camera_element = category_element_map[category]
        try:
            write_tank["custom_knob_camera_element"].setValue(camera_element)
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

        # Position WriteTank
        write_tank.setXYpos(x_offset, 100)

        # Store results for this category
        results[category] = {
            "playblast_read": playblast_read,
            "transform": transform,
            "ld_group": ld_group,
            "merge": merge,
            "crop": crop,
            "write_tank": write_tank,
        }

        nuke.tprint(f"[Slap Comp] ✓ {category} pipeline complete")

    nuke.tprint("[Slap Comp] ✓✓ COMPLETE! Created dual-export setup")
    nuke.tprint(f"[Slap Comp]   • Shared Plate: {plate_bg} v{plate_v}")
    nuke.tprint(f"[Slap Comp]   • LD: {ld_plate} v{ld_v}")

    return results


def run() -> dict[str, dict[str, nuke.Node]]:
    """
    Stable entry point for menus and hotkeys.

    Creates dual-export slap comp setup (Cones + Wireframe) sharing one plate.

    Returns:
        Dictionary of created nodes grouped by category

    Example:
        # From menu.py or Script Editor:
        import mm_slapcomp_export_setup
        mm_slapcomp_export_setup.run()  # Creates Cones + Wireframe export trees
    """
    return create_slapcomp_export_setup()

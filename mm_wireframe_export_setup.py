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

import re
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
import nuke

from pipeline_config import PipelineConfig


def _err(msg: str) -> None:
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


def _version_num(vname: str) -> int:
    """
    Extract version number from version string.

    Args:
        vname: Version string (e.g., "v001", "V123")

    Returns:
        Version number as integer, or -1 if invalid format
    """
    m = re.match(r"v(\d+)$", vname, re.IGNORECASE)
    return int(m.group(1)) if m else -1


def _infer_context_from_nk() -> tuple[str, str, str, str]:
    """
    Parse show, seq, shot, and user from current Nuke script path.

    Returns:
        Tuple of (show, seq, shot, user)

    Raises:
        RuntimeError: If script not saved or path doesn't match expected structure
    """
    nk_path = nuke.root().name()
    if not nk_path or nk_path == "Root":
        _err("Please save the Nuke script first so I can infer the shot path.")

    p = Path(nk_path)
    parts = p.parts
    i_shows = _find_index(parts, "shows")
    i_shots = _find_index(parts, "shots")
    i_user = _find_index(parts, "user")

    if min(i_shows, i_shots, i_user) < 0:
        _err("Couldn't parse show/shot/user from the Nuke script path.\\nExpected /shows/<show>/shots/<seq>/<shot>/user/<user>/...")

    try:
        show = parts[i_shows+1]
        seq = parts[i_shots+1]
        shot = parts[i_shots+2]
        user = parts[i_user+1]
    except Exception:
        _err("Path didn't have enough segments after /shows or /shots or /user.")

    return show, seq, shot, user


# ============================================================================
# PLAYBLAST FINDING (from mm_playblast_read.py)
# ============================================================================

def _scan_playblast(vdir: Path, base_name: str) -> Optional[Dict[str, Any]]:
    """
    Scan a version folder for playblast image sequences or movie files.

    Args:
        vdir: Version directory to scan (e.g., .../Wireframe/v001/)
        base_name: Base name to match (e.g., "Wireframe")

    Returns:
        Dictionary with type-specific data or None if nothing matches
    """
    if not vdir.exists():
        return None

    # 1) Try image sequence
    rx_seq = re.compile(rf"^{re.escape(base_name)}\\.(\d+)\\.([A-Za-z0-9]+)$", re.IGNORECASE)
    files: List[tuple[Path, int, int, str]] = []

    for p in vdir.iterdir():
        if not p.is_file():
            continue
        m = rx_seq.match(p.name)
        if not m:
            continue
        frame_str, ext = m.group(1), m.group(2)
        files.append((p, int(frame_str), len(frame_str), ext))

    if files:
        # Group by extension
        groups: Dict[str, List[tuple[Path, int, int, str]]] = {}
        for p, frame, pad, ext in files:
            key = ext.lower()
            groups.setdefault(key, []).append((p, frame, pad, ext))

        # Choose the group with most files, then newest mtime
        def group_key(kv: tuple[str, List[tuple[Path, int, int, str]]]) -> tuple[int, float]:
            _, vals = kv
            count = len(vals)
            newest = max(v[0].stat().st_mtime for v in vals)
            return (count, newest)

        ext, vals = max(groups.items(), key=group_key)
        frames = [v[1] for v in vals]
        pads = [v[2] for v in vals]
        fmin, fmax = min(frames), max(frames)
        pad = max(pads)
        best_prefix = str(vdir / base_name)

        return {
            "type": "sequence",
            "best_prefix": best_prefix,
            "ext": ext,
            "fmin": fmin,
            "fmax": fmax,
            "pad": pad,
            "files": [v[0] for v in vals],
        }

    # 2) Try single movie file
    movie_exts = ("mov", "mp4", "m4v", "avi", "mxf", "webm", "mkv")
    for p in vdir.iterdir():
        if not p.is_file():
            continue
        name_low = p.name.lower()
        for me in movie_exts:
            if name_low == f"{base_name.lower()}.{me}":
                return {"type": "movie", "path": str(p)}

    return None


def _find_latest_playblast(
    show: str, seq: str, shot: str, user: str, category: str
) -> tuple[Dict[str, Any], str]:
    """
    Find the latest playblast sequence for the given category.

    Args:
        show: Show name
        seq: Sequence name
        shot: Shot name
        user: User name
        category: Playblast category (e.g., "Wireframe", "Cones")

    Returns:
        Tuple of (playblast_data_dict, version_string)

    Raises:
        RuntimeError: If no playblasts found
    """
    playblast_root = PipelineConfig.get_playblast_root(show, seq, shot, user)
    if not playblast_root.exists():
        _err(f"Playblast root not found:\\n{playblast_root}")

    cat_dir = playblast_root / category
    if not cat_dir.exists() or not cat_dir.is_dir():
        _err(f"No '{category}' folder under:\\n{playblast_root}")

    # Find version directories (latest first)
    vdirs = [
        d for d in cat_dir.iterdir()
        if d.is_dir() and re.match(r"v\d+$", d.name, re.IGNORECASE)
    ]
    if not vdirs:
        _err(f"No version folders under:\\n{cat_dir}")
    vdirs.sort(key=lambda d: _version_num(d.name), reverse=True)

    chosen: Optional[Dict[str, Any]] = None
    chosen_v: Optional[str] = None

    for vdir in vdirs:
        hit = _scan_playblast(vdir, category)
        if hit:
            chosen = hit
            chosen_v = vdir.name[1:].zfill(3)
            break

    if not chosen:
        _err(f"No sequences or movies matching '{category}' found under versions in:\\n{cat_dir}")

    return chosen, chosen_v


# ============================================================================
# PLATE ID DETECTION & FINDING (from mm_plate_read.py and mm_ld_import.py)
# ============================================================================

PLATE_RX = re.compile(r'\\b([A-Z]{2}\\d{2})\\b', re.IGNORECASE)


def _norm_plate_token(tok: str) -> Optional[str]:
    """
    Normalize plate token to standard format.

    Args:
        tok: Token to normalize (e.g., "fg1", "FG01")

    Returns:
        Normalized plate ID (e.g., "FG01") or None if invalid
    """
    m = re.match(r"^([A-Za-z]{2})(\\d{1,2})$", tok)
    if not m:
        return None
    letters = m.group(1).upper()
    digits = f"{int(m.group(2)):02d}"
    return f"{letters}{digits}"


def _detect_plate_from_reads() -> Optional[str]:
    """
    Detect plate ID from existing Read nodes in the current Nuke script.

    Returns:
        Plate ID in uppercase (e.g., "FG01") or None if not found
    """
    for r in nuke.allNodes('Read'):
        try:
            p = r['file'].value()
        except Exception:
            continue

        # Check path for /plate/input_plate/<ID>/ or /plate/output_plate/<ID>/
        m = re.search(r'/plate/(?:input_plate|output_plate)/([A-Za-z]{2}\\d{2})/', p, re.IGNORECASE)
        if m:
            return m.group(1).upper()

        # Check filename for _plate_<ID>_
        m = re.search(r'_plate_([A-Za-z]{2}\\d{2})_', os.path.basename(p), re.IGNORECASE)
        if m:
            return m.group(1).upper()

    return None


def _detect_plate_from_nkpath(parts: tuple[str, ...]) -> Optional[str]:
    """
    Detect plate ID from .nk path segments.

    Args:
        parts: Path components from Path.parts

    Returns:
        Plate ID in uppercase (e.g., "FG01") or None if not found
    """
    for seg in parts:
        m = PLATE_RX.search(seg)
        if m:
            return m.group(1).upper()
    return None


def _collect_plate_dirs(scene_root: Path) -> list[tuple[Path, str]]:
    """
    Collect plate directories from scene root.

    Args:
        scene_root: Root directory to scan

    Returns:
        List of tuples: (plate_directory_path, plate_id_uppercase)
    """
    out: list[tuple[Path, str]] = []
    if not scene_root.exists():
        return out

    for d in scene_root.iterdir():
        if d.is_dir():
            m = PLATE_RX.fullmatch(d.name)
            if m:
                out.append((d, m.group(1).upper()))

    return out


def _scan_plate_seq(
    dir_path: Path,
    shot: str,
    vnum: str,
    plate_id: Optional[str]
) -> Optional[tuple[str, str, int, int, int, list[Path]]]:
    """
    Scan directory for plate image sequences.

    Args:
        dir_path: Directory to scan for sequences
        shot: Shot name to match
        vnum: Version number string
        plate_id: Plate ID to match or None for wildcard

    Returns:
        Tuple of (prefix_path, extension, min_frame, max_frame, padding, file_list) or None
    """
    if plate_id:
        rx = re.compile(
            rf"^{re.escape(shot)}_turnover-plate_{re.escape(plate_id)}_.+?_v{re.escape(vnum)}\\.(\d+)\\.([A-Za-z0-9]+)$"
        )
    else:
        rx = re.compile(
            rf"^{re.escape(shot)}_turnover-plate_[A-Za-z0-9]+_.+?_v{re.escape(vnum)}\\.(\d+)\\.([A-Za-z0-9]+)$"
        )

    files: list[tuple[Path, int, int, str]] = []
    if not dir_path.exists():
        return None

    for p in dir_path.iterdir():
        if not p.is_file():
            continue
        m = rx.match(p.name)
        if not m:
            continue
        frame_str, ext = m.group(1), m.group(2)
        files.append((p, int(frame_str), len(frame_str), ext))

    if not files:
        return None

    # Group by (prefix_without_frame, ext) and pick the largest, newest
    groups: dict[tuple[str, str], list[tuple[Path, int, int, str]]] = {}
    for p, frame, pad, ext in files:
        prefix = re.sub(r"\\.\\d+\\.[A-Za-z0-9]+$", "", str(p))
        groups.setdefault((prefix, ext.lower()), []).append((p, frame, pad, ext))

    def group_key(kv: tuple[tuple[str, str], list[tuple[Path, int, int, str]]]) -> tuple[int, float]:
        _, vals = kv
        count = len(vals)
        newest = max(v[0].stat().st_mtime for v in vals)
        return (count, newest)

    (best_prefix, ext), vals = max(groups.items(), key=group_key)
    frames = [v[1] for v in vals]
    pads = [v[2] for v in vals]
    fmin, fmax = min(frames), max(frames)
    pad = max(pads)

    return best_prefix, ext, fmin, fmax, pad, [v[0] for v in vals]


def _find_latest_plate(
    show: str, seq: str, shot: str, plate_id: Optional[str]
) -> tuple[str, str, int, int, int, str, str]:
    """
    Find the latest plate sequence.

    Args:
        show: Show name
        seq: Sequence name
        shot: Shot name
        plate_id: Detected plate ID or None

    Returns:
        Tuple of (prefix, ext, fmin, fmax, pad, version_str, plate_id)

    Raises:
        RuntimeError: If no plates found
    """
    plate_root = PipelineConfig.get_plate_root(show, seq, shot)
    if not plate_root.exists():
        _err(f"Plate root not found:\\n{plate_root}")

    # Gather candidate plate folders
    bg_dirs: list[Path]
    if plate_id and (plate_root / plate_id).exists():
        bg_dirs = [plate_root / plate_id]
    else:
        bg_dirs = [d for d in plate_root.iterdir() if d.is_dir()]

    chosen: Optional[tuple[str, str, int, int, int, list[Path]]] = None
    chosen_v: Optional[str] = None
    chosen_bg: Optional[str] = None

    # Find latest v### that has frames under .../exr/[WxH]/ or .../exr/
    for bg_dir in bg_dirs:
        vdirs = [
            d for d in bg_dir.iterdir()
            if d.is_dir() and re.match(r"v\\d+$", d.name, re.IGNORECASE)
        ]
        vdirs.sort(key=lambda d: _version_num(d.name), reverse=True)

        for vdir in vdirs:
            vnum = vdir.name[1:].zfill(3)
            exr_dir = vdir / "exr"
            if not exr_dir.exists():
                continue

            # 1) Directly in exr/
            hit = _scan_plate_seq(exr_dir, shot, vnum, plate_id=bg_dir.name)
            if hit:
                chosen = hit
                chosen_v = vnum
                chosen_bg = bg_dir.name
                break

            # 2) Subfolder like 4448x3096 inside exr/
            for sd in [d for d in exr_dir.iterdir() if d.is_dir()]:
                hit = _scan_plate_seq(sd, shot, vnum, plate_id=bg_dir.name)
                if hit:
                    chosen = hit
                    chosen_v = vnum
                    chosen_bg = bg_dir.name
                    break
            if chosen:
                break
        if chosen:
            break

    if not chosen:
        _err("No plate sequences found under:\\n" + str(plate_root))

    # Unpack results
    best_prefix, ext, fmin, fmax, pad, _files = chosen

    return best_prefix, ext, fmin, fmax, pad, chosen_v, chosen_bg


# ============================================================================
# LD FINDING & IMPORT (from mm_ld_import.py)
# ============================================================================

LD_TAIL_RX = re.compile(r'_LD_v(\\d+)\\.nk$', re.IGNORECASE)
TURNOVER_RX_TMPL = r'^{plate}_{shot}_turnover-plate_{plate}_.+$'


def _path_has_dot_dir(p: Path, stop_at: Path) -> bool:
    """
    Check if any ancestor directory (between stop_at and p) contains a dot.

    Args:
        p: File path to check
        stop_at: Directory to stop checking at

    Returns:
        True if any ancestor directory name contains a dot
    """
    cur = p.parent
    while True:
        if cur == stop_at or cur == stop_at.parent or cur == cur.parent:
            break
        if '.' in cur.name:
            return True
        cur = cur.parent
    return False


def _find_latest_ld_under(
    plate_dir: Path,
    shot: str,
    plate: str
) -> tuple[Optional[Path], Optional[str]]:
    """
    Find the latest lens distortion .nk file under a plate directory.

    Args:
        plate_dir: Plate directory to search
        shot: Shot name for filename matching
        plate: Plate ID for filename matching

    Returns:
        Tuple of (best_file_path, version_string) or (None, None)
    """
    nld = plate_dir / "nuke_lens_distortion"
    if not nld.exists():
        return None, None

    # Find version directories
    vdirs = [
        d for d in nld.iterdir()
        if d.is_dir() and re.match(r'v\\d+$', d.name, re.IGNORECASE)
    ]
    if not vdirs:
        return None, None
    vdirs.sort(key=lambda d: _version_num(d.name), reverse=True)

    # Precompile scoring regexes
    fname_rx = re.compile(
        rf'^{re.escape(shot)}_mm_default_{re.escape(plate)}_LD_v(\\d+)\\.nk$',
        re.IGNORECASE
    )
    turnover_rx = re.compile(
        TURNOVER_RX_TMPL.format(plate=re.escape(plate), shot=re.escape(shot)),
        re.IGNORECASE
    )
    plate_rx_inline = re.compile(re.escape(plate), re.IGNORECASE)

    best: Optional[Path] = None
    best_v: Optional[str] = None
    best_score: Optional[int] = None
    best_mtime: Optional[float] = None

    # Search latest versions first
    for vdir in vdirs:
        vnum = vdir.name[1:].zfill(3)

        for p in vdir.rglob("*.nk"):
            # Must end with _LD_v###.nk
            if not LD_TAIL_RX.search(p.name):
                continue

            # Skip paths with dot directories
            if _path_has_dot_dir(p, vdir):
                continue

            # Score candidate
            score = 0
            if fname_rx.match(p.name):
                score += 6
            if turnover_rx.match(p.parent.name):
                score += 3
            if plate_rx_inline.search(str(p.parent)) or plate_rx_inline.search(p.name):
                score += 1

            mtime = p.stat().st_mtime

            # Higher score wins; newest mtime breaks ties
            if best is None or (score, mtime) > (best_score, best_mtime):
                best, best_v, best_score, best_mtime = p, vnum, score, mtime

        # Stop at first version that yields any acceptable candidate
        if best:
            break

    return best, best_v


def _find_latest_ld(
    show: str, seq: str, shot: str, user: str, plate_id: Optional[str]
) -> tuple[Path, str, str]:
    """
    Find the latest LD file for the given plate.

    Args:
        show: Show name
        seq: Sequence name
        shot: Shot name
        user: User name
        plate_id: Detected plate ID

    Returns:
        Tuple of (ld_file_path, version_string, plate_id)

    Raises:
        RuntimeError: If no LD files found
    """
    scene_root = PipelineConfig.get_ld_root(show, seq, shot, user)

    # Build plate preference list
    plate_candidates: list[str] = []

    if plate_id:
        plate_candidates.append(plate_id)

    for d, pid in _collect_plate_dirs(scene_root):
        if pid not in plate_candidates:
            plate_candidates.append(pid)

    if not plate_candidates:
        _err(f"No plate folders found under:\\n{scene_root}")

    # Search for LD file in order of plate preference
    chosen_file: Optional[Path] = None
    chosen_v: Optional[str] = None
    chosen_plate: Optional[str] = None

    for pid in plate_candidates:
        ld_file, vnum = _find_latest_ld_under(scene_root / pid, shot, pid)
        if ld_file:
            chosen_file, chosen_v, chosen_plate = ld_file, vnum, pid
            break

    if not chosen_file:
        _err("No 3DE LD .nk found under any plate folder in:\\n" + str(scene_root))

    return chosen_file, chosen_v, chosen_plate


# ============================================================================
# MAIN SETUP FUNCTION
# ============================================================================

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
    show, seq, shot, user = _infer_context_from_nk()
    nk_parts = Path(nuke.root().name()).parts

    # Detect plate ID
    plate_id = _detect_plate_from_reads()
    if not plate_id:
        plate_id = _detect_plate_from_nkpath(tuple(s.lower() for s in nk_parts))

    nuke.tprint(f"[Export Setup] Detected plate ID: {plate_id or '(auto-detect from available plates)'}")

    # Find latest playblast
    nuke.tprint(f"[Export Setup] Finding latest {category} playblast...")
    playblast_data, playblast_v = _find_latest_playblast(show, seq, shot, user, category)

    # Find latest plate
    nuke.tprint(f"[Export Setup] Finding latest plate...")
    plate_prefix, plate_ext, plate_fmin, plate_fmax, plate_pad, plate_v, plate_bg = _find_latest_plate(
        show, seq, shot, plate_id
    )

    # Find latest LD
    nuke.tprint(f"[Export Setup] Finding latest LD file...")
    ld_file, ld_v, ld_plate = _find_latest_ld(show, seq, shot, user, plate_bg)

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
        _err("Internal error: unknown playblast type.")

    # ========================================================================
    # 2. CREATE TRANSFORM NODE
    # ========================================================================
    nuke.tprint(f"[Export Setup] Creating Transform node...")

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
    ld_group: Optional[nuke.Node] = None
    for n in pasted:
        if n.Class() in ("Group", "LiveGroup"):
            ld_group = n
            break

    if not ld_group:
        _err(f"No Group/LiveGroup found in pasted LD file:\\n{ld_file}")

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
    nuke.tprint(f"[Export Setup] Creating plate Read node...")

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
    nuke.tprint(f"[Export Setup] Creating Merge node...")

    merge = nuke.nodes.Merge2()
    merge["name"].setValue("Merge_WireframePlate")

    # Connect inputs: A=Plate (foreground), B=Wireframe+LD (background)
    merge.setInput(0, ld_group)  # B input (background)
    merge.setInput(1, plate_read)  # A input (foreground)

    # ========================================================================
    # 6. CREATE WRITETANK NODE
    # ========================================================================
    nuke.tprint(f"[Export Setup] Creating WriteTank node...")

    # Check if WriteTank exists
    try:
        write_tank = nuke.nodes.WriteTank()
    except Exception:
        _err("WriteTank node type not found.\\nThis node requires Shotgun/Flow toolkit integration.")

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

    nuke.tprint(f"[Export Setup] ✓ Complete! Created 6-node export pipeline")
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

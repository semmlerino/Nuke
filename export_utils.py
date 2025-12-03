"""
export_utils.py

Shared utilities for export setup scripts.

This module contains common functions used by:
- mm_wireframe_export_setup.py
- mm_slapcomp_export_setup.py
- mm_plate_read.py

Functions include:
- Context parsing from Nuke script path
- Playblast finding and scanning
- Plate ID detection and finding
- Lens distortion file finding
- User prompts for ambiguous selections

Path structures:
    Playblast: /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/maya/playblast/{category}/v###/
    Plate: /shows/<show>/shots/<seq>/<shot>/publish/turnover/plate/input_plate/<PLATE>/v###/exr/
    LD: /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/3de/mm-default/exports/scene/<PLATE>/nuke_lens_distortion/v###/
"""

import os
import re
from pathlib import Path
from typing import Any, NoReturn

import nuke

from pipeline_config import PipelineConfig

# ============================================================================
# CORE UTILITIES
# ============================================================================

def err(msg: str) -> NoReturn:
    """
    Display error message to user and raise RuntimeError.

    Args:
        msg: Error message to display

    Raises:
        RuntimeError: Always raised after showing message
    """
    nuke.message(msg)
    raise RuntimeError(msg)


def find_index(parts: tuple[str, ...], name: str) -> int:
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


def version_num(vname: str) -> int:
    """
    Extract version number from version string.

    Args:
        vname: Version string (e.g., "v001", "V123")

    Returns:
        Version number as integer, or -1 if invalid format
    """
    m = re.match(r"v(\d+)$", vname, re.IGNORECASE)
    return int(m.group(1)) if m else -1


def infer_context_from_nk() -> tuple[str, str, str, str]:
    """
    Parse show, seq, shot, and user from current Nuke script path.

    Returns:
        Tuple of (show, seq, shot, user)

    Raises:
        RuntimeError: If script not saved or path doesn't match expected structure
    """
    nk_path = nuke.root().name()
    if not nk_path or nk_path == "Root":
        err("Please save the Nuke script first so I can infer the shot path.")

    p = Path(nk_path)
    parts = p.parts
    i_shows = find_index(parts, "shows")
    i_shots = find_index(parts, "shots")
    i_user = find_index(parts, "user")

    if min(i_shows, i_shots, i_user) < 0:
        err("Couldn't parse show/shot/user from the Nuke script path.\nExpected /shows/<show>/shots/<seq>/<shot>/user/<user>/...")

    try:
        show = parts[i_shows+1]
        seq = parts[i_shots+1]
        shot = parts[i_shots+2]
        user = parts[i_user+1]
    except Exception:
        err("Path didn't have enough segments after /shows or /shots or /user.")

    return show, seq, shot, user


# ============================================================================
# PLAYBLAST FINDING
# ============================================================================

def scan_playblast(vdir: Path, base_name: str) -> dict[str, Any] | None:
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
    rx_seq = re.compile(rf"^{re.escape(base_name)}\.(\d+)\.([A-Za-z0-9]+)$", re.IGNORECASE)
    files: list[tuple[Path, int, int, str]] = []

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
        groups: dict[str, list[tuple[Path, int, int, str]]] = {}
        for p, frame, pad, ext in files:
            key = ext.lower()
            groups.setdefault(key, []).append((p, frame, pad, ext))

        # Choose the group with most files, then newest mtime
        def group_key(kv: tuple[str, list[tuple[Path, int, int, str]]]) -> tuple[int, float]:
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


def find_latest_playblast(
    show: str, seq: str, shot: str, user: str, category: str
) -> tuple[dict[str, Any], str]:
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
        err(f"Playblast root not found:\n{playblast_root}")

    cat_dir = playblast_root / category
    if not cat_dir.exists() or not cat_dir.is_dir():
        err(f"No '{category}' folder under:\n{playblast_root}")

    # Find version directories (latest first)
    vdirs = [
        d for d in cat_dir.iterdir()
        if d.is_dir() and re.match(r"v\d+$", d.name, re.IGNORECASE)
    ]
    if not vdirs:
        err(f"No version folders under:\n{cat_dir}")
    vdirs.sort(key=lambda d: version_num(d.name), reverse=True)

    chosen: dict[str, Any] | None = None
    chosen_v: str | None = None

    for vdir in vdirs:
        hit = scan_playblast(vdir, category)
        if hit:
            chosen = hit
            chosen_v = vdir.name[1:].zfill(3)
            break

    if not chosen:
        err(f"No sequences or movies matching '{category}' found under versions in:\n{cat_dir}")

    assert chosen_v is not None  # Set when chosen is set
    return chosen, chosen_v


# ============================================================================
# PLATE ID DETECTION & FINDING
# ============================================================================

PLATE_RX = re.compile(r'\b([A-Z]{2}\d{2})\b', re.IGNORECASE)


def norm_plate_token(tok: str) -> str | None:
    """
    Normalize plate token to standard format.

    Args:
        tok: Token to normalize (e.g., "fg1", "FG01")

    Returns:
        Normalized plate ID (e.g., "FG01") or None if invalid
    """
    m = re.match(r"^([A-Za-z]{2})(\d{1,2})$", tok)
    if not m:
        return None
    letters = m.group(1).upper()
    digits = f"{int(m.group(2)):02d}"
    return f"{letters}{digits}"


def detect_plate_from_reads() -> str | None:
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
        m = re.search(r'/plate/(?:input_plate|output_plate)/([A-Za-z]{2}\d{2})/', p, re.IGNORECASE)
        if m:
            return m.group(1).upper()

        # Check filename for _plate_<ID>_
        m = re.search(r'_plate_([A-Za-z]{2}\d{2})_', os.path.basename(p), re.IGNORECASE)
        if m:
            return m.group(1).upper()

    return None


def detect_plate_from_nkpath(parts: tuple[str, ...]) -> str | None:
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


def collect_plate_dirs(scene_root: Path) -> list[tuple[Path, str]]:
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


def scan_plate_seq(
    dir_path: Path,
    shot: str,
    vnum: str,
    plate_id: str | None
) -> tuple[str, str, int, int, int, list[Path]] | None:
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
            rf"^{re.escape(shot)}_turnover-plate_{re.escape(plate_id)}_.+?_v{re.escape(vnum)}\.(\d+)\.([A-Za-z0-9]+)$"
        )
    else:
        rx = re.compile(
            rf"^{re.escape(shot)}_turnover-plate_[A-Za-z0-9]+_.+?_v{re.escape(vnum)}\.(\d+)\.([A-Za-z0-9]+)$"
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
        prefix = re.sub(r"\.\d+\.[A-Za-z0-9]+$", "", str(p))
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


def find_latest_plate(
    show: str, seq: str, shot: str, plate_id: str | None,
    prompt_on_ambiguity: bool = True
) -> tuple[str, str, int, int, int, str, str]:
    """
    Find the latest plate sequence.

    Args:
        show: Show name
        seq: Sequence name
        shot: Shot name
        plate_id: Detected plate ID or None
        prompt_on_ambiguity: If True, show user dialog when multiple plates found
            and no plate ID was detected

    Returns:
        Tuple of (prefix, ext, fmin, fmax, pad, version_str, plate_id)

    Raises:
        RuntimeError: If no plates found or user cancels selection
    """
    plate_root = PipelineConfig.get_plate_root(show, seq, shot)
    if not plate_root.exists():
        err(f"Plate root not found:\n{plate_root}")

    # Gather candidate plate folders
    bg_dirs: list[Path]
    if plate_id and (plate_root / plate_id).exists():
        bg_dirs = [plate_root / plate_id]
    else:
        # Get all plate directories and sort alphabetically for deterministic order
        bg_dirs = sorted([d for d in plate_root.iterdir() if d.is_dir()])

        # If multiple plates and no plate ID detected, prompt user
        if len(bg_dirs) > 1 and prompt_on_ambiguity:
            choices = [d.name for d in bg_dirs]
            nuke.tprint(f"[Plate Selection] Multiple plates found: {', '.join(choices)}")

            # Show user dialog to select plate
            panel = nuke.Panel("Select Plate")
            panel.addEnumerationPulldown("Plate:", " ".join(choices))
            result = panel.show()

            if not result:
                err("Plate selection cancelled by user.")

            selected_plate = panel.value("Plate:")
            nuke.tprint(f"[Plate Selection] User selected: {selected_plate}")

            # Filter to just the selected plate
            bg_dirs = [d for d in bg_dirs if d.name == selected_plate]
            if not bg_dirs:
                err(f"Selected plate '{selected_plate}' not found.")

    chosen: tuple[str, str, int, int, int, list[Path]] | None = None
    chosen_v: str | None = None
    chosen_bg: str | None = None

    # Find latest v### that has frames under .../exr/[WxH]/ or .../exr/
    for bg_dir in bg_dirs:
        vdirs = [
            d for d in bg_dir.iterdir()
            if d.is_dir() and re.match(r"v\d+$", d.name, re.IGNORECASE)
        ]
        vdirs.sort(key=lambda d: version_num(d.name), reverse=True)

        for vdir in vdirs:
            vnum = vdir.name[1:].zfill(3)
            exr_dir = vdir / "exr"
            if not exr_dir.exists():
                continue

            # 1) Directly in exr/
            hit = scan_plate_seq(exr_dir, shot, vnum, plate_id=bg_dir.name)
            if hit:
                chosen = hit
                chosen_v = vnum
                chosen_bg = bg_dir.name
                break

            # 2) Subfolder like 4448x3096 inside exr/
            for sd in [d for d in exr_dir.iterdir() if d.is_dir()]:
                hit = scan_plate_seq(sd, shot, vnum, plate_id=bg_dir.name)
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
        err("No plate sequences found under:\n" + str(plate_root))

    # Unpack results
    best_prefix, ext, fmin, fmax, pad, _files = chosen

    assert chosen_v is not None and chosen_bg is not None  # Set when chosen is set
    return best_prefix, ext, fmin, fmax, pad, chosen_v, chosen_bg


# ============================================================================
# LD FINDING & IMPORT
# ============================================================================

LD_TAIL_RX = re.compile(r'_LD_v(\d+)\.nk$', re.IGNORECASE)
TURNOVER_RX_TMPL = r'^{plate}_{shot}_turnover-plate_{plate}_.+$'


def path_has_dot_dir(p: Path, stop_at: Path) -> bool:
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


def find_latest_ld_under(
    plate_dir: Path,
    shot: str,
    plate: str
) -> tuple[Path | None, str | None]:
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
        if d.is_dir() and re.match(r'v\d+$', d.name, re.IGNORECASE)
    ]
    if not vdirs:
        return None, None
    vdirs.sort(key=lambda d: version_num(d.name), reverse=True)

    # Precompile scoring regexes
    fname_rx = re.compile(
        rf'^{re.escape(shot)}_mm_default_{re.escape(plate)}_LD_v(\d+)\.nk$',
        re.IGNORECASE
    )
    turnover_rx = re.compile(
        TURNOVER_RX_TMPL.format(plate=re.escape(plate), shot=re.escape(shot)),
        re.IGNORECASE
    )
    plate_rx_inline = re.compile(re.escape(plate), re.IGNORECASE)

    best: Path | None = None
    best_v: str | None = None
    best_score: int | None = None
    best_mtime: float | None = None

    # Search latest versions first
    for vdir in vdirs:
        vnum = vdir.name[1:].zfill(3)

        for p in vdir.rglob("*.nk"):
            # Must end with _LD_v###.nk
            if not LD_TAIL_RX.search(p.name):
                continue

            # Skip paths with dot directories
            if path_has_dot_dir(p, vdir):
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


def find_latest_ld(
    show: str, seq: str, shot: str, user: str, plate_id: str | None
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

    for _d, pid in collect_plate_dirs(scene_root):
        if pid not in plate_candidates:
            plate_candidates.append(pid)

    if not plate_candidates:
        err(f"No plate folders found under:\n{scene_root}")

    # Search for LD file in order of plate preference
    chosen_file: Path | None = None
    chosen_v: str | None = None
    chosen_plate: str | None = None

    for pid in plate_candidates:
        ld_file, vnum = find_latest_ld_under(scene_root / pid, shot, pid)
        if ld_file:
            chosen_file, chosen_v, chosen_plate = ld_file, vnum, pid
            break

    if not chosen_file:
        err("No 3DE LD .nk found under any plate folder in:\n" + str(scene_root))

    assert chosen_v is not None and chosen_plate is not None  # Set when chosen_file is set
    return chosen_file, chosen_v, chosen_plate

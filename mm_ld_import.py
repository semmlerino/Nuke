"""
mm_ld_import.py

Import (paste) the latest 3DE lens distortion Nuke script for the current shot.

This script finds and imports 3DE-exported lens distortion .nk files, intelligently
selecting the best match based on filename patterns, folder structure, and modification
time. It uses a scoring system to prefer files that match expected conventions.
If a node is selected when running, the LD group will be automatically connected to it.

Path structure:
    /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/3de/mm-default/exports/scene/<PLATE>/nuke_lens_distortion/v###/

Filename preferences (scored):
    1. <SHOT>_mm_default_<PLATE>_LD_v###.nk (highest priority)
    2. Folder name matches turnover context: <PLATE>_<SHOT>_turnover-plate_<PLATE>_...
    3. Path contains plate token
    4. Files under directories with dots (e.g., IMG_1241.JPG/) are skipped

Plate ID detection:
    - From existing Read nodes in current script
    - From .nk filename or path segments
    - From scene/ subdirectories (FG01, BG01, etc.)

Features:
    - Automatically connects to selected node (e.g., a Read node)
    - Renames main Group/LiveGroup to LD_3DE_<PLATE>_v###

Usage:
    import mm_ld_import
    mm_ld_import.run()  # Pastes latest LD .nk and connects to selected node
"""

import os
import re
from pathlib import Path
from typing import NoReturn

import nuke

from pipeline_config import PipelineConfig

# Regex patterns
PLATE_RX = re.compile(r'\b([A-Z]{2}\d{2})\b', re.IGNORECASE)  # FG01 / BG01 / MG01 ...
LD_TAIL_RX = re.compile(r'_LD_v(\d+)\.nk$', re.IGNORECASE)
TURNOVER_RX_TMPL = r'^{plate}_{shot}_turnover-plate_{plate}_.+$'  # folder name pattern


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


def _idx(parts: tuple[str, ...], name: str) -> int:
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


def _vnum(s: str) -> int:
    """
    Extract version number from version string.

    Args:
        s: Version string (e.g., "v001", "V123")

    Returns:
        Version number as integer, or -1 if invalid format
    """
    m = re.match(r'v(\d+)$', s, re.IGNORECASE)
    return int(m.group(1)) if m else -1


def _detect_plate_from_reads() -> str | None:
    """
    Detect plate ID from existing Read nodes in the current Nuke script.

    Searches Read node file paths for patterns like:
        - .../plate/input_plate/<ID>/...
        - .../plate/output_plate/<ID>/...
        - ..._plate_<ID>_... in filename

    Returns:
        Plate ID in uppercase (e.g., "FG01") or None if not found

    Example:
        Read node with file: "/shows/demo/.../plate/input_plate/FG01/..."
        Returns: "FG01"
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


def _detect_plate_from_nkpath(parts: tuple[str, ...]) -> str | None:
    """
    Detect plate ID from .nk path segments.

    Searches for patterns like FG01, BG01, MG01 in the path.

    Args:
        parts: Path components from Path.parts

    Returns:
        Plate ID in uppercase (e.g., "FG01") or None if not found

    Example:
        Path: .../scene/FG01/comp_v001.nk
        Returns: "FG01"
    """
    for seg in parts:
        m = PLATE_RX.search(seg)
        if m:
            return m.group(1).upper()
    return None


def _collect_plate_dirs(scene_root: Path) -> list[tuple[Path, str]]:
    """
    Collect plate directories from scene root.

    Scans scene root for subdirectories matching plate ID pattern (e.g., FG01, BG01).

    Args:
        scene_root: Root directory to scan (typically .../exports/scene/)

    Returns:
        List of tuples: (plate_directory_path, plate_id_uppercase)

    Example:
        scene_root contains: FG01/, BG01/, MG02/
        Returns: [(Path('.../FG01'), 'FG01'), (Path('.../BG01'), 'BG01'), ...]
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


def _path_has_dot_dir(p: Path, stop_at: Path) -> bool:
    """
    Check if any ancestor directory (between stop_at and p) contains a dot.

    This helps skip spurious files in folders like "IMG_1241.JPG/".

    Args:
        p: File path to check
        stop_at: Directory to stop checking at

    Returns:
        True if any ancestor directory name contains a dot

    Example:
        p = Path("/path/IMG_1241.JPG/subdir/file.nk")
        stop_at = Path("/path")
        Returns: True (IMG_1241.JPG contains dot)
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
) -> tuple[Path | None, str | None]:
    """
    Find the latest lens distortion .nk file under a plate directory.

    Searches plate_dir/nuke_lens_distortion/v###/** for *_LD_v###.nk files.
    Uses a scoring system to rank candidates:
        +6: Filename exactly matches <SHOT>_mm_default_<PLATE>_LD_v###.nk
        +3: Parent folder matches turnover context pattern
        +1: Path contains plate token
        -∞: Path contains directory with dot in name (skipped)

    Picks highest scoring candidate from the latest version directory,
    using newest mtime as tiebreaker.

    Args:
        plate_dir: Plate directory to search (e.g., .../scene/FG01/)
        shot: Shot name for filename matching
        plate: Plate ID for filename matching

    Returns:
        Tuple of (best_file_path, version_string) or (None, None) if not found

    Example:
        Returns: (Path(".../v003/FG01_shot_LD_v003.nk"), "003")
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
    vdirs.sort(key=lambda d: _vnum(d.name), reverse=True)

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

            # Skip paths with dot directories (e.g., IMG_1241.JPG/)
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


def import_latest_ld_nk() -> list[nuke.Node]:
    """
    Import the latest 3DE lens distortion .nk file into the current script.

    Parses the current Nuke script path to determine show/shot context,
    detects the appropriate plate ID, then searches for the best matching
    lens distortion file. If a node is selected before running, the LD group
    will be automatically connected to it.

    The search process:
    1. Parse show/seq/shot/user from current .nk file path
    2. Detect plate ID from Read nodes, filename, or path
    3. Search scene/<PLATE>/nuke_lens_distortion/v###/ directories
    4. Score candidates and select best match
    5. Paste .nk file contents into current script
    6. Rename primary Group/LiveGroup node with plate ID and version
    7. Connect LD group to selected node (if any)

    Returns:
        List of pasted Nuke nodes

    Raises:
        RuntimeError: If script not saved, path unparseable, or no LD files found

    Example:
        With a Read node selected, pastes contents of:
        .../FG01/nuke_lens_distortion/v003/shot_mm_default_FG01_LD_v003.nk

        Creates Group node named: "LD_3DE_FG01_v003"
        And connects it to the selected Read node
    """
    nk_path = nuke.root().name()
    if not nk_path or nk_path == "Root":
        _err("Please save the Nuke script first so I can infer the shot path.")

    parts = Path(nk_path).parts
    i_shows = _idx(parts, "shows")
    i_shots = _idx(parts, "shots")
    i_user = _idx(parts, "user")
    if min(i_shows, i_shots, i_user) < 0:
        _err("Couldn't parse show/shot/user from path.\nExpected /shows/<show>/shots/<seq>/<shot>/user/<user>/...")

    show = parts[i_shows+1]
    seq = parts[i_shots+1]
    shot = parts[i_shots+2]
    user = parts[i_user+1]

    # Get LD root using config
    scene_root = PipelineConfig.get_ld_root(show, seq, shot, user)

    # Build plate preference list: Reads -> NK path -> all scene/* plate dirs
    plate_candidates: list[str] = []

    p_from_reads = _detect_plate_from_reads()
    if p_from_reads:
        plate_candidates.append(p_from_reads)

    p_from_nk = _detect_plate_from_nkpath(tuple(s.lower() for s in parts))
    if p_from_nk and p_from_nk not in plate_candidates:
        plate_candidates.append(p_from_nk)

    for _d, pid in _collect_plate_dirs(scene_root):
        if pid not in plate_candidates:
            plate_candidates.append(pid)

    if not plate_candidates:
        _err(f"No plate folders found under:\n{scene_root}")

    # Search for LD file in order of plate preference
    chosen_file: Path | None = None
    chosen_v: str | None = None
    chosen_plate: str | None = None

    for pid in plate_candidates:
        ld_file, vnum = _find_latest_ld_under(scene_root / pid, shot, pid)
        if ld_file:
            chosen_file, chosen_v, chosen_plate = ld_file, vnum, pid
            break

    if not chosen_file:
        _err("No 3DE LD .nk found under any plate folder in:\n" + str(scene_root))

    # Save the currently selected node to connect to it later
    selected_before_paste = nuke.selectedNodes()
    source_node: nuke.Node | None = selected_before_paste[0] if selected_before_paste else None

    # Paste into the graph
    for n in nuke.selectedNodes():
        n.setSelected(False)

    nuke.nodePaste(str(chosen_file))
    pasted = nuke.selectedNodes()

    # Give the primary Group/LiveGroup a stable name with plate & version
    main: nuke.Node | None = None
    for n in pasted:
        if n.Class() in ("Group", "LiveGroup"):
            main = n
            break

    if main:
        try:
            main.setName(f"LD_3DE_{chosen_plate}_v{chosen_v}", unique=False)
        except Exception:
            pass

    # Connect the LD group to the source node if one was selected
    if source_node and main:
        try:
            main.setInput(0, source_node)
            nuke.tprint(f"[3DE-LD] Connected LD group to: {source_node.name()}")
        except Exception as e:
            nuke.tprint(f"[3DE-LD] Warning: Could not connect to {source_node.name()}: {e}")

    nuke.tprint(f"[3DE-LD] Pasted: {chosen_file} ({chosen_plate} v{chosen_v})")
    return pasted


def run() -> list[nuke.Node]:
    """
    Stable entry point for menus and hotkeys.

    Returns:
        List of pasted Nuke nodes

    Example:
        # From menu.py or Script Editor:
        import mm_ld_import
        mm_ld_import.run()
    """
    return import_latest_ld_nk()

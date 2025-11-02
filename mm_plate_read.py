"""
mm_plate_read.py

Create Read nodes for the latest RAW plate sequences.

This script automates finding and loading the latest published plate sequences
for the current shot. It intelligently detects plate IDs (FG01, BG01, etc.) from
the Nuke script path or filename, and searches for matching sequences.

Path structure:
    /shows/<show>/shots/<seq>/<shot>/publish/turnover/plate/input_plate/<PLATEID>/v###/exr/[WxH]/

Filename patterns matched:
    <shot>_turnover-plate_<PLATEID>_<colorspace>_v###.####.exr

Plate ID detection:
    - From NK filename: DM_066_3580_mm-default_FG01_scene_v001.nk -> FG01
    - From path segments: .../scene/FG01/... -> FG01
    - Auto-validates against actual plate folders on disk

Usage:
    import mm_plate_read
    mm_plate_read.run()  # Creates Read node for latest plate
"""

import os
import re
from pathlib import Path
from typing import Optional
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


def _norm_plate_token(tok: str) -> Optional[str]:
    """
    Normalize plate token to standard format.

    Converts various plate ID formats to uppercase 2-letter + 2-digit format.
    Requires exactly 2 letters followed by 1-2 digits.

    Args:
        tok: Token to normalize (e.g., "fg1", "FG01", "bc02")

    Returns:
        Normalized plate ID (e.g., "FG01", "BC02") or None if invalid format

    Example:
        >>> _norm_plate_token("fg1")
        'FG01'
        >>> _norm_plate_token("FG01")
        'FG01'
        >>> _norm_plate_token("bc02")
        'BC02'
        >>> _norm_plate_token("invalid")
        None
    """
    m = re.match(r"^([A-Za-z]{2})(\d{1,2})$", tok)
    if not m:
        return None
    letters = m.group(1).upper()
    digits = f"{int(m.group(2)):02d}"
    return f"{letters}{digits}"


def _candidate_plate_ids_from_path(nk_path: Path) -> list[str]:
    """
    Extract potential plate IDs from Nuke script path and filename.

    Searches for patterns like FG01, BG01, MG02, BC01 in:
    1. Filename tokens (split on non-alphanumeric)
    2. Directory path segments

    Args:
        nk_path: Path to Nuke script file

    Returns:
        List of normalized plate IDs found (deduplicated, order preserved)

    Example:
        For path: .../scene/FG01/DM_066_FG01_v001.nk
        Returns: ['FG01']
    """
    cands: list[str] = []

    # 1) From filename tokens (split on non-alnum)
    stem = nk_path.stem
    for tok in re.split(r"[^A-Za-z0-9]+", stem):
        norm = _norm_plate_token(tok) if tok else None
        if norm:
            cands.append(norm)

    # 2) From directory segments
    for seg in nk_path.parts:
        norm = _norm_plate_token(seg)
        if norm:
            cands.append(norm)

    # Deduplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in cands:
        if t not in seen:
            seen.add(t)
            out.append(t)

    return out


def _detect_plate_id(nk_path: Path, plate_root: Path) -> Optional[str]:
    """
    Detect the most appropriate plate ID for this shot.

    Tries to match candidate plate IDs from the path against actual
    directories that exist under plate_root. If multiple candidates
    exist, prefers the first one that has a matching folder.

    Args:
        nk_path: Path to current Nuke script
        plate_root: Root directory containing plate ID folders

    Returns:
        Detected plate ID (e.g., "FG01") or None if none found

    Example:
        >>> _detect_plate_id(
        ...     Path("/shows/demo/.../FG01_v001.nk"),
        ...     Path("/shows/demo/.../plate/input_plate")
        ... )
        'FG01'  # if /shows/demo/.../plate/input_plate/FG01 exists
    """
    cands = _candidate_plate_ids_from_path(nk_path)
    if not cands:
        return None

    # Prefer candidate that exists on disk
    for c in cands:
        if (plate_root / c).exists():
            return c

    # Fallback to first detected token
    return cands[0]


def _scan_seq(
    dir_path: Path,
    shot: str,
    vnum: str,
    plate_id: Optional[str]
) -> Optional[tuple[str, str, int, int, int, list[Path]]]:
    """
    Scan directory for plate image sequences matching shot, version, and plate ID.

    Looks for files matching pattern:
        <shot>_turnover-plate_<PLATEID>_<anything>_v<vvv>.<frame>.<ext>

    If plate_id is None, wildcards any plate ID (less specific matching).

    Groups files by prefix and extension, selecting the group with the most
    files and newest modification time.

    Args:
        dir_path: Directory to scan for sequences
        shot: Shot name to match in filenames
        vnum: Version number string (e.g., "001")
        plate_id: Plate ID to match (e.g., "FG01") or None for wildcard

    Returns:
        Tuple of (prefix_path, extension, min_frame, max_frame, padding, file_list)
        or None if no matching sequences found

    Example:
        Result might be:
        ("/path/to/shot_turnover-plate_FG01_linear_v001", "exr", 1001, 1100, 4, [...])
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


def _maybe_set_format_from_res(read_node: nuke.Node, seq_dir: Path) -> None:
    """
    Auto-detect and set format based on resolution folder name.

    Checks if the directory name or parent directory name matches pattern
    like "4448x3096". If found, creates a custom Nuke format and applies it.

    Args:
        read_node: Nuke Read node to set format on
        seq_dir: Directory path that may contain resolution in name

    Example:
        For path: .../v001/exr/4448x3096/
        Creates format: "4448x3096_from_plate"
    """
    def wh(name: Optional[str]) -> tuple[Optional[int], Optional[int]]:
        """Extract width and height from string like '4448x3096'."""
        m = re.match(r"^(\d+)x(\d+)$", name or "")
        return (int(m.group(1)), int(m.group(2))) if m else (None, None)

    w, h = wh(seq_dir.name)
    if not w and seq_dir.parent:
        w, h = wh(seq_dir.parent.name)

    if w and h:
        fmt_name = f"{w}x{h}_from_plate"
        try:
            # Create format if it doesn't exist
            if not any(f.name() == fmt_name for f in nuke.formats()):
                nuke.addFormat(f"{w} {h} 0 0 {w} {h} 1 {fmt_name}")
            read_node["format"].setValue(fmt_name)
        except Exception:
            # Fallback: set format directly
            read_node["format"].setValue(f"{w} {h} 0 0 {w} {h} 1")


def create_latest_plate_read_hash() -> nuke.Node:
    """
    Create a Read node for the latest RAW plate sequence.

    Intelligently detects the appropriate plate ID from the Nuke script path
    and filename, then searches for the latest published plate version.
    Automatically connects to the currently selected node if one exists.

    The search process:
    1. Parse show/seq/shot from current .nk file path
    2. Detect plate ID from filename or path (e.g., FG01)
    3. Find version directories (v001, v002, etc.) in reverse order
    4. Look under exr/ and subfolders like exr/4448x3096/
    5. Scan for matching plate sequences
    6. Create Read node with discovered sequence
    7. Connect to selected node (if any)

    Returns:
        Created Nuke Read node configured with the latest plate sequence

    Raises:
        RuntimeError: If script not saved, path unparseable, or no sequences found

    Example:
        Creates node named "Read_rawPlate_FG01_v002" pointing to:
        /shows/demo/.../FG01/v002/exr/4448x3096/shot_turnover-plate_FG01_linear_v002.####.exr
        And connects to the selected node if one was selected
    """
    # Save the currently selected node to connect to it later
    selected_nodes = nuke.selectedNodes()
    source_node: Optional[nuke.Node] = selected_nodes[0] if selected_nodes else None

    nk_path = nuke.root().name()
    if not nk_path or nk_path == "Root":
        _err("Please save the Nuke script first so I can infer the shot path.")

    p = Path(nk_path)
    parts = p.parts
    i_shows = _find_index(parts, "shows")
    i_shots = _find_index(parts, "shots")
    if min(i_shows, i_shots) < 0:
        _err("Couldn't parse show/shot from the Nuke script path.\nExpected /shows/<show>/shots/<seq>/<shot>/...")

    try:
        show = parts[i_shows+1]
        seq = parts[i_shots+1]
        shot = parts[i_shots+2]
    except Exception:
        _err("Path didn't have enough segments after /shows or /shots.")

    # Get plate root using config
    plate_root = PipelineConfig.get_plate_root(show, seq, shot)
    if not plate_root.exists():
        _err(f"Plate root not found:\n{plate_root}")

    # Detect preferred plate ID
    plate_id = _detect_plate_id(p, plate_root)

    # Gather candidate plate folders (prefer detected ID if it exists, else scan all)
    bg_dirs: list[Path]
    if plate_id and (plate_root / plate_id).exists():
        bg_dirs = [plate_root / plate_id]
    else:
        bg_dirs = [d for d in plate_root.iterdir() if d.is_dir()]

    chosen: Optional[tuple[str, str, int, int, int, list[Path]]] = None
    chosen_v: Optional[str] = None
    chosen_seq_dir: Optional[Path] = None
    chosen_bg: Optional[str] = None

    # For each plate folder, find latest v### that has frames under .../exr/[WxH]/ or .../exr/
    for bg_dir in bg_dirs:
        vdirs = [
            d for d in bg_dir.iterdir()
            if d.is_dir() and re.match(r"v\d+$", d.name, re.IGNORECASE)
        ]
        vdirs.sort(key=lambda d: _version_num(d.name), reverse=True)

        for vdir in vdirs:
            vnum = vdir.name[1:].zfill(3)
            exr_dir = vdir / "exr"
            if not exr_dir.exists():
                continue

            # 1) Directly in exr/
            hit = _scan_seq(exr_dir, shot, vnum, plate_id=bg_dir.name)
            if hit:
                chosen = hit
                chosen_v = vnum
                chosen_seq_dir = exr_dir
                chosen_bg = bg_dir.name
                break

            # 2) Subfolder like 4448x3096 inside exr/
            for sd in [d for d in exr_dir.iterdir() if d.is_dir()]:
                hit = _scan_seq(sd, shot, vnum, plate_id=bg_dir.name)
                if hit:
                    chosen = hit
                    chosen_v = vnum
                    chosen_seq_dir = sd
                    chosen_bg = bg_dir.name
                    break
            if chosen:
                break
        if chosen:
            break

    # Last resort: wildcard any plate ID across all folders/versions
    if not chosen:
        for bg_dir in [d for d in plate_root.iterdir() if d.is_dir()]:
            vdirs = [
                d for d in bg_dir.iterdir()
                if d.is_dir() and re.match(r"v\d+$", d.name, re.IGNORECASE)
            ]
            vdirs.sort(key=lambda d: _version_num(d.name), reverse=True)

            for vdir in vdirs:
                vnum = vdir.name[1:].zfill(3)
                exr_dir = vdir / "exr"
                if not exr_dir.exists():
                    continue

                hit = _scan_seq(exr_dir, shot, vnum, plate_id=None)
                if hit:
                    chosen = hit
                    chosen_v = vnum
                    chosen_seq_dir = exr_dir
                    chosen_bg = bg_dir.name
                    break

                for sd in [d for d in exr_dir.iterdir() if d.is_dir()]:
                    hit = _scan_seq(sd, shot, vnum, plate_id=None)
                    if hit:
                        chosen = hit
                        chosen_v = vnum
                        chosen_seq_dir = sd
                        chosen_bg = bg_dir.name
                        break
                if chosen:
                    break
            if chosen:
                break

    if not chosen:
        _err("No plate sequences found under:\n" + str(plate_root))

    # Unpack results
    best_prefix, ext, fmin, fmax, pad, _files = chosen
    hashes = "#" * pad
    hash_pattern = f"{best_prefix}.{hashes}.{ext}"
    first_frame_path = f"{best_prefix}.{str(fmin).zfill(pad)}.{ext}"

    # Create Read node
    r = nuke.nodes.Read()
    r["name"].setValue(f"Read_rawPlate_{chosen_bg}_v{chosen_v}")

    # Concrete frame first, then #### to make Nuke scan the sequence
    r["file"].fromUserText(first_frame_path)
    r["file"].fromUserText(hash_pattern)

    # Set EXR-specific settings
    if ext.lower() == "exr":
        try:
            r["file_type"].setValue("exr")
        except Exception:
            pass
        try:
            r["colorspace"].setValue("linear")  # Adjust for your OCIO if needed
        except Exception:
            pass
        try:
            r["raw"].setValue(True)
        except Exception:
            pass

    # Set frame range
    for knob, val in (("first", fmin), ("last", fmax), ("origfirst", fmin), ("origlast", fmax)):
        try:
            r[knob].setValue(int(val))
        except Exception:
            pass

    # Auto-detect format from folder name
    if chosen_seq_dir:
        _maybe_set_format_from_res(r, chosen_seq_dir)

    # Reload to scan sequence
    try:
        r["reload"].execute()
    except Exception:
        pass

    # Connect to selected node if one was selected
    if source_node:
        try:
            r.setInput(0, source_node)
            nuke.tprint(f"[plate] Connected to: {source_node.name()}")
        except Exception as e:
            nuke.tprint(f"[plate] Warning: Could not connect to {source_node.name()}: {e}")

    nuke.tprint(f"[plate] Created Read: {hash_pattern}")
    nuke.tprint(f"[plate] Plate: {chosen_bg}  Version v{chosen_v}  Frames: {fmin}-{fmax}  Pad: {pad}")
    return r


def run() -> nuke.Node:
    """
    Stable entry point for menus and hotkeys.

    Returns:
        Created Nuke Read node

    Example:
        # From menu.py or Script Editor:
        import mm_plate_read
        mm_plate_read.run()
    """
    return create_latest_plate_read_hash()

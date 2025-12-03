"""
mm_geo_read.py

Create Read nodes for the latest geometry render sequences.

This script automates the process of finding and loading the latest geometry
renders for the current shot. It searches under version-controlled directories
for image sequences matching the shot's naming convention.

Path structure:
    /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/maya/renders/mm-default/v###/geo*/[WxH]/

Filename patterns matched:
    <shot>_scene_<anything>_v###.####.exr
    <shot>_scene_geoRender_acescg_v001.####.exr
    <shot>_scene_GeoLayer_sRGB_v003.####.exr

Usage:
    import mm_geo_read
    mm_geo_read.run()  # Creates Read node for latest geo render
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

    Example:
        >>> _find_index(("shows", "demo", "shots"), "shows")
        0
        >>> _find_index(("shows", "demo", "shots"), "missing")
        -1
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

    Example:
        >>> _version_num("v001")
        1
        >>> _version_num("V123")
        123
        >>> _version_num("invalid")
        -1
    """
    m = re.match(r"v(\d+)$", vname, re.IGNORECASE)
    return int(m.group(1)) if m else -1


def _scan_seq(
    dir_path: Path,
    shot: str,
    vnum: str
) -> tuple[str, str, int, int, int, list[Path]] | None:
    """
    Scan directory for image sequences matching the shot and version.

    Looks for files matching pattern:
        <shot>_scene_<anything>_v<vvv>.<frame>.<ext>

    Groups files by prefix and extension, selecting the group with the most
    files and newest modification time.

    Args:
        dir_path: Directory to scan for sequences
        shot: Shot name to match in filenames
        vnum: Version number string (e.g., "001")

    Returns:
        Tuple of (prefix_path, extension, min_frame, max_frame, padding, file_list)
        or None if no matching sequences found

    Example:
        Result might be:
        ("/path/to/shot_scene_geoRender_v001", "exr", 1001, 1100, 4, [...])
    """
    rx = re.compile(
        rf"^{re.escape(shot)}_scene_.+?_v{re.escape(vnum)}\.(\d+)\.([A-Za-z0-9]+)$",
        re.IGNORECASE
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

    # Group by (prefix_without_frame, ext)
    groups: dict[tuple[str, str], list[tuple[Path, int, int, str]]] = {}
    for p, frame, pad, ext in files:
        prefix = re.sub(r"\.\d+\.[A-Za-z0-9]+$", "", str(p))
        groups.setdefault((prefix, ext.lower()), []).append((p, frame, pad, ext))

    # Choose group with most files, then newest mtime
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
    like "4096x2268". If found, creates a custom Nuke format and applies it.

    Args:
        read_node: Nuke Read node to set format on
        seq_dir: Directory path that may contain resolution in name

    Example:
        For path: .../v001/geoRender/4096x2268/
        Creates format: "4096x2268_from_geo"
    """
    def wh(name: str | None) -> tuple[int | None, int | None]:
        """Extract width and height from string like '4096x2268'."""
        m = re.match(r"^(\d+)x(\d+)$", name or "")
        return (int(m.group(1)), int(m.group(2))) if m else (None, None)

    w, h = wh(seq_dir.name)
    if not w and seq_dir.parent:
        w, h = wh(seq_dir.parent.name)

    if w and h:
        fmt_name = f"{w}x{h}_from_geo"
        try:
            # Create format if it doesn't exist
            if not any(f.name() == fmt_name for f in nuke.formats()):
                nuke.addFormat(f"{w} {h} 0 0 {w} {h} 1 {fmt_name}")
            read_node["format"].setValue(fmt_name)
        except Exception:
            # Fallback: set format directly
            read_node["format"].setValue(f"{w} {h} 0 0 {w} {h} 1")


def create_latest_geo_read_hash() -> nuke.Node:
    """
    Create a Read node for the latest geometry render sequence.

    Parses the current Nuke script path to determine show/shot context,
    then searches for the latest version containing geometry renders.
    Automatically connects to the currently selected node if one exists.

    The search process:
    1. Parse show/seq/shot/user from current .nk file path
    2. Find version directories (v001, v002, etc.) in reverse order
    3. Look for subdirectories starting with "geo" (geoRender, GeoLayer, etc.)
    4. Scan for matching image sequences
    5. Create Read node with discovered sequence
    6. Connect to selected node (if any)

    Returns:
        Created Nuke Read node configured with the latest geo sequence

    Raises:
        RuntimeError: If script not saved, path unparseable, or no sequences found

    Example:
        Creates node named "Read_geoRender_v003" pointing to:
        /shows/demo/.../v003/geoRender/4096x2268/shot_scene_geoRender_v003.####.exr
    """
    nk_path = nuke.root().name()
    if not nk_path or nk_path == "Root":
        _err("Please save the Nuke script first so I can infer the shot path.")

    # Parse context from path
    try:
        context = PipelineConfig.parse_show_shot_from_path(Path(nk_path))
        show = context['show']
        seq = context['seq']
        shot = context['shot']
        user = context['user']
    except ValueError as e:
        _err(str(e))

    # Get renders root using config
    renders_root = PipelineConfig.get_renders_root(show, seq, shot, user)
    if not renders_root.exists():
        _err(f"Renders root not found:\n{renders_root}")

    # Find version directories (latest first)
    vdirs = [
        d for d in renders_root.iterdir()
        if d.is_dir() and re.match(r"v\d+$", d.name, re.IGNORECASE)
    ]
    if not vdirs:
        _err(f"No version folders under:\n{renders_root}")
    vdirs.sort(key=lambda d: _version_num(d.name), reverse=True)

    chosen: tuple[str, str, int, int, int, list[Path]] | None = None
    chosen_v: str | None = None
    seq_dir_for_format: Path | None = None

    # Search latest versions first
    for vdir in vdirs:
        vnum = vdir.name[1:].zfill(3)

        # Collect any subdirectory starting with "geo"
        geo_dirs = [
            d for d in vdir.iterdir()
            if d.is_dir() and d.name.lower().startswith("geo")
        ]
        if not geo_dirs:
            continue

        # 1) Scan directly in each geo*/ directory
        found: tuple[Path, tuple[str, str, int, int, int, list[Path]]] | None = None
        for gdir in geo_dirs:
            hit = _scan_seq(gdir, shot, vnum)
            if hit:
                found = (gdir, hit)
                break

        # 2) If not found, scan subfolders (e.g., 4096x2268)
        if not found:
            for gdir in geo_dirs:
                for sd in [d for d in gdir.iterdir() if d.is_dir()]:
                    hit = _scan_seq(sd, shot, vnum)
                    if hit:
                        found = (sd, hit)
                        break
                if found:
                    break

        if found:
            seq_dir_for_format, chosen = found
            chosen_v = vnum
            break

    if not chosen:
        _err("No GEO sequences found in any version under:\n" + str(renders_root))

    # Unpack results
    best_prefix, ext, fmin, fmax, pad, _files = chosen
    hashes = "#" * pad
    hash_pattern = f"{best_prefix}.{hashes}.{ext}"
    first_frame_path = f"{best_prefix}.{str(fmin).zfill(pad)}.{ext}"

    # Create Read node
    r = nuke.nodes.Read()
    r["name"].setValue(f"Read_geoRender_v{chosen_v}")

    # Load concrete frame first, then swap to #### for sequence detection
    r["file"].fromUserText(first_frame_path)
    r["file"].fromUserText(hash_pattern)

    # Set EXR-specific settings
    if ext.lower() == "exr":
        for k, v in (("file_type", "exr"), ("colorspace", "linear")):
            try:
                r[k].setValue(v)
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
    if seq_dir_for_format:
        _maybe_set_format_from_res(r, seq_dir_for_format)

    # Reload to scan sequence
    try:
        r["reload"].execute()
    except Exception:
        pass

    # Note: Read nodes are source nodes and don't have inputs.
    # Auto-connection is not applicable for Read nodes.

    nuke.tprint(f"[geo] Created Read: {hash_pattern}")
    nuke.tprint(f"[geo] Version v{chosen_v}  Frames: {fmin}-{fmax}  Pad: {pad}")
    return r


def run() -> nuke.Node:
    """
    Stable entry point for menus and hotkeys.

    Returns:
        Created Nuke Read node

    Example:
        # From menu.py or Script Editor:
        import mm_geo_read
        mm_geo_read.run()
    """
    return create_latest_geo_read_hash()

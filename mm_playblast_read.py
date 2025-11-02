"""
mm_playblast_read.py

Create Read nodes for the latest Maya playblast sequences.

This script automates finding and loading the latest playblast renders from Maya,
supporting both image sequences and movie files. Commonly used for wireframe
previews and animation playback.

Path structure:
    /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/maya/playblast/<category>/v###/

Supported formats:
    - Image sequences: <category>.####.ext (e.g., Wireframe.1001.png)
    - Movie files: <category>.mov/mp4/etc (e.g., Wireframe.mov)

Categories:
    - Wireframe (default)
    - Shaded
    - Custom (any folder name under playblast/)

Usage:
    import mm_playblast_read
    mm_playblast_read.run()  # Creates Read node for latest Wireframe playblast
"""

import os
import re
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


def _scan_playblast(vdir: Path, base_name: str) -> Optional[Dict[str, Any]]:
    """
    Scan a version folder for playblast image sequences or movie files.

    Looks for two types of content:
    1. Image sequence: <base_name>.####.ext (e.g., Wireframe.1001.png)
    2. Movie file: <base_name>.mov/mp4/etc (e.g., Wireframe.mov)

    For sequences, groups by extension and selects the group with most files
    and newest modification time.

    Args:
        vdir: Version directory to scan (e.g., .../Wireframe/v001/)
        base_name: Base name to match (e.g., "Wireframe")

    Returns:
        Dictionary with type-specific data:
            For sequences:
                {
                    "type": "sequence",
                    "best_prefix": str,
                    "ext": str,
                    "fmin": int,
                    "fmax": int,
                    "pad": int,
                    "files": list[Path]
                }
            For movies:
                {
                    "type": "movie",
                    "path": str
                }
            Or None if nothing matches

    Example:
        For Wireframe.1001.png through Wireframe.1100.png:
        Returns: {"type": "sequence", "best_prefix": ".../Wireframe", "ext": "png", ...}

        For Wireframe.mov:
        Returns: {"type": "movie", "path": ".../Wireframe.mov"}
    """
    if not vdir.exists():
        return None

    # 1) Try image sequence
    rx_seq = re.compile(rf"^{re.escape(base_name)}\.(\d+)\.([A-Za-z0-9]+)$", re.IGNORECASE)
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
        # Group by extension. Prefix is constant (base_name).
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
        _err("Couldn't parse show/shot/user from the Nuke script path.\nExpected /shows/<show>/shots/<seq>/<shot>/user/<user>/...")

    try:
        show = parts[i_shows+1]
        seq = parts[i_shots+1]
        shot = parts[i_shots+2]
        user = parts[i_user+1]
    except Exception:
        _err("Path didn't have enough segments after /shows or /shots or /user.")

    return show, seq, shot, user


def create_latest_playblast_read(category: str = "Wireframe") -> nuke.Node:
    """
    Create a Read node for the latest playblast in the specified category.

    Searches for the latest version under the playblast root, supporting both
    image sequences and movie files.

    The search process:
    1. Parse show/seq/shot/user from current .nk file path
    2. Navigate to playblast root: .../mm/maya/playblast/<category>/
    3. Find version directories (v001, v002, etc.) in reverse order
    4. Scan for image sequences or movie files matching category name
    5. Create Read node with discovered content

    Args:
        category: Playblast category folder name (default: "Wireframe")
            Common values: "Wireframe", "Shaded", or any custom folder name

    Returns:
        Created Nuke Read node configured with the latest playblast

    Raises:
        RuntimeError: If script not saved, path unparseable, or no playblasts found

    Example:
        For Wireframe category:
        Creates node named "Read_playblast_Wireframe_v003" pointing to:
        .../playblast/Wireframe/v003/Wireframe.####.png

        For movie file:
        Creates node named "Read_playblast_Wireframe_v002" pointing to:
        .../playblast/Wireframe/v002/Wireframe.mov
    """
    show, seq, shot, user = _infer_context_from_nk()

    # Get playblast root using config
    playblast_root = PipelineConfig.get_playblast_root(show, seq, shot, user)
    if not playblast_root.exists():
        _err(f"Playblast root not found:\n{playblast_root}")

    cat_dir = playblast_root / category
    if not cat_dir.exists() or not cat_dir.is_dir():
        _err(f"No '{category}' folder under:\n{playblast_root}")

    # Find version directories (latest first)
    vdirs = [
        d for d in cat_dir.iterdir()
        if d.is_dir() and re.match(r"v\d+$", d.name, re.IGNORECASE)
    ]
    if not vdirs:
        _err(f"No version folders under:\n{cat_dir}")
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
        _err(f"No sequences or movies matching '{category}' found under versions in:\n{cat_dir}")

    # Build the Read node based on type
    if chosen["type"] == "sequence":
        best_prefix = chosen["best_prefix"]
        ext = chosen["ext"]
        fmin = chosen["fmin"]
        fmax = chosen["fmax"]
        pad = chosen["pad"]

        hashes = "#" * pad
        hash_pattern = f"{best_prefix}.{hashes}.{ext}"
        first_frame_path = f"{best_prefix}.{str(fmin).zfill(pad)}.{ext}"

        r = nuke.nodes.Read()
        r["name"].setValue(f"Read_playblast_{category}_v{chosen_v}")

        # Load a real frame first, then the hash pattern
        r["file"].fromUserText(first_frame_path)
        r["file"].fromUserText(hash_pattern)

        # Set frame range
        for knob, val in (("first", fmin), ("last", fmax), ("origfirst", fmin), ("origlast", fmax)):
            try:
                r[knob].setValue(int(val))
            except Exception:
                pass

        # PNG/JPG etc: leave colorspace to project defaults; EXR: set raw/linear
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

        try:
            r["reload"].execute()
        except Exception:
            pass

        nuke.tprint(f"[playblast] Created Read (sequence): {hash_pattern}")
        nuke.tprint(f"[playblast] Category: {category}  Version v{chosen_v}  Frames: {fmin}-{fmax}  Pad: {pad}")
        return r

    elif chosen["type"] == "movie":
        movie_path = chosen["path"]

        r = nuke.nodes.Read()
        r["name"].setValue(f"Read_playblast_{category}_v{chosen_v}")
        r["file"].fromUserText(movie_path)

        try:
            r["reload"].execute()
        except Exception:
            pass

        nuke.tprint(f"[playblast] Created Read (movie): {movie_path}")
        nuke.tprint(f"[playblast] Category: {category}  Version v{chosen_v}")
        return r

    else:
        _err("Internal error: unknown playblast type.")


def run() -> nuke.Node:
    """
    Stable entry point for menus and hotkeys.

    Creates Read node for Wireframe playblasts by default.
    Change the category parameter if you want different playblast types.

    Returns:
        Created Nuke Read node

    Example:
        # From menu.py or Script Editor:
        import mm_playblast_read
        mm_playblast_read.run()  # Loads Wireframe

        # For custom category:
        mm_playblast_read.create_latest_playblast_read(category="Shaded")
    """
    return create_latest_playblast_read(category="Wireframe")

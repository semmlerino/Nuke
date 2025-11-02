"""
mm_cone_read.py

Create Read nodes for the latest Cones playblast sequences.

This script automates finding and loading the latest Cones playblast renders from Maya,
supporting both image sequences and movie files. Cones renders are typically used for
lighting reference and animation preview.

Path structure:
    /shows/<show>/shots/<seq>/<shot>/user/<user>/mm/maya/playblast/Cones/v###/

Supported formats:
    - Image sequences: Cones.####.ext (e.g., Cones.1001.png)
    - Movie files: Cones.mov/mp4/etc

This is a thin wrapper around mm_playblast_read.py with category="Cones".

Usage:
    import mm_cone_read
    mm_cone_read.run()  # Creates Read node for latest Cones playblast
"""

import nuke
from mm_playblast_read import create_latest_playblast_read


def run() -> nuke.Node:
    """
    Stable entry point for menus and hotkeys.

    Creates Read node for Cones playblasts.

    Returns:
        Created Nuke Read node

    Example:
        # From menu.py or Script Editor:
        import mm_cone_read
        mm_cone_read.run()  # Loads latest Cones playblast
    """
    return create_latest_playblast_read(category="Cones")

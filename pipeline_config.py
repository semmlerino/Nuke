"""
pipeline_config.py

Centralized configuration for VFX pipeline paths and settings.
Manages path templates for renders, plates, lens distortion, and playblasts.
"""

from pathlib import Path
from typing import Dict, Any


class PipelineConfig:
    """
    Configuration class for VFX pipeline paths.

    All path templates use Python format strings with named placeholders:
    - {show}: Show name
    - {seq}: Sequence name
    - {shot}: Shot name
    - {user}: User name
    - {plate}: Plate ID (e.g., FG01, BG01)
    - {category}: Playblast category (e.g., Wireframe)
    """

    # Render paths
    RENDERS_ROOT_TEMPLATE = "/shows/{show}/shots/{seq}/{shot}/user/{user}/mm/maya/renders/mm-default"

    # Plate paths
    PLATE_ROOT_TEMPLATE = "/shows/{show}/shots/{seq}/{shot}/publish/turnover/plate/input_plate"

    # Lens distortion paths
    LD_ROOT_TEMPLATE = "/shows/{show}/shots/{seq}/{shot}/user/{user}/mm/3de/mm-default/exports/scene"

    # Playblast paths
    PLAYBLAST_ROOT_TEMPLATE = "/shows/{show}/shots/{seq}/{shot}/user/{user}/mm/maya/playblast"

    # Nuke output paths
    NUKE_OUTPUTS_TEMPLATE = "/shows/{show}/shots/{seq}/{shot}/user/{user}/mm/nuke/outputs/{subdir}"
    ALTPLATES_OUTPUT_TEMPLATE = "/shows/{show}/shots/{seq}/{shot}/user/gabriel-h/mm/nuke/outputs/AltPlates"

    # File naming patterns
    GEO_FILENAME_PATTERN = "{shot}_scene_*_v{version}.####.{ext}"
    PLATE_FILENAME_PATTERN = "{shot}_turnover-plate_{plate}_*_v{version}.####.{ext}"
    LD_FILENAME_PATTERN = "{shot}_mm_default_{plate}_LD_v{version}.nk"

    # Supported file extensions
    IMAGE_EXTENSIONS = ("exr", "dpx", "jpg", "jpeg", "png", "tif", "tiff")
    MOVIE_EXTENSIONS = ("mov", "mp4", "m4v", "avi", "mxf", "webm", "mkv")

    # Default settings
    DEFAULT_PADDING = 4
    DEFAULT_COLORSPACE_EXR = "linear"

    @staticmethod
    def get_renders_root(show: str, seq: str, shot: str, user: str) -> Path:
        """
        Get the renders root directory for a given shot.

        Args:
            show: Show name
            seq: Sequence name
            shot: Shot name
            user: User name

        Returns:
            Path to renders root directory

        Example:
            >>> PipelineConfig.get_renders_root("demo", "010", "0100", "artist")
            PosixPath('/shows/demo/shots/010/0100/user/artist/mm/maya/renders/mm-default')
        """
        return Path(PipelineConfig.RENDERS_ROOT_TEMPLATE.format(
            show=show, seq=seq, shot=shot, user=user
        ))

    @staticmethod
    def get_plate_root(show: str, seq: str, shot: str) -> Path:
        """
        Get the plate root directory for a given shot.

        Args:
            show: Show name
            seq: Sequence name
            shot: Shot name

        Returns:
            Path to plate root directory

        Example:
            >>> PipelineConfig.get_plate_root("demo", "010", "0100")
            PosixPath('/shows/demo/shots/010/0100/publish/turnover/plate/input_plate')
        """
        return Path(PipelineConfig.PLATE_ROOT_TEMPLATE.format(
            show=show, seq=seq, shot=shot
        ))

    @staticmethod
    def get_ld_root(show: str, seq: str, shot: str, user: str) -> Path:
        """
        Get the lens distortion root directory for a given shot.

        Args:
            show: Show name
            seq: Sequence name
            shot: Shot name
            user: User name

        Returns:
            Path to 3DE lens distortion exports directory

        Example:
            >>> PipelineConfig.get_ld_root("demo", "010", "0100", "artist")
            PosixPath('/shows/demo/shots/010/0100/user/artist/mm/3de/mm-default/exports/scene')
        """
        return Path(PipelineConfig.LD_ROOT_TEMPLATE.format(
            show=show, seq=seq, shot=shot, user=user
        ))

    @staticmethod
    def get_playblast_root(show: str, seq: str, shot: str, user: str) -> Path:
        """
        Get the playblast root directory for a given shot.

        Args:
            show: Show name
            seq: Sequence name
            shot: Shot name
            user: User name

        Returns:
            Path to playblast root directory

        Example:
            >>> PipelineConfig.get_playblast_root("demo", "010", "0100", "artist")
            PosixPath('/shows/demo/shots/010/0100/user/artist/mm/maya/playblast')
        """
        return Path(PipelineConfig.PLAYBLAST_ROOT_TEMPLATE.format(
            show=show, seq=seq, shot=shot, user=user
        ))

    @staticmethod
    def get_altplates_output(show: str, seq: str, shot: str) -> Path:
        """
        Get the AltPlates output directory for a given shot.

        This path is always under user/gabriel-h regardless of who runs the script,
        as AltPlates outputs are centralized to a specific user.

        Args:
            show: Show name
            seq: Sequence name
            shot: Shot name

        Returns:
            Path to AltPlates output directory

        Example:
            >>> PipelineConfig.get_altplates_output("jack_ryan", "DD_230", "DD_230_0360")
            PosixPath('/shows/jack_ryan/shots/DD_230/DD_230_0360/user/gabriel-h/mm/nuke/outputs/AltPlates')
        """
        return Path(PipelineConfig.ALTPLATES_OUTPUT_TEMPLATE.format(
            show=show, seq=seq, shot=shot
        ))

    @staticmethod
    def parse_show_shot_from_path(nk_path: Path) -> Dict[str, str]:
        """
        Parse show, sequence, shot, and user from a Nuke script path.

        Expected path structure:
            /shows/<show>/shots/<seq>/<shot>/user/<user>/...

        Args:
            nk_path: Path to Nuke script

        Returns:
            Dictionary with keys: 'show', 'seq', 'shot', 'user'

        Raises:
            ValueError: If path doesn't match expected structure

        Example:
            >>> path = Path("/shows/demo/shots/010/0100/user/artist/scene/comp.nk")
            >>> PipelineConfig.parse_show_shot_from_path(path)
            {'show': 'demo', 'seq': '010', 'shot': '0100', 'user': 'artist'}
        """
        parts = nk_path.parts

        try:
            show_idx = parts.index("shows")
            shot_idx = parts.index("shots")
            user_idx = parts.index("user")
        except ValueError as e:
            raise ValueError(
                "Couldn't parse show/shot/user from path.\n"
                f"Expected: /shows/<show>/shots/<seq>/<shot>/user/<user>/...\n"
                f"Got: {nk_path}"
            ) from e

        try:
            return {
                'show': parts[show_idx + 1],
                'seq': parts[shot_idx + 1],
                'shot': parts[shot_idx + 2],
                'user': parts[user_idx + 1],
            }
        except IndexError as e:
            raise ValueError(
                f"Path didn't have enough segments after /shows, /shots, or /user.\n"
                f"Got: {nk_path}"
            ) from e


# Convenience function for backward compatibility
def parse_show_shot_user(nk_path: Path) -> tuple[str, str, str, str]:
    """
    Parse show, seq, shot, and user from Nuke script path.

    Args:
        nk_path: Path to Nuke script

    Returns:
        Tuple of (show, seq, shot, user)

    Raises:
        ValueError: If path doesn't match expected structure
    """
    result = PipelineConfig.parse_show_shot_from_path(nk_path)
    return result['show'], result['seq'], result['shot'], result['user']

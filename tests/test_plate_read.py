"""
Tests for mm_plate_read module.

Tests the core functionality including:
- Plate ID normalization
- Version number extraction
- Path parsing
- Auto-connection behavior
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from conftest import MockNukeModule, create_image_sequence, create_version_dirs


class TestVersionNum:
    """Tests for _version_num function."""

    @pytest.mark.parametrize("version_str,expected", [
        # Standard versions
        ("v001", 1),
        ("v010", 10),
        ("v123", 123),
        # Uppercase versions (case-insensitive)
        ("V001", 1),
        ("V100", 100),
        # Invalid versions return -1
        ("version1", -1),
        ("001", -1),
        ("v", -1),
        ("", -1),
        ("v1a", -1),
    ])
    def test_version_num(self, mock_nuke: MockNukeModule, version_str: str, expected: int) -> None:
        """Test version number extraction from various formats."""
        import mm_plate_read

        assert mm_plate_read._version_num(version_str) == expected


class TestNormPlateToken:
    """Tests for _norm_plate_token function."""

    @pytest.mark.parametrize("input_token,expected", [
        # Standard format (already normalized)
        ("FG01", "FG01"),
        ("BG02", "BG02"),
        ("MG10", "MG10"),
        # Lowercase normalization
        ("fg01", "FG01"),
        ("bg02", "BG02"),
        # Single digit padding
        ("fg1", "FG01"),
        ("BG2", "BG02"),
        ("mg9", "MG09"),
        # Mixed case
        ("Fg1", "FG01"),
        ("bG02", "BG02"),
        # Invalid formats (return None)
        ("F01", None),      # Wrong letter count (1)
        ("FGH01", None),    # Wrong letter count (3)
        ("FG", None),       # No digits
        ("FG123", None),    # Too many digits
        ("invalid", None),  # No match
        ("123", None),      # Only digits
        ("", None),         # Empty
    ])
    def test_norm_plate_token(
        self, mock_nuke: MockNukeModule, input_token: str, expected: str | None
    ) -> None:
        """Test plate ID normalization from various formats."""
        import mm_plate_read

        assert mm_plate_read._norm_plate_token(input_token) == expected


class TestPathParsing:
    """Tests for path parsing functionality."""

    @pytest.mark.parametrize("target,expected", [
        ("shows", 0),
        ("shots", 2),
        ("user", 5),
    ])
    def test_find_index(
        self, mock_nuke: MockNukeModule, target: str, expected: int
    ) -> None:
        """Test _find_index helper function."""
        import mm_plate_read

        parts = ("shows", "MYSHOW", "shots", "SEQ", "SEQ_0010", "user", "artist")
        assert mm_plate_read._find_index(parts, target) == expected

    @pytest.mark.parametrize("target", ["user", "missing", "notfound"])
    def test_find_index_not_found(self, mock_nuke: MockNukeModule, target: str) -> None:
        """Test _find_index returns -1 for missing elements."""
        import mm_plate_read

        parts = ("shows", "MYSHOW", "shots")
        assert mm_plate_read._find_index(parts, target) == -1


class TestErrorConditions:
    """Tests for error handling and user-friendly error messages."""

    def test_unsaved_script_raises_error(self, mock_nuke: MockNukeModule) -> None:
        """Test that unsaved script raises RuntimeError with helpful message."""
        mock_nuke._set_script_path("")  # Unsaved script
        import mm_plate_read

        with pytest.raises(RuntimeError, match="(?i)save"):
            mm_plate_read.run()

    def test_invalid_path_structure_raises_error(self, mock_nuke: MockNukeModule) -> None:
        """Test that invalid path structure raises RuntimeError."""
        mock_nuke._set_script_path("/invalid/path/without/shows")
        import mm_plate_read

        with pytest.raises(RuntimeError):
            mm_plate_read.run()


# Note: Auto-connection tests removed.
# Read nodes are source nodes in Nuke and don't have inputs.
# The auto-connection functionality was removed from mm_plate_read.py
# as it was semantically incorrect.


class TestMockNukeIntegration:
    """Tests to verify the mock nuke module works correctly."""

    def test_mock_nuke_installed(self, mock_nuke: MockNukeModule) -> None:
        """Test that mock nuke is properly installed in sys.modules."""
        assert "nuke" in sys.modules
        import nuke

        assert nuke is mock_nuke

    def test_script_path_setting(self, mock_nuke: MockNukeModule) -> None:
        """Test setting and getting script path."""
        test_path = "/shows/TEST/shots/ABC/ABC_0010/user/artist/scene/comp.nk"
        mock_nuke._set_script_path(test_path)

        import nuke

        assert nuke.root().name() == test_path

    def test_selected_nodes(self, mock_nuke: MockNukeModule) -> None:
        """Test selected nodes functionality."""
        from conftest import MockNode

        node1 = MockNode("Read")
        node2 = MockNode("Write")

        mock_nuke._set_selected_nodes([node1, node2])

        import nuke

        selected = nuke.selectedNodes()
        assert len(selected) == 2
        assert node1 in selected
        assert node2 in selected

    def test_node_creation(self, mock_nuke: MockNukeModule) -> None:
        """Test node creation via nodes factory."""
        import nuke

        read_node = nuke.nodes.Read()
        assert read_node.Class() == "Read"

        write_node = nuke.nodes.Write()
        assert write_node.Class() == "Write"

    def test_knob_operations(self, mock_nuke: MockNukeModule) -> None:
        """Test knob value setting and getting."""
        import nuke

        node = nuke.nodes.Read()

        # Test fromUserText
        node["file"].fromUserText("/path/to/file.exr")
        assert node["file"].value() == "/path/to/file.exr"

        # Test setValue
        node["first"].setValue(1001)
        assert node["first"].value() == 1001

    def test_tprint_recording(self, mock_nuke: MockNukeModule) -> None:
        """Test that tprint calls are recorded."""
        import nuke

        nuke.tprint("Test message 1")
        nuke.tprint("Test message 2")

        assert len(mock_nuke._tprint_messages) == 2
        assert "Test message 1" in mock_nuke._tprint_messages
        assert "Test message 2" in mock_nuke._tprint_messages


@pytest.mark.integration
class TestIntegration:
    """Integration tests with file system operations."""

    def test_version_directory_sorting(self, tmp_path: Path) -> None:
        """Test that version directories sort correctly."""
        base = tmp_path / "versions"
        create_version_dirs(base, ["v001", "v003", "v002", "v010"])

        dirs = [d for d in base.iterdir() if d.is_dir()]
        dirs.sort(key=lambda d: int(d.name[1:]), reverse=True)

        names = [d.name for d in dirs]
        assert names == ["v010", "v003", "v002", "v001"]

    def test_image_sequence_creation(self, tmp_path: Path) -> None:
        """Test helper creates correct image sequences."""
        files = create_image_sequence(
            tmp_path,
            "shot_scene_v001",
            "exr",
            range(1001, 1006)
        )

        assert len(files) == 5
        assert all(f.exists() for f in files)
        assert files[0].name == "shot_scene_v001.1001.exr"
        assert files[-1].name == "shot_scene_v001.1005.exr"

"""
Tests for export_utils module.

Tests the shared utility functions used by export setup scripts.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from conftest import MockNukeModule, create_version_dirs


def _reload_export_utils() -> None:
    """Reload export_utils to pick up the mock nuke module."""
    if "export_utils" in sys.modules:
        importlib.reload(sys.modules["export_utils"])


class TestVersionNum:
    """Tests for version_num function."""

    @pytest.mark.parametrize("version_str,expected", [
        ("v001", 1),
        ("v010", 10),
        ("v123", 123),
        ("V001", 1),
        ("V100", 100),
        ("version1", -1),
        ("001", -1),
        ("v", -1),
        ("", -1),
        ("v1a", -1),
    ])
    def test_version_num(self, mock_nuke: MockNukeModule, version_str: str, expected: int) -> None:
        """Test version number extraction from various formats."""
        import export_utils

        assert export_utils.version_num(version_str) == expected


class TestFindIndex:
    """Tests for find_index function."""

    def test_find_existing_element(self, mock_nuke: MockNukeModule) -> None:
        """Test finding existing elements in tuple."""
        import export_utils

        parts = ("shows", "MYSHOW", "shots", "SEQ", "SEQ_0010", "user", "artist")
        assert export_utils.find_index(parts, "shows") == 0
        assert export_utils.find_index(parts, "shots") == 2
        assert export_utils.find_index(parts, "user") == 5

    def test_find_missing_element(self, mock_nuke: MockNukeModule) -> None:
        """Test finding missing element returns -1."""
        import export_utils

        parts = ("shows", "MYSHOW", "shots")
        assert export_utils.find_index(parts, "user") == -1
        assert export_utils.find_index(parts, "missing") == -1


class TestNormPlateToken:
    """Tests for norm_plate_token function."""

    @pytest.mark.parametrize("input_token,expected", [
        ("FG01", "FG01"),
        ("BG02", "BG02"),
        ("fg01", "FG01"),
        ("bg02", "BG02"),
        ("fg1", "FG01"),
        ("BG2", "BG02"),
        ("mg9", "MG09"),
        ("Fg1", "FG01"),
        ("F01", None),
        ("FGH01", None),
        ("FG", None),
        ("FG123", None),
        ("invalid", None),
        ("", None),
    ])
    def test_norm_plate_token(
        self, mock_nuke: MockNukeModule, input_token: str, expected: str | None
    ) -> None:
        """Test plate ID normalization from various formats."""
        import export_utils

        assert export_utils.norm_plate_token(input_token) == expected


class TestDetectPlateFromReads:
    """Tests for detect_plate_from_reads function."""

    def test_detect_from_read_path(self, mock_nuke: MockNukeModule) -> None:
        """Test plate detection from existing Read node file paths."""
        from conftest import MockNode
        _reload_export_utils()
        import export_utils

        # Create a Read node with a plate path
        read_node = MockNode("Read")
        read_node["file"].setValue("/shows/DEMO/shots/SEQ/SEQ_0010/plate/input_plate/FG01/v001/file.exr")
        mock_nuke._add_node(read_node)

        result = export_utils.detect_plate_from_reads()
        assert result == "FG01"

    def test_detect_from_filename(self, mock_nuke: MockNukeModule) -> None:
        """Test plate detection from filename pattern."""
        from conftest import MockNode
        _reload_export_utils()
        import export_utils

        # Create a Read node with plate in filename
        read_node = MockNode("Read")
        read_node["file"].setValue("/path/to/shot_plate_BG02_linear.exr")
        mock_nuke._add_node(read_node)

        result = export_utils.detect_plate_from_reads()
        assert result == "BG02"

    def test_no_read_nodes(self, mock_nuke: MockNukeModule) -> None:
        """Test returns None when no Read nodes exist."""
        _reload_export_utils()
        import export_utils

        result = export_utils.detect_plate_from_reads()
        assert result is None


class TestDetectPlateFromNkpath:
    """Tests for detect_plate_from_nkpath function."""

    def test_detect_from_path_segment(self, mock_nuke: MockNukeModule) -> None:
        """Test plate detection from path segments."""
        import export_utils

        parts = ("shows", "DEMO", "shots", "SEQ", "SEQ_0010", "user", "artist", "FG01", "scene")
        result = export_utils.detect_plate_from_nkpath(parts)
        assert result == "FG01"

    def test_no_plate_in_path(self, mock_nuke: MockNukeModule) -> None:
        """Test returns None when no plate ID in path."""
        import export_utils

        parts = ("shows", "DEMO", "shots", "SEQ", "SEQ_0010", "user", "artist", "scene")
        result = export_utils.detect_plate_from_nkpath(parts)
        assert result is None


class TestCollectPlateDirs:
    """Tests for collect_plate_dirs function."""

    def test_collect_from_directory(self, mock_nuke: MockNukeModule, tmp_path: Path) -> None:
        """Test collecting plate directories from scene root."""
        import export_utils

        # Create plate directories
        (tmp_path / "FG01").mkdir()
        (tmp_path / "BG02").mkdir()
        (tmp_path / "not_a_plate").mkdir()

        result = export_utils.collect_plate_dirs(tmp_path)
        plate_ids = [pid for _, pid in result]

        assert "FG01" in plate_ids
        assert "BG02" in plate_ids
        assert len(result) == 2  # not_a_plate excluded

    def test_empty_directory(self, mock_nuke: MockNukeModule, tmp_path: Path) -> None:
        """Test returns empty list for empty directory."""
        import export_utils

        result = export_utils.collect_plate_dirs(tmp_path)
        assert result == []


class TestPathHasDotDir:
    """Tests for path_has_dot_dir function."""

    def test_no_dot_dir(self, mock_nuke: MockNukeModule, tmp_path: Path) -> None:
        """Test returns False when no dot directories."""
        import export_utils

        test_file = tmp_path / "sub" / "file.nk"
        result = export_utils.path_has_dot_dir(test_file, tmp_path)
        assert result is False

    def test_with_dot_dir(self, mock_nuke: MockNukeModule, tmp_path: Path) -> None:
        """Test returns True when dot directory exists."""
        import export_utils

        test_file = tmp_path / "IMG_1234.JPG" / "file.nk"
        result = export_utils.path_has_dot_dir(test_file, tmp_path)
        assert result is True


class TestErrorHandling:
    """Tests for error handling functions."""

    def test_err_shows_message_and_raises(self, mock_nuke: MockNukeModule) -> None:
        """Test err() shows message and raises RuntimeError."""
        _reload_export_utils()
        import export_utils

        with pytest.raises(RuntimeError, match="Test error"):
            export_utils.err("Test error")

        assert "Test error" in mock_nuke._message_calls


class TestInferContextFromNk:
    """Tests for infer_context_from_nk function."""

    def test_valid_path(self, mock_nuke: MockNukeModule) -> None:
        """Test context inference from valid path."""
        mock_nuke._set_script_path("/shows/DEMO/shots/SEQ/SEQ_0010/user/artist/scene/comp.nk")
        _reload_export_utils()
        import export_utils

        show, seq, shot, user = export_utils.infer_context_from_nk()

        assert show == "DEMO"
        assert seq == "SEQ"
        assert shot == "SEQ_0010"
        assert user == "artist"

    def test_unsaved_script_raises(self, mock_nuke: MockNukeModule) -> None:
        """Test raises RuntimeError for unsaved script."""
        mock_nuke._set_script_path("")
        _reload_export_utils()
        import export_utils

        with pytest.raises(RuntimeError, match="(?i)save"):
            export_utils.infer_context_from_nk()

    def test_invalid_path_raises(self, mock_nuke: MockNukeModule) -> None:
        """Test raises RuntimeError for invalid path structure."""
        mock_nuke._set_script_path("/invalid/path/structure")
        _reload_export_utils()
        import export_utils

        with pytest.raises(RuntimeError):
            export_utils.infer_context_from_nk()


class TestScanPlayblast:
    """Tests for scan_playblast function."""

    def test_scan_image_sequence(self, mock_nuke: MockNukeModule, tmp_path: Path) -> None:
        """Test scanning directory for image sequence."""
        import export_utils

        # Create test sequence
        vdir = tmp_path / "v001"
        vdir.mkdir()
        for i in range(1001, 1006):
            (vdir / f"Wireframe.{i:04d}.png").touch()

        result = export_utils.scan_playblast(vdir, "Wireframe")

        assert result is not None
        assert result["type"] == "sequence"
        assert result["ext"] == "png"
        assert result["fmin"] == 1001
        assert result["fmax"] == 1005

    def test_scan_movie_file(self, mock_nuke: MockNukeModule, tmp_path: Path) -> None:
        """Test scanning directory for movie file."""
        import export_utils

        vdir = tmp_path / "v001"
        vdir.mkdir()
        (vdir / "Wireframe.mov").touch()

        result = export_utils.scan_playblast(vdir, "Wireframe")

        assert result is not None
        assert result["type"] == "movie"
        assert "Wireframe.mov" in result["path"]

    def test_scan_empty_directory(self, mock_nuke: MockNukeModule, tmp_path: Path) -> None:
        """Test scanning empty directory returns None."""
        import export_utils

        vdir = tmp_path / "v001"
        vdir.mkdir()

        result = export_utils.scan_playblast(vdir, "Wireframe")
        assert result is None


@pytest.mark.integration
class TestIntegration:
    """Integration tests with file system operations."""

    def test_version_directory_sorting(self, tmp_path: Path) -> None:
        """Test that version directories sort correctly."""
        base = tmp_path / "versions"
        create_version_dirs(base, ["v001", "v003", "v002", "v010"])

        import export_utils

        dirs = [d for d in base.iterdir() if d.is_dir()]
        dirs.sort(key=lambda d: export_utils.version_num(d.name), reverse=True)

        names = [d.name for d in dirs]
        assert names == ["v010", "v003", "v002", "v001"]

"""
Tests for pipeline_config module.

Tests the centralized configuration for all VFX pipeline paths.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pipeline_config import PipelineConfig, parse_show_shot_user


class TestPipelineConfigPaths:
    """Tests for PipelineConfig path generation methods."""

    def test_get_renders_root(self) -> None:
        """Test renders root path generation."""
        result = PipelineConfig.get_renders_root("demo", "010", "0100", "artist")
        expected = Path("/shows/demo/shots/010/0100/user/artist/mm/maya/renders/mm-default")
        assert result == expected

    def test_get_plate_root(self) -> None:
        """Test plate root path generation."""
        result = PipelineConfig.get_plate_root("demo", "010", "0100")
        expected = Path("/shows/demo/shots/010/0100/publish/turnover/plate/input_plate")
        assert result == expected

    def test_get_ld_root(self) -> None:
        """Test lens distortion root path generation."""
        result = PipelineConfig.get_ld_root("demo", "010", "0100", "artist")
        expected = Path("/shows/demo/shots/010/0100/user/artist/mm/3de/mm-default/exports/scene")
        assert result == expected

    def test_get_playblast_root(self) -> None:
        """Test playblast root path generation."""
        result = PipelineConfig.get_playblast_root("demo", "010", "0100", "artist")
        expected = Path("/shows/demo/shots/010/0100/user/artist/mm/maya/playblast")
        assert result == expected

    def test_get_altplates_output(self) -> None:
        """Test altplates output path generation."""
        result = PipelineConfig.get_altplates_output("demo", "010", "0100")
        # Note: hardcoded to gabriel-h user
        expected = Path("/shows/demo/shots/010/0100/user/gabriel-h/mm/nuke/outputs/AltPlates")
        assert result == expected

    @pytest.mark.parametrize("show,seq,shot,user", [
        ("SHOW1", "ABC", "ABC_0010", "john"),
        ("demo", "010", "0100", "artist"),
        ("MYSHOW", "XYZ", "XYZ_0999", "jane-d"),
    ])
    def test_path_generation_various_inputs(
        self, show: str, seq: str, shot: str, user: str
    ) -> None:
        """Test path generation with various input combinations."""
        renders_root = PipelineConfig.get_renders_root(show, seq, shot, user)
        assert show in str(renders_root)
        assert seq in str(renders_root)
        assert shot in str(renders_root)
        assert user in str(renders_root)


class TestParseShowShotFromPath:
    """Tests for parse_show_shot_from_path method."""

    def test_valid_path_parsing(self) -> None:
        """Test parsing a valid Nuke script path."""
        path = Path("/shows/demo/shots/010/0100/user/artist/scene/comp.nk")
        result = PipelineConfig.parse_show_shot_from_path(path)

        assert result["show"] == "demo"
        assert result["seq"] == "010"
        assert result["shot"] == "0100"
        assert result["user"] == "artist"

    def test_path_with_mm_structure(self) -> None:
        """Test parsing path with mm directory structure."""
        path = Path("/shows/MYSHOW/shots/ABC/ABC_0010/user/john/mm/nuke/scene/comp.nk")
        result = PipelineConfig.parse_show_shot_from_path(path)

        assert result["show"] == "MYSHOW"
        assert result["seq"] == "ABC"
        assert result["shot"] == "ABC_0010"
        assert result["user"] == "john"

    @pytest.mark.parametrize("invalid_path", [
        "/invalid/path/without/shows",
        "/shows/demo/invalid",
        "/shows/demo/shots",  # Missing shot
        "/completely/wrong/structure",
    ])
    def test_invalid_path_raises_error(self, invalid_path: str) -> None:
        """Test that invalid paths raise ValueError."""
        with pytest.raises(ValueError):
            PipelineConfig.parse_show_shot_from_path(Path(invalid_path))


class TestParseShowShotUser:
    """Tests for standalone parse_show_shot_user function."""

    def test_valid_path(self) -> None:
        """Test parsing a valid path."""
        path = Path("/shows/demo/shots/010/0100/user/artist/mm/nuke/scene/comp.nk")
        show, seq, shot, user = parse_show_shot_user(path)

        assert show == "demo"
        assert seq == "010"
        assert shot == "0100"
        assert user == "artist"

    def test_returns_tuple(self) -> None:
        """Test that function returns a tuple of 4 elements."""
        path = Path("/shows/SHOW/shots/SEQ/SHOT/user/USER/file.nk")
        result = parse_show_shot_user(path)

        assert isinstance(result, tuple)
        assert len(result) == 4


class TestPipelineConfigConstants:
    """Tests for PipelineConfig constants."""

    def test_image_extensions(self) -> None:
        """Test that common image extensions are supported."""
        assert "exr" in PipelineConfig.IMAGE_EXTENSIONS
        assert "png" in PipelineConfig.IMAGE_EXTENSIONS
        assert "jpg" in PipelineConfig.IMAGE_EXTENSIONS

    def test_movie_extensions(self) -> None:
        """Test that common movie extensions are supported."""
        assert "mov" in PipelineConfig.MOVIE_EXTENSIONS
        assert "mp4" in PipelineConfig.MOVIE_EXTENSIONS

    def test_default_colorspace(self) -> None:
        """Test default colorspace for EXR files."""
        assert PipelineConfig.DEFAULT_COLORSPACE_EXR == "linear"

    def test_default_padding(self) -> None:
        """Test default frame padding."""
        assert PipelineConfig.DEFAULT_PADDING == 4

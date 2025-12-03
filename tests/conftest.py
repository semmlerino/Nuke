"""
Pytest configuration and fixtures for testing Nuke Python scripts.

This module provides a mock nuke module that simulates Nuke's Python API,
allowing tests to run outside of Nuke's environment.

Quick Start
-----------

1. Use `mock_nuke` fixture to get a fresh mock::

    def test_my_script(mock_nuke):
        mock_nuke._set_script_path("/shows/DEMO/shots/SEQ/SEQ_0010/user/artist/scene/comp.nk")
        import my_script
        my_script.run()

2. Create test directories with `tmp_shot_structure`::

    def test_with_files(mock_nuke, tmp_shot_structure):
        # tmp_shot_structure has full directory tree under tmp_path

3. Verify mock calls:
   - `mock_nuke._tprint_messages` - list of logged messages
   - `mock_nuke._message_calls` - list of error dialogs shown
   - `mock_nuke._pasted_files` - list of files passed to nodePaste()
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

# =============================================================================
# Mock Nuke Module
# =============================================================================


class MockKnob:
    """Mock Nuke knob for storing node values."""

    def __init__(self, name: str, value: Any = None) -> None:
        self._name = name
        self._value = value
        self._from_user_text_calls: list[str] = []

    def value(self) -> Any:
        return self._value

    def setValue(self, value: Any) -> None:
        self._value = value

    def fromUserText(self, text: str) -> None:
        """Record calls for testing file path loading."""
        self._from_user_text_calls.append(text)
        self._value = text

    def getValue(self) -> Any:
        return self._value

    def execute(self) -> None:
        """Execute action knob (no-op in mock)."""
        pass


class MockNode:
    """Mock Nuke node with knob support."""

    _node_counter = 0

    def __init__(self, node_class: str = "Node") -> None:
        MockNode._node_counter += 1
        self._class = node_class
        self._name = f"{node_class}{MockNode._node_counter}"
        self._knobs: dict[str, MockKnob] = {
            # File knobs
            "file": MockKnob("file"),
            "first": MockKnob("first", 1001),
            "last": MockKnob("last", 1100),
            "origfirst": MockKnob("origfirst", 1001),
            "origlast": MockKnob("origlast", 1100),
            # Color/format knobs
            "colorspace": MockKnob("colorspace"),
            "raw": MockKnob("raw", False),
            "file_type": MockKnob("file_type"),
            "format": MockKnob("format"),
            "ocioColorspace": MockKnob("ocioColorspace"),
            "display": MockKnob("display"),
            "view": MockKnob("view"),
            # Write knobs
            "create_directories": MockKnob("create_directories", False),
            "channels": MockKnob("channels"),
            "first_part": MockKnob("first_part"),
            # Transform knobs
            "scale": MockKnob("scale", 1.0),
            "center": MockKnob("center", [0, 0]),
            # Action knobs
            "reload": MockKnob("reload"),
            # WriteTank knobs
            "profile_name": MockKnob("profile_name"),
            "custom_knob_camera_element": MockKnob("custom_knob_camera_element"),
            # General
            "name": MockKnob("name"),
        }
        self._inputs: list[MockNode | None] = [None] * 10
        self._selected = False
        self._xpos = 0
        self._ypos = 0

    def __getitem__(self, key: str) -> MockKnob:
        if key not in self._knobs:
            self._knobs[key] = MockKnob(key)
        return self._knobs[key]

    def __setitem__(self, key: str, value: Any) -> None:
        if key not in self._knobs:
            self._knobs[key] = MockKnob(key)
        self._knobs[key].setValue(value)

    def name(self) -> str:
        return self._name

    def setName(self, name: str, unique: bool = True) -> None:
        """Set node name. unique parameter is ignored in mock."""
        self._name = name

    def Class(self) -> str:
        return self._class

    def setInput(self, index: int, node: MockNode | None) -> None:
        """
        Set node input connection.

        Note: In real Nuke, Read nodes are source nodes and don't have inputs.
        Calling setInput on a Read node would be silently ignored or raise an error.
        """
        if index < len(self._inputs):
            self._inputs[index] = node

    def input(self, index: int) -> MockNode | None:
        return self._inputs[index] if index < len(self._inputs) else None

    def setSelected(self, selected: bool) -> None:
        self._selected = selected

    def isSelected(self) -> bool:
        return self._selected

    def xpos(self) -> int:
        return self._xpos

    def ypos(self) -> int:
        return self._ypos

    def setXpos(self, x: int) -> None:
        self._xpos = x

    def setYpos(self, y: int) -> None:
        self._ypos = y

    def setXYpos(self, x: int, y: int) -> None:
        """Set both X and Y position at once."""
        self._xpos = x
        self._ypos = y

    def knob(self, name: str) -> MockKnob | None:
        return self._knobs.get(name)


class MockRoot(MockNode):
    """Mock Nuke root node with script path."""

    def __init__(self, script_path: str = "") -> None:
        super().__init__("Root")
        self._script_path = script_path
        self._width = 1920
        self._height = 1080

    def name(self) -> str:
        return self._script_path

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height


class MockNodesFactory:
    """Factory for creating mock Nuke nodes."""

    def Read(self, **kwargs: Any) -> MockNode:
        node = MockNode("Read")
        for key, value in kwargs.items():
            node[key].setValue(value)
        return node

    def Write(self, **kwargs: Any) -> MockNode:
        node = MockNode("Write")
        for key, value in kwargs.items():
            node[key].setValue(value)
        return node

    def Merge2(self, **kwargs: Any) -> MockNode:
        node = MockNode("Merge2")
        for key, value in kwargs.items():
            node[key].setValue(value)
        return node

    def Transform(self, **kwargs: Any) -> MockNode:
        node = MockNode("Transform")
        for key, value in kwargs.items():
            node[key].setValue(value)
        return node

    def Group(self, **kwargs: Any) -> MockNode:
        node = MockNode("Group")
        for key, value in kwargs.items():
            node[key].setValue(value)
        return node

    def WriteTank(self, **kwargs: Any) -> MockNode:
        node = MockNode("WriteTank")
        for key, value in kwargs.items():
            node[key].setValue(value)
        return node

    def LiveGroup(self, **kwargs: Any) -> MockNode:
        node = MockNode("LiveGroup")
        for key, value in kwargs.items():
            node[key].setValue(value)
        return node

    def Crop(self, **kwargs: Any) -> MockNode:
        node = MockNode("Crop")
        for key, value in kwargs.items():
            node[key].setValue(value)
        return node


class MockPanel:
    """Mock Nuke panel for user dialogs."""

    def __init__(self, title: str) -> None:
        self._title = title
        self._knobs: dict[str, Any] = {}
        self._show_result = True  # Default to user accepting

    def addEnumerationPulldown(self, name: str, options: str) -> None:
        """Add enumeration pulldown with space-separated options."""
        option_list = options.split()
        self._knobs[name] = option_list[0] if option_list else ""

    def addSingleLineInput(self, name: str, default: str = "") -> None:
        """Add single line text input."""
        self._knobs[name] = default

    def show(self) -> bool:
        """Show panel and return True if user accepted."""
        return self._show_result

    def value(self, name: str) -> Any:
        """Get value of knob by name."""
        return self._knobs.get(name, "")

    def _set_show_result(self, result: bool) -> None:
        """Test helper to set whether show() returns True or False."""
        self._show_result = result

    def _set_value(self, name: str, value: Any) -> None:
        """Test helper to set knob value."""
        self._knobs[name] = value


class MockNukeModule:
    """Mock implementation of the nuke module."""

    def __init__(self) -> None:
        self._root = MockRoot()
        self._selected_nodes: list[MockNode] = []
        self._all_nodes: list[MockNode] = []
        self.nodes = MockNodesFactory()
        self._tprint_messages: list[str] = []
        self._message_calls: list[str] = []
        self._pasted_files: list[str] = []
        self._formats: list[str] = []
        self._panels: list[MockPanel] = []

        # Hotkey tracking (used by menu.py)
        self._bb_hotkeys_bound: set[tuple[str, str]] = set()

        # Type aliases for type hints in Nuke scripts
        self.Node = MockNode  # type: ignore[assignment]

    def Panel(self, title: str) -> MockPanel:
        """Create and return a mock panel."""
        panel = MockPanel(title)
        self._panels.append(panel)
        return panel

    def root(self) -> MockRoot:
        return self._root

    def selectedNodes(self) -> list[MockNode]:
        return self._selected_nodes.copy()

    def allNodes(self, node_class: str | None = None) -> list[MockNode]:
        if node_class:
            return [n for n in self._all_nodes if n.Class() == node_class]
        return self._all_nodes.copy()

    def tprint(self, message: str) -> None:
        """Record tprint calls for testing."""
        self._tprint_messages.append(message)

    def message(self, message: str) -> None:
        """Record message dialog calls for testing."""
        self._message_calls.append(message)

    def nodePaste(self, filepath: str) -> None:
        """
        Record nodePaste calls and update selectedNodes.

        After pasting, scripts call selectedNodes() to get the pasted nodes.
        This mock creates a Group node and sets it as selected.
        """
        self._pasted_files.append(filepath)
        # Create mock pasted node and set as selected
        pasted_node = MockNode("Group")
        pasted_node.setName("LD_3DE_FG01_v001", unique=False)
        self._selected_nodes = [pasted_node]
        self._all_nodes.append(pasted_node)

    def formats(self) -> list[str]:
        """Return list of available formats."""
        return self._formats.copy()

    def addFormat(self, format_string: str) -> None:
        """Add a custom format."""
        self._formats.append(format_string)

    def menu(self, name: str) -> Mock:
        """Return a mock menu."""
        menu_mock = Mock()
        menu_mock.addCommand = Mock()
        return menu_mock

    def createNode(self, node_class: str, **kwargs: Any) -> MockNode:
        """Create a node (interactive mode - usually avoided in scripts)."""
        node = MockNode(node_class)
        for key, value in kwargs.items():
            node[key].setValue(value)
        self._all_nodes.append(node)
        return node

    # Test helpers
    def _set_script_path(self, path: str) -> None:
        """Set the current script path for testing."""
        self._root._script_path = path

    def _set_selected_nodes(self, nodes: list[MockNode]) -> None:
        """Set the currently selected nodes for testing."""
        self._selected_nodes = nodes

    def _add_node(self, node: MockNode) -> None:
        """Add a node to the scene for testing."""
        self._all_nodes.append(node)

    def _clear(self) -> None:
        """Clear all state for fresh tests."""
        self._selected_nodes = []
        self._all_nodes = []
        self._tprint_messages = []
        self._message_calls = []
        self._pasted_files = []
        self._panels = []
        MockNode._node_counter = 0


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture
def mock_nuke() -> Generator[MockNukeModule, None, None]:
    """
    Provide a fresh mock nuke module for each test.

    The mock is automatically installed as 'nuke' in sys.modules.
    Node counter is reset to ensure deterministic node names.
    """
    MockNode._node_counter = 0  # Reset for deterministic names
    mock = MockNukeModule()
    sys.modules["nuke"] = mock  # type: ignore[assignment]
    yield mock
    # Cleanup
    if "nuke" in sys.modules:
        del sys.modules["nuke"]


@pytest.fixture
def sample_script_path() -> str:
    """Provide a sample Nuke script path for testing."""
    return "/shows/MYSHOW/shots/ABC/ABC_0010/user/artist/scene/comp.nk"


@pytest.fixture
def mock_nuke_with_script(mock_nuke: MockNukeModule, sample_script_path: str) -> MockNukeModule:
    """Provide a mock nuke module with script path set."""
    mock_nuke._set_script_path(sample_script_path)
    return mock_nuke


@pytest.fixture
def tmp_shot_structure(tmp_path: Path) -> Path:
    """
    Create a temporary directory structure mimicking a VFX shot.

    Structure:
        /shows/TESTSHOW/shots/SEQ/SEQ_0010/
            user/artist/
                mm/maya/scenes/
                mm/nuke/scene/comp.nk
                mm/3de/
                mm/playblasts/
            turnovers/plates/
    """
    show = tmp_path / "shows" / "TESTSHOW"
    seq = "SEQ"
    shot = "SEQ_0010"
    user = "artist"

    shot_path = show / "shots" / seq / shot
    user_path = shot_path / "user" / user

    # Create directories
    (user_path / "mm" / "maya" / "scenes").mkdir(parents=True)
    (user_path / "mm" / "nuke" / "scene").mkdir(parents=True)
    (user_path / "mm" / "3de").mkdir(parents=True)
    (user_path / "mm" / "playblasts" / "Wireframe").mkdir(parents=True)
    (user_path / "mm" / "playblasts" / "Cones").mkdir(parents=True)
    (shot_path / "turnovers" / "plates" / "FG01" / "v001").mkdir(parents=True)

    # Create a comp.nk file
    comp_file = user_path / "mm" / "nuke" / "scene" / "comp.nk"
    comp_file.write_text("# Nuke script\n")

    return tmp_path


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


# =============================================================================
# Test Utilities
# =============================================================================


def create_version_dirs(base_path: Path, versions: list[str]) -> None:
    """
    Helper to create version directories with test files.

    Args:
        base_path: Parent directory for versions
        versions: List of version names (e.g., ["v001", "v002"])
    """
    for version in versions:
        (base_path / version).mkdir(parents=True, exist_ok=True)


def create_image_sequence(
    directory: Path,
    prefix: str,
    extension: str,
    frames: range,
    padding: int = 4
) -> list[Path]:
    """
    Create dummy image sequence files for testing.

    Args:
        directory: Directory to create files in
        prefix: Filename prefix (e.g., "shot_scene_geo_v001")
        extension: File extension (e.g., "exr")
        frames: Range of frame numbers
        padding: Frame number padding

    Returns:
        List of created file paths
    """
    files = []
    for frame in frames:
        filename = f"{prefix}.{str(frame).zfill(padding)}.{extension}"
        filepath = directory / filename
        filepath.touch()
        files.append(filepath)
    return files


def create_ld_file(
    directory: Path,
    shot: str,
    plate: str,
    version: int
) -> Path:
    """
    Create a dummy LD .nk file for testing.

    Args:
        directory: Directory to create file in
        shot: Shot name (e.g., "SEQ_0010")
        plate: Plate ID (e.g., "FG01")
        version: Version number

    Returns:
        Path to created file
    """
    filename = f"{shot}_mm_default_{plate}_LD_v{version:03d}.nk"
    filepath = directory / filename
    filepath.write_text("# Mock LD file\n")
    return filepath


def create_playblast_sequence(
    directory: Path,
    shot: str,
    category: str,
    version: int,
    frames: range,
    extension: str = "png"
) -> list[Path]:
    """
    Create a playblast sequence for testing.

    Args:
        directory: Directory to create files in
        shot: Shot name (e.g., "SEQ_0010")
        category: Playblast category (e.g., "Wireframe", "Cones")
        version: Version number
        frames: Range of frame numbers
        extension: File extension (default: "png")

    Returns:
        List of created file paths
    """
    prefix = f"{shot}_{category}_v{version:03d}"
    return create_image_sequence(directory, prefix, extension, frames)

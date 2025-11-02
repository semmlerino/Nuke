# Nuke Python Scripting Best Practices

**Document Version:** 1.0
**Last Updated:** 2025-11-02
**Sources:** Foundry Official Documentation, Codebase Analysis

---

## Table of Contents

1. [File Organization](#file-organization)
2. [Node Creation Patterns](#node-creation-patterns)
3. [Knob Manipulation](#knob-manipulation)
4. [Error Handling](#error-handling)
5. [Threading & Long Operations](#threading--long-operations)
6. [Python Code Quality](#python-code-quality)
7. [Codebase Analysis Learnings](#codebase-analysis-learnings)
8. [Quick Reference](#quick-reference)

---

## File Organization

### init.py vs menu.py

**Critical Rule:** Understand the difference between these two files.

#### init.py
- **Purpose:** Persistent configuration, command-line compatibility
- **Use for:**
  - Knob defaults (`nuke.knobDefault()`)
  - Python path modifications
  - Global settings that must work in both GUI and command-line modes
  - Module imports needed at startup

**Example:**
```python
# ~/.nuke/init.py
import nuke

# Set defaults for all Blur nodes
nuke.knobDefault("Blur.size", "10")

# Add custom Python path
import sys
sys.path.append("/path/to/custom/modules")
```

#### menu.py
- **Purpose:** UI-specific features
- **Use for:**
  - Menu items
  - Keyboard shortcuts
  - Toolbars
  - Panels and dialogs
  - Anything that requires the GUI

**Example:**
```python
# ~/.nuke/menu.py
import nuke

toolbar = nuke.menu("Nodes")
toolbar.addCommand("Custom/MyTool", "mymodule.run()", "ctrl+shift+m")
```

**Why This Matters:**
> "It is important that you add statements in your init.py file rather than menu.py to ensure they are set for command-line start-up as well as the graphical user interface (GUI)."
> — Foundry Official Documentation

---

## Node Creation Patterns

### Two Methods: Choose Wisely

#### nuke.createNode()
- **Interactive/GUI mode**
- Opens control panel
- Auto-connects to selected nodes
- Triggers callbacks

**Use when:**
- Creating nodes interactively through scripts
- User expects UI feedback
- Need automatic node connections

```python
# Creates a Blur node, shows panel, connects to selected
blur = nuke.createNode("Blur")
```

**Suppress panel:**
```python
blur = nuke.createNode("Blur", inpanel=False)
```

#### nuke.nodes.NodeName()
- **Batch/automation mode**
- No UI side effects
- No automatic connections
- Faster execution

**Use when:**
- Batch processing
- Background operations
- Building node graphs programmatically
- Performance matters

```python
# Creates a Read node without UI interaction
read = nuke.nodes.Read()
read["file"].setValue("/path/to/file.exr")
```

### Setting Values at Creation

**Preferred:** Set values during instantiation
```python
# Good: Set values at creation
blur = nuke.nodes.Blur(size=10, name="MyBlur")
```

**Alternative:** Set after creation
```python
# Also valid, but less efficient
blur = nuke.nodes.Blur()
blur["size"].setValue(10)
blur["name"].setValue("MyBlur")
```

### Setting Knob Defaults

Use `nuke.knobDefault()` for class-wide defaults:

```python
# Format: "ClassName.knobname"
nuke.knobDefault("Blur.size", "10")
nuke.knobDefault("Write.file_type", "exr")
```

**Important:** Class names must be capitalized!

---

## Knob Manipulation

### Reading Values

```python
node = nuke.toNode("Read1")

# Get value
path = node["file"].value()

# Get as text (with expressions evaluated)
text = node["file"].getValue()
```

### Setting Values

```python
read = nuke.nodes.Read()

# Simple value
read["first"].setValue(1001)

# File path - use fromUserText() for proper parsing
read["file"].fromUserText("/path/to/sequence.####.exr")

# Or set directly
read["file"].setValue("/path/to/sequence.####.exr")
```

### Frame Ranges

```python
# Single range
range1 = nuke.FrameRange("1-100")

# Multiple ranges
ranges = nuke.FrameRanges("1-50,75-100,200-250")

# Every other frame
every_other = nuke.FrameRange("1-100x2")
```

**Note:** Invalid ranges throw exceptions - use try/except for user input!

### Animation Copying

```python
# Copy animation curves between nodes
source_node["size"].copyAnimations(dest_node["size"].animations())
```

### Adding Custom Knobs

```python
node = nuke.nodes.NoOp()

# Create knob
text_knob = nuke.String_Knob("my_text", "My Label")

# Add to node
node.addKnob(text_knob)
```

---

## Error Handling

### User-Friendly Error Messages

**Pattern: Show message AND raise exception**

```python
def _err(msg: str) -> None:
    nuke.message(msg)  # Show to user
    raise RuntimeError(msg)  # Stop execution
```

**Usage:**
```python
if not Path(nk_path).exists():
    _err("Please save the Nuke script first.")
```

### Graceful Knob Setting

Some knobs may not exist in all Nuke versions:

```python
# Robust knob setting
try:
    read_node["raw"].setValue(True)
except Exception:
    pass  # Knob doesn't exist, continue

# Or log the warning
try:
    read_node["raw"].setValue(True)
except Exception as e:
    nuke.tprint(f"Warning: Could not set 'raw' knob: {e}")
```

### Specific Exception Handling

**Prefer specific exceptions when possible:**

```python
# Too broad
try:
    value = int(user_input)
except Exception:
    pass

# Better
try:
    value = int(user_input)
except ValueError:
    nuke.message("Please enter a valid number")
    return
```

---

## Threading & Long Operations

### Critical Rule for Progress Dialogs

**NEVER run lengthy operations in the main thread!**

```python
import threading
import nuke

def long_operation():
    # Your lengthy code here
    for i in range(100):
        # Do work...
        pass

    # Update UI from worker thread
    nuke.executeInMainThread(
        nuke.message,
        args=("Operation complete!",)
    )

# Run in background
thread = threading.Thread(target=long_operation)
thread.start()
```

**Why:** Nuke's main thread handles UI updates. Blocking it freezes the interface.

---

## Python Code Quality

### Type Hints (Python 3.11+)

```python
from pathlib import Path
from typing import Optional

def scan_sequence(
    dir_path: Path,
    shot: str,
    version: str
) -> tuple[str, str, int, int, int, list[Path]] | None:
    """
    Scan directory for image sequences.

    Args:
        dir_path: Directory to scan
        shot: Shot name to match
        version: Version number (e.g., "001")

    Returns:
        Tuple of (prefix, ext, min_frame, max_frame, padding, files)
        or None if no sequence found
    """
    # Implementation...
    pass
```

### Docstrings

**Module docstring:**
```python
"""
mm_geo_read.py

Create Read nodes for latest geometry renders.
Searches under .../v###/geo*/[WxH]/ for sequences matching:
    <shot>_scene_<anything>_v###.####.exr
"""
```

**Function docstring:**
```python
def detect_plate_id(nk_path: Path, plate_root: Path) -> str | None:
    """
    Extract plate ID from Nuke script path or filename.

    Tries to match patterns like FG01, BG01, MG02 from:
    1. Filename tokens (e.g., "shot_FG01_v001.nk")
    2. Directory segments (e.g., ".../scene/FG01/...")

    Args:
        nk_path: Path to current Nuke script
        plate_root: Root directory containing plate folders

    Returns:
        Normalized plate ID (e.g., "FG01") or None if not found

    Example:
        >>> detect_plate_id(Path("shot_FG01_v001.nk"), Path("/plates"))
        'FG01'
    """
    pass
```

### Module-Level Constants

```python
# At top of file
PLATE_REGEX = re.compile(r'\b([A-Z]{2}\d{2})\b', re.IGNORECASE)
VERSION_REGEX = re.compile(r'v(\d+)$', re.IGNORECASE)

# Configuration
DEFAULT_PADDING = 4
SUPPORTED_EXTENSIONS = ("exr", "dpx", "jpg", "png")
```

### Pathlib Over os.path

**Prefer:**
```python
from pathlib import Path

renders_root = Path("/shows") / show / "shots" / seq / shot
if renders_root.exists():
    for file in renders_root.glob("*.exr"):
        print(file.name)
```

**Over:**
```python
import os

renders_root = os.path.join("/shows", show, "shots", seq, shot)
if os.path.exists(renders_root):
    for file in os.listdir(renders_root):
        if file.endswith(".exr"):
            print(file)
```

---

## Codebase Analysis Learnings

### What This Codebase Does Well

#### 1. Hotkey Deduplication Pattern ⭐

Prevents multiple hotkey registrations across sessions:

```python
# Excellent defensive programming
if not hasattr(nuke, "_bb_hotkeys_bound"):
    nuke._bb_hotkeys_bound = set()

def add_hidden_hotkey_once(label: str, command: str, shortcut: str):
    key = (label, shortcut)
    if key in nuke._bb_hotkeys_bound:
        return
    nuke.menu("Nuke").addCommand(
        f"@BlueBolt/{label}",
        command,
        shortcut,
        shortcutContext=2  # DAG context
    )
    nuke._bb_hotkeys_bound.add(key)
```

**Lesson:** Use module-level state on `nuke` object for persistence.

#### 2. Module Hot-Reloading for Development ⭐

```python
cmd_plate = (
    "import importlib, mm_plate_read; "
    "importlib.reload(mm_plate_read); "
    "mm_plate_read.run()"
)
```

**Lesson:** `importlib.reload()` enables live code updates without restarting Nuke.

#### 3. Stable Entry Points

Every script exports a consistent `run()` function:

```python
def create_latest_plate_read():
    # Complex implementation...
    pass

# Stable entry point for menus/hotkeys
def run():
    return create_latest_plate_read()
```

**Lesson:** Separate public API from implementation. Makes refactoring easier.

#### 4. File Sequence Detection Pattern

Robust handling of hash patterns with Nuke:

```python
# Load concrete frame first, then hash pattern
first_frame_path = f"{prefix}.{str(fmin).zfill(pad)}.{ext}"
hash_pattern = f"{prefix}.{'#' * pad}.{ext}"

read_node["file"].fromUserText(first_frame_path)  # Load metadata
read_node["file"].fromUserText(hash_pattern)      # Switch to sequence
```

**Lesson:** Loading a real frame first helps Nuke detect sequence metadata correctly.

#### 5. Resolution Auto-Detection

Smart format detection from folder names:

```python
def maybe_set_format_from_res(read_node, seq_dir: Path):
    # Check for "4096x2268" in folder name
    match = re.match(r"^(\d+)x(\d+)$", seq_dir.name)
    if match:
        w, h = int(match.group(1)), int(match.group(2))
        fmt_name = f"{w}x{h}_from_plate"

        # Create format if doesn't exist
        if not any(f.name() == fmt_name for f in nuke.formats()):
            nuke.addFormat(f"{w} {h} 0 0 {w} {h} 1 {fmt_name}")

        read_node["format"].setValue(fmt_name)
```

**Lesson:** Auto-create custom formats based on discovered metadata.

#### 6. Colorspace Handling

Appropriate defaults by file type:

```python
if ext.lower() == "exr":
    try:
        read_node["file_type"].setValue("exr")
        read_node["colorspace"].setValue("linear")
        read_node["raw"].setValue(True)
    except Exception:
        pass  # Knob may not exist in all versions
```

**Lesson:** Set sensible defaults based on file extension, but handle missing knobs gracefully.

### Areas for Improvement

#### 1. Configuration Management

**Current:** Hardcoded paths
```python
renders_root = Path("/").joinpath(
    "shows", show, "shots", seq, shot,
    "user", user, "mm", "maya", "renders", "mm-default"
)
```

**Better:** Configuration module
```python
# config.py
from pathlib import Path

class PipelineConfig:
    RENDERS_ROOT = "/shows/{show}/shots/{seq}/{shot}/user/{user}/mm/maya/renders/mm-default"
    PLATE_ROOT = "/shows/{show}/shots/{seq}/{shot}/publish/turnover/plate/input_plate"
    PLAYBLAST_ROOT = "/shows/{show}/shots/{seq}/{shot}/user/{user}/mm/maya/playblast"

    @staticmethod
    def get_renders_root(show: str, seq: str, shot: str, user: str) -> Path:
        return Path(PipelineConfig.RENDERS_ROOT.format(
            show=show, seq=seq, shot=shot, user=user
        ))

# Usage:
renders_root = PipelineConfig.get_renders_root(show, seq, shot, user)
```

#### 2. Testing Structure

Add unit tests for complex logic:

```python
# tests/test_plate_detection.py
import pytest
from pathlib import Path
from mm_plate_read import _detect_plate_id, _norm_plate_token

def test_norm_plate_token():
    assert _norm_plate_token("fg1") == "FG01"
    assert _norm_plate_token("FG01") == "FG01"
    assert _norm_plate_token("bc02") == "BC02"
    assert _norm_plate_token("invalid") is None

def test_detect_plate_id_from_filename():
    nk_path = Path("/shows/demo/shots/010/0100/user/test/scene/FG01/comp_FG01_v001.nk")
    plate_root = Path("/shows/demo/shots/010/0100/publish/turnover/plate/input_plate")

    result = _detect_plate_id(nk_path, plate_root)
    assert result == "FG01"
```

#### 3. Structured Logging

```python
import logging

logger = logging.getLogger(__name__)

def create_latest_plate_read():
    logger.info(f"Searching for plates under: {plate_root}")
    logger.debug(f"Detected plate ID: {plate_id}")

    if not chosen:
        logger.error(f"No plate sequences found under: {plate_root}")
        _err("No plate sequences found")

    logger.info(f"Created Read node: {hash_pattern}")
```

#### 4. Complete Type Annotations

```python
# Current (partial)
def _scan_seq(dir_path: Path, shot: str, vnum: str):
    ...

# Better (complete)
def _scan_seq(
    dir_path: Path,
    shot: str,
    vnum: str
) -> tuple[str, str, int, int, int, list[Path]] | None:
    """Scan directory for matching sequences."""
    ...
```

---

## Quick Reference

### Common Patterns

**Get current script path:**
```python
nk_path = nuke.root().name()
if not nk_path or nk_path == "Root":
    nuke.message("Please save the script first")
    return
```

**Parse show/shot from path:**
```python
from pathlib import Path

parts = Path(nk_path).parts
try:
    show_idx = parts.index("shows")
    shot_idx = parts.index("shots")
    show = parts[show_idx + 1]
    seq = parts[shot_idx + 1]
    shot = parts[shot_idx + 2]
except (ValueError, IndexError):
    nuke.message("Could not parse shot from path")
    return
```

**Create Read node with sequence:**
```python
read = nuke.nodes.Read()
read["name"].setValue("Read_plate_v001")

# Set file (use first frame, then hash pattern)
read["file"].fromUserText("/path/to/shot.1001.exr")
read["file"].fromUserText("/path/to/shot.####.exr")

# Set frame range
read["first"].setValue(1001)
read["last"].setValue(1100)
read["origfirst"].setValue(1001)
read["origlast"].setValue(1100)

# Reload to scan sequence
read["reload"].execute()
```

**Print to Script Editor:**
```python
nuke.tprint("Message appears in Script Editor")
```

**Show message dialog:**
```python
nuke.message("Message appears in popup")
```

**Ask user for confirmation:**
```python
if nuke.ask("Continue with operation?"):
    # User clicked Yes
    proceed()
```

**Get selected nodes:**
```python
selected = nuke.selectedNodes()
for node in selected:
    print(node.name())
```

**Deselect all:**
```python
for node in nuke.selectedNodes():
    node.setSelected(False)
```

---

## Resources

### Official Documentation
- [Nuke Python Developer's Guide](https://learn.foundry.com/nuke/developers/140/pythondevguide/)
- [Nuke Python API Reference](https://learn.foundry.com/nuke/developers/140/pythonreference/)

### Key Documentation Pages
- Getting Started: https://learn.foundry.com/nuke/developers/140/pythonreference/basics.html
- Nuke as Python Module: https://learn.foundry.com/nuke/developers/140/pythonreference/nuke_as_python_module.html
- Callbacks: https://support.foundry.com/hc/en-us/articles/115000007364

### Python Version
- Nuke uses Python 3.11.7 (as of recent versions)
- Can be imported as module into external Python interpreter

---

## Scorecard for This Codebase

| Category | Status | Score | Notes |
|----------|--------|-------|-------|
| File Organization | ✅ Excellent | 5/5 | Correct menu.py usage |
| Node Creation | ✅ Excellent | 5/5 | Proper nuke.nodes.* pattern |
| Knob Manipulation | ✅ Excellent | 5/5 | Efficient setting, good defaults |
| Error Handling | ✅ Good | 4/5 | User-friendly, could be more specific |
| Code Reusability | ✅ Good | 4/5 | Good helper functions |
| Type Safety | ⚠️ Partial | 3/5 | Some type hints, needs completion |
| Documentation | ⚠️ Partial | 3/5 | Some docstrings, needs more |
| Testing | ⚠️ Missing | 1/5 | No unit tests |
| Configuration | ⚠️ Hardcoded | 2/5 | Paths should be configurable |

**Overall: 32/45 (71%)**

### Priority Improvements

1. **High Priority:**
   - Add comprehensive docstrings
   - Complete type annotations
   - Extract paths to configuration

2. **Medium Priority:**
   - Add unit tests
   - Implement structured logging
   - Narrow exception handling

3. **Low Priority:**
   - Add module `__version__`
   - Add usage examples in docstrings

---

## Conclusion

This codebase demonstrates strong understanding of Nuke Python API fundamentals:
- Correct file organization (menu.py vs init.py)
- Appropriate node creation patterns
- Defensive programming (hotkey deduplication)
- Module hot-reloading for development
- Sophisticated path parsing and fallback logic

The main opportunities for improvement are in **code documentation, type safety, and testing** - all important for long-term maintainability in production pipelines.

### Key Takeaways

1. **Always use nuke.nodes.* for automation** - Faster, no UI side effects
2. **Keep menu.py for UI only** - Put persistent config in init.py
3. **Implement hot-reloading** - Makes development much faster
4. **Handle missing knobs gracefully** - Different Nuke versions vary
5. **Load real frame before hash pattern** - Better metadata detection
6. **Never block the main thread** - Use threading for long operations
7. **Type hints + docstrings = maintainability** - Worth the investment

---

**Last Updated:** 2025-11-02
**Author:** Analysis based on Foundry official documentation and codebase review

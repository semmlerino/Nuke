#!/usr/bin/env python3
"""Extract individual Nuke scripts from scripts.txt file."""

import re
from pathlib import Path


def clean_text(text: str) -> str:
    """Clean text if needed."""
    # If the file was read correctly with UTF-16-LE,
    # it should already be properly decoded.
    # Just return as-is and let's see if it needs cleaning
    return text


def extract_filename(script_content: str) -> str | None:
    """Extract filename from script header comment."""
    lines = script_content.strip().split('\n')
    for line in lines[:5]:  # Check first 5 lines
        # Look for comment like: # ~/.nuke/mm_plate_read.py
        if '/.nuke/' in line and '.py' in line:
            # Extract the filename
            match = re.search(r'\.nuke/([^/\s]+\.py)', line)
            if match:
                return match.group(1)

    # Fallback: generate a name
    return None


def main():
    script_file = Path('/mnt/c/CustomScripts/Python/Work/Linux/Nuke/scripts.txt')

    # Read the entire file - try different encodings
    print(f"Reading {script_file}...")
    encodings = ['utf-16-le', 'utf-16', 'utf-8', 'latin-1']
    raw_content = None

    for encoding in encodings:
        try:
            with open(script_file, encoding=encoding) as f:
                raw_content = f.read()
            print(f"Successfully read with encoding: {encoding}")
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if raw_content is None:
        raise ValueError("Could not read file with any known encoding")

    # Clean the text (remove extra spaces)
    print("Cleaning text...")
    cleaned_content = clean_text(raw_content)

    # Split by script delimiters (-- or ---)
    print("Splitting scripts...")
    # Split by lines containing only dashes
    scripts = re.split(r'\n-{2,}\n', cleaned_content)

    print(f"Found {len(scripts)} scripts")

    # Process each script
    extracted = []
    seen_filenames = {}  # Track duplicate filenames

    for i, script in enumerate(scripts, 1):
        script = script.strip()
        if not script or len(script) < 50:  # Skip empty or very short content
            continue

        # Extract filename from script
        filename = extract_filename(script)
        if not filename:
            filename = f"nuke_script_{i}.py"

        # Handle duplicates by adding a counter
        original_filename = filename
        if filename in seen_filenames:
            seen_filenames[filename] += 1
            name, ext = filename.rsplit('.', 1)
            filename = f"{name}_{seen_filenames[original_filename]}.{ext}"
        else:
            seen_filenames[filename] = 1

        print(f"Script {i}: {filename}")
        extracted.append((filename, script))

    # Write each script to its own file
    print("\nWriting scripts to individual files...")
    output_dir = Path('/mnt/c/CustomScripts/Python/Work/Linux/Nuke')

    for filename, script in extracted:
        output_path = output_dir / filename
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(script)
        print(f"  Wrote: {filename}")

    print(f"\nDone! Extracted {len(extracted)} scripts.")


if __name__ == '__main__':
    main()

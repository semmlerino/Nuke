#!/usr/bin/env python3
"""
Decode application bundle from base64-encoded tar.gz file.

This script decodes the base64-encoded compressed application bundle
and extracts it to a specified directory.
"""

import argparse
import base64
import io
import sys
import tarfile
from pathlib import Path
from typing import cast


def decode_bundle(encoded_file: str, output_dir: str | None = None, list_only: bool = False) -> bool:
    """
    Decode a base64-encoded tar.gz bundle and extract it.

    Args:
        encoded_file: Path to the base64-encoded file
        output_dir: Directory to extract to (default: current directory)
        list_only: If True, only list contents without extracting

    Returns:
        True if successful, False otherwise
    """
    try:
        # Default output directory
        if output_dir is None:
            output_dir = str(Path.cwd())

        # Read the encoded file
        print(f"Reading encoded file: {encoded_file}")
        with Path(encoded_file).open(encoding="utf-8") as f:
            content = f.read()

        # Check if this is a FOLDER_TRANSFER_V1 format (with header)
        if content.startswith("FOLDER_TRANSFER_V1"):
            # Parse header
            header_end = content.find("\n")
            if header_end == -1:
                print("ERROR: Invalid bundle format - no data after header")
                return False

            header_line = content[:header_end]
            encoded_data = content[header_end + 1:]  # Everything after first newline

            # Parse header: FOLDER_TRANSFER_V1|chunk_num|total_chunks|folder_name
            header_parts = header_line.split("|")
            if len(header_parts) >= 4:
                chunk_num = header_parts[1]
                total_chunks = header_parts[2]
                folder_name = header_parts[3]
                print(f"Bundle format: {header_parts[0]}")
                print(f"Chunk {chunk_num}/{total_chunks}, Folder: {folder_name}")
        else:
            # Plain base64 format
            encoded_data = content

        print(f"Encoded data size: {len(encoded_data)} characters")

        # Add proper padding for base64
        padding = len(encoded_data) % 4
        if padding:
            encoded_data += "=" * (4 - padding)
            print(f"Added {4 - padding} bytes of padding")

        # Decode from base64
        print("Decoding base64...")
        try:
            tar_data = base64.b64decode(encoded_data)
            print(f"Decoded to {len(tar_data)} bytes")
        except Exception as e:
            print(f"ERROR: Base64 decode failed: {e}")
            print(f"Data length: {len(encoded_data)}")
            return False

        # Extract tar archive
        print("Extracting archive...")
        tar_buffer = io.BytesIO(tar_data)

        try:
            with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
                # List contents
                members = tar.getmembers()
                print(f"Found {len(members)} items in archive")

                if list_only:
                    print("\nArchive contents:")
                    for member in members:
                        print(f"  {member.name}")
                    return True

                # Extract
                print(f"Extracting to: {output_dir}")
                tar.extractall(path=output_dir)
                print(f"✓ Successfully extracted to {output_dir}")
                return True

        except tarfile.TarError as e:
            # Try without gzip compression
            print("Trying uncompressed tar...")
            _ = tar_buffer.seek(0)
            try:
                with tarfile.open(fileobj=tar_buffer, mode="r:") as tar:
                    members = tar.getmembers()
                    print(f"Found {len(members)} items in archive")

                    if list_only:
                        print("\nArchive contents:")
                        for member in members:
                            print(f"  {member.name}")
                        return True

                    tar.extractall(path=output_dir)
                    print(f"✓ Successfully extracted to {output_dir}")
                    return True
            except Exception as e2:
                print(f"ERROR: Archive extraction failed: {e} / {e2}")
                return False

    except FileNotFoundError:
        print(f"ERROR: File not found: {encoded_file}")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Decode base64-encoded tar.gz application bundle",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract to current directory
  python decode_app.py encoded_app_20251106.txt

  # Extract to specific directory
  python decode_app.py encoded_app_20251106.txt -o /tmp/shotbot_bundle

  # List contents without extracting
  python decode_app.py encoded_app_20251106.txt --list-only
        """
    )

    _ = parser.add_argument(
        "encoded_file",
        help="Path to the base64-encoded bundle file"
    )

    _ = parser.add_argument(
        "-o", "--output-dir",
        help="Output directory (default: current directory)",
        default=None
    )

    _ = parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list archive contents without extracting"
    )

    args = parser.parse_args()

    # Decode the bundle with explicit casting for argparse attributes
    success = decode_bundle(
        cast("str", args.encoded_file),
        cast("str | None", args.output_dir),
        cast("bool", args.list_only)
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

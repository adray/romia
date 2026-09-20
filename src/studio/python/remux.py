#!/usr/bin/env python3

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Fragment all mp4s in a directory using ffmpeg."
    )
    parser.add_argument("directory", type=Path, help="Directory containing mp4 files")
    parser.add_argument(
        "-f", "--force", action="store_true",
        help="Overwrite existing fragmented files"
    )
    args = parser.parse_args()

    directory = args.directory
    if not directory.is_dir():
        sys.exit(f"Error: {directory} is not a valid directory")

    frag_dir = directory / "Frags"
    frag_dir.mkdir(exist_ok=True)

    mp4_files = sorted(directory.glob("*.mp4"))
    if not mp4_files:
        print(f"No .mp4 files found in {directory}")
        return

    for src in mp4_files:
        out = frag_dir / f"{src.stem}frag{src.suffix}"

        if out.exists() and not args.force:
            print(f"Skipping {src.name} (already exists in Frags, use -f to overwrite)")
            continue

        print(f"Processing {src.name} -> {out.name}")
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-c", "copy",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            str(out),
        ]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print(f"Warning: ffmpeg failed on {src.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Extract first/last frame pHashes from every .mp4 in a directory.

Requires ffmpeg on PATH, plus the Python packages `imagehash` and `Pillow`:
    pip install imagehash Pillow --break-system-packages

Usage:
    python video_phash.py /path/to/videos -o hashes.json
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
import imagehash


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def extract_first_frame(video_path: Path, out_path: Path):
    run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(out_path),
    ])


def extract_last_frame(video_path: Path, out_path: Path, seek_back: float = 3.0):
    """
    Seek near the end of the file and keep overwriting out_path with each
    decoded frame (-update 1). Whatever is left on disk when ffmpeg exits
    is the last frame of the video.
    """
    run([
        "ffmpeg", "-y",
        "-sseof", f"-{seek_back}",
        "-i", str(video_path),
        "-update", "1",
        "-q:v", "2",
        str(out_path),
    ])


def phash_of(image_path: Path):
    with Image.open(image_path) as img:
        return str(imagehash.phash(img))


def process_video(video_path: Path, tmp_dir: Path, seek_back: float):
    first_path = tmp_dir / f"{video_path.stem}_first.jpg"
    last_path = tmp_dir / f"{video_path.stem}_last.jpg"
    first_hash = last_hash = None

    try:
        extract_first_frame(video_path, first_path)
        extract_last_frame(video_path, last_path, seek_back)

        if first_path.exists():
            first_hash = phash_of(first_path)
        if last_path.exists():
            last_hash = phash_of(last_path)

    except subprocess.CalledProcessError as e:
        print(f"  ffmpeg failed on {video_path.name}: {e}", file=sys.stderr)

    finally:
        first_path.unlink(missing_ok=True)
        last_path.unlink(missing_ok=True)

    return first_hash, last_hash


def main():
    parser = argparse.ArgumentParser(
        description="pHash the first/last frame of every mp4 in a directory."
    )
    parser.add_argument("directory", type=Path, help="Directory containing .mp4 files")
    parser.add_argument("-o", "--output", type=Path, default=Path("hashes.json"),
                         help="Output JSON path (default: hashes.json)")
    parser.add_argument("--seek-back", type=float, default=3.0,
                         help="Seconds before EOF to start seeking for the last frame (default: 3.0)")
    args = parser.parse_args()

    videos = sorted(args.directory.glob("*.mp4"))
    if not videos:
        print(f"No .mp4 files found in {args.directory}", file=sys.stderr)
        sys.exit(1)

    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for i, video in enumerate(videos, 1):
            print(f"[{i}/{len(videos)}] {video.name}")
            first_hash, last_hash = process_video(video, tmp_dir, args.seek_back)
            results[video.name] = {
                "path": str(video.resolve()),
                "first_frame_phash": first_hash,
                "last_frame_phash": last_hash,
            }

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nWrote {len(results)} entries to {args.output}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Extract frames from a video (or every video in a directory) into their own
subfolder, with the timestamp (seconds into the video) baked into each
frame's filename, so frames and their eventual captions stay tied to a
point in the video.

Usage:
    ./extract_frames.py <video_file_or_dir> [fps] [output_root]

    video_file_or_dir  path to a single input video, OR a directory
                        containing video files (required)
    fps                 frames per second to extract (default: 1)
    output_root         parent folder to create per-video subfolders under
                         (default: ./Frames) - point batch_frame_captions.py's
                         --frames-root at this same folder afterwards.

Output:
    <output_root>/<video_stem>/frame_000001_t0.000s.png, ...
    (one subfolder per video processed)
"""

import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v",
    ".mpg", ".mpeg", ".wmv", ".flv", ".ts",
}


def check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        sys.exit("Error: ffmpeg not found on PATH")


def find_videos(path: Path) -> list[Path]:
    """Return a sorted list of video files: just [path] if it's a file,
    or every video file directly inside it if it's a directory."""
    if path.is_file():
        return [path]

    if path.is_dir():
        videos = sorted(
            p for p in path.iterdir()
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
        )
        if not videos:
            sys.exit(f"Error: no video files found in directory: {path}")
        return videos

    sys.exit(f"Error: path not found: {path}")


def extract_one(video: Path, fps: float, output_root: Path) -> None:
    out_dir = output_root / video.stem

    if out_dir.exists():
        print(f"Removing existing frames in {out_dir}")
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    print(f"Extracting frames from '{video}' at {fps}fps into {out_dir} ...")
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error",
            "-i", str(video),
            "-vf", f"fps={fps}",
            str(out_dir / "frame_%06d.png"),
        ],
        check=True,
    )

    print(f"Embedding timestamps into filenames (based on {fps}fps)...")
    for f in sorted(out_dir.glob("frame_*.png")):
        num_str = f.stem.removeprefix("frame_")
        n = int(num_str)  # int() handles leading zeros fine
        ts = (n - 1) / fps
        new_name = f"frame_{num_str}_t{ts:.3f}s.png"
        f.rename(out_dir / new_name)

    count = len(list(out_dir.glob("*.png")))
    print(f"Done. {count} frames in: {out_dir}")


def main() -> None:
    args = sys.argv[1:]
    if len(args) < 1:
        sys.exit(f"Usage: {sys.argv[0]} <video_file_or_dir> [fps] [output_root]")

    input_path = Path(args[0])
    fps = float(args[1]) if len(args) >= 2 else 1.0
    output_root = Path(args[2]) if len(args) >= 3 else Path("./Frames")

    check_ffmpeg()
    videos = find_videos(input_path)

    if len(videos) > 1:
        print(f"Found {len(videos)} videos in '{input_path}'")

    failures = []
    for video in videos:
        try:
            extract_one(video, fps, output_root)
        except subprocess.CalledProcessError as e:
            print(f"Error: ffmpeg failed on {video}: {e}", file=sys.stderr)
            failures.append(video)
        print()

    if failures:
        sys.exit(f"Failed to process {len(failures)} video(s): "
                  f"{', '.join(str(v) for v in failures)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Validate an uploaded avatar model package (a zip) before it is published.

Usage:
    python package_scanner.py model.zip --schema-dir ../schema
    python package_scanner.py model.zip --schema-dir ../schema --out-dir ./approved \
        --limits hub_limits.json --report report.json

What it does:
    1. Inspects the zip (names, types, sizes, symlinks, encryption) BEFORE extracting.
    2. Extracts into a private temp dir with hard byte caps.
    3. Validates manifest.json, then the FSM and metadata files, against the JSON schemas.
    4. Cross-checks layout, FSM references (initial_state, transition ids, clip names)
       and the clip directory against the metadata.
    5. Probes every clip with ffprobe (codec, size, bitrate, duration, fragmented MP4)
       and fully decodes it with ffmpeg.
    6. Re-encodes the thumbnail as a fresh small JPEG (or generates one from the first
       idle frame if none was supplied).
    7. With --out-dir, writes a normalized copy of the package to it (only on success).
       Publish from that directory, never from the uploader's original files.

Output:
    A JSON report on stdout (and --report FILE): {"ok", "errors", "warnings", ...}.

Exit codes:
    0  package is valid
    1  package was rejected (see "errors" in the report) - do not retry
    2  internal/operator error (missing tool, bad schema dir, ...) - safe to retry

Requires: jsonschema, Pillow, ffmpeg and ffprobe on PATH.
Run it in a sandbox with no network and hard CPU/memory/time limits.
"""

import argparse
import concurrent.futures
import hashlib
import json
import math
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import traceback
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import jsonschema
from PIL import Image, ImageOps

EXIT_OK, EXIT_REJECTED, EXIT_INTERNAL = 0, 1, 2

MB = 1024 * 1024

# Hub policy can override any of these with --limits.
DEFAULT_LIMITS = {
    "max_package_bytes": 2048 * MB,       # size of the zip itself
    "max_uncompressed_bytes": 4096 * MB,  # total extracted size
    "max_entries": 1050,                  # files in the zip
    "max_clips": 1000,
    "max_clip_bytes": 50 * MB,
    "max_json_bytes": 5 * MB,
    "max_thumbnail_bytes": 10 * MB,
    "max_thumbnail_pixels": 4096 * 4096,
    "thumbnail_size": 512,                # longest edge of the output thumbnail
    "allowed_video_codecs": ["h264"],
    "allowed_pix_fmts": ["yuv420p"],
    "allowed_audio_codecs": ["aac"],
    "max_width": 2048,
    "max_height": 2048,
    "max_bitrate": 20_000_000,            # bits per second
    "max_clip_duration_ms": 60_000,
    "duration_tolerance_ms": 150,         # probed vs metadata duration (~2.4 frames @16fps)
    "ffprobe_timeout": 30,
    "ffmpeg_timeout": 120,
}

ALLOWED_EXT = {".json", ".mp4", ".jpg", ".jpeg", ".png"}
IGNORED_TOP = {"__MACOSX"}
IGNORED_NAMES = {".DS_Store"}
# Each path component starts with an alphanumeric/underscore, so this also rejects
# absolute paths, "..", hidden files, backslashes, drive letters and control characters.
SAFE_ENTRY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*/?$")
CLIP_SUFFIX = "frag.mp4"  # metadata key "a.mp4" is packaged as "<clipDir>/afrag.mp4"
MAX_REPORT_ITEMS = 100
THUMBNAIL_NAME = "thumbnail.jpg"


# --------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------

class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.truncated = False
        self.info = {}

    def _add(self, bucket, code, message, file):
        if len(bucket) >= MAX_REPORT_ITEMS:
            self.truncated = True
            return
        bucket.append({"code": code, "file": file, "message": str(message)[:300]})

    def error(self, code, message, file=None):
        self._add(self.errors, code, message, file)

    def warn(self, code, message, file=None):
        self._add(self.warnings, code, message, file)

    @property
    def ok(self):
        return not self.errors

    def to_dict(self):
        return {
            "ok": self.ok,
            **self.info,
            "errors": self.errors,
            "warnings": self.warnings,
            "truncated": self.truncated,
        }


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(MB), b""):
            h.update(chunk)
    return h.hexdigest()


def run_tool(cmd, timeout):
    """Run an external tool. Returns CompletedProcess, or None on timeout."""
    try:
        return subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def require_tools():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"{tool} not found on PATH")


def _reject_constant(name):
    raise ValueError(f"invalid JSON constant {name}")


def load_json_file(path, max_bytes, report, label):
    try:
        if path.stat().st_size > max_bytes:
            report.error("json_too_large", f"{label} is larger than {max_bytes} bytes", label)
            return None
        text = path.read_bytes().decode("utf-8")
        return json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as e:  # includes JSONDecodeError and UnicodeDecodeError
        report.error("json_invalid", f"{label} is not valid JSON: {e}", label)
        return None


def check_schema(data, schema_dir, schema_name, label, report):
    """Validate against a schema, reporting up to 20 errors. Returns True if valid."""
    with open(Path(schema_dir) / schema_name, encoding="utf-8") as f:
        schema = json.load(f)
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
    for e in errors[:20]:
        loc = "/".join(str(p) for p in e.absolute_path) or "(root)"
        report.error("schema", f"{loc}: {e.message}", label)
    if len(errors) > 20:
        report.error("schema", f"... and {len(errors) - 20} more schema errors", label)
    return not errors


# --------------------------------------------------------------------------------------
# Zip handling
# --------------------------------------------------------------------------------------

def inspect_zip(zf, limits, report):
    """Check the zip's entries without extracting. Returns the list of ZipInfo to extract."""
    infos = zf.infolist()
    if len(infos) > limits["max_entries"]:
        report.error("zip_too_many_entries", f"zip has {len(infos)} entries (max {limits['max_entries']})")
        return []

    entries = []
    seen = set()
    total = 0
    for info in infos:
        name = info.filename
        parts = name.split("/")
        if parts[0] in IGNORED_TOP or parts[-1] in IGNORED_NAMES:
            continue  # macOS metadata; never extracted
        if len(name) > 200 or not SAFE_ENTRY.match(name):
            report.error("zip_unsafe_name", f"unsupported file name in zip: {name!r}")
            continue
        if info.flag_bits & 0x1:
            report.error("zip_encrypted", f"encrypted entries are not allowed: {name}")
            continue
        file_type = stat.S_IFMT(info.external_attr >> 16)
        if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
            report.error("zip_special_file", f"symlinks and special files are not allowed: {name}")
            continue
        if info.is_dir():
            continue
        key = name.lower()
        if key in seen:
            report.error("zip_duplicate", f"duplicate file name in zip: {name}")
            continue
        seen.add(key)
        if PurePosixPath(name).suffix.lower() not in ALLOWED_EXT:
            report.error("zip_file_type", f"file type not allowed: {name}")
            continue
        total += info.file_size
        entries.append(info)

    if total > limits["max_uncompressed_bytes"]:
        report.error("zip_too_large", f"package is {total} bytes when extracted (max {limits['max_uncompressed_bytes']})")
    return entries


def safe_extract(zf, entries, dest, limits, report):
    """Extract with a hard byte budget, ignoring the sizes the zip header claims."""
    dest = dest.resolve()
    budget = limits["max_uncompressed_bytes"]
    for info in entries:
        target = (dest / info.filename).resolve()
        if not target.is_relative_to(dest):
            report.error("zip_unsafe_name", f"unsafe path in zip: {info.filename}")
            return False
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            written = 0
            with zf.open(info) as src, open(target, "wb") as dst:
                while True:
                    chunk = src.read(MB)
                    if not chunk:
                        break
                    written += len(chunk)
                    budget -= len(chunk)
                    if written > info.file_size or budget < 0:
                        report.error("zip_bomb", f"{info.filename} is larger than the zip declares")
                        return False
                    dst.write(chunk)
            if written != info.file_size:
                report.error("zip_corrupt", f"{info.filename} is truncated or corrupt")
                return False
        except (zipfile.BadZipFile, NotImplementedError, EOFError, RuntimeError, OSError) as e:
            report.error("zip_corrupt", f"could not extract {info.filename}: {type(e).__name__}")
            return False
    return True


# --------------------------------------------------------------------------------------
# FSM cross-checks (things JSON Schema can't express)
# --------------------------------------------------------------------------------------

def check_fsm(fsm, metadata, report, label):
    """initial_state is an INDEX into states[]; transitions are state IDs. Returns used clip names."""
    used = set()
    for fi, f in enumerate(fsm["fsms"]):
        where = f"fsms[{fi}]"
        states = f["states"]
        counts = Counter(s["id"] for s in states)
        for sid, n in counts.items():
            if n > 1:
                report.error("fsm_duplicate_state_id", f"{where}: state id {sid} is used {n} times", label)
        ids = set(counts)
        if f["initial_state"] >= len(states):
            report.error("fsm_initial_state", f"{where}: initial_state {f['initial_state']} is out of range", label)
        for si, state in enumerate(states):
            for pi, path in enumerate(state["paths"]):
                loc = f"{where}.states[{si}].paths[{pi}]"
                for clip in path["clips"]:
                    if clip in metadata:
                        used.add(clip)
                    else:
                        report.error("fsm_unknown_clip", f"{loc}: clip '{clip}' is not in the metadata", label)
                for t in path["transition"]:
                    if t not in ids:
                        report.error("fsm_unknown_transition", f"{loc}: transition to unknown state id {t}", label)
    return used


# --------------------------------------------------------------------------------------
# Clip checks
# --------------------------------------------------------------------------------------

def mp4_top_level_boxes(path):
    """Return the list of top-level MP4 box types. Raises ValueError on a corrupt structure."""
    total = path.stat().st_size
    boxes = []
    pos = 0
    with open(path, "rb") as f:
        while pos < total:
            if len(boxes) > 100_000:
                raise ValueError("too many boxes")
            f.seek(pos)
            header = f.read(16)
            if len(header) < 8:
                raise ValueError("truncated box header")
            size = int.from_bytes(header[:4], "big")
            kind = header[4:8].decode("latin-1")
            header_len = 8
            if size == 1:
                if len(header) < 16:
                    raise ValueError("truncated box header")
                size = int.from_bytes(header[8:16], "big")
                header_len = 16
            elif size == 0:
                size = total - pos
            if size < header_len or pos + size > total:
                raise ValueError("box extends past end of file")
            boxes.append(kind)
            pos += size
    return boxes


def check_clip(path, expected_ms, limits):
    """Returns a list of (severity, code, message). Runs in a worker thread."""
    problems = []

    def bad(code, msg):
        problems.append(("error", code, msg))

    size = path.stat().st_size
    if size > limits["max_clip_bytes"]:
        bad("clip_too_large", f"clip is {size} bytes (max {limits['max_clip_bytes']})")
        return problems

    # Container structure: must be a fragmented MP4 so it can be streamed.
    try:
        boxes = mp4_top_level_boxes(path)
    except (OSError, ValueError) as e:
        bad("clip_not_mp4", f"clip is not a valid MP4 file ({e})")
        return problems
    if not boxes or boxes[0] != "ftyp":
        bad("clip_not_mp4", "clip is not an MP4 file")
        return problems
    if "moov" not in boxes or "moof" not in boxes:
        bad("clip_not_fragmented",
            "clip is not a fragmented MP4 (remux with -movflags frag_keyframe+empty_moov+default_base_moof)")
        return problems

    # Probe. -f mov forces the demuxer (ffmpeg otherwise guesses from content) and the
    # protocol whitelist stops playlist-style files from reading anything but this file.
    proc = run_tool(
        ["ffprobe", "-v", "error", "-protocol_whitelist", "file", "-f", "mov",
         "-show_format", "-show_streams", "-of", "json", str(path)],
        limits["ffprobe_timeout"])
    if proc is None:
        bad("clip_timeout", "probing the clip took too long")
        return problems
    if proc.returncode != 0:
        bad("clip_unreadable", "clip could not be read")
        return problems
    try:
        info = json.loads(proc.stdout)
    except ValueError:
        bad("clip_unreadable", "clip could not be read")
        return problems

    streams = info.get("streams", [])
    fmt = info.get("format", {})
    video = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    other = [s for s in streams if s.get("codec_type") not in ("video", "audio")]

    if len(video) != 1:
        bad("clip_streams", f"expected exactly one video stream, found {len(video)}")
        return problems
    v = video[0]
    if v.get("codec_name") not in limits["allowed_video_codecs"]:
        bad("clip_codec", f"video codec '{v.get('codec_name')}' is not allowed (allowed: {limits['allowed_video_codecs']})")
    if v.get("pix_fmt") not in limits["allowed_pix_fmts"]:
        bad("clip_pix_fmt", f"pixel format '{v.get('pix_fmt')}' is not allowed (allowed: {limits['allowed_pix_fmts']})")
    w, h = v.get("width"), v.get("height")
    if not (isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0):
        bad("clip_dimensions", "clip has no valid dimensions")
    elif w > limits["max_width"] or h > limits["max_height"]:
        bad("clip_dimensions", f"clip is {w}x{h} (max {limits['max_width']}x{limits['max_height']})")
    for a in audio:
        if a.get("codec_name") not in limits["allowed_audio_codecs"]:
            bad("clip_audio_codec", f"audio codec '{a.get('codec_name')}' is not allowed")
    if other:
        problems.append(("warning", "clip_extra_streams", f"{len(other)} non-audio/video stream(s) ignored"))

    # Duration: the player schedules clips from the metadata value, so it must match.
    try:
        dur_ms = float(fmt.get("duration")) * 1000.0
    except (TypeError, ValueError):
        dur_ms = None
    if dur_ms is None or not math.isfinite(dur_ms) or dur_ms <= 0:
        bad("clip_duration", "clip duration could not be determined")
    else:
        if dur_ms > limits["max_clip_duration_ms"]:
            bad("clip_duration", f"clip is {dur_ms:.0f} ms long (max {limits['max_clip_duration_ms']})")
        if abs(dur_ms - expected_ms) > limits["duration_tolerance_ms"]:
            bad("clip_duration_mismatch",
                f"clip is {dur_ms:.0f} ms but metadata says {expected_ms:.0f} ms")
        bitrate = size * 8 / (dur_ms / 1000.0)
        if bitrate > limits["max_bitrate"]:
            bad("clip_bitrate", f"bitrate {bitrate / 1e6:.1f} Mbps exceeds {limits['max_bitrate'] / 1e6:.1f} Mbps")

    if any(p[0] == "error" for p in problems):
        return problems  # don't spend a full decode on a clip that already failed

    # Full decode catches truncation and corrupt frames.
    proc = run_tool(
        ["ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "file", "-f", "mov",
         "-i", str(path), "-f", "null", "-"],
        limits["ffmpeg_timeout"])
    if proc is None:
        bad("clip_timeout", "decoding the clip took too long")
    elif proc.returncode != 0:
        bad("clip_decode", "clip failed to decode")
    return problems


def check_clips(root, clip_dir, metadata, limits, report, workers):
    clip_path = root / clip_dir
    expected = {key[:-4] + CLIP_SUFFIX: key for key in metadata}  # packaged name -> metadata key

    actual = set()
    for p in sorted(clip_path.iterdir()):
        if p.is_file():
            actual.add(p.name)
        else:
            report.error("clip_dir_layout", f"unexpected subdirectory in {clip_dir}: {p.name}", clip_dir)

    for name in sorted(expected.keys() - actual):
        report.error("clip_missing", f"metadata lists '{expected[name]}' but {clip_dir}/{name} is missing", clip_dir)
    for name in sorted(actual - expected.keys()):
        report.error("clip_unexpected", f"{clip_dir}/{name} is not listed in the metadata", clip_dir)

    names = sorted(actual & expected.keys())
    tasks = []
    for name in names:
        metadata_entry = metadata[expected[name]]
        duration = metadata_entry["duration"] if "duration" in metadata_entry else 5062.5
        tasks.append((name, clip_path / name, duration))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = pool.map(lambda t: check_clip(t[1], t[2], limits), tasks)
        for (name, _, _), problems in zip(tasks, results):
            for severity, code, message in problems:
                add = report.error if severity == "error" else report.warn
                add(code, message, f"{clip_dir}/{name}")


# --------------------------------------------------------------------------------------
# Thumbnail
# --------------------------------------------------------------------------------------

def process_thumbnail(src, dst, limits):
    """Re-encode as a small JPEG so nothing from the uploader's file (EXIF, odd chunks) survives.
    Returns an error message, or None on success."""
    try:
        if src.stat().st_size > limits["max_thumbnail_bytes"]:
            return "thumbnail file is too large"
        Image.MAX_IMAGE_PIXELS = limits["max_thumbnail_pixels"]
        with Image.open(src) as img:  # lazy: reads the header only
            if img.format not in ("JPEG", "PNG"):  # trust the content, not the extension
                return "thumbnail must be a JPEG or PNG image"
            if img.width * img.height > limits["max_thumbnail_pixels"]:
                return "thumbnail dimensions are too large"
            img = ImageOps.exif_transpose(img)  # apply rotation before metadata is dropped
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgba = img.convert("RGBA")
                flat = Image.new("RGB", rgba.size, (255, 255, 255))
                flat.paste(rgba, mask=rgba.getchannel("A"))
                img = flat
            else:
                img = img.convert("RGB")
            size = limits["thumbnail_size"]
            img.thumbnail((size, size))
            img.save(dst, "JPEG", quality=85, optimize=True)
    except Exception as e:  # image decoders can raise almost anything on hostile input
        print(f"thumbnail error: {type(e).__name__}: {e}", file=sys.stderr)
        return "thumbnail could not be read"
    return None


def generate_thumbnail(root, clip_dir, fsm, tmp, dst, limits):
    """Make a thumbnail from the first frame of the first clip of the initial state."""
    try:
        f = fsm["fsms"][0]
        clip = f["states"][f["initial_state"]]["paths"][0]["clips"][0]
        clip_file = root / clip_dir / (clip[:-4] + CLIP_SUFFIX)
        frame = tmp / "first_frame.png"
        proc = run_tool(
            ["ffmpeg", "-v", "error", "-nostdin", "-protocol_whitelist", "file", "-f", "mov",
             "-i", str(clip_file), "-frames:v", "1", "-y", str(frame)],
            limits["ffmpeg_timeout"])
        if proc is None or proc.returncode != 0 or not frame.exists():
            return False
        return process_thumbnail(frame, dst, limits) is None
    except (KeyError, IndexError, TypeError):
        return False


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------

def validate_extracted(root, tmp, schema_dir, limits, report, workers):
    """Validate an extracted package. Returns (manifest, thumbnail_path_or_None)."""
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        report.error("manifest_missing", "manifest.json is missing from the package root")
        return None, None
    manifest = load_json_file(manifest_path, limits["max_json_bytes"], report, "manifest.json")
    if manifest is None or not check_schema(manifest, schema_dir, "manifest.schema.json", "manifest.json", report):
        return None, None  # nothing else can be trusted yet

    fsm_name, metadata_name = manifest["fsm"], manifest["metadata"]
    clip_dir, thumb_name = manifest["clipDir"], manifest.get("thumbnail")
    report.info["name"] = manifest["name"]

    # Layout: the root must contain exactly what the manifest references.
    files = ["manifest.json", fsm_name, metadata_name] + ([thumb_name] if thumb_name else [])
    if len(set(files)) != len(files):
        report.error("manifest_layout", "manifest.json, fsm, metadata and thumbnail must be different files", "manifest.json")
        return manifest, None
    for name in files:
        if not (root / name).is_file():
            report.error("file_missing", f"referenced file is missing: {name}", name)
    if not (root / clip_dir).is_dir():
        report.error("file_missing", f"clip directory is missing: {clip_dir}", clip_dir)
    for p in sorted(root.iterdir()):
        if p.is_dir() and p.name == clip_dir:
            continue
        if p.is_file() and p.name in files:
            continue
        report.error("unexpected_file", f"unexpected item in package root: {p.name}", p.name)
    if not report.ok:
        return manifest, None

    # Content of the JSON files.
    fsm = load_json_file(root / fsm_name, limits["max_json_bytes"], report, fsm_name)
    metadata = load_json_file(root / metadata_name, limits["max_json_bytes"], report, metadata_name)
    fsm_ok = fsm is not None and check_schema(fsm, schema_dir, "fsm.schema.json", fsm_name, report)
    metadata_ok = metadata is not None and check_schema(metadata, schema_dir, "metadata.schema.json", metadata_name, report)

    if metadata_ok:
        report.info["num_clips"] = len(metadata)
        if len(metadata) > limits["max_clips"]:
            report.error("too_many_clips", f"{len(metadata)} clips (max {limits['max_clips']})", metadata_name)
            metadata_ok = False
    if fsm_ok and metadata_ok:
        used = check_fsm(fsm, metadata, report, fsm_name)
        unused = sorted(set(metadata) - used)
        if unused:
            sample = ", ".join(unused[:5]) + (" ..." if len(unused) > 5 else "")
            report.warn("clips_unused", f"{len(unused)} clip(s) are not used by any FSM: {sample}", metadata_name)
    if metadata_ok:
        check_clips(root, clip_dir, metadata, limits, report, workers)

    # Thumbnail: always produce our own re-encoded copy.
    thumb_out = tmp / THUMBNAIL_NAME
    if thumb_name:
        err = process_thumbnail(root / thumb_name, thumb_out, limits)
        if err:
            report.error("thumbnail", err, thumb_name)
            return manifest, None
    elif report.ok and fsm_ok:
        if generate_thumbnail(root, clip_dir, fsm, tmp, thumb_out, limits):
            report.warn("thumbnail_generated", "no thumbnail supplied; generated one from the first frame", "manifest.json")
        else:
            report.warn("thumbnail_missing", "no thumbnail supplied and none could be generated", "manifest.json")
            return manifest, None
    else:
        return manifest, None
    return manifest, thumb_out


def publish(root, manifest, thumb_path, out_dir):
    """Write the normalized, approved copy of the package."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / manifest["fsm"], out / manifest["fsm"])
    shutil.copy2(root / manifest["metadata"], out / manifest["metadata"])
    shutil.copytree(root / manifest["clipDir"], out / manifest["clipDir"])
    shutil.copy2(thumb_path, out / THUMBNAIL_NAME)
    clean = dict(manifest)
    clean["thumbnail"] = THUMBNAIL_NAME
    clean.setdefault("schema_version", 1)
    (out / "manifest.json").write_text(json.dumps(clean, indent=2), encoding="utf-8")


def validate_package(package_path, schema_dir, limits=None, out_dir=None, workers=4):
    """Validate a package zip. Returns a Report. Raises on operator errors (missing tools, etc.)."""
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    require_tools()
    package_path = Path(package_path)
    report = Report()

    size = package_path.stat().st_size  # FileNotFoundError is an operator error, not a rejection
    report.info["package_bytes"] = size
    report.info["sha256"] = sha256_file(package_path)
    if size > limits["max_package_bytes"]:
        report.error("package_too_large", f"package is {size} bytes (max {limits['max_package_bytes']})")
        return report

    with tempfile.TemporaryDirectory(prefix="avatar_pkg_") as tmp_name:
        tmp = Path(tmp_name)
        root = tmp / "pkg"
        root.mkdir()
        try:
            with zipfile.ZipFile(package_path) as zf:
                entries = inspect_zip(zf, limits, report)
                if not report.ok or not safe_extract(zf, entries, root, limits, report):
                    return report
        except zipfile.BadZipFile:
            report.error("not_a_zip", "the uploaded file is not a valid zip archive")
            return report

        manifest, thumb = validate_extracted(root, tmp, Path(schema_dir), limits, report, workers)
        if report.ok and out_dir and manifest and thumb:
            publish(root, manifest, thumb, out_dir)
            report.info["output_dir"] = str(out_dir)
    return report


def main():
    ap = argparse.ArgumentParser(description="Validate an avatar model package.")
    ap.add_argument("package_path", help="Path to the model zip")
    ap.add_argument("--schema-dir", required=True, help="Directory containing the *.schema.json files")
    ap.add_argument("--limits", help="JSON file overriding DEFAULT_LIMITS (hub policy)")
    ap.add_argument("--out-dir", help="Write the normalized package here on success (must be empty or new)")
    ap.add_argument("--report", help="Also write the JSON report to this file")
    ap.add_argument("--workers", type=int, default=4, help="Parallel clip checks (default 4)")
    args = ap.parse_args()

    limits = {}
    if args.limits:
        with open(args.limits, encoding="utf-8") as f:
            limits = json.load(f)
        unknown = set(limits) - set(DEFAULT_LIMITS)
        if unknown:
            ap.error(f"unknown limit(s): {', '.join(sorted(unknown))}")
    if args.out_dir and Path(args.out_dir).exists() and any(Path(args.out_dir).iterdir()):
        ap.error("--out-dir must be empty or not exist")

    try:
        report = validate_package(args.package_path, args.schema_dir, limits, args.out_dir, args.workers)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"ok": False, "internal_error": True}))
        return EXIT_INTERNAL

    result = report.to_dict()
    text = json.dumps(result, indent=2)
    print(text)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
    if report.ok:
        print(f"OK: package is valid ({len(report.warnings)} warning(s))", file=sys.stderr)
        return EXIT_OK
    print(f"REJECTED: {len(report.errors)} error(s)", file=sys.stderr)
    return EXIT_REJECTED


if __name__ == "__main__":
    sys.exit(main())

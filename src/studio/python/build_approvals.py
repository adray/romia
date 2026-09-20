#!/usr/bin/env python3

import argparse
import json
import re
import os
import glob
from pathlib import Path

TIMESTAMP_RE = re.compile(r"_t([0-9]+(?:\.[0-9]+)?)s(?:\.[a-zA-Z0-9]+)?$")

# Matches ```json ... ``` or plain ``` ... ``` fences
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_timestamp(stem: str):
    m = TIMESTAMP_RE.search(stem)
    return float(m.group(1)) if m else None


def strip_code_fence(text: str) -> str:
    m = FENCE_RE.search(text)
    return m.group(1).strip() if m else text

def find_balanced_json(text: str):
    """Scan for the first balanced {...} or [...] substring and return it."""
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


def lenient_json_fixups(candidate: str) -> str:
    # Trailing commas before a closing bracket/brace
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    return candidate


def parse_caption_json(raw_text: str):
    """
    Try progressively looser strategies to pull a JSON value out of raw
    LLM output. Returns (data, None) on success, or (None, error_message).
    """
    text = raw_text.strip()
    if not text:
        return None, "caption file is empty"

    attempts = []

    # 1) Whole thing, as-is
    attempts.append(text)
    # 2) Inside a markdown code fence, if present
    fenced = strip_code_fence(text)
    if fenced != text:
        attempts.append(fenced)
    # 3) First balanced {...}/[...] found anywhere in the raw text
    balanced = find_balanced_json(text)
    if balanced:
        attempts.append(balanced)
    balanced_fenced = find_balanced_json(fenced) if fenced != text else None
    if balanced_fenced:
        attempts.append(balanced_fenced)

    last_error = "no JSON object found in caption text"
    for candidate in attempts:
        for fixed in (candidate, lenient_json_fixups(candidate)):
            try:
                return json.loads(fixed), None
            except json.JSONDecodeError as e:
                last_error = str(e)

    return None, last_error


def build_video_entry(path, video):
    frames = []
    parsed_ok = 0
    parse_errors = 0

    for frame, cluster in video:
        frame_path = Path(frame)
        entry = {
            "frame_file": os.path.basename(frame),
            "caption_file": "",
            "timestamp_seconds": extract_timestamp(frame_path.stem)
        }
        if cluster:
            entry["caption_file"] = cluster["caption_file"]
            if cluster["parse_status"] == "ok":
                entry["data"] = cluster["data"]
                entry["parse_status"] = cluster["parse_status"]
                parsed_ok += 1
            else:
                entry["error"] = cluster["error"]
                entry["raw_text"] = cluster["raw_text"]
                entry["parse_status"] = cluster["parse_status"]
                parse_errors += 1
        else:
            entry["error"] = "Requires manual check"
            entry["raw_text"] = ""
            entry["parse_status"] = "error"
            parse_errors += 1

        frames.append(entry)

    return {
        "video": os.path.basename(path),
        "frame_count": len(frames),
        "parsed_ok": parsed_ok,
        "parse_errors": parse_errors,
        "frames": frames,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames-root", required=True,
                     help="Parent dir containing one subfolder of frames+captions per video")
    ap.add_argument("--clusters", default="clusters.json")
    ap.add_argument("--out", default="approvals.json")
    args = ap.parse_args()

    root = Path(args.frames_root)
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")

    # We need to copy the frame captions to clusters

    clusterData = {}
    with open(args.clusters) as f:
        clusters = json.load(f)
    sourcePath = f"{args.frames_root}/*.txt"
    for path in glob.glob(sourcePath):
        filename = os.path.basename(path)
        clusterId = Path(filename).stem
        raw_text = Path(path).read_text(encoding="utf-8", errors="replace")
        data, error = parse_caption_json(raw_text)
        entry = {
            "frame_file": "",
            "caption_file": filename,
            "timestamp_seconds": ""
        }
        if error is None:
            entry["parse_status"] = "ok"
            entry["data"] = data
        else:
            entry["parse_status"] = "error"
            entry["error"] = error
            entry["raw_text"] = raw_text
        clusterData[clusterId] = entry

    # Then we can generate video entries

    videoDir = {}
    for id, node in clusters.items():
        for frame in node:
            cluster = clusterData[id] if id in clusterData else None
            videoPath = os.path.dirname(frame)
            if videoPath in videoDir:
                videoDir[videoPath].append((frame, cluster))
            else:
                videoDir[videoPath] = [(frame, cluster)]

    videos = []
    total_frames = total_ok = total_errors = 0
    for path, video in videoDir.items():
        entry = build_video_entry(path, video)
        #if entry["frame_count"] == 0:
        #    print(f"Warning: no .txt caption files found in {root}, skipping")
        #    continue
        videos.append(entry)
        total_frames += entry["frame_count"]
        total_ok += entry["parsed_ok"]
        total_errors += entry["parse_errors"]
        print(f"{entry['video']}: {entry['parsed_ok']}/{entry['frame_count']} parsed ok"
                + (f", {entry['parse_errors']} need review" if entry["parse_errors"] else ""))
        
    output = {
        "videos": videos,
        "summary": {
            "videos": len(videos),
            "frames": total_frames,
            "parsed_ok": total_ok,
            "parse_errors": total_errors,
        },
    }

    Path(args.out).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote {args.out} ({total_frames} frames, {total_ok} ok, {total_errors} need review)")


if __name__ == "__main__":
    main()




#!/usr/bin/env python3
"""
Drive ComfyUI-JoyCaption's built-in "Caption Tools" batch workflow
(Image Batch Path -> JoyCaption -> Caption Saver) once per video's frame
folder, so each frame gets a sidecar .txt caption written next to it.

Unlike a per-image loop, this submits exactly ONE prompt per folder -
ComfyUI-JoyCaption's Image Batch Path + Caption Saver nodes already handle
loading every image in the directory and writing each caption's sidecar
file internally, so we only need to point Image Batch Path at the right
folder and wait for the whole batch to finish.

Usage:
    ./.venv/bin/python batch_frame_captions.py \
        --frame-dirs-file frame_dirs.txt \
        --workflow workflow_api.json

    # or, if you keep one subfolder per video under a common parent:
    ./.venv/bin/python batch_frame_captions.py \
        --frames-root /path/to/extracted_frames \
        --workflow workflow_api.json

frame_dirs.txt / --frames-root subfolders should be ABSOLUTE paths ComfyUI's
process can read directly - Image Batch Path reads straight from disk, so
(unlike LoadImage) there's no need to upload frames through the API first.

Requirements:
    pip install requests   # (into the SAME venv ComfyUI runs from)
"""

import argparse
import json
import time
import uuid
import os
import shutil
from pathlib import Path

import requests

IMAGE_BATCH_PATH_HINTS = ["imagebatchpath", "image_batch_path"]


def find_node_by_hint(workflow: dict, hints, explicit_id=None) -> str:
    if explicit_id:
        if explicit_id not in workflow:
            raise SystemExit(f"Node id '{explicit_id}' not found in workflow JSON.")
        return explicit_id

    matches = []
    for nid, node in workflow.items():
        class_type = str(node.get("class_type", "")).lower()
        if any(h in class_type for h in hints):
            matches.append(nid)

    if not matches:
        raise SystemExit(
            f"Couldn't autodetect a node matching {hints}. Open your workflow_api.json, "
            f"find the Image Batch Path node's id, and pass it via --image-batch-node."
        )
    if len(matches) > 1:
        print(f"Warning: multiple candidate nodes found {matches}; using the first one.")
    return matches[0]


def submit_prompt(server: str, workflow: dict, client_id: str) -> str:
    resp = requests.post(f"{server}/prompt", json={"prompt": workflow, "client_id": client_id})
    resp.raise_for_status()
    return resp.json()["prompt_id"]


def wait_for_result(server: str, prompt_id: str, poll_interval: float = 2.0, timeout: float = 7200):
    start = time.time()
    while True:
        if time.time() - start > timeout:
            raise TimeoutError(f"Timed out waiting for prompt {prompt_id}")
        resp = requests.get(f"{server}/history/{prompt_id}")
        resp.raise_for_status()
        history = resp.json()
        if prompt_id in history:
            entry = history[prompt_id]
            status = entry.get("status", {})
            if status.get("completed") is True or status.get("status_str") == "success":
                return entry
            if status.get("status_str") == "error":
                raise RuntimeError(f"Prompt {prompt_id} failed: {status}")
        time.sleep(poll_interval)

def use_clusters(path):
    clusters = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        os.mkdir("batch_queue")
    except FileExistsError:
        print("batch_queue dir already present")

    for id, node in clusters.items():
        if not(id == "noise"):
            target = f"batch_queue/{id}.png"
            shutil.copy(node[0], target)
            print(target)
    abspath = os.path.abspath("batch_queue")
    print(abspath)
    return [Path(abspath)]

def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--frame-dirs-file", help="Text file, one frame-folder path per line")
    group.add_argument("--frames-root", help="Parent dir containing one subfolder of frames per video")
    group.add_argument("--clusters", help="Use the specified clusters JSON")
    ap.add_argument("--workflow", required=True, help="Exported API-format workflow JSON")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--image-batch-node", default=None,
                     help="Node id of the Image Batch Path node, if autodetect picks wrong one")
    ap.add_argument("--image-dir-key", default="image_dir")
    ap.add_argument("--batch-size", type=int, default=0, help="Passed to Image Batch Path (0 = all images)")
    args = ap.parse_args()

    if args.frame_dirs_file:
        frame_dirs = [Path(l.strip()) for l in Path(args.frame_dirs_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    elif args.clusters:
        frame_dirs = use_clusters(args.clusters)
    else:
        root = Path(args.frames_root)
        frame_dirs = sorted(p for p in root.iterdir() if p.is_dir())

    if not frame_dirs:
        raise SystemExit("No frame directories found.")
    missing = [d for d in frame_dirs if not d.exists()]
    if missing:
        raise SystemExit(f"These frame directories don't exist: {missing}")

    workflow_template = json.loads(Path(args.workflow).read_text(encoding="utf-8"))
    batch_node_id = find_node_by_hint(workflow_template, IMAGE_BATCH_PATH_HINTS, args.image_batch_node)

    if args.image_dir_key not in workflow_template[batch_node_id]["inputs"]:
        available = list(workflow_template[batch_node_id]["inputs"].keys())
        raise SystemExit(
            f"Node {batch_node_id} has no '{args.image_dir_key}' input (available: {available}). "
            f"Pass --image-dir-key with the right one."
        )

    client_id = str(uuid.uuid4())

    print(f"Captioning {len(frame_dirs)} frame folders via {args.server} ...")
    for i, frame_dir in enumerate(frame_dirs):
        workflow = json.loads(json.dumps(workflow_template))  # deep copy
        workflow[batch_node_id]["inputs"][args.image_dir_key] = str(frame_dir.resolve())
        if "batch_size" in workflow[batch_node_id]["inputs"]:
            workflow[batch_node_id]["inputs"]["batch_size"] = args.batch_size

        prompt_id = submit_prompt(args.server, workflow, client_id)
        print(f"[{i+1}/{len(frame_dirs)}] submitted (prompt_id={prompt_id}): {frame_dir}")

        wait_for_result(args.server, prompt_id)

        n_frames = len(list(frame_dir.glob("*.txt")))
        print(f"    -> done, {n_frames} caption file(s) now in {frame_dir}")

    print("\nAll videos captioned.")


if __name__ == "__main__":
    main()

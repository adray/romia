#!/usr/bin/env python3
"""
Batch-generate VibeVoice speech for every line in a text file by driving a
running ComfyUI instance through its HTTP API.

Usage:
    ./.venv/bin/python batch_tts.py \
        --lines lines.txt \
        --workflow workflow_api.json \
        --server http://127.0.0.1:8188 \
        --prefix voiceline

Requirements:
    pip install requests   # (into the SAME venv ComfyUI runs from)

How it works:
    1. Loads your exported API-format workflow JSON.
    2. Finds the VibeVoiceSingleSpeakerNode and SaveAudio node in it.
    3. For each non-empty line in --lines, sets the text input, gives
       SaveAudio a unique filename_prefix, submits the prompt, and polls
       /history until it's done.
    4. Keeps the model loaded between lines (free_memory_after_generate=False)
       and frees it after the last line.
    5. Writes a manifest.json mapping line index -> text -> output filename.

This does NOT require importing any ComfyUI internals directly - it only
talks to the already-running server over HTTP, so there's nothing to stub
out and no risk of drifting from however your install is actually configured.
"""

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import requests


def find_node_by_class(workflow: dict, class_type: str) -> str:
    """Return the node id (key) whose class_type matches, or raise."""
    matches = [nid for nid, node in workflow.items() if node.get("class_type") == class_type]
    if not matches:
        raise SystemExit(f"No node with class_type='{class_type}' found in workflow JSON.")
    if len(matches) > 1:
        print(f"Warning: multiple '{class_type}' nodes found ({matches}); using the first one.")
    return matches[0]


def slugify(text: str, max_len: int = 40) -> str:
    keep = [c if c.isalnum() else "_" for c in text.strip()]
    slug = "".join(keep).strip("_")
    slug = "_".join(filter(None, slug.split("_")))  # collapse repeats
    return (slug[:max_len] or "line").lower()


def submit_prompt(server: str, workflow: dict, client_id: str) -> str:
    resp = requests.post(f"{server}/prompt", json={"prompt": workflow, "client_id": client_id})
    resp.raise_for_status()
    return resp.json()["prompt_id"]


def wait_for_result(server: str, prompt_id: str, poll_interval: float = 1.0, timeout: float = 1800):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", required=True, help="Text file, one line per voice line")
    ap.add_argument("--workflow", required=True, help="Exported API-format workflow JSON")
    ap.add_argument("--server", default="http://127.0.0.1:8188")
    ap.add_argument("--prefix", default="voiceline", help="Filename prefix for outputs")
    ap.add_argument("--single-speaker-node", default=None,
                     help="Node id of the VibeVoiceSingleSpeakerNode, if autodetect picks wrong one")
    ap.add_argument("--save-audio-node", default=None,
                     help="Node id of the SaveAudio node, if autodetect picks wrong one")
    ap.add_argument("--text-input-key", default="text",
                     help="Input key on the speaker node that holds the text")
    args = ap.parse_args()

    lines = [l.strip() for l in Path(args.lines).read_text(encoding="utf-8").splitlines()]
    lines = [l for l in lines if l]
    if not lines:
        raise SystemExit("No non-empty lines found in --lines file.")

    workflow_template = json.loads(Path(args.workflow).read_text(encoding="utf-8"))

    speaker_node_id = args.single_speaker_node or find_node_by_class(
        workflow_template, "VibeVoiceSingleSpeakerNode"
    )
    save_node_id = args.save_audio_node or find_node_by_class(workflow_template, "SaveAudio")

    client_id = str(uuid.uuid4())
    manifest = []

    print(f"Generating {len(lines)} lines via {args.server} ...")
    for i, line in enumerate(lines):
        workflow = json.loads(json.dumps(workflow_template))  # deep copy

        # Set the text for this line
        workflow[speaker_node_id]["inputs"][args.text_input_key] = line

        # Keep the model resident between calls to avoid reloading it every line;
        # free it after the last line.
        if "free_memory_after_generate" in workflow[speaker_node_id]["inputs"]:
            workflow[speaker_node_id]["inputs"]["free_memory_after_generate"] = (i == len(lines) - 1)

        # Give this line's output file a predictable, unique name
        file_slug = f"{args.prefix}_{i:04d}_{slugify(line)}"
        workflow[save_node_id]["inputs"]["filename_prefix"] = file_slug

        prompt_id = submit_prompt(args.server, workflow, client_id)
        print(f"[{i+1}/{len(lines)}] submitted (prompt_id={prompt_id}): {line[:60]!r}")

        entry = wait_for_result(args.server, prompt_id)

        # Pull the actual saved filename(s) out of the history response
        outputs = entry.get("outputs", {}).get(save_node_id, {})
        saved_files = []
        for audio_info in outputs.get("audio", []):
            saved_files.append(audio_info.get("filename"))

        manifest.append({
            "index": i,
            "text": line,
            "prompt_id": prompt_id,
            "files": saved_files,
        })
        print(f"    -> saved: {saved_files}")

    manifest_path = Path(f"{args.prefix}_manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone. Wrote manifest: {manifest_path}")


if __name__ == "__main__":
    main()

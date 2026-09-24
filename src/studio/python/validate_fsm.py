#!/usr/bin/env python3
"""
Validate an FSM json (see src/video/roServer.cpp load_custom_fsm() /
romia_custom_fsm.json) against a hashes.json produced by video_phash.py,
to check that clip-to-clip transitions will look visually smooth (i.e. the
last frame of one clip perceptually matches the first frame of the next).

Checks performed:
  1. Every clip referenced by the FSM exists in hashes.json and has both a
     first and last frame pHash.
  2. Within each path, consecutive clips connect smoothly: clip[i]'s last
     frame vs clip[i+1]'s first frame, Hamming distance <= --threshold.
  3. Looping paths (state.loop == true) connect back to their own first
     clip: last clip's last frame vs first clip's first frame.
  4. Cross-state transitions: each path's final clip's last frame is
     compared against the first frame of every path in each target state
     listed in "transition", and the best (closest) match must be within
     the threshold.

Requires: imagehash
    pip install imagehash --break-system-packages

Usage:
    python validate_fsm.py romia_custom_fsm.json hashes.json
    python validate_fsm.py romia_custom_fsm.json hashes.json --threshold 8 -o report.json
"""

import argparse
import json
import sys
from pathlib import Path

import imagehash


def load_json(path):
    with open(path) as f:
        return json.load(f)


def hash_or_none(hex_str):
    if not hex_str:
        return None
    return imagehash.hex_to_hash(hex_str)


def get_clip_hashes(hashes, clip):
    """Return (first_hash, last_hash, error) for a clip name."""
    entry = hashes.get(clip)
    if entry is None:
        return None, None, "clip not found in hashes.json"
    first_hex = entry.get("first_frame_phash")
    last_hex = entry.get("last_frame_phash")
    if not first_hex or not last_hex:
        return None, None, "missing first/last hash in hashes.json"
    return hash_or_none(first_hex), hash_or_none(last_hex), None


def check_pair(hash_a, hash_b, threshold):
    """Return (distance, ok) between two hashes."""
    distance = int(hash_a - hash_b)
    return distance, distance <= threshold


def validate_fsm(fsm_data, hashes, threshold):
    issues = []
    checks = []

    for fsm in fsm_data.get("fsms", []):
        fsm_name = fsm.get("name", "<unnamed>")
        state_by_id = {state["id"]: state for state in fsm.get("states", [])}

        for state in fsm.get("states", []):
            state_id = state["id"]
            state_name = state.get("name", f"state{state_id}")
            loop = state.get("loop", False)

            for path_idx, path in enumerate(state.get("paths", [])):
                clips = path.get("clips", [])
                label = f"{fsm_name}/{state_name}(id={state_id})/path{path_idx}"

                if not clips:
                    issues.append(f"{label}: path has no clips")
                    continue

                # Resolve hashes for every clip in the path, noting missing ones
                clip_hashes = []
                missing = False
                for clip in clips:
                    first_h, last_h, err = get_clip_hashes(hashes, clip)
                    if err:
                        issues.append(f"{label}: clip '{clip}' - {err}")
                        missing = True
                    clip_hashes.append((clip, first_h, last_h))

                # 1. Internal chain checks (clip[i] last frame -> clip[i+1] first frame)
                for i in range(len(clip_hashes) - 1):
                    clip_a, _, last_a = clip_hashes[i]
                    clip_b, first_b, _ = clip_hashes[i + 1]
                    if last_a is None or first_b is None:
                        continue
                    distance, ok = check_pair(last_a, first_b, threshold)
                    checks.append({
                        "type": "chain",
                        "path": label,
                        "from_clip": clip_a,
                        "to_clip": clip_b,
                        "distance": distance,
                        "ok": ok,
                    })
                    if not ok:
                        issues.append(
                            f"{label}: '{clip_a}' -> '{clip_b}' distance {distance} "
                            f"> threshold {threshold}"
                        )

                # 2. Loop-back check (last clip's last frame -> first clip's first frame)
                if loop and not missing:
                    first_clip, first_first_h, _ = clip_hashes[0]
                    last_clip, _, last_last_h = clip_hashes[-1]
                    if first_first_h is not None and last_last_h is not None:
                        distance, ok = check_pair(last_last_h, first_first_h, threshold)
                        checks.append({
                            "type": "loop",
                            "path": label,
                            "from_clip": last_clip,
                            "to_clip": first_clip,
                            "distance": distance,
                            "ok": ok,
                        })
                        if not ok:
                            issues.append(
                                f"{label}: loop '{last_clip}' -> '{first_clip}' distance "
                                f"{distance} > threshold {threshold}"
                            )

                # 3. Cross-state transition checks
                if not missing:
                    last_clip, _, last_last_h = clip_hashes[-1]
                    if last_last_h is not None:
                        for target_id in path.get("transition", []):
                            target_state = state_by_id.get(target_id)
                            if target_state is None:
                                issues.append(
                                    f"{label}: transition target state id {target_id} "
                                    f"does not exist"
                                )
                                continue
                            target_paths = target_state.get("paths", [])
                            if not target_paths:
                                issues.append(
                                    f"{label}: target state "
                                    f"'{target_state.get('name')}' (id={target_id}) "
                                    f"has no paths"
                                )
                                continue

                            best_distance = None
                            best_target_clip = None
                            for t_path in target_paths:
                                t_clips = t_path.get("clips", [])
                                if not t_clips:
                                    continue
                                t_first_clip = t_clips[0]
                                t_first_h, _, t_err = get_clip_hashes(hashes, t_first_clip)
                                if t_err or t_first_h is None:
                                    continue
                                distance = int(last_last_h - t_first_h)
                                if best_distance is None or distance < best_distance:
                                    best_distance = distance
                                    best_target_clip = t_first_clip

                            target_label = f"{target_state.get('name')}(id={target_id})"
                            if best_distance is None:
                                issues.append(
                                    f"{label}: no usable target clip hashes found in "
                                    f"target state {target_label}"
                                )
                                continue

                            ok = best_distance <= threshold
                            checks.append({
                                "type": "transition",
                                "path": label,
                                "from_clip": last_clip,
                                "to_state": target_label,
                                "best_target_clip": best_target_clip,
                                "distance": best_distance,
                                "ok": ok,
                            })
                            if not ok:
                                issues.append(
                                    f"{label}: transition to {target_label} best match "
                                    f"'{best_target_clip}' distance {best_distance} "
                                    f"> threshold {threshold}"
                                )

    return checks, issues


def main():
    ap = argparse.ArgumentParser(
        description="Validate FSM clip transitions against pHash data."
    )
    ap.add_argument("fsm", type=Path, help="Path to the FSM JSON (e.g. romia_custom_fsm.json)")
    ap.add_argument("hashes", type=Path, help="Path to the hashes JSON produced by video_phash.py")
    ap.add_argument("--threshold", type=int, default=6,
                     help="Max Hamming distance for a transition to count as smooth (default: 6)")
    ap.add_argument("-o", "--output", type=Path, default=None,
                     help="Optional path to write a detailed JSON report")
    args = ap.parse_args()

    fsm_data = load_json(args.fsm)
    hashes = load_json(args.hashes)

    checks, issues = validate_fsm(fsm_data, hashes, args.threshold)

    total = len(checks)
    failed = [c for c in checks if not c["ok"]]

    print(f"Checked {total} transition(s) at threshold={args.threshold}")
    print(f"  OK:     {total - len(failed)}")
    print(f"  Failed: {len(failed)}")

    if issues:
        print(f"\n{len(issues)} issue(s) found:\n")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nNo issues found. All transitions look smooth.")

    if args.output:
        report = {
            "threshold": args.threshold,
            "summary": {
                "total_checks": total,
                "failed_checks": len(failed),
                "issue_count": len(issues),
            },
            "checks": checks,
            "issues": issues,
        }
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote detailed report to {args.output}")

    sys.exit(1 if issues else 0)


if __name__ == "__main__":
    main()

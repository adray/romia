"""
Run the pose landmarker in the frames.

Usage:
    python pose_landmarker.py --root-dir ~/.AI/Frames
"""

import argparse
import json
import os
import glob
from pathlib import Path

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

def find_images(dir):
    # Load images
    images = []
    sourcePath = f"{dir}/**/*.png"
    for path in glob.glob(sourcePath):
        images = images + [path]
    return images

def transform_landmarker(result):
    data = {}
    landmarks = []
    for landmark in result.pose_landmarks:
        for sub_landmark in landmark:
            landmarks = landmarks + [{
                "x": sub_landmark.x,
                "y": sub_landmark.y,
                "z": sub_landmark.z,
                "visibility": sub_landmark.visibility,
                "presence": sub_landmark.presence
                }]
    data["pose_landmarks"] = landmarks
    return data

def analyze_poses(images, model):
    # Initialize the pose landmarker
    base_options = python.BaseOptions(model_asset_path=model)
    options = vision.PoseLandmarkerOptions(base_options=base_options)
    with vision.PoseLandmarker.create_from_options(options) as landmarker:
        results = []
        for image_path in images:
            image = mp.Image.create_from_file(image_path)
            detection_result = transform_landmarker(landmarker.detect(image))
            results.append({
                "image": image_path,
                "result": detection_result
            })
        return results

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root-dir", required=True, help="Path to the frames root dir")
    ap.add_argument("-out-json", type=str, default="poses.json", help="Path to write poses.json")
    args = ap.parse_args()

    images = find_images(args.root_dir)
    print(f"Found {len(images)} images")

    model = "./pose_landmarker_heavy.task"
    results = analyze_poses(images, model)

    with open(args.out_json, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()


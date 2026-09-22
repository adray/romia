#!/bin/python3

"""
Analyze the faces in the frames.

Usage:
    python analyze_faces.py --model-dir
    or probing a specific subject using the --probe argument.
    python analyze_faces.py --model-dir <model_dir> --probe <subject_id>
"""

import argparse
import json
import pickle
import os
import sklearn
import numpy as np
from pathlib import Path

def extract_blendshapes(blendshapes):
    result = {}
    for shape in blendshapes:
        result[shape["name"]] = shape["score"]
    return result

def calculate_annoyed(blendshapes):
    eyeSquintLeft = blendshapes["eyeSquintLeft"] if "eyeSquintLeft"   in blendshapes else 0
    eyeSquintRight = blendshapes["eyeSquintRight"] if "eyeSquintRight"   in blendshapes else 0
    browDownLeft   = blendshapes["browDownLeft"] if "browDownLeft"   in blendshapes else 0
    browDownRight    = blendshapes["browDownRight"]  if "browDownRight" in blendshapes else 0
    return eyeSquintLeft > 0.5 and eyeSquintRight > 0.5 and browDownLeft > 0.3 and browDownRight > 0.3

def calculate_squint(blendshapes):
    eyeSquintLeft = blendshapes["eyeSquintLeft"] if "eyeSquintLeft"   in blendshapes else 0
    eyeSquintRight = blendshapes["eyeSquintRight"] if "eyeSquintRight"   in blendshapes else 0
    return eyeSquintLeft > 0.5 and eyeSquintRight > 0.5

def calculate_smile(blendshapes):
    smileLeft   = blendshapes["mouthSmileLeft"] if "mouthSmileLeft"   in blendshapes else 0
    smileRight  = blendshapes["mouthSmileRight"]  if "mouthSmileRight" in blendshapes else 0
    return smileLeft > 0.5 and smileRight > 0.5

def calculate_frown(blendshapes):
    #browDownLeft   = blendshapes["browDownLeft"] if "browDownLeft"   in blendshapes else 0
    #browDownRight    = blendshapes["browDownRight"]  if "browDownRight" in blendshapes else 0
    mouthFrownLeft  = blendshapes["mouthFrownLeft"] if "mouthFrownLeft"   in blendshapes else 0
    mouthFrownRight = blendshapes["mouthFrownRight"]  if "mouthFrownRight" in blendshapes else 0
    return mouthFrownRight > 0.5 and mouthFrownLeft > 0.5

def calculate_mouth_closed(blendshapes):
    mouthClose   = blendshapes["mouthClose"]  if "mouthClose" in blendshapes else 0
    return mouthClose > 0.5    

def calculate_jaw_open(blendshapes):
    jawOpen     = blendshapes["jawOpen"] if "jawOpen"   in blendshapes else 0
    mouthClose  = blendshapes["mouthClose"]  if "mouthClose" in blendshapes else 0
    return jawOpen > 0.5 and mouthClose < 0.5

def calculate_face_undetected(blendshapes):
    return len(list(blendshapes)) == 0

def analyze_faces(faces):
    for face in faces:
        image = face["image"]
        result = face["result"]
        blendshapes = extract_blendshapes(result["face_blendshapes"])
        undetected = calculate_face_undetected(blendshapes)
        smile = calculate_smile(blendshapes)
        frown = calculate_frown(blendshapes)
        jaw_open = calculate_jaw_open(blendshapes)
        mouth_closed = calculate_mouth_closed(blendshapes)
        eye_squint = calculate_squint(blendshapes)
        annoyed = calculate_annoyed(blendshapes)
        print(f"{image} Smile:{smile} Frown:{frown} JawOpen:{jaw_open} Annoyed:{annoyed} MouthClosed:{mouth_closed} Undetected:{undetected}")

def load_model(model_dir, model_filename):
    model_path = os.path.join(model_dir, model_filename)
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    return model

def evaluate_model(clip_average, clip_min, clip_max, model):
    input_data = np.array([clip_average + clip_min + clip_max])
    predictions = model.predict(input_data)
    return predictions

def probe_face(faces, probe, model_dir):
    model = load_model(model_dir, "face_model.pkl")
    num_features = 52
    num_images = 5
    clip_average = [0] * num_features
    clip_min = [1] * num_features
    clip_max = [0] * num_features
    for face in faces:
        image = face["image"]
        result = face["result"]
        image_dir = Path(image).parent.name
        if image_dir == probe:
            blendshapes = result["face_blendshapes"]
            for blendshape in blendshapes:
                index = blendshape.get("index")
                value = blendshape.get("score")
                clip_average[index] = clip_average[index] / num_images
                clip_min[index] = min(clip_min[index], value)
                clip_max[index] = max(clip_max[index], value)
    for key in range(num_features):
        clip_average[key] = clip_average[key] / num_images

    predictions = evaluate_model(clip_average, clip_min, clip_max, model)
    print(f"Face Predictions: {predictions}")

def probe_pose(poses, probe, model_dir):
    model = load_model(model_dir, "pose_model.pkl")
    num_features = 33
    num_images = 5
    clip_average = [0] * num_features
    clip_min = [1] * num_features
    clip_max = [0] * num_features
    for pose in poses:
        image = pose["image"]
        result = pose["result"]
        image_dir = Path(image).parent.name
        if image_dir == probe:
            keypoints = result["pose_landmarks"]
            for landmark in keypoints:
                x = landmark.get("x")
                y = landmark.get("y")
                z = landmark.get("z")
                visibility = landmark.get("visibility")
                presence = landmark.get("presence")
                value = [x, y, z, visibility, presence]
                for i, v in enumerate(value):
                    clip_average[i] = clip_average[i] + v / num_images
                    clip_min[i] = min(clip_min[i], v)
                    clip_max[i] = max(clip_max[i], v)
    for key in range(num_features):
        clip_average[key] = clip_average[key] / num_images

    predictions = evaluate_model(clip_average, clip_min, clip_max, model)
    print(f"Pose Predictions: {predictions}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=str, help="Path to the model directory containing the .keras file")
    ap.add_argument("--probe", type=str, help="Optional video to probe")
    ap.add_argument("-out-json", type=str, default="states.json", help="Path to write states.json")
    args = ap.parse_args()

    faces = []
    with open(os.path.join(args.model_dir, "faces.json"), "r") as f:
        faces = json.load(f)
    poses = []
    with open(os.path.join(args.model_dir, "poses.json"), "r") as f:
        poses = json.load(f)
    if args.probe is None:
        analyze_faces(faces)
    else:
        probe_face(faces, args.probe, args.model_dir)
        probe_pose(poses, args.probe, args.model_dir)

if __name__ == "__main__":
    main()



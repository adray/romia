"""
Run the face landmarker in the frames.

Usage:
    python face_landmarker.py --root-dir ~/.AI/Frames
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
    blendshapes = []
    for face in result.face_landmarks:
        for landmark in face: 
            landmarks = landmarks + [{"x": landmark.x, "y": landmark.y, "z": landmark.z}]
    for shapes in result.face_blendshapes:
        for shape in shapes:
            blendshapes = blendshapes + [{
                "index": shape.index,
                "score": shape.score,
                "name": shape.category_name
                }]
    data["face_landmarks"] = landmarks;
    data["face_blendshapes"] = blendshapes;
    return data;

def analyze_faces(images, model):
    BaseOptions = mp.tasks.BaseOptions
    FaceLandmarker = mp.tasks.vision.FaceLandmarker
    FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    results = []

    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model),
        running_mode=VisionRunningMode.IMAGE,
        output_face_blendshapes=True)

    with FaceLandmarker.create_from_options(options) as landmarker:
        for image in images:
            # Load the input image from an image file.
            mp_image = mp.Image.create_from_file(image)

            # Perform face landmarking on the provided single image.
            # The face landmarker must be created with the image mode.
            face_landmarker_result = transform_landmarker(landmarker.detect(mp_image))
            results = results + [{"result": face_landmarker_result, "image": image}]
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root-dir", required=True, help="Path to the frames root dir")
    ap.add_argument("-out-json", type=str, default="faces.json", help="Path to write faces.json")
    args = ap.parse_args()

    images = find_images(args.root_dir)
    print(f"Found {len(images)} images")

    model = "./face_landmarker.task"
    results = analyze_faces(images, model)

    with open(args.out_json, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()


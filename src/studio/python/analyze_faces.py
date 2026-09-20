#!/bin/python3

"""
Analyze the faces in the frames.

Usage:
    python analyze_faces.py --file faces.json
"""

import argparse
import json

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

def probe_face(faces, probe):
    for face in faces:
        image = face["image"]
        result = face["result"]
        if image == probe:
            blendshapes = extract_blendshapes(result["face_blendshapes"])
            for key, value in blendshapes.items():
                print(f"{key}: {value}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", type=str, default="faces.json", help="Path to the faces.json")
    ap.add_argument("--probe", type=str, help="Optional video path to probe")
    ap.add_argument("-out-json", type=str, default="states.json", help="Path to write states.json")
    args = ap.parse_args()

    faces = []
    with open(args.file, "r") as f:
        faces = json.load(f)
    if args.probe is None:
        analyze_faces(faces)
    else:
        probe_face(faces, args.probe)

if __name__ == "__main__":
    main()



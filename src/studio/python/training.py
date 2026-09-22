"""
Training script for the model.
Builds and trains a models for faces and poses using a gradient boosting approach.

The training_metadata.json contains each video clip and its classification.
Using each frame in the video clips calculate the:
-Average
-Variance
-Min/Max
-First derivative (frame to frame delta) mean/variance
This collapses the video clips into one fixed-size feature vector per clip.
This data is fed into the gradient boosting models for training.

Usage:
    python training.py --model-dir <model_dir>
"""

import argparse
import json
import os
import glob
import pickle
from pathlib import Path

import sklearn
from sklearn.ensemble import GradientBoostingClassifier

def train_face_model(faces, metadata):
    clip_averages, clip_mins, clip_maxs = calculate_face_features(faces)
    clip_emotion = extract_clip_emotion(metadata)
    print("Training face model...")
    X = [clip_averages[clip] + clip_mins[clip] + clip_maxs[clip] for clip in clip_emotion]
    y = [clip_emotion[clip] for clip in clip_emotion]
    model = GradientBoostingClassifier()
    model.fit(X, y)
    print("Training accuracy:", model.score(X, y))
    return model

def train_pose_model(poses, metadata):
    clip_averages, clip_mins, clip_maxs = calculate_pose_features(poses)
    clip_action = extract_clip_action(metadata)
    print("Training pose model...")
    X = [clip_averages[clip] + clip_mins[clip] + clip_maxs[clip] for clip in clip_action]
    y = [clip_action[clip] for clip in clip_action]
    model = GradientBoostingClassifier()
    model.fit(X, y)
    print("Training accuracy:", model.score(X, y))
    return model

def load_json(metadata_json):
    with open(metadata_json, "r") as f:
        metadata = json.load(f)
    return metadata

def extract_clip_emotion(metadata):
    clip_emotion = {}
    for name, clip in metadata.items():
        name_without_ext = Path(name).stem
        emotion = clip.get("emotion")
        clip_emotion[name_without_ext] = emotion
    return clip_emotion

def extract_clip_action(metadata):
    clip_action = {}
    for name, clip in metadata.items():
        name_without_ext = Path(name).stem
        action = clip.get("action")
        clip_action[name_without_ext] = action
    return clip_action

def calculate_face_features(faces):

    clip_averages = {}
    clip_mins = {}
    clip_maxs = {}

    num_blendshapes = 52

    # Calculate clip-level statistics for each blendshape type
    for face in faces:
        result = face.get("result")
        face_blendshapes = result.get("face_blendshapes")
        image = face.get("image")
        # Get the name of the video clip
        video_dir = Path(image).parent.name
        for blendshape in face_blendshapes:
            index = blendshape.get("index")
            score = blendshape.get("score")
            if video_dir not in clip_averages:
                clip_averages[video_dir] = [0] * num_blendshapes
                clip_mins[video_dir] = [1] * num_blendshapes
                clip_maxs[video_dir] = [0] * num_blendshapes
            clip_averages[video_dir][index] = (clip_averages[video_dir][index]) + score/num_blendshapes
            clip_mins[video_dir][index] = min(clip_mins[video_dir][index], score)
            clip_maxs[video_dir][index] = max(clip_maxs[video_dir][index], score)

    return clip_averages, clip_mins, clip_maxs

def calculate_pose_features(poses):

    clip_averages = {}
    clip_mins = {}
    clip_maxs = {}

    num_features = 33

    for pose in poses:
        result = pose.get("result")
        pose_landmarks = result.get("pose_landmarks")
        image = pose.get("image")
        video_dir = Path(image).parent.name
        for landmark in pose_landmarks:
            x = landmark.get("x")
            y = landmark.get("y")
            z = landmark.get("z")
            visibility = landmark.get("visibility")
            presence = landmark.get("presence")
            value = [x, y, z, visibility, presence]
            if video_dir not in clip_averages:
                clip_averages[video_dir] = [0] * num_features
                clip_mins[video_dir] = [1] * num_features
                clip_maxs[video_dir] = [0] * num_features
            for i, score in enumerate(value):
                clip_averages[video_dir][i] = (clip_averages[video_dir][i]) + score/num_features
                clip_mins[video_dir][i] = min(clip_mins[video_dir][i], score)
                clip_maxs[video_dir][i] = max(clip_maxs[video_dir][i], score)

    return clip_averages, clip_mins, clip_maxs

def test_face_model(face_model, test_metadata, faces): 
    clip_averages, clip_mins, clip_maxs = calculate_face_features(faces)
    clip_emotion = extract_clip_emotion(test_metadata)
    X_test = [clip_averages[clip] + clip_mins[clip] + clip_maxs[clip] for clip in clip_emotion]
    y_test = [clip_emotion[clip] for clip in clip_emotion]
    print("Face Test accuracy:", face_model.score(X_test, y_test))

def test_pose_model(pose_model, test_metadata, poses):
    clip_averages, clip_mins, clip_maxs = calculate_pose_features(poses)
    clip_action = extract_clip_action(test_metadata)
    X_test = [clip_averages[clip] + clip_mins[clip] + clip_maxs[clip] for clip in clip_action]
    y_test = [clip_action[clip] for clip in clip_action]
    print("Pose Test accuracy:", pose_model.score(X_test, y_test))

def save_model(model, model_path):
    with open(model_path, "wb") as f:
        pickle.dump(model, f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", help="Path to the directory where the trained models will be saved")
    args = ap.parse_args()

    model_dir = args.model_dir
    if model_dir is None:
        print("Model directory not specified.")
        return

    training_metadata_json = os.path.join(model_dir, "training_metadata.json")
    test_metadata_json = os.path.join(model_dir, "test_metadata.json")
    faces_json = os.path.join(model_dir, "faces.json")
    poses_json = os.path.join(model_dir, "poses.json")

    metadata = load_json(training_metadata_json)
    test_metadata = load_json(test_metadata_json)
    faces = load_json(faces_json)
    poses = load_json(poses_json)

    print(f"Loaded {len(faces)} faces and {len(poses)} poses")


    face_model = train_face_model(faces, metadata)
    pose_model = train_pose_model(poses, metadata)

    print("Training completed.")
    test_face_model(face_model, test_metadata, faces)
    test_pose_model(pose_model, test_metadata, poses)

    save_model(face_model, os.path.join(model_dir, "face_model.pkl"))
    save_model(pose_model, os.path.join(model_dir, "pose_model.pkl"))

if __name__ == "__main__":
    main()


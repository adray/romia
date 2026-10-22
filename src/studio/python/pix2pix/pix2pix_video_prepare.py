
"""
Prepare the pix2pix video dataset.

1) Take video data from metadata
2) Generate two directories:
   a) Training data
   b) Testing data
3) Using media pipe extract the each frames face mesh data and render it to a file within the training or testing data

"""

import argparse
from pathlib import Path
import shutil
import json
import random
import os
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.vision import drawing_utils
from mediapipe.tasks.python.vision import drawing_styles


def render_output(face, pose, width, height, output_path):
    #image = mp.Image.create_from_file(face["image"])
    image = blank_image = np.zeros((height,width,3), np.uint8)
    annotated_image = image.copy()

    face_landmarks = []
    # Render the face landmarks to the output path
    for landmarks in face["result"].face_landmarks:
        for landmark in landmarks:
            face_landmarks.append(landmark)

    drawing_utils.draw_landmarks(
        image=annotated_image,
        landmark_list=face_landmarks,
        connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION,
        landmark_drawing_spec=None,
        connection_drawing_spec=drawing_styles.get_default_face_mesh_tesselation_style())
    drawing_utils.draw_landmarks(
        image=annotated_image,
        landmark_list=face_landmarks,
        connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_CONTOURS,
        landmark_drawing_spec=None,
        connection_drawing_spec=drawing_styles.get_default_face_mesh_contours_style())
    drawing_utils.draw_landmarks(
        image=annotated_image,
        landmark_list=face_landmarks,
        connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_LEFT_IRIS,
        landmark_drawing_spec=None,
        connection_drawing_spec=drawing_styles.get_default_face_mesh_iris_connections_style())
    drawing_utils.draw_landmarks(
        image=annotated_image,
        landmark_list=face_landmarks,
        connections=vision.FaceLandmarksConnections.FACE_LANDMARKS_RIGHT_IRIS,
        landmark_drawing_spec=None,
        connection_drawing_spec=drawing_styles.get_default_face_mesh_iris_connections_style())
    
    pose_landmarks = []
    for landmarks in pose["result"].pose_landmarks:
        for landmark in landmarks:
            pose_landmarks.append(landmark)

    pose_landmark_style = drawing_styles.get_default_pose_landmarks_style()
    pose_connection_style = drawing_utils.DrawingSpec(color=(0, 255, 0), thickness=2)
    drawing_utils.draw_landmarks(
        image=annotated_image,
        landmark_list=pose_landmarks,
        connections=vision.PoseLandmarksConnections.POSE_LANDMARKS,
        landmark_drawing_spec=pose_landmark_style,
        connection_drawing_spec=pose_connection_style)

    image_path = face["image"]
    image_filename = os.path.basename(image_path)
    parent_dir_name = os.path.basename(os.path.dirname(image_path))
    os.makedirs(os.path.join(output_path, parent_dir_name), exist_ok=True)
    output_file = os.path.join(output_path, parent_dir_name, image_filename.replace(".png", "_data.png"))
    cv2.imwrite(output_file, cv2.cvtColor(annotated_image, cv2.COLOR_RGB2BGR))
    #Copy the original image to the output directory as well
    original_output_file = os.path.join(output_path, parent_dir_name, image_filename)
    shutil.copy(image_path, original_output_file)
    #print(f"Processed image: {image_path} -> {output_file}")

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
            face_landmarker_result = landmarker.detect(mp_image)
            results = results + [{"result": face_landmarker_result, "image": image}]
    return results

def analyze_poses(images, model):
    BaseOptions = mp.tasks.BaseOptions
    PoseLandmarker = mp.tasks.vision.PoseLandmarker
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    results = []

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model),
        running_mode=VisionRunningMode.IMAGE)

    with PoseLandmarker.create_from_options(options) as landmarker:
        for image in images:
            mp_image = mp.Image.create_from_file(image)
            pose_landmarker_result = landmarker.detect(mp_image)
            results = results + [{"result": pose_landmarker_result, "image": image}]
    return results

def load_metadata(metadata_path):
    with open(metadata_path, 'r') as f:
        metadata = json.load(f)
    return metadata

def get_frame_path(video_path, frame_index):
    period = 625
    source_time = frame_index * (period/10000.0)
    source_frame_path = os.path.join(video_path, f"frame_{frame_index+1:06d}_t{source_time:01.3f}s.png")
    return source_frame_path

def extract_frames(video, fps, info):
    duration = info.get('duration', 5062.5)
    num_frames = int(duration * fps / 1000)-1
    frames = []
    for frame_index in range(num_frames):
        frame_path = get_frame_path(video, frame_index)
        frames.append(frame_path)
    return frames

def main():
    fps = 16  # Assuming a default frames per second value for video processing

    parser = argparse.ArgumentParser()
    parser.add_argument('--metadata_path', type=str, required=True, help='Path to the metadata file')
    parser.add_argument('--clip_dir', type=str, required=True, help='Directory containing video clips')
    parser.add_argument('--output_dir', type=str, required=True, help='Path to the output directory for prepared dataset')
    parser.add_argument("--dry-run", action="store_true", help="If set, the script will not write any output files")
    args = parser.parse_args()

    PATH = Path(args.clip_dir)
    WIDTH = 640
    HEIGHT = 640

    #Prepare output directory
    training_output_dir = os.path.join(args.output_dir, "train")
    testing_output_dir = os.path.join(args.output_dir, "test")
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(training_output_dir, exist_ok=True)
    os.makedirs(testing_output_dir, exist_ok=True)

    videos = []
    metadata = load_metadata(args.metadata_path)
    for video, info in metadata.items():
        # Strip mp4 extension from video filename
        video = PATH / video.replace('.mp4', '')
        videos.append(video)
    # Shuffle the videos to ensure random distribution between training and testing sets
    random.shuffle(videos)

    training = []
    testing = []
    # Distribute videos frames into training and testing sets based on the shuffled order
    for i, video in enumerate(videos):
        frames = extract_frames(video, fps, metadata[video.name + '.mp4'])
        if i % 10 == 0:
            testing.extend(frames)
        else:
            training.extend(frames)
    
    if args.dry_run:
        print("Dry run enabled. No output files will be written.")
        print("Num Training frames:", len(training))
        print("Num Testing frames:", len(testing))
        print("Output directory:", args.output_dir)
        return

    face_model = "../face_landmarker.task"
    pose_model = "../pose_landmarker_heavy.task"
    print("Analyzing training frames...")
    training_results = zip(analyze_faces(training, face_model), analyze_poses(training, pose_model))
    print("Rendering training frames...")
    for face_result, pose_result in training_results:
        render_output(face_result, pose_result, WIDTH, HEIGHT, training_output_dir)
    print("Analyzing testing frames...")
    testing_results = zip(analyze_faces(testing, face_model), analyze_poses(testing, pose_model))
    print("Rendering testing frames...")
    for face_result, pose_result in testing_results:
        render_output(face_result, pose_result, WIDTH, HEIGHT, testing_output_dir)
    print("Processing complete.")

if __name__ == "__main__":
    main()

    
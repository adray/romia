# Pre-processing

cd python
python -m venv .venv
./.venv/bin/python ./.venv/bin/pip install -r requirements.txt

## Video Generation

./batch_video.py --image <image> ../models/romia --workflow ../config/bulk_image_to_video.json
./batch_video.py --start-video ~/.AI/Desktop/Romia/Video-Wan-2.2/Wan2.2_i2v_00571_.mp4 --end-video ~/.AI/Desktop/Romia/Video-Wan-2.2/Wan2.2_i2v_00571_.mp4 --workflow ../config/single_thread_videos.json ../models/romia/

## Extracting frames

python ./extract_frames.py ~/.AI/Desktop/Romia/Video-Wan-2.2 1 ~/.AI/Frames

## Video analysis (pHash, Analyze transtions, Generate embedding)
## The embedding step will download the OpenAI clip model (https://huggingface.co/openai/clip-vit-large-patch14)

./.venv/bin/python video_phash.py ~/.AI/Desktop/Romia/Video-Wan-2.2/ -o ../models/romia/hashes.json
./.venv/bin/python embeddings.py ~/.AI/Frames -o ../models/romia/embeddings.npy
./.venv/bin/python analyze_transitions.py ../models/romia/hashes.json --threshold 3 -o ../models/romia/output.json

# Generate FSM groups (Finite State Machine)

./.venv/bin/python ./fsm_groups.py ../models/romia/embeddings.npy ../models/romia/output.json -root-dir ~/.AI/Frames -out-json ../models/romia/fsm_approvals.json

# Google Face and Pose landmarker (needs sudo for some reason)
https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task

sudo ./.venv/bin/python ./face_landmarker.py --root-dir ~/.AI/Frames/ -out-json ../models/romia/faces.json
sudo ./.venv/bin/python ./pose_landmarker.py --root-dir ~/.AI/Frames/ -out-json ../models/romia/poses.json
./.venv/bin/python ./analyze_landmarks.py --model-dir ../models/romia/

# FSM gen
python ./generate_fsm.py ../models/romia --clip_analysis output.json

# Remux
# Transform the videos into the right format to be streamed.

./remux.py ~/.AI/Desktop/Romia/Video-Wan-2.2/

# Train the classification models

./.venv/bin/python training.py --model-dir ../models/romia

===============
OTHER SCRIPTS
===============

# Cluster embeddings: Adjust the k for the number of results. The sweet spot is just below when it starts to produce similar images.
./.venv/bin/python cluster_embeddings.py embeddings.npy clusters.json --method kmeans --k 15

# Batch captions
# This may get cached by comfyui in which case restart the comfyui to rerun the script

python ./batch_frame_captions.py --clusters clusters.json --workflow clip_vision_batch_clothing.json

# Build approvals

./build_approvals.py --frames-root ./batch_queue --out approvals.json

# Negative
"negative": "low quality, blurry, low resolution, low lighting, low detail, low contrast, deformed, distorted, poorly rendered, jewellery, watches, expensive accessories",
    


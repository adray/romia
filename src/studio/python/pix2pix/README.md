# Dev
Generate dataset:
sudo ../.venv/bin/python ./pix2pix_video_prepare.py --metadata_path ../../models/romia/metadata.json --clip_dir ~/.AI/Frames/ --output_dir ~/.AI/romia/prod

Process dataset for dev:
python ./pix2pix_video_postprocess.py --dir ~/.AI/romia/dev --scale 0.5


Training:
../.venv/bin/python ./pix2pix_video.py --dev train --dataset_path ~/.AI/romia/dev/

Inference:
../.venv/bin/python ./pix2pix_video.py --dev inference --dataset_path ~/.AI/romia/dev/

Export:
../.venv/bin/python ./pix2pix_video.py --dev export --export-path ./export
../.venv/bin/python -m tf2onnx.convert --saved-model export --output generator.onnx --opset 17

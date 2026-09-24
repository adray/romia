#!/usr/bin/env python3
import sys
import copy
import sys
import os
import json
import argparse
import requests
import time
import uuid
from pathlib import Path

'''
Batch video processing script

Usage;
    python batch_video.py ../models/romia --image <image> --workflow ../config/video.json
    python batch_video.py ../models/romia --start-video <video> --end-video <video> --workflow ../config/video.json
'''

def load_video_config(config_path):
    if not os.path.exists(config_path):
        print(f"Video config '{config_path}' does not exist.")
        return None
    with open(config_path, 'r') as f:
        return json.load(f)

def load_workflow(workflow_path):
    if not os.path.exists(workflow_path):
        print(f"Workflow config '{workflow_path}' does not exist.")
        return None
    with open(workflow_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def build_prompt(base_prompt, clips):
    # Replace {n} placeholders in the base prompt with clip-specific values
    prompt = base_prompt
    for value in range(len(clips)):
        prompt = prompt.replace(f"{{{value}}}", str(clips[value]))
    return prompt

def generate_jobs(base_prompt, clips):
    jobs = []
    for clip in clips:
        prompt = build_prompt(base_prompt, clip["prompt_parameters"])
        jobs.append({
            "prompt": prompt,
            "workflow": clip["workflow"],
            "category": clip["category"],
            "action": clip["action"],
            "emotion": clip["emotion"],
            "speaking": clip.get("speaking", False),
            "state": "pending",
            "client_id": str(uuid.uuid4()),
        })
    return jobs

def save_jobs(jobs, jobs_path):
    root = {}
    root["jobs"] = jobs
    output_directory = os.path.dirname(jobs_path)
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    with open(jobs_path, 'w', encoding='utf-8') as f:
        json.dump(root, f, indent=4)
    print(f"Jobs saved to '{jobs_path}'")

def load_jobs(jobs_path):
    if not os.path.exists(jobs_path):
        print(f"Jobs file '{jobs_path}' does not exist.")
        return None
    with open(jobs_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        return data.get("jobs", [])

def process_job(server, job, workflows, input_image, start_video, end_video):
    workflow_name = job.get("workflow").get("type")
    workflow_item = workflows.get(workflow_name)
    if workflow_item is None:
        print(f"Workflow '{workflow_name}' not found for job: {job['prompt']}")
        job["state"] = "error"
        return
    workflow = patch_workflow(
        job,
        copy.deepcopy(workflow_item),
        Path(input_image).name if input_image else None,
        Path(start_video).name if start_video else None,
        Path(end_video).name if end_video else None)
    if workflow is None:
        job["state"] = "error"
        return
    #Debug: save the patched workflow to a file
    #with open("debug_workflow.json", "w", encoding='utf-8') as f:
    #    json.dump(workflow, f, indent=4)
    id = submit_prompt(server, workflow, job.get("client_id"))
    entry = wait_for_result(server, id)
    job["state"] = "done"
    if "outputs" in entry:
        images = []
        for node_id in entry["outputs"]:
            if "images" in entry["outputs"][node_id]:
                items = entry["outputs"][node_id]["images"]
                for image in items:
                    images.append(image["filename"])
        job["output"] = images

def patch_node(workflow, id, nodeClass, inputName, value):
    success = False
    node = workflow.get(id)
    #print(f"Patching node '{id}' with input '{inputName}' and value '{value}'")
    if node is not None:
        #print(f"Found node '{id}' with class_type '{node.get('class_type')}'")
        class_type = node.get("class_type")
        if class_type == nodeClass:
            if "inputs" not in node:
                node["inputs"] = {}
            node["inputs"][inputName] = value
            success = True
    return success

def patch_workflow(job, workflow_item, input_image, start_video, end_video):
    job_params = job.get("workflow").get("parameters", {})
    prompt = job.get("prompt")
    workflow = workflow_item.get("workflow")
    for job_param in job_params:
        for parameter in workflow_item.get("parameters", []):
            parameterName = parameter.get("parameter")
            success = False
            if parameterName == "prompt":
                success = patch_node(workflow, parameter.get("id"), parameter.get("name"), parameter.get("input"), prompt)
            elif parameterName == job_param:
                value = job_params[job_param]
                if value == "base_image":
                    value = input_image
                elif value == "start_video":
                    value = start_video
                elif value == "end_video":
                    value = end_video
                success = patch_node(workflow, parameter.get("id"), parameter.get("name"), parameter.get("input"), value)
            else:
                continue
            if not success:
                print(f"Failed to patch parameter '{parameterName}' for job: {job['prompt']}")
                return None
    return workflow

def submit_prompt(server: str, workflow: dict, client_id: str) -> str:
    resp = requests.post(f"{server}/prompt", json={"prompt": workflow, "client_id": client_id})
    if not resp.ok:
        try:
            print("Server error response:", json.dumps(resp.json(), indent=2, ensure_ascii=False))
        except ValueError:
            print("Server error response (non-JSON):", resp.text)
    resp.raise_for_status()
    return resp.json()["prompt_id"]

def wait_for_result(server: str, prompt_id: str, poll_interval: float = 2.0, timeout: float = 7200):
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

def upload_file(server: str, file_path: str) -> str:
    with open(file_path, "rb") as f:
        body = {"image": f}
        resp = requests.post(f"{server}/upload/image", files=body, data={"overwrite": "true"})
    if not resp.ok:
        try:
            print("Server error response:", json.dumps(resp.json(), indent=2, ensure_ascii=False))
        except ValueError:
            print("Server error response (non-JSON):", resp.text)
    resp.raise_for_status()
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to upload file: {resp.text}")
    return resp.json()["name"]

def load_clip_metadata(file_path: str) -> dict:
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r") as f:
        return json.load(f)

def save_clip_metadata(metadata: dict, file_path: str):
    with open(file_path, "w") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

def main():

    ap = argparse.ArgumentParser()
    ap.add_argument("output_directory", help="Path to the output directory")
    ap.add_argument("--image", help="Path to the input image or video")
    ap.add_argument("--start-video", help="Path to the start video")
    ap.add_argument("--end-video", help="Path to the end video")
    ap.add_argument("--resume", action="store_true", help="Resume from existing jobs")
    ap.add_argument("--server", default="http://127.0.0.1:8188", help="URL of the server")
    ap.add_argument("--workflow", help="Path to the workflow JSON file")
    args = ap.parse_args()

    input_image = args.image
    start_video = args.start_video
    end_video = args.end_video
    output_directory = args.output_directory
    resume = args.resume

    if not os.path.exists(output_directory):
        print(f"Output directory '{output_directory}' does not exist.")
        return

    video_config = load_video_config(args.workflow)
    if video_config is None:
        return

    workflow_files = {
        "image_start_end_workflow": "../workflows/wan-image-start-end-to-video.json",
        "image_to_video_workflow": "../workflows/video_wan2_2_14B_i2v.json"
    }

    workflow_data = {}

    for key, path in workflow_files.items():
        workflow_data[key] = load_workflow(path)

    workflows = {}
    workflows["firstLastFrameToVideo"] = {
        "workflow": workflow_data["image_start_end_workflow"],
        "parameters": [
            {
                "name": "LoadImage",
                "id": "149",
                "input": "image",
                "parameter": "frame"
            },
            {
                "name": "CLIPTextEncode",
                "id": "7",
                "input": "text",
                "parameter": "prompt"
            },
            {
                "name": "LoadVideo",
                "id": "145",
                "input": "file",
                "parameter": "startVideo"
            },
            {
                "name": "LoadVideo",
                "id": "138",
                "input": "file",
                "parameter": "endVideo"
            },
            {
                "name": "PrimitiveBoolean",
                "id": "150",
                "input": "value",
                "parameter": "use_image"
            }
        ],
    }
    workflows["imageToVideo"] = {
        "workflow": workflow_data["image_to_video_workflow"],
        "parameters": [
            {
                "name": "LoadImage",
                "id": "97",
                "input": "image",
                "parameter": "frame"
            },
            {
                "name": "CLIPTextEncode",
                "id": "129:93",
                "input": "text",
                "parameter": "prompt"
            },
        ],
    }
    
    metadata_path = os.path.join(output_directory, "metadata.json")
    metadata = load_clip_metadata(metadata_path)

    jobs = []
    jobs_dir = os.path.join(output_directory, "jobs.json")
    if resume:
        jobs = load_jobs(jobs_dir)
    else:
        if os.path.exists(jobs_dir):
            # Check if any jobs are still pending
            jobs = load_jobs(jobs_dir)
            pending_jobs = [job for job in jobs if job.get("state", "pending") == "pending"]
            if pending_jobs:
                print(f"Error: there are still pending jobs in {jobs_dir}. Use --resume to continue.")
                return
        base_prompt = video_config.get("base_prompt", "")
        clips = video_config.get("clips", [])
        jobs = generate_jobs(base_prompt, clips)
        save_jobs(jobs, jobs_dir)

    if not jobs:
        print("No jobs to process.")
        return

    server = args.server
    if start_video and  os.path.exists(start_video):
        upload_file(server, start_video)
    if end_video and os.path.exists(end_video):
        upload_file(server, end_video)
    if input_image and os.path.exists(input_image):
        upload_file(server, input_image)

    num_jobs = len(jobs)
    for i, job in enumerate(jobs, start=1):
        state = job.get("state", "pending")
        if state == "pending":
            print(f"Processing job {i}/{num_jobs} {job['prompt']}")
            process_job(server, job, workflows, input_image, start_video, end_video)
            if "output" in job:
                for video in job["output"]:
                    metadata[video] = {
                        "prompt": job["prompt"],
                        "category": job.get("category", ""),
                        "emotion": job.get("emotion", ""),
                        "speaking": job.get("speaking", False),
                        "action": job.get("action", ""),
                    }
            save_jobs(jobs, jobs_dir)
            save_clip_metadata(metadata, metadata_path)

if __name__ == "__main__":
    main()


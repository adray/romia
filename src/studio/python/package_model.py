#!/usr/bin/env python3

import os
import json

'''
Package a model for distribution.

Usage:
    python package_model.py <model_directory>
'''

def load_json(model_directory, file_name):
    manifest_path = os.path.join(model_directory, file_name)
    if not os.path.isfile(manifest_path):
        print(f"Error: Manifest file not found in {model_directory}")
        return

    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    return manifest

def copy_clips(metadata, src_clip_dir, dest_clip_dir):
    import shutil
    if os.path.exists(dest_clip_dir):
        shutil.rmtree(dest_clip_dir)
    # Check if all clips in metadata exist in the destination directory
    for clip_file, _ in iter(metadata.items()):
        clip_file = clip_file.replace(".mp4", "frag.mp4")
        # Copy the clip file from the source to the destination directory if it exists
        if not os.path.exists(os.path.join(src_clip_dir, clip_file)):
            return f"Error: Referenced clip file missing in source clip directory: {clip_file}"
        os.makedirs(dest_clip_dir, exist_ok=True)
        shutil.copy2(os.path.join(src_clip_dir, clip_file), os.path.join(dest_clip_dir, clip_file))
        if not os.path.exists(os.path.join(dest_clip_dir, clip_file)):
            return f"Error: Referenced clip file missing in clip directory: {clip_file}"
    return None

def package_model(model_directory):
    # Load manifest file
    manifest = load_json(model_directory, "manifest.json")
    if manifest is None:
        return "Unable to load manifest"
    # Create the package directory if it doesn't exist
    package_dir = os.path.join(model_directory, "package")
    if not os.path.exists(package_dir):
        os.makedirs(package_dir)

    clipDir = manifest.get("clipDir")
    if clipDir is None:
        return "clipDir not specified in manifest"

    # Copy the clip directory to the package directory
    import shutil
    src_clip_dir = None
    # Check absolute path
    if os.path.isabs(clipDir):
        src_clip_dir = clipDir
    else:
        src_clip_dir = os.path.join(model_directory, clipDir)
    if not os.path.exists(src_clip_dir):
        return f"Error: clipDir {src_clip_dir} does not exist"
    dest_clip_dir = os.path.join(package_dir, "clip")
    if os.path.exists(dest_clip_dir):
        shutil.rmtree(dest_clip_dir)
    error = copy_clips(load_json(model_directory, "metadata.json"), src_clip_dir, dest_clip_dir)
    if error:
        return error
    #Update the manifest to point to the new clip directory location
    new_manifest = {}
    new_manifest["name"] = manifest.get("name")
    new_manifest["clipDir"] = "clip"
    new_manifest["fsm"] = manifest.get("fsm")
    new_manifest["metadata"] = manifest.get("metadata")
    if "thumbnail" in manifest:
        new_manifest["thumbnail"] = manifest.get("thumbnail")
    manifest_path = os.path.join(package_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(new_manifest, f, indent=4)
    # Copy any additional files specified in the manifest
    fsm_file = manifest.get("fsm")
    metadata_file = manifest.get("metadata")
    thumbnail_file = manifest.get("thumbnail")
    files = [fsm_file, metadata_file, thumbnail_file]
    for file in files:
        if file is None:
            continue
        src_file = os.path.join(model_directory, file)
        if not os.path.exists(src_file):
            return f"Error: {file} {src_file} does not exist"
        dest_file = os.path.join(package_dir, os.path.basename(file))
        shutil.copy2(src_file, dest_file)
    # Compress the package directory into a zip file
    import zipfile
    package_zip_path = os.path.join(model_directory, "package.zip")
    with zipfile.ZipFile(package_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(package_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, package_dir)
                zipf.write(file_path, arcname)
    # Remove the temporary package directory
    shutil.rmtree(package_dir)

    return package_zip_path

def main():
    if len(os.sys.argv) != 2:
        print("Usage: python package_model.py <model_directory>")
        return

    model_directory = os.sys.argv[1]
    if not os.path.isdir(model_directory):
        print(f"Error: {model_directory} is not a valid directory")
        return

    # Implement the packaging logic here
    print(f"Packaging model from directory: {model_directory}")
    result = package_model(model_directory)
    if result is not None:
        print(result)

if __name__ == "__main__":
    main()

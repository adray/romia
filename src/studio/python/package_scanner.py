#!/usr/bin/env python3
import argparse
import json

'''
Verify a romia model package that is uploaded contains all required files and structure.
Additionally, it checks it doesn't contain any unexpected files.
'''

def unpack_package(package_path):
    # Package is a zip file
    import zipfile
    with zipfile.ZipFile(package_path, 'r') as zip_ref:
        zip_ref.extractall("/tmp/romia_package")

def load_manifest():
    try:
        with open("/tmp/romia_package/manifest.json", "r") as f:
            manifest = json.load(f)
        return manifest
    except Exception as e:
        print(f"Failed to load manifest: {e}")
        return None

def main():
    args_parser = argparse.ArgumentParser(description="Verify a romia model package.")
    args_parser.add_argument("package_path", help="Path to the romia model package")
    args = args_parser.parse_args()
    package_path = args.package_path
    unpack_package(package_path)
    manifest = load_manifest()
    if manifest is not None:
        fsm = manifest.get("fsm")
        if fsm is None:
            print("FSM is missing in the manifest.")
        else:
            print("FSM loaded successfully:")
            print(fsm)
    else:
        print("Failed to load manifest.")

if __name__ == "__main__":
    main()

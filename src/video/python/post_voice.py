#!/usr/bin/env python3

'''
Post voice script from a text-to-speech manifest
Usage: post_voice.py <manifest_file>
'''

import sys
import json
import os
import requests

def post_event(event):
    url = "http://localhost:7777/api/event"
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=json.dumps(event))
    return response.json()

def upload_audio(audio_file):
    success = False
    uploaded_name = None
    with open(audio_file, 'rb') as f:
        response = requests.post('http://localhost:7777/api/speak', data=f)
        if response.status_code == 200:
            print("Upload successful")
            print("Response:", response.text)
            success = True
            uploaded_name = response.json().get('audio')
        else:
            print("Upload failed")
            print("Response:", response.text)
    return success, uploaded_name

def main():
    if len(sys.argv) != 2:
        print("Usage: post_voice.py <manifest_file>")
        sys.exit(1)

    manifest_file = sys.argv[1]
    manifest_dir = os.path.dirname(os.path.abspath(manifest_file))
    print(f"Processing manifest file: {manifest_file}")
    
    #Load the JSON manifest
    with open(manifest_file, 'r') as f:
        manifest = json.load(f)
    #Upload each audio file listed in the manifest
    files = []
    for entry in manifest:
        for file in entry.get('files', []):
            file_path = os.path.join(manifest_dir, file)
            success, uploaded_name = upload_audio(file_path)
            if not success:
                print(f"Failed to upload audio file: {file_path}")
                break
            else:
                files.append(uploaded_name)
    #Post an event for each entry
    for entry in files:
        event = {"data": entry, "type": "audio", "state": "speaking", "interrupt": False}
        post_event(event)

if __name__ == "__main__":
    main()

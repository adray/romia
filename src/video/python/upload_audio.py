#!/usr/bin/env python3

'''
Uploads an audio file to the server

Usage:
    python upload_audio.py <audio_file>

'''

import sys
import requests

if len(sys.argv) != 2:
    print("Usage: python upload_audio.py <audio_file>")
    sys.exit(1)

audio_file = sys.argv[1]
with open(audio_file, 'rb') as f:
    response = requests.post('http://localhost:7777/api/speak', data=f)
    if response.status_code == 200:
        print("Upload successful")
        print("Response:", response.text)
    else:
        print("Upload failed")
        print("Response:", response.text)

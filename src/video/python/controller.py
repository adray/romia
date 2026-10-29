#!/usr/bin/env python3

'''  
Controller for the AI avatar.

This script runs in a loop, using the romia endpoints to control the AI avatar's actions and states.

Usage:
    python3 controller.py <manifest.json>
Optional:
    --advanced    Enable advanced features of the controller
'''

import sys
import requests
import json
import os

# Controller parameters
ROMIA_ENDPOINT = "http://localhost:7777/api/"  # Example endpoint for the romia server
TTS_ENDPOINT = "http://localhost:7777/api/tts"  # Example endpoint for the TTS server
LLM_ENDPOINT = "http://localhost:7777/api/llm"  # Example endpoint for the LLM server
FSM_CUT_TIME = 100  # Time in seconds to cut FSM transitions
EVENT_TIME = 30  # Time in seconds to trigger events
AUDIO_TIME = 60  # Time in seconds to trigger audio events
STAGE_TIME = 20 # Time in seconds to trigger stage transitions

# Controller state
controller_state = {
    "current_fsm": 0,  # The currently active FSM
    "current_state": 0,  # The currently active state within the FSM
}

def post_event(event):
    url = ROMIA_ENDPOINT + "event"
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=json.dumps(event))
    return response.json()

def controller_choose_event(fsm, state_filter=None):
    # Collect all possible events from the FSM's states
    # Remove the initial state's events from the list of possible events
    initial_state = fsm["initial_state"]
    state_list = [state for state in fsm["states"] if state["id"] != initial_state]
    if state_filter is not None:
        state_list = [state for state in state_list if state["name"] in state_filter]
    # Select and random state
    import random
    if not state_list:
        return None
    selected_state = random.choice(state_list)
    # build the event data
    event = {
        "type": "update",
        "data": "",
        "interrupt": False,
        "state": selected_state["name"]
    }
    return event

def controller_choose_fsm(fsms, filter=None):
    mapping = {fsm["name"]: i for i, fsm in enumerate(fsms)}
    if filter is not None:
        fsms = [fsm for fsm in fsms if fsm["name"] in filter]
    if not fsms:
        return None
    import random
    selected_fsm = random.choice(fsms)
    return mapping[selected_fsm["name"]]

def controller_send_fsm(fsm_id):
    event = {
        "type": "fsm",
        "data": str(fsm_id)
    }
    post_event(event)


def controller_choose_dialogue(stage_data, dialogue_index):
    dialogues = stage_data["dialogues"]
    dialogue_strategy = stage_data["dialogue_strategy"]
    if not dialogues:
        return None, dialogue_index
    if dialogue_strategy == "sequential":
        dialogue = dialogues[dialogue_index % len(dialogues)]
        dialogue_index += 1
        return dialogue, dialogue_index
    elif dialogue_strategy == "random":
        import random
        dialogue = random.choice(dialogues)
        dialogue_index += 1
        return dialogue, dialogue_index
    else:
        return None, dialogue_index

def controller_choose_audio(audio_manifest, dialogue_text):
    if not audio_manifest:
        return None
    # Lookup audio file corresponding to the dialogue text
    audio_file = audio_manifest.get(dialogue_text, None)
    audio_name = upload_audio(audio_file)["audio"]
    return {"type": "audio", "data": audio_name, "state": "speaking"}

def load_stage(script, script_stage_index):
    stage = script.get("stages")[script_stage_index]
    states = stage.get("states", [])
    fsm = stage.get("fsm", None)
    dialogues = stage.get("dialogues", [])
    dialogue_strategy = stage.get("dialogue_strategy", "sequential")

    transition = stage.get("transition", {})
    transition_type = transition.get("type", None)
    transition_count = transition.get("count", None)

    return {
        "stage": stage,
        "states": states,
        "fsm": fsm,
        "dialogues": dialogues,
        "dialogue_strategy": dialogue_strategy,
        "transition": transition,
        "transition_type": transition_type,
        "transition_count": transition_count
    }

def upload_audio(audio):
    url = ROMIA_ENDPOINT + "speak"
    with open(audio, 'rb') as f:
        response = requests.post(url, data=f)
    return response.json()

def parse_audio_manifest(audio_manifest_file):
    if audio_manifest_file is not None:
        with open(audio_manifest_file, "r") as f:
            data = json.load(f)
            manifest_dir = os.path.dirname(audio_manifest_file)
            audio_manifest = {}
            for item in data:
                dialogue_text = item.get("text")
                audio_file = item.get("files")[0]
                if dialogue_text and audio_file:
                    audio_manifest[dialogue_text] = os.path.join(manifest_dir, audio_file)
            print("Parsed audio manifest - items:", len(audio_manifest))
    else:
        audio_manifest = None
        print("Audio manifest file not found.")
    return audio_manifest

def advanced_controller_loop(fsms, script):
    import time
    start_time = time.time()
    event_start_time = time.time()
    audio_start_time = time.time()
    transition_timer = None

    options = script.get("options", {})
    FSM_CUT_TIME = options.get("fsm_cut_time", 100)  # Default to 100 seconds if not specified
    EVENT_TIME = options.get("event_time", 30)  # Default to 30 seconds if not specified
    AUDIO_TIME = options.get("audio_time", 60)  # Default to 60 seconds if not specified
    STAGE_TIME = options.get("stage_time", 20)  # Default to 20 seconds if not specified
    
    audio_manifest_file = options.get("audio_manifest", None)
    audio_manifest = parse_audio_manifest(audio_manifest_file)

    # Load the initial stage
    script_stage_index = 0
    dialogue_index = 0
    dialogue_count = 0
    stage_data = load_stage(script, script_stage_index)
    initial_fsm_id = controller_choose_fsm(fsms, stage_data.get("fsm", None))
    if initial_fsm_id is not None:
        print("Initial FSM selected:", initial_fsm_id)
        controller_state["current_fsm"] = initial_fsm_id
        controller_send_fsm(initial_fsm_id)

    while True:
        fsm = fsms[controller_state["current_fsm"]]
        elapsed_time = time.time() - start_time
        if elapsed_time >= FSM_CUT_TIME:
            start_time = time.time()
            # Implement FSM transition logic here
            new_fsm_id = controller_choose_fsm(fsms, stage_data.get("fsm", None))
            if new_fsm_id is not None:
                print("Switching to new FSM:", new_fsm_id)
                controller_state["current_fsm"] = new_fsm_id
                controller_send_fsm(new_fsm_id)
        event_elapsed_time = time.time() - event_start_time
        if event_elapsed_time >= EVENT_TIME and transition_timer is None:
            event_start_time = time.time()
            # Implement event triggering logic here
            event = controller_choose_event(fsm, stage_data["states"])
            if event is not None:
                print("Triggering event:", event)
                post_event(event)
        audio_elapsed_time = time.time() - audio_start_time
        if audio_elapsed_time >= AUDIO_TIME and transition_timer is None:
            audio_start_time = time.time()
            text, dialogue_index = controller_choose_dialogue(stage_data, dialogue_index)
            post_event({"type": "subtitle", "data": text, "state": "speaking"})
            if audio_manifest is not None:
                audio = controller_choose_audio(audio_manifest, text)
                if audio is not None:
                    print("Triggering audio:", audio)
                    post_event(audio)
        if stage_data["transition_type"] == "auto" and dialogue_index == len(stage_data["dialogues"]) and transition_timer is None:
            transition_timer = time.time() + STAGE_TIME
        elif stage_data["transition_type"] == "dialogue" and dialogue_index == stage_data["transition_count"] and transition_timer is None:
            transition_timer = time.time() + STAGE_TIME
        if transition_timer is not None:
            if time.time() >= transition_timer:
                transition_timer = None
                # Increment stage index and load the next stage
                script_stage_index += 1
                dialogue_index = 0
                dialogue_count = 0
                if script_stage_index < len(script.get("stages", [])):
                    stage_data = load_stage(script, script_stage_index)
                else:
                    print("Reached the end of the script stages.")
                    break
        time.sleep(1)  # Sleep for a short duration to prevent busy-waiting

def controller_loop(fsms):
    import time
    start_time = time.time()
    event_start_time = time.time()
    while True:
        fsm = fsms[controller_state["current_fsm"]]
        elapsed_time = time.time() - start_time
        if elapsed_time >= FSM_CUT_TIME:
            start_time = time.time()
            # Implement FSM transition logic here
            new_fsm_id = controller_choose_fsm(fsms)
            if new_fsm_id is not None:
                print("Switching to new FSM:", new_fsm_id)
                controller_state["current_fsm"] = new_fsm_id
                controller_send_fsm(new_fsm_id)
        event_elapsed_time = time.time() - event_start_time
        if event_elapsed_time >= EVENT_TIME:
            event_start_time = time.time()
            # Implement event triggering logic here
            event = controller_choose_event(fsm)
            if event is not None:
                print("Triggering event:", event)
                post_event(event)
        time.sleep(1)  # Sleep for a short duration to prevent busy-waiting

def load_json(file_path):
    with open(file_path, "r") as f:
        return json.load(f)

def parse_model(model):
    # Extract fsms
    fsms = model.get("fsms", [])
    return fsms

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 controller.py <manifest.json>")
        sys.exit(1)

    manifest_file = sys.argv[1]
    manifest_dir = os.path.dirname(manifest_file)
    manifest = load_json(manifest_file)

    model_file =  os.path.join(manifest_dir, manifest.get("fsm", ""))
    model = load_json(model_file)
    print("Model loaded successfully")
    fsms = parse_model(model)

    advanced = "--advanced" in sys.argv
    if advanced:
        script_file = os.path.join(manifest_dir, manifest.get("script", ""))
        if script_file:
            script = load_json(script_file)
            print("Script loaded successfully")
            advanced_controller_loop(fsms, script)
            return

    controller_loop(fsms)

if __name__ == "__main__":
    main()

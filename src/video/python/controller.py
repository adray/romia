#!/usr/bin/env python3

'''  
Controller for the AI avatar.

This script runs in a loop, using the romia endpoints to control the AI avatar's actions and states.

Usage:
    python3 controller.py <model.json>
'''

import sys
import requests
import json

# Controller parameters
ROMIA_ENDPOINT = "http://localhost:7777/api/"  # Example endpoint for the romia server
TTS_ENDPOINT = "http://localhost:7777/api/tts"  # Example endpoint for the TTS server
LLM_ENDPOINT = "http://localhost:7777/api/llm"  # Example endpoint for the LLM server
FSM_CUT_TIME = 100  # Time in seconds to cut FSM transitions
EVENT_TIME = 30  # Time in seconds to trigger events

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

def controller_choose_event(fsm):
    # Collect all possible events from the FSM's states
    # Remove the initial state's events from the list of possible events
    initial_state = fsm["initial_state"]
    state_list = [state for state in fsm["states"] if state["id"] != initial_state]
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

def controller_choose_fsm(fsms):
    import random
    if not fsms:
        return None
    selected_fsm = random.choice(range(len(fsms)))
    return selected_fsm

def controller_send_fsm(fsm_id):
    event = {
        "type": "fsm",
        "data": str(fsm_id)
    }
    post_event(event)

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

def load_model(file_path):
    with open(file_path, "r") as f:
        return json.load(f)

def parse_model(model):
    # Extract fsms
    fsms = model.get("fsms", [])
    return fsms

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 controller.py <model.json>")
        sys.exit(1)

    model_file = sys.argv[1]
    model = load_model(model_file)
    print("Model loaded successfully")
    fsms = parse_model(model)
    controller_loop(fsms)

if __name__ == "__main__":
    main()

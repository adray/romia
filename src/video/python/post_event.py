#!/usr/bin/env python3

'''
Post an event to the local Romia server.

Usage:
    python post_event.py <type> --data <data> --interrupt --state <state>

'''

import requests
import json
import argparse

def post_event(event):
    url = "http://localhost:7777/api/event"
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=json.dumps(event))
    return response.json()

def main():    
    argsParser = argparse.ArgumentParser()
    argsParser.add_argument("type", help="Type of the event")
    argsParser.add_argument("--data", help="Data associated with the event")
    argsParser.add_argument("--interrupt", action="store_true", help="Whether the event is interrupting")
    argsParser.add_argument("--state", default="idle", help="State associated with the event")
    args = argsParser.parse_args()

    type = args.type
    data = args.data
    interrupt = args.interrupt
    state = args.state

    event = {
        "type": type,
        "data": data,
        "interrupt": interrupt,
        "state": state
    }
    response = post_event(event)
    print(response)

if __name__ == "__main__":
    main()

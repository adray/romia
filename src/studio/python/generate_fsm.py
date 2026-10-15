#!/usr/bin/env python3
"""
Generate a finite state machine (FSM) for the Romia model.

Usage:
    python generate_fsm.py <model_directory> --grouping <fsm_grouping_file> --clip_analysis <clip_analysis_file>

Method:
    1. Load the manifest.json file from the specified model directory.
    2. Load the metadata file specified in the manifest.
    3. Use idle states as the root states for the FSM.
    4. (Optional) Use a fsm grouping file to organize states into groups.
    5. (Optional) Load the clip analysis from the metadata.
    6. Generate the FSM based on the loaded metadata and grouping information.
"""

import os
import json

def load_manifest(model_directory):
    manifest_path = os.path.join(model_directory, "manifest.json")
    if not os.path.isfile(manifest_path):
        print(f"Error: Manifest file not found in {model_directory}")
        return

    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    return manifest

def load_metadata(model_directory, manifest):
    metadata_file = manifest.get("metadata")
    if metadata_file is None:
        print("Error: Metadata file not specified in manifest")
        return

    metadata_path = os.path.join(model_directory, metadata_file)
    if not os.path.isfile(metadata_path):
        print(f"Error: Metadata file {metadata_path} does not exist")
        return

    with open(metadata_path, "r") as f:
        metadata = json.load(f)
    return metadata

def load_fsm_grouping(model_directory, fsm_grouping_file):
    if fsm_grouping_file is None:
        return None

    fsm_grouping_path = os.path.join(model_directory, fsm_grouping_file)
    if not os.path.isfile(fsm_grouping_path):
        print(f"Error: FSM grouping file {fsm_grouping_path} does not exist")
        return None

    with open(fsm_grouping_path, "r") as f:
        fsm_grouping = json.load(f)
    return fsm_grouping

def load_clip_analysis(model_directory, clip_analysis_file):
    if clip_analysis_file is None:
        return None

    clip_analysis_path = os.path.join(model_directory, clip_analysis_file)
    if not os.path.isfile(clip_analysis_path):
        print(f"Error: Clip analysis file {clip_analysis_path} does not exist")
        return None

    with open(clip_analysis_path, "r") as f:
        clip_analysis = json.load(f)
    return clip_analysis

def scan_root_states(metadata):
    if not metadata:
        return []
    root_states = []
    for clip_name, clip in metadata.items():
        category = clip.get("category")
        if category == "idle":
            root_states.append(clip_name)
    return root_states

def deduplicate_root_states(root_states, clip_analysis):
    analysis = clip_analysis.get("_graph_analysis")
    if not analysis:
        return root_states

    groups = {}
    for id, nodes in analysis.get("nodes", {}).items():
        for node in nodes:
            if node.get("position") == "first":
                if id not in groups:
                    groups[id] = []
                groups[id].append(node)

    groups_used = set()
    deduplicated_root_states = []
    for root_state in root_states:
        is_duplicate = False
        for group_id, nodes in groups.items():
            for node in nodes:
                if node.get("video") == root_state:
                    if group_id in groups_used:
                        is_duplicate = True
                        break
                    groups_used.add(group_id)
                    break
            if is_duplicate:
                break
        if not is_duplicate:
            deduplicated_root_states.append(root_state)
    return deduplicated_root_states

def search_graph(clip_analysis, start_node):
    analysis = clip_analysis.get("_graph_analysis")
    if not analysis:
        return []
    # Find where the start_node is located in the graph analysis (nodes with "position" == "last")
    group = None
    for id, nodes in analysis.get("nodes", {}).items():
        for node in nodes:
            if node.get("video") == start_node and node.get("position") == "last":
                group = {"id": id, "nodes": nodes}
                break
        if group is not None:
            break
    return group

def get_fan_out_nodes(clip_analysis, group):
    analysis = clip_analysis.get("_graph_analysis")
    # Search for nodes starting from the given group in the graph analysis
    if group is None:
        return []
    fan_out_nodes = []
    fan_out_nodes = analysis.get("fan_out_groups", {}).get(group["id"], [])
    return fan_out_nodes

def generate_idle_loop(root_state, clip_analysis, fan_out_loops):
    paths = []
    clips = [root_state]
    transitions = []
    for loop in fan_out_loops:
        if loop["name"] == "secondary":
            transitions.append(loop["id"])
    paths.append({
        "clips": clips,
        "transition": transitions
    })
    return {
        "name": "idle",
        "id": 0,
        "loop": True,
        "loop_count": 3,
        "paths": paths
    }

def generate_fan_out_loops(root_state, clip_analysis, metadata):
    initial_group = search_graph(clip_analysis, root_state)
    fan_out_nodes = get_fan_out_nodes(clip_analysis, initial_group)
    paths = []
    for node in fan_out_nodes:
        if node == root_state:
            continue
        clip_metadata = metadata.get(node, {})
        clips = [node]
        next_group = search_graph(clip_analysis, node)
        while next_group is not None and next_group["id"] != initial_group["id"]:
            # Add a "first" node from the next group to the clips
            group = next_group
            next_group = None
            if group["nodes"]:
                for node in group["nodes"]:
                    if node.get("position") != "first":
                        continue
                    clips.append(node.get("video"))
                    next_group = search_graph(clip_analysis, node.get("video"))
                    break

        transitions = [0]
        paths.append((clip_metadata, {
            "clips": clips,
            "transition": transitions
        }))

    # Allocate paths to states by creating a state for each unique category in the fan-out loops
    states = []
    states_by_category = {}
    for clip_metadata, path in paths:
        category = clip_metadata.get("category")
        if category not in states_by_category:
            states_by_category[category] = {
                "name": category,
                "id": len(states_by_category) + 1,
                "loop": False,
                "loop_count": 0,
                "paths": []
            }
        states_by_category[category]["paths"].append(path)

    states = list(states_by_category.values())
    return states

def generate_fsms(metadata, root_states, fsm_grouping, clip_analysis):
    data = {}
    fsms = []
    for root_state in root_states:
        fan_out_loops = generate_fan_out_loops(root_state, clip_analysis, metadata)
        states = [generate_idle_loop(root_state, clip_analysis, fan_out_loops)] + fan_out_loops
        fsms.append({
            "name": "default",
            "initial_state": 0,
            "states": states
        })
    data["fsms"] = fsms
    return data

def main():
    if len(os.sys.argv) < 2:
        print("Usage: python generate_fsm.py <model_directory> [--grouping <fsm_grouping_file>] [--clip_analysis <clip_analysis_file>]")
        return

    model_directory = os.sys.argv[1]
    fsm_grouping_file = None
    clip_analysis_file = None
    if "--grouping" in os.sys.argv:
        grouping_index = os.sys.argv.index("--grouping")
        if grouping_index + 1 < len(os.sys.argv):
            fsm_grouping_file = os.sys.argv[grouping_index + 1]
    if "--clip_analysis" in os.sys.argv:
        clip_analysis_index = os.sys.argv.index("--clip_analysis")
        if clip_analysis_index + 1 < len(os.sys.argv):
            clip_analysis_file = os.sys.argv[clip_analysis_index + 1]
    
    # Load FSM grouping if specified
    fsm_grouping = load_fsm_grouping(model_directory, fsm_grouping_file)
    
    # Load clip analysis if specified
    clip_analysis = load_clip_analysis(model_directory, clip_analysis_file)

    if not os.path.isdir(model_directory):
        print(f"Error: {model_directory} is not a valid directory")
        return

    manifest = load_manifest(model_directory)
    if manifest is None:
        return

    fsm_file = manifest.get("fsm")
    fsm_path = os.path.join(model_directory, fsm_file)
    print(f"Generating FSM for model at {fsm_path}")

    metadata = load_metadata(model_directory, manifest)
    if metadata is None:
        return

    root_states = scan_root_states(metadata)
    root_states = deduplicate_root_states(root_states, clip_analysis)
    print(f"Root states: {root_states}")
    
    fsm = generate_fsms(metadata, root_states, fsm_grouping, clip_analysis)
    with open(fsm_path, "w") as f:
        json.dump(fsm, f, indent=4)
    print(f"FSM saved to {fsm_path}")

if __name__ == "__main__":
    main()

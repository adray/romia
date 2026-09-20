#!/usr/bin/env python3
"""
Analyze the pHash JSON produced by video_phash.py to find how clips connect:

  - Node   = a distinct frame "point" (a cluster of near-identical pHashes)
  - Edge   = a clip, directed from its first-frame node to its last-frame node

A clip whose last frame matches another clip's first frame (within the
Hamming-distance threshold) is treated as "transitions into" that clip, so
chains of edges (Clip A -> Clip B -> Clip C) reveal sequences that were
likely cut from one continuous take, or that could be stitched back together.

Also reports:
  - fan-out nodes: multiple clips that all start from the same frame
  - fan-in nodes: multiple clips that all end on the same frame
  - cycles: chains that loop back to their own starting frame

Requires: imagehash (already installed if you ran video_phash.py)
    pip install imagehash --break-system-packages

Usage:
    python analyze_transitions.py hashes.json
    python analyze_transitions.py hashes.json -o hashes.json --threshold 8
"""

import argparse
import json
import sys
from collections import defaultdict

import imagehash


DATA_KEY_FIRST = "first_frame_phash"
DATA_KEY_LAST = "last_frame_phash"
ANALYSIS_KEY = "_graph_analysis"


class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def load_clips(data):
    """Return list of dicts: {video, first_hash, last_hash} skipping missing hashes."""
    clips = []
    for video, info in data.items():
        if video == ANALYSIS_KEY:
            continue
        first_hex = info.get(DATA_KEY_FIRST)
        last_hex = info.get(DATA_KEY_LAST)
        if not first_hex or not last_hex:
            print(f"  skipping {video}: missing a first/last hash", file=sys.stderr)
            continue
        clips.append({
            "video": video,
            "first_hash": imagehash.hex_to_hash(first_hex),
            "last_hash": imagehash.hex_to_hash(last_hex),
        })
    return clips


def cluster_frames(clips, threshold):
    """
    Cluster every (video, position) frame-hash into nodes using union-find,
    joining any two frames whose Hamming distance <= threshold.
    Returns:
      node_of: dict[(video, position)] -> node_id (small int)
      node_members: dict[node_id] -> list of (video, position)
      node_hash: dict[node_id] -> representative imagehash
    """
    entries = []  # (video, position, hash)
    for c in clips:
        entries.append((c["video"], "first", c["first_hash"]))
        entries.append((c["video"], "last", c["last_hash"]))

    uf = UnionFind(len(entries))
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            if entries[i][2] - entries[j][2] <= threshold:
                uf.union(i, j)

    root_to_node = {}
    node_of = {}
    node_members = defaultdict(list)
    node_hash = {}
    next_id = 0
    for i, (video, pos, h) in enumerate(entries):
        root = uf.find(i)
        if root not in root_to_node:
            root_to_node[root] = next_id
            next_id += 1
        node_id = root_to_node[root]
        node_of[(video, pos)] = node_id
        node_members[node_id].append({"video": video, "position": pos})
        node_hash.setdefault(node_id, str(h))

    return node_of, node_members, node_hash


def build_graph(clips, node_of):
    """edges: list of (video, start_node, end_node). Also adjacency + degrees."""
    edges = []
    out_edges = defaultdict(list)  # node -> list of (video, end_node)
    in_degree = defaultdict(int)
    out_degree = defaultdict(int)

    for c in clips:
        start = node_of[(c["video"], "first")]
        end = node_of[(c["video"], "last")]
        edges.append((c["video"], start, end))
        out_edges[start].append((c["video"], end))
        out_degree[start] += 1
        in_degree[end] += 1

    #for edge in edges:
    #    print(f"{edge}")

    return edges, out_edges, in_degree, out_degree


def find_chains(edges, out_edges, in_degree):
    """
    Enumerate chains (sequences of >=2 clips) by DFS from every node that
    has no incoming edge (a true chain start). Also separately detect pure
    cycles (components where every node has in_degree >= 1).
    """
    all_nodes = set()
    for video, start, end in edges:
        all_nodes.add(start)
        all_nodes.add(end)

    chains = []

    def dfs(node, path_videos, path_nodes, used_videos, used_nodes):
        extended = False
        for video, nxt in out_edges.get(node, []):
            if video in used_videos:
                continue
            if nxt in used_nodes:
                continue;
            extended = True
            dfs(nxt, path_videos + [video], path_nodes + [nxt], used_videos | {video}, used_nodes | {nxt})
        if not extended and len(path_videos) >= 2:
            chains.append(list(path_videos))

    start_nodes = [n for n in all_nodes if in_degree.get(n, 0) == 0]
    for n in start_nodes:
        dfs(n, [], [n], frozenset(), frozenset([n]))

    # Pure cycles: nodes with in_degree >= 1 everywhere in their component
    # (never visited as a start_node above). Walk from any such node until
    # we return to it.
    visited_in_cycle_search = set()
    cycles = []
    covered_nodes = set(start_nodes)
    for video, start, end in edges:
        if start in covered_nodes or start in visited_in_cycle_search:
            continue
        path_videos, path_nodes = [], [start]
        cur = start
        used = set()
        while True:
            candidates = [(v, n) for v, n in out_edges.get(cur, []) if v not in used]
            if not candidates:
                break
            video_c, nxt = candidates[0]
            path_videos.append(video_c)
            used.add(video_c)
            visited_in_cycle_search.add(cur)
            cur = nxt
            path_nodes.append(cur)
            if cur == start:
                cycles.append(path_videos)
                break
            if len(path_videos) > len(out_edges) + 5:
                break  # safety valve

    return chains, cycles


def main():
    parser = argparse.ArgumentParser(
        description="Analyze clip pHashes to find transition chains between clips."
    )
    parser.add_argument("input", type=str, help="Path to the JSON produced by video_phash.py")
    parser.add_argument("-o", "--output", type=str, default="output.json",
                         help="Where to write results")
    parser.add_argument("--threshold", type=int, default=6,
                         help="Max Hamming distance for two frames to count as the same point (default: 6)")
    args = parser.parse_args()

    output_path = args.output

    with open(args.input) as f:
        data = json.load(f)

    clips = load_clips(data)
    if not clips:
        print("No clips with both first and last hashes found.", file=sys.stderr)
        sys.exit(1)
    print("Clips loaded")

    node_of, node_members, node_hash = cluster_frames(clips, args.threshold)
    print("Finished clustering frames")
    edges, out_edges, in_degree, out_degree = build_graph(clips, node_of)
    print("Finished building graph")
    chains, cycles = find_chains(edges, out_edges, in_degree)
    print("Finished finding chains")

    fan_out = {n: [v for v, _ in lst] for n, lst in out_edges.items() if len(lst) > 1}
    fan_in = defaultdict(list)
    for video, start, end in edges:
        fan_in[end].append(video)
    fan_in = {n: vids for n, vids in fan_in.items() if len(vids) > 1}

    # Write results back onto each clip entry + a top-level analysis block
    for c in clips:
        video = c["video"]
        data[video]["first_frame_node"] = node_of[(video, "first")]
        data[video]["last_frame_node"] = node_of[(video, "last")]

    data[ANALYSIS_KEY] = {
        "threshold": args.threshold,
        "nodes": {str(n): members for n, members in node_members.items()},
        "chains": chains,
        "cycles": cycles,
        "fan_out_groups": {str(n): vids for n, vids in fan_out.items()},
        "fan_in_groups": {str(n): vids for n, vids in fan_in.items()},
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    # ---- Summary ----
    print(f"\nAnalyzed {len(clips)} clips -> {len(node_members)} distinct frame nodes\n")

    if chains:
        print(f"Chains found ({len(chains)}):")
        for chain in chains:
            print("  " + " -> ".join(chain))
    else:
        print("No multi-clip chains found.")

    if cycles:
        print(f"\nCycles found ({len(cycles)}):")
        for cyc in cycles:
            print("  " + " -> ".join(cyc) + " -> (loops back)")

    if fan_out:
        print(f"\nShared start points ({len(fan_out)} node(s) with multiple clips starting there):")
        for n, vids in fan_out.items():
            print(f"  node {n}: " + ", ".join(vids))

    if fan_in:
        print(f"\nShared end points ({len(fan_in)} node(s) with multiple clips ending there):")
        for n, vids in fan_in.items():
            print(f"  node {n}: " + ", ".join(vids))

    print(f"\nWrote updated analysis to {output_path}")


if __name__ == "__main__":
    main()


"""
Find suggested groups to merge

Usage:
    python fsm_groups.py embeddings.npy output.json
"""
import argparse
import json
import numpy as np
import os
from pathlib import Path
from sklearn.cluster import AgglomerativeClustering
from sklearn.preprocessing import normalize


def load_embeddings(path, reps):
    data = np.load(path, allow_pickle=True).item()  # dict: {frame_path: vector}
    paths = list(data.keys())
    vectors = np.stack([data[p[0]] for p in reps])
    return paths, vectors


def cluster(vectors):
    # CLIP/DINO embeddings work best compared by cosine similarity,
    # so L2-normalize first and then use Euclidean distance downstream
    # (on unit vectors, Euclidean distance is a monotonic function of cosine similarity).

    model = AgglomerativeClustering(compute_distances=True, n_clusters=1, metric="cosine", linkage="average")
    model = model.fit(vectors)

    return model

def write_json(model, groups, reps, out_path):
    data = {}

    grp = []
    for group, rep in zip(groups.items(), reps):
        path = Path(rep[0])
        grp.append({
            "id": group[0],
            "representative": rep[0],
            "video": path.parent.name,
            "frame": path.name,
            "videos": group[1]
        })
    data["groups"] = grp

    #labels = []
    children = []
    #for lbl in model.labels_:
    #    labels.append(int(lbl))
    for idx, item in enumerate(model.children_):
        children.append({
            "left": int(item[0]),
            "right": int(item[1]),
            "distance": float(model.distances_[idx])
        })

    #data["labels"] = labels
    data["children"] = children

    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Wrote {len(groups)} groups to {out_path}")



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("embeddings", help="Path to embeddings.npy")
    ap.add_argument("graph", help="Path to the hashes file with graph data")
    ap.add_argument("-root-dir", help="Path to the frames root dir")
    ap.add_argument("-out-json", type=str, default="fsm_approvals.json", help="Path to write fsm_approvals.json")
    args = ap.parse_args()

    groups = {}
    reps = []

    root = args.root_dir

    with open(args.graph) as f:
        data = json.load(f)
    for key, value in data["_graph_analysis"]["fan_out_groups"].items():
        groups[key] = value
    for key, val in groups.items():
        rep = Path(val[0]).stem
        dir = f"{root}/{rep}"
        files = list(Path(dir).glob("*.png"))
        if len(files) > 0:
            path = f"{os.path.abspath(dir)}/{files[0].name}"
            reps = reps + [(path, key)]

    paths, vectors = load_embeddings(args.embeddings, reps)
    model = cluster(
        vectors
    )

    write_json(model, groups, reps, args.out_json)


if __name__ == "__main__":
    main()



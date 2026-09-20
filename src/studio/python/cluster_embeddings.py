"""
Cluster frame embeddings and write results to JSON.

Usage:
    python cluster_embeddings.py embeddings.npy clusters.json --method hdbscan
    python cluster_embeddings.py embeddings.npy clusters.json --method kmeans --k 8
"""
import argparse
import json
import numpy as np
from sklearn.cluster import HDBSCAN, KMeans
from sklearn.preprocessing import normalize


def load_embeddings(path):
    data = np.load(path, allow_pickle=True).item()  # dict: {frame_path: vector}
    paths = list(data.keys())
    vectors = np.stack([data[p] for p in paths])
    return paths, vectors


def cluster(vectors, method="hdbscan", k=8, min_cluster_size=5):
    # CLIP/DINO embeddings work best compared by cosine similarity,
    # so L2-normalize first and then use Euclidean distance downstream
    # (on unit vectors, Euclidean distance is a monotonic function of cosine similarity).
    vectors = normalize(vectors)

    if method == "kmeans":
        model = KMeans(n_clusters=k, n_init="auto", random_state=0)
        labels = model.fit_predict(vectors)
    elif method == "hdbscan":
        model = HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")
        labels = model.fit_predict(vectors)  # -1 = noise/outlier, not in any cluster
    else:
        raise ValueError(f"Unknown method: {method}")

    return labels


def write_json(paths, labels, out_path):
    clusters = {}
    for path, label in zip(paths, labels):
        key = "noise" if label == -1 else str(int(label))
        clusters.setdefault(key, []).append(path)

    with open(out_path, "w") as f:
        json.dump(clusters, f, indent=2)

    sizes = {k: len(v) for k, v in clusters.items()}
    print(f"Wrote {len(clusters)} clusters to {out_path}")
    print("Cluster sizes:", sizes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("embeddings", help="Path to embeddings.npy")
    ap.add_argument("out_json", help="Path to write clusters.json")
    ap.add_argument("--method", choices=["kmeans", "hdbscan"], default="hdbscan")
    ap.add_argument("--k", type=int, default=8, help="Number of clusters (kmeans only)")
    ap.add_argument("--min-cluster-size", type=int, default=5, help="hdbscan only")
    args = ap.parse_args()

    paths, vectors = load_embeddings(args.embeddings)
    labels = cluster(
        vectors, method=args.method, k=args.k, min_cluster_size=args.min_cluster_size
    )
    write_json(paths, labels, args.out_json)


if __name__ == "__main__":
    main()

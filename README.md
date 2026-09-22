# Interactive AI Avatar

Tools for authoring and serving an interactive, video-based AI avatar. A
subject is filmed/generated as a large library of short video clips (idle
loops, gestures, reactions, speaking lines, ...). An offline pipeline
analyzes those clips, works out which ones can be chained together, and
groups them into a finite state machine (FSM). At runtime, a lightweight
web server walks that FSM and streams the right clip to the browser,
creating the illusion of one continuous, responsive video avatar.

The project has two halves that share the same C++ server stack:

| Component | Path | Purpose |
|---|---|---|
| **Studio** | `src/studio/` | Authoring tool. Generates/organizes clips into an "avatar model" (a folder of video clips + JSON config), and provides a review UI for approving AI-generated metadata and clip transitions. |
| **Video** | `src/video/` | Playback demo. A minimal local server that serves the finished avatar model and drives the interactive FSM-based video player in the browser. |

## Repository layout

```
src/
├── studio/                 # Authoring app
│   ├── roStudio.cpp/.h     # entry point
│   ├── roServer.cpp/.h     # HTTP server + Sun-script route handlers
│   ├── CMakeLists.txt
│   ├── scripts/            # server-side (Sun script) pages + JS served to the browser
│   ├── python/             # offline preprocessing / ML pipeline (see below)
│   └── models/<name>/      # per-avatar working data (clips, hashes, embeddings, FSM, approvals)
│
├── video/                  # Playback demo app
│   ├── roVideo.cpp/.h      # entry point
│   ├── roServer.cpp/.h     # HTTP server + Sun-script route handlers
│   ├── CMakeLists.txt
│   ├── scripts/            # server-side pages (FSM/show APIs)
│   └── js/                 # browser player (video.js, fsm.js, playback.js, shows.js)
│
├── sun/                    # Embedded "Sun" scripting language + JIT (used for server-side .txt scripts)
├── cpp-httplib-*/          # vendored HTTP library
└── json/                   # vendored nlohmann/json
```

Both `studio` and `video` are separate CMake targets that link against the
same `roServer`/Sun-script plumbing, but each has its own `main()`,
`roServer.h`, and route set (see their individual `CMakeLists.txt`).

## How it fits together

1. **Generate clips** — `src/studio/python/batch_video.py` drives a running
   ComfyUI instance to turn a base image + prompt config into short video
   clips for each pose/emotion/action combination.
2. **Analyze clips** — a chain of Python scripts (pHash first/last frames,
   embeddings, clustering, face/pose landmarking) figures out which clips'
   end frames match other clips' start frames, so they can be chained or
   looped without a visible cut.
3. **Build the FSM** — matching clips are grouped into states and
   transitions (`fsm_groups.py`, plus manual review through the Studio
   web UI) and written out as an avatar model under `src/studio/models/<name>/`.
4. **Serve it** — the `video` server loads that avatar model's FSM and
   clips, and the browser player requests transitions and streams the
   matching clip, giving the appearance of one continuous interactive video.

Full step-by-step preprocessing commands (venv setup, frame extraction,
hashing, embeddings, training, remuxing, etc.) are documented in
[`src/studio/README.md`](src/studio/README.md).

## Building the C++ servers

Requirements:
- CMake 3.8+
- A C++20 compiler
- `ffmpeg` on `PATH` (used by several preprocessing steps and by the video pipeline)

```bash
# Studio (authoring server, default port 7777)
cd src/studio
mkdir build && cd build
cmake ..
cmake --build .
./studio

# Video (playback demo server, default port 7777)
cd src/video
mkdir build && cd build
cmake ..
cmake --build .
./video
```

> Both servers default to port `7777` — run them on different machines/ports
> if you need Studio and Video up at the same time.

## Python preprocessing environment

The ML/analysis pipeline lives in `src/studio/python/` and is independent of
the C++ build:

```bash
cd src/studio/python
python -m venv .venv
./.venv/bin/pip install -r requirements.txt --break-system-packages
```

Key scripts (see `src/studio/README.md` for the full ordered walkthrough):

| Script | Role |
|---|---|
| `batch_video.py` | Batch-generate clips via a ComfyUI workflow |
| `batch_tts.py` | Batch-generate speech lines via a ComfyUI VibeVoice workflow |
| `extract_frames.py` | Pull timestamped frames out of each clip |
| `video_phash.py` | Perceptual-hash each clip's first/last frame |
| `analyze_transitions.py` | Build the clip transition graph from those hashes |
| `embeddings.py` / `cluster_embeddings.py` | CLIP embeddings + clustering of frames |
| `fsm_groups.py` | Suggest FSM state groupings from the transition graph + embeddings |
| `face_landmarker.py` / `analyze_landmarks.py` | MediaPipe face/pose landmarking and heuristics |
| `training.py` | Train gradient-boosting emotion/action classifiers from landmark features |
| `batch_frame_captions.py` / `build_approvals.py` | Caption frames and assemble the human-review approvals file |
| `remux.py` | Fragment clips for streaming playback |

## Status

This is a research/prototype-stage project — expect rough edges in both the
Python pipeline (paths and model URLs are currently hard-coded for one
example avatar, "romia") and the C++ servers (single hard-coded avatar
model, no auth). Treat the `models/<name>/` folders and `--model-dir`/config
paths as the main things you'll need to point at your own data.

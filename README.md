# Video Face Scanner

A lightweight face recognition app for video files, built with Python. Scan your video library to find and track where specific people appear — all running locally on low-resource hardware like a Raspberry Pi 5.

## Features

- Scans video files every N frames (default: 10) to detect faces
- Prompts you to name any unrecognised face
- Builds a local database of known people over time
- Auto-identifies known faces in future scans
- Browse timecodes for every appearance of a person across your video files
- Runs entirely offline — no cloud, no internet required

## Requirements

- Python 3.10+
- Raspberry Pi 5 (or any Linux/Windows machine with 2GB+ RAM)
- A display (tkinter GUI)

## Installation

### Windows (download — no Python needed)

Grab the latest `VideoFaceScanner.exe` from the [Releases page](https://github.com/clewstudios-lang/video-face-scanner/releases) and double-click. Your face database is stored at `%LOCALAPPDATA%\VideoFaceScanner\faces.db`.

### Raspberry Pi / Linux

```bash
bash install.sh
```

This installs all system and Python dependencies into a virtual environment. On Raspberry Pi, prebuilt wheels from [PiWheels](https://www.piwheels.org) mean no compilation is needed.

### Manual install (any platform)

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

```bash
source venv/bin/activate
python main.py
```

### Workflow

1. **Scan tab** — click *Select Video & Scan* and pick a video file
2. Adjust the frame interval (default 10 — checks every 10th frame)
3. Known faces are recorded automatically
4. Unknown faces appear one at a time — type a name to add them to your database
5. **Search tab** — select a person to see every video file and timecode where they appear
6. **Known Persons panel** — view thumbnails, rename, or delete any person

## Project structure

```
video_face_scanner/
├── main.py          # Entry point
├── database.py      # SQLite: persons, encodings, appearances
├── scanner.py       # Video processing and face matching
├── gui.py           # tkinter interface
├── requirements.txt
└── install.sh       # Raspberry Pi / Linux installer
```

## How it works

- Face detection uses dlib's HOG model (CPU-friendly, no GPU needed)
- Each detected face is encoded as a 128-dimension vector and stored in SQLite
- Matching uses Euclidean distance with a 0.55 tolerance threshold
- Frames are scaled to 50% before processing to reduce CPU load
- Unknown faces are de-duplicated per scan so the same person isn't queued multiple times

## License

MIT

import io

import cv2
import face_recognition
import numpy as np
from PIL import Image


def extract_thumbnail(frame_bgr: np.ndarray, face_location: tuple, size=120) -> bytes:
    top, right, bottom, left = face_location
    pad = 20
    h, w = frame_bgr.shape[:2]
    top = max(0, top - pad)
    left = max(0, left - pad)
    bottom = min(h, bottom + pad)
    right = min(w, right + pad)
    crop = frame_bgr[top:bottom, left:right]
    rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb).resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def scan_video(video_path: str, frame_interval: int = 10, progress_callback=None):
    """
    Generator — yields one dict per detected face per sampled frame:
        frame_number, timestamp_sec, encoding (np.ndarray), thumbnail (bytes)
    Uses HOG model (CPU-friendly, good for Raspberry Pi).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_number = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_number % frame_interval == 0:
            if progress_callback:
                progress_callback(frame_number, total_frames)

            # Scale down for faster processing, then scale locations back up
            small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            locations = face_recognition.face_locations(rgb_small, model="hog")
            if locations:
                encodings = face_recognition.face_encodings(rgb_small, locations)
                for loc, enc in zip(locations, encodings):
                    top, right, bottom, left = loc
                    full_loc = (top * 2, right * 2, bottom * 2, left * 2)
                    thumb = extract_thumbnail(frame, full_loc)
                    yield {
                        "frame_number": frame_number,
                        "timestamp_sec": frame_number / fps,
                        "encoding": enc,
                        "thumbnail": thumb,
                    }

        frame_number += 1

    cap.release()


def match_face(encoding: np.ndarray, known: list, tolerance: float = 0.55):
    """
    known: list of (person_id, name, encoding)
    Returns (person_id, name) of best match, or (None, None).
    """
    if not known:
        return None, None
    known_encs = [k[2] for k in known]
    distances = face_recognition.face_distance(known_encs, encoding)
    best = int(np.argmin(distances))
    if distances[best] <= tolerance:
        return known[best][0], known[best][1]
    return None, None


def is_new_unknown(encoding: np.ndarray, seen_encodings: list, threshold: float = 0.50) -> bool:
    """Return True if this encoding is distinct from all encodings in seen_encodings."""
    if not seen_encodings:
        return True
    distances = face_recognition.face_distance(seen_encodings, encoding)
    return bool(np.min(distances) > threshold)

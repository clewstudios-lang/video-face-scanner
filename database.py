import sqlite3
import json
import os
import sys
from datetime import datetime

import numpy as np


def _user_data_dir() -> str:
    """Per-user app data directory, cross-platform."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    d = os.path.join(base, "VideoFaceScanner")
    os.makedirs(d, exist_ok=True)
    return d


# Allow override via env var (useful for tests or portable mode)
DB_PATH = os.environ.get("VFS_DB_PATH") or os.path.join(_user_data_dir(), "faces.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS persons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS face_encodings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id INTEGER NOT NULL,
        encoding TEXT NOT NULL,
        FOREIGN KEY (person_id) REFERENCES persons(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS appearances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id INTEGER NOT NULL,
        video_path TEXT NOT NULL,
        frame_number INTEGER NOT NULL,
        timestamp_sec REAL NOT NULL,
        thumbnail BLOB,
        scanned_at TEXT NOT NULL,
        UNIQUE(person_id, video_path, frame_number),
        FOREIGN KEY (person_id) REFERENCES persons(id)
    )""")
    conn.commit()
    conn.close()


def get_all_persons():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, name, created_at FROM persons ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return rows


def add_person(name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO persons (name, created_at) VALUES (?, ?)",
            (name, datetime.now().isoformat()),
        )
        person_id = c.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        c.execute("SELECT id FROM persons WHERE name = ?", (name,))
        person_id = c.fetchone()[0]
    finally:
        conn.close()
    return person_id


def rename_person(person_id, new_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE persons SET name = ? WHERE id = ?", (new_name, person_id))
    conn.commit()
    conn.close()


def delete_person(person_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM face_encodings WHERE person_id = ?", (person_id,))
    c.execute("DELETE FROM appearances WHERE person_id = ?", (person_id,))
    c.execute("DELETE FROM persons WHERE id = ?", (person_id,))
    conn.commit()
    conn.close()


def add_face_encoding(person_id, encoding: np.ndarray):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO face_encodings (person_id, encoding) VALUES (?, ?)",
        (person_id, json.dumps(encoding.tolist())),
    )
    conn.commit()
    conn.close()


def get_all_encodings():
    """Returns list of (person_id, name, np.ndarray)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT fe.person_id, p.name, fe.encoding
           FROM face_encodings fe
           JOIN persons p ON fe.person_id = p.id"""
    )
    rows = c.fetchall()
    conn.close()
    return [(pid, name, np.array(json.loads(enc))) for pid, name, enc in rows]


def add_appearance(person_id, video_path, frame_number, timestamp_sec, thumbnail: bytes):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute(
            """INSERT INTO appearances
               (person_id, video_path, frame_number, timestamp_sec, thumbnail, scanned_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (person_id, video_path, frame_number, timestamp_sec,
             thumbnail, datetime.now().isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # already recorded this exact frame
    finally:
        conn.close()


def get_appearances_by_person(person_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT video_path, frame_number, timestamp_sec, thumbnail, scanned_at
           FROM appearances WHERE person_id = ?
           ORDER BY video_path, frame_number""",
        (person_id,),
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_person_counts():
    """Returns list of (person_id, name, appearance_count)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """SELECT p.id, p.name, COUNT(a.id) as cnt
           FROM persons p
           LEFT JOIN appearances a ON p.id = a.person_id
           GROUP BY p.id, p.name
           ORDER BY p.name"""
    )
    rows = c.fetchall()
    conn.close()
    return rows

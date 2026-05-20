"""Open a video file at a specific timestamp, cross-platform.

Tries VLC and mpv first (both support a `--start` flag). Falls back to the
OS default video player, which opens the file at the beginning.
"""
import os
import shutil
import subprocess
import sys


_WINDOWS_VLC_PATHS = [
    r"C:\Program Files\VideoLAN\VLC\vlc.exe",
    r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
]

_MAC_VLC_PATHS = [
    "/Applications/VLC.app/Contents/MacOS/VLC",
]


def _find_player():
    """Return (binary_path, start_arg_template) of a CLI-jumpable player, or (None, None)."""
    # VLC
    vlc = shutil.which("vlc")
    if not vlc and sys.platform == "win32":
        vlc = next((p for p in _WINDOWS_VLC_PATHS if os.path.exists(p)), None)
    if not vlc and sys.platform == "darwin":
        vlc = next((p for p in _MAC_VLC_PATHS if os.path.exists(p)), None)
    if vlc:
        return vlc, "--start-time={sec:.0f}"
    # mpv
    mpv = shutil.which("mpv")
    if mpv:
        return mpv, "--start={sec:.0f}"
    return None, None


def open_video_at(video_path: str, timestamp_sec: float) -> str:
    """Open the video at the given second.

    Returns a short human-readable status describing what was done. Never raises.
    """
    if not os.path.exists(video_path):
        return f"File not found: {video_path}"

    player, arg_tmpl = _find_player()
    sec = max(0, int(timestamp_sec))

    try:
        if player:
            args = [player, arg_tmpl.format(sec=sec), video_path]
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen(args, **kwargs)
            return f"Opened in {os.path.basename(player)} at {sec}s"

        # No CLI-jumpable player — fall back to OS default (no seek)
        if sys.platform == "win32":
            os.startfile(video_path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", video_path], start_new_session=True)
        else:
            subprocess.Popen(["xdg-open", video_path], start_new_session=True)
        return f"Opened with default player (install VLC to jump to {sec}s)"
    except Exception as e:
        return f"Could not open video: {type(e).__name__}: {e}"

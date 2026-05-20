#!/usr/bin/env python3
"""Video Face Scanner — entry point."""

import multiprocessing
import sys


def check_imports():
    missing = []
    for pkg, imp in [("face_recognition", "face_recognition"),
                     ("cv2", "opencv-python"),
                     ("PIL", "Pillow"),
                     ("numpy", "numpy")]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(imp)
    if missing:
        print("Missing dependencies. Run:\n")
        print(f"  pip install {' '.join(missing)}\n")
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    check_imports()
    from gui import VideoFaceScanner
    app = VideoFaceScanner()
    app.mainloop()

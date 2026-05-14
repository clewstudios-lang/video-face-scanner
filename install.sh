#!/bin/bash
# Install script for Video Face Scanner on Raspberry Pi 5 (Raspberry Pi OS Bookworm)
set -e

echo "=== Video Face Scanner — Dependency Installer ==="
echo ""

# System packages needed to compile dlib
echo ">>> Installing system build dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3-dev \
    python3-pip \
    python3-venv \
    python3-tk \
    cmake \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libboost-python-dev

echo ""
echo ">>> Creating Python virtual environment..."
python3 -m venv ~/video_face_scanner/venv
source ~/video_face_scanner/venv/bin/activate

echo ""
echo ">>> Installing Python packages..."
echo "    (dlib compilation takes 10-20 minutes on Pi — please be patient)"
pip install --upgrade pip wheel setuptools
pip install numpy
pip install dlib          # compiled from source — slow on Pi, one-time only
pip install face_recognition
pip install opencv-python
pip install Pillow

echo ""
echo "=== Installation complete! ==="
echo ""
echo "To run the app:"
echo "  source ~/video_face_scanner/venv/bin/activate"
echo "  python ~/video_face_scanner/main.py"
echo ""
echo "Tip: add this alias to ~/.bashrc for quick launch:"
echo "  alias faceapp='source ~/video_face_scanner/venv/bin/activate && python ~/video_face_scanner/main.py'"

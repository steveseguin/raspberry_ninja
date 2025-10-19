#!/bin/bash
#
# Quick update helper for Nvidia Jetson images that already ship with
# Raspberry Ninja pre-installed. This keeps package operations minimal
# and avoids distro upgrades or destructive cleanups performed by the
# full build script.
#
# Usage:
#   cd ~/raspberry_ninja/installers/nvidia_jetson
#   chmod +x quick_update.sh   # first run only
#   ./quick_update.sh
#
# The script:
#   1. Ensures the repository is present and up to date
#   2. Installs the small set of runtime packages the latest code expects
#   3. Refreshes Python dependencies used by Raspberry Ninja
#

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "== Raspberry Ninja Jetson quick update =="
echo "Repository root: ${REPO_ROOT}"

if [ ! -d "${REPO_ROOT}/.git" ]; then
    echo "Error: ${REPO_ROOT} does not look like a git checkout."
    echo "Clone https://github.com/steveseguin/raspberry_ninja.git first."
    exit 1
fi

echo
echo "--> Pulling latest code..."
git -C "${REPO_ROOT}" fetch --all --tags
git -C "${REPO_ROOT}" pull --ff-only

echo
echo "--> Installing runtime packages..."
sudo apt-get update
sudo apt-get install -y \
    python3 \
    python3-pip \
    python3-gi \
    python3-gi-cairo \
    python3-aiohttp \
    python3-cryptography \
    python3-websockets \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-gl \
    gstreamer1.0-tools \
    gstreamer1.0-nice \
    drm-tools \
    libdrm-tests \
    kms++-utils

echo
echo "--> Refreshing Python packages..."
python3 -m pip install --upgrade --no-cache-dir websockets cryptography aiohttp PyGObject

echo
echo "--> Checking GStreamer just in case..."
gst-launch-1.0 --version || true

echo
echo "Quick update complete. To run Raspberry Ninja:"
echo "  cd ${REPO_ROOT}"
echo "  python3 publish.py --streamid <your_id>"
echo

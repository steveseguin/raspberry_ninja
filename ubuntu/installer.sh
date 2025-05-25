## Ubuntu (newest LTS) simple installer without building requirements
## Non-free components may not be included in this

sudo apt-get update

 # Use a virtual environment or delete the following file if having issues
# Remove EXTERNALLY-MANAGED file for any Python version (Debian 12+ systems)
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
sudo rm /usr/lib/python${PYTHON_VERSION}/EXTERNALLY-MANAGED 2>/dev/null || true

# Install GStreamer and development packages
sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 \
    gstreamer1.0-qt5 gstreamer1.0-pulseaudio gstreamer1.0-nice

# Try to install rust plugins for WHIP/WHEP support
sudo apt-get install -y gstreamer1.0-plugins-rs 2>/dev/null || echo "Note: WHIP/WHEP plugins not available in repos"

# Install Python and required modules
sudo apt install python3-pip -y
pip3 install websockets cryptography

# Install additional recommended packages
sudo apt-get install -y python3-rtmidi git

# Orange Pi Installation Guide for Raspberry Ninja

<img width="360" src="https://github.com/steveseguin/raspberry_ninja/assets/5319910/63a664aa-acab-4a7e-a836-524b9a4460fb">

## Supported Hardware
It is recommended to use Orange Pi 5 and Orange Pi 5 Plus, as other models have not been thoroughly tested yet.

## Installation Options

### Option 1: Using Pre-built OS Image
There are no preinstalled images specifically for Raspberry Ninja. However, you can download the prebuilt OS from the manufacturer website [orangepi.org](https://orangepi.org) and follow the setup instructions below.

> **Note:** This guide is based on Debian, but should work with Ubuntu and other Linux distributions. For the Orange Pi 5+, the HDMI input works when using `--raw` as a `publish.py` parameter. If it doesn't work, check if the HDMI input is listed when running `gst-device-monitor-1.0`. Confirmed working with `Armbian_24.2.3_Orangepi5-plus_bookworm_legacy_5.10.160_minimal.img.xz` as of May 10th, 2024. If multiple video devices are connected, use the `--v4l2` parameter to specify which video device ID to use.

### Option 2: Setting Up from Scratch

## Quick Install Script

Copy and paste this entire block to install all dependencies and set up Raspberry Ninja:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# For Debian bookworm, remove EXTERNALLY-MANAGED file (skip if using venv)
sudo rm /usr/lib/python3.11/EXTERNALLY-MANAGED

# Install Python PIP
sudo apt install python3-pip -y

# Install required GStreamer libraries
sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl \
    gstreamer1.0-gtk3 gstreamer1.0-qt5 gstreamer1.0-pulseaudio \
    gstreamer1.0-nice gstreamer1.0-plugins-base-apps git

# Install Python dependencies
pip3 install websockets cryptography

# Install PyGObject dependencies (may be needed for Ubuntu)
sudo apt-get install -y libcairo-dev
sudo apt-get install -y python3-dev cmake libgirepository1.0-dev

# Use system-provided PyGObject instead of pip version
sudo apt-get install -y python3-gi python3-gi-cairo

# Clone Raspberry Ninja repository
cd ~
git clone https://github.com/steveseguin/raspberry_ninja
cd raspberry_ninja
```

## Running the Software

Test the stream with colored bars and static noise:

```bash
python3 publish.py --test
```

If successful, configure the command-line as needed, removing `--test`, and customizing for your setup.

## Camera Configuration

### MIPI RK Camera
If using the MIPI RKCamera, edit `publish.py` to use `/dev/video11`.

### USB Camera
If using a USB Camera, edit to `/dev/video0`.

### HDMI Input
HDMI Input is typically found at `/dev/video1`, but you must first enable HDMI-RX using `orangepi-config`. Once enabled, it works with any HDMI input, even at high resolutions.

![Orange Pi 5 Plus with USB webcam](https://github.com/steveseguin/raspberry_ninja/assets/5319910/25934ec7-da3a-4cff-96ac-5a723840caf4)

## Setting Up Auto-boot Service

There's a service file included that sets up the Orange Pi to auto-boot. You'll need to modify it with your preferred settings:

```bash
# Edit the service file
cd ~/raspberry_ninja/orangepi
sudo nano raspininja.service  # or sudo vi raspininja.service
```

After editing the file with your stream ID and other settings, install and enable the service:

```bash
# Install and enable auto-boot service
sudo cp raspininja.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable raspininja
sudo systemctl restart raspininja

# Check the service status
sudo systemctl status raspininja
```

The service should now auto-start on system boot and restart if it crashes.

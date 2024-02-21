## Installation on a Raspberry Pi /w Bullseye 32bit

This is a simple approach to install Raspberry.Ninja onto a vanilla Raspberry Pi image, and possibly any system really

At the moment this may lead to the installation of Gstreamer 1.18, which works for publishing video to VDO.Ninja, but doens't quite work well with playing back video. A newer version may be needed if intending to restream from VDO.Ninja to RTSP, NDI, file, etc.

#### Setting up and connecting

Run command to update the board, be sure that python3 and pip are installed

``sudo apt update && sudo apt upgrade -y``

If running a Debian 12-based system, including new Raspberry OS systems, you'll either want to deploy things as a virtual environment, or disable the flag that prevents self-managing depedencies. You can skip this step if you don't have issues otherwise though.

```sudo rm /usr/lib/python3.11/EXTERNALLY-MANAGED  # Delete this file or use a venv```

Install some required lib

``
sudo apt-get install -y python3-pip libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x python3-pyqt5 python3-opengl gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-pulseaudio gstreamer1.0-nice gstreamer1.0-plugins-base-apps
``

Install websocket and gi module

```
pip3 install websockets 
sudo apt-get install -y libcairo-dev libgirepository1.0-dev # may or may not be needed for the next step
pip3 install PyGObject
```

#### Downloading Raspberry.Ninja
Y
```sudo apt-get install git vim -y```

```git clone https://github.com/steveseguin/raspberry_ninja```

## Running things

After all, run the command to test

```python3 publish.py --rpi --test```

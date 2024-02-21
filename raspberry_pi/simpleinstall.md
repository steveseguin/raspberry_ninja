## Installation on a Raspberry Pi /w Bullseye 32bit

This is the `'simple approach'` to installing Raspberry.Ninja onto a vanilla Raspberry Pi image.

At the moment this may lead to the installation of Gstreamer 1.18, which works for publishing video to VDO.Ninja, but doesn't quite work well with playing back video. A newer version may be needed if intending to restream from VDO.Ninja to RTSP, NDI, file, etc.

(Please note, Linux in general is designed to torment users, and so this install script may fail to work in the future as the world changes. I will try to keep it updated as best I can, but I can only say it last worked for me on February 21, 2024, using a fresh install of Raspberry Pi OS - Bookworm Lite 64-bit edition.)

#### Setting up and connecting

Run command to update the board, be sure that python3 and pip are installed

``sudo apt update && sudo apt upgrade -y``

If running a Debian 12-based system, including new Raspberry OS systems (eg; bookworm), you'll either want to deploy things as a virtual environment (suggested), or disable the flag that prevents self-managing depedencies (easier). You can skip this step if you don't have issues or if you prefer to manage your environment some other way. Pretty much though, this new install speedbump was added by others because the world doesn't like us having fun.

```sudo rm /usr/lib/python3.11/EXTERNALLY-MANAGED  # Delete this file to prefer fun over safety```

Install some required lib

``
sudo apt-get install -y python3-pip libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x python3-pyqt5 python3-opengl gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-pulseaudio gstreamer1.0-nice gstreamer1.0-plugins-base-apps
``

Install websocket and gi module. (Installing PyGObject often breaks due to changing dependencies, and it's near impossible to install on Windows, so consider it your lucky day if it installs without issues.)

```
pip3 install websockets 
sudo apt-get install -y libcairo-dev libgirepository1.0-dev # these dependencies may or may not be needed; it rather depends on the mood of the universe.
pip3 install PyGObject
```

Since Linux in general is designed to cause endless grief to casual users, if using Bookworm with your Raspberry Pi, you'll now need to also install libcamerasrc manually. This may fail if using an older or future version of Linux however.

``
sudo apt-get install -y gstreamer1.0-libcamera
``

#### Downloading Raspberry.Ninja

```sudo apt-get install git vim -y```

```git clone https://github.com/steveseguin/raspberry_ninja```

## Running things

After all, run the command to test

```
cd raspberry_ninja # change into the directory
python3 publish.py --rpi --test
```

`--test` should show a test video with static sounds.  You can remove it afterwards and configure Raspberry Ninja for your actual camera.

## Installation on a Raspberry Pi /w Bullseye 32bit

#### Setting up and connecting

Run command to update the board, be sure that python3 and pip are installed

``sudo apt update && sudo apt upgrade -y``

``sudo apt install python3-pip``

#### Installing from scratch

Install some required lib


``sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-pulseaudio gstreamer1.0-nice gstreamer1.0-plugins-base-apps``

Install websocket module

``pip3 install websockets PyGObject``

#### Downloading Raspberry.Ninja

```sudo apt-get install git vim -y```

```git clone https://github.com/steveseguin/raspberry_ninja```

## Running things

After all, run the command to test

```python3 publish.py```

## Ubuntu (newest LTS) simple installer without building requirements
## Non-free components may not be included in this

sudo apt-get update

 # Use a virtual environment or delete the following file if having issues
sudo rm /usr/lib/python3.11/EXTERNALLY-MANAGED ## For Debian 12-based systems

sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-qt5 gstreamer1.0-pulseaudio gstreamer1.0-nice
sudo apt install python3-pip -y
pip3 install websockets

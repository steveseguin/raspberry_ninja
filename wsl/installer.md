
## Windows (WSL) installer - Ubuntu

### Install Windows for Linux

https://learn.microsoft.com/en-us/windows/wsl/install

The basic idea is to open up the windows Powershell and enter something like: `wsl -s Ubuntu`

Ubuntu would install, and you'd open that. From that command prompt shell, you'd install and use Raspberry Ninja

### This install may not have broad hardware support; cameras, encoders, etc, but the basics are there
```
sudo apt-get update && sudo apt upgrade -y
sudo apt-get install libcairo-dev -y
sudo apt-get install python3-pip -y

sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x python3-pyqt5 python3-opengl gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-qt5 gstreamer1.0-gtk3 gstreamer1.0-pulseaudio gstreamer1.0-nice gstreamer1.0-plugins-base-apps

pip3 install websockets PyGObject

sudo apt-get install vim git -y
cd ~ 
git clone https://github.com/steveseguin/raspberry_ninja
cd raspberry_ninja
python3 publish.py --test

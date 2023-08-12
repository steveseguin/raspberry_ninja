
## Windows (WSL) installer - Ubuntu

### Install Windows Subsystem for Linux

https://learn.microsoft.com/en-us/windows/wsl/install

The basic idea of how to install WSL is to open up the Windows Powershell and enter something like:

```
wsl --install
wsl --install -d Ubuntu
```
 There might also be graphical installers for Ubuntu for Windows these days, perhaps already installed on your computer, ready to go.

<img width="383" alt="image" src="https://github.com/steveseguin/raspberry_ninja/assets/2575698/c4075955-8f7f-4f7f-87a8-07cff9c8463f">

Anyways, once Ubuntu is installed, you'd open that. You might be able to just search in Windows for and run `wsl` to open it.

From that Linux command prompt shell, you'd install and use Raspberry Ninja. Pretty nifty!

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

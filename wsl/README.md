
## Windows (WSL) installer - Ubuntu

### Install Windows Subsystem for Linux

https://learn.microsoft.com/en-us/windows/wsl/install

The basic idea of how to install WSL is to open up the Windows Powershell and enter something like:

```
wsl --install
wsl --install -d Ubuntu
```
<img width="383" alt="image" src="https://github.com/steveseguin/raspberry_ninja/assets/2575698/c4075955-8f7f-4f7f-87a8-07cff9c8463f">

There might also be graphical installers for Ubuntu for Windows these days, perhaps already installed on your computer, ready to go.

Anyways, once Ubuntu is installed, you'd open that. You might be able to just search in Windows for and run `wsl` to open it.

From that Linux command prompt shell, you'd install and use Raspberry Ninja. Pretty nifty!

### This install may not have broad hardware support; cameras, encoders, etc, but the basics are there
```
sudo apt-get update && sudo apt upgrade -y
sudo apt-get install python3-pip -y

sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x python3-pyqt5 python3-opengl gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-qt5 gstreamer1.0-gtk3 gstreamer1.0-pulseaudio gstreamer1.0-nice gstreamer1.0-plugins-base-apps

pip3 install --break-system-packages websockets cryptography

sudo apt-get install git -y
cd ~ 
git clone https://github.com/steveseguin/raspberry_ninja
cd raspberry_ninja
python3 publish.py --test
```
Raspberry.Ninja should be running now, and you can open the provided link in your browser to confirm.

Using a camera on WSL is a bit more tricky, but running `gst-inspect-1.0 | grep "src"` will give you a sense of what media sources you have available to you. It could be possible to pipe encoded video data into Raspberry.Ninja via OBS Studio for example, however specifying the video meta data (caps) and getting the piping setup right is then needed.  This process needs to be documented.

If wishing to record a remote video to disk, without decoding it first, you can use:

```
python3 publish.py --record STREAMIDHERE123
```
You can then access the saved recording in File Explorer here at `\\wsl$`, and navigate to the raspberry_ninja folder as needed:

ie, for me, username `vdo`, it would be here: `\\wsl.localhost\Ubuntu\home\vdo\raspberry_ninja\STREAMIDHERE123.mkv`


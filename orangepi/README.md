
![opi5-camera-rk](https://github.com/steveseguin/raspberry_ninja/assets/5319910/63a664aa-acab-4a7e-a836-524b9a4460fb)

## Installation on a Orange Pi

It is recommended to use Orange Pi 5 and Orange Pi 5 Plus, since other model i did test yet.

#### Installing from the provided image

There are no preinstalled image since I don't have time to create it. However, you can download the prebuilt OS from manufaturer website orangepi.org and start to use it

*note: This guide I think was based on Debian, but it should also work with Ubuntu and maybe other Linux flavours

#### Setting up and connecting

Run command to update the board, be sure that python3 and pip are installed

``sudo apt update && sudo apt upgrade -y``

``sudo apt install python3-pip``

#### Installing from scratch

Install some required lib

``sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-qt5 gstreamer1.0-pulseaudio gstreamer1.0-nice gstreamer1.0-plugins-base-apps``

Install websocket module

``pip3 install websockets``

You may also need to install PyGObject, such as if running Ubuntu


```
sudo apt-get install -y libcairo-dev
pip3 install PyGObject
```

## Running things

After all, run the command to test

``python3 publish.py --streamid orangepi5 --noaudio --raw``

### Camera considerations

I have tested with RK Camera using the MIPI connector and also USB Webcam, both run well, you just need to edit the file publish.py 

If you use MIPI RKCamera , edit to /dev/video11

If you use USB Camera, edit to /dev/video0 

I found out that /dev/video1 is the HDMI Input but you will need to enter orangepi-config to enable hdmirx first, then it can be use with any HDMI Input, even in high resolution

Orange Pi 5 Plus with usb webcam
![opi5plus-webcam](https://github.com/steveseguin/raspberry_ninja/assets/5319910/25934ec7-da3a-4cff-96ac-5a723840caf4)


<img src="https://user-images.githubusercontent.com/2575698/127804804-7ee38ebd-6f98-4242-af34-ac9ef0d9a82e.png" width="400">

## Installation on a Raspberry Pi

It is recommended to use the provided raspberry pi image, as the install process is otherwise quite challenging.

#### Installing from the provided image

Download and extract the image file:
https://drive.google.com/file/d/1NchpcHYHcNMvjm7NaBf84ZH0xKgLomXR/view?usp=sharing

Write the image to a SD / microSD card; at least 8GB in size is needed, using the appropriate tool. 

On Windows, you can use Win32DiskImager (https://sourceforge.net/projects/win32diskimager/) to write this image to a disk.  If you need to format your SD card first, you can use the SD Card Formatter (https://www.sdcard.org/downloads/formatter/).  

(balenaEtcher also works for writing the image, but using the official Raspberry Pi image writer may have problems.)

To connect, use a display and keyboard, or you can SSH into it as SSH on port 22 if enabled.

Login information for the device is:
```
username: pi
password: raspberry
```

#### Installing from scratch

If you do not want to use the provided image, you can try to install from scratch, but be prepared to lose a weekend on it. Please see the install script provided, but others exist online that might be better. Gstreamer 1.14 can be made to work with VDO.Ninja, but GStreamer 1.16 or newer is generally recommend; emphasis on the newer.

The official image setup for the Raspberry Pi is here: https://www.raspberrypi.org/documentation/installation/installing-images/windows.md

The `installer.sh` file in this folder contains the general idea on how to install an updated version of Gstreamer on a Raspberry Pi. Expect to waste a week of time on it, chasing compiling issues I'm sure.

## Running things

Once connected to you Pi, you can pull the most recent files from this Github repo to the disk using:

```
sudo rm raspberry_ninja -r
git clone https://github.com/steveseguin/raspberry_ninja.git
cd raspberry_ninja
python3 publish.py --streamid YOURSTREAMIDHERE --bitrate 4000
```

If you are using a Raspberry Pi 4, then you should be pretty good to go at this point.

If you are using a Raspberry Pi 2 or 3, you might want to limit the resolution to 720p.  You may need to do this at a code level.

The hardware-encoder in the Raspberry Pi doesn't like USB-connect cameras, and only really the CSI camera, so USB cameras will use software-based encoding by default. This means if you want to use the harware encoder with a USB device, you'll need to use a Jetson or modify the code to uncomment the line that enables the hardware encoder.  This however will cause the video to look like 8-bit graphics or something.

If using the CSI camera, even a raspberry Pi zero will work, although it might still be best to limit the resolution to 720p30 or 360p30 if using a raspberry pi zero w.

###### Please return to the parent folder for more details on how to run and configure


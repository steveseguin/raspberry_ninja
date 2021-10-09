
<img src="https://user-images.githubusercontent.com/2575698/127804804-7ee38ebd-6f98-4242-af34-ac9ef0d9a82e.png" width="400">

## Installation on a Raspberry Pi

It is recommended to use the provided raspberry pi image, as the install process is otherwise quite challenging.

#### Installing from the provided image

Download and extract the image file:
https://drive.google.com/file/d/1NchpcHYHcNMvjm7NaBf84ZH0xKgLomXR/view?usp=sharing

Write the image to a SD / microSD card; at least 8GB in size is needed, using the appropriate tool. 

On Windows, you can use Win32DiskImager (https://sourceforge.net/projects/win32diskimager/) to write this image to a disk.  If you need to format your SD card first, you can use the SD Card Formatter (https://www.sdcard.org/downloads/formatter/).  balenaEtcher also works for writing the image, but the official Raspberry Pi image writer may have problems.

SSH is enabled on port 22 if needed.

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
git clone https://github.com/steveseguin/raspberry_ninja.git
```

The newest code supports streaming over the Internet, rather than just a LAN, so be sure to update if you need that functionality.



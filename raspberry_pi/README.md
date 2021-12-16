
<img src="https://user-images.githubusercontent.com/2575698/127804804-7ee38ebd-6f98-4242-af34-ac9ef0d9a82e.png" width="400">

## Installation on a Raspberry Pi

It is recommended to use the provided raspberry pi image, as the install process is otherwise quite challenging.

If using a Raspberry Pi Zero, using a CSI Raspicam is probably the best bet, as using a USB-based camera will likely not perform that well. Any of the Raspberry Pis will use the hardware-encoder when a CSI camera, although you need to specify via command line arguments to use the CSI camera.

If using a USB 2.0 camera (default mode), an overclocked Raspberry Pi 4 or 400 is recommend to achieve 1080p30.. A Raspberry Pi 2 or 3 with a USB camera can be set to do 360p60, 480p, or 720p30. The default target resolution is currently 1080p30. The USB-based camera pipeline will be partially hardware-accelerated, doing some of the encoding at a software-level, but this is for the best if you have a Raspberry Pi 4 or faster to work with.

Using a CSI-based camera with a Raspberry Pi will currently give better results than a USB-based one.

#### Installing from the provided image

Download and extract the image file:
https://drive.google.com/file/d/1veyVEu5Mg2eG2yD2A00cVKZHNEuHVDES/view?usp=sharing

Write the image to a SD / microSD card; at least 8GB in size is needed, using the appropriate tool. 

On Windows, you can use Win32DiskImager (https://sourceforge.net/projects/win32diskimager/) to write this image to a disk.  If you need to format your SD card first, you can use the SD Card Formatter (https://www.sdcard.org/downloads/formatter/).  

(balenaEtcher also works for writing the image, but using the official Raspberry Pi image writer may have problems.)

To connect, use a display and keyboard, or you can SSH into it as SSH on port 22 if enabled.

Login information for the device is:
```
username: pi
password: raspberry
```

You can then run `sudo raspi-config` from the command-line to configure the Pi as needed. If using the Raspberry Pi camera or another CSI-based camera, you'll want to make sure it's enabled there. 

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

If you are using a Raspberry Pi 4, then you should be pretty good to go at this point.  1080p30 with a USB camera might struggle with higher bitrates though.

If you are using a Raspberry Pi 2 or 3, you might want to limit the resolution to 720p.  You may need to do this at a code level.

The hardware-encoder in the Raspberry Pi doesn't like USB-connect cameras, and only really the CSI camera, so USB cameras will use software-based encoding by default. This means if you want to use the harware encoder with a USB device, you'll need to use a Jetson or modify the code to uncomment the line that enables the hardware encoder.  This however will cause the video to look like 8-bit graphics or something.

If using the CSI camera, even a raspberry Pi zero will work, although it might still be best to limit the resolution to 720p30 or 360p30 if using a raspberry pi zero w.

To enable the CSI camera, you'll need to add `--rpicam` to the command-line, as the default is USB MPJEG.  You may need to run `sudo raspi-config` ane enable the CSI camera inteface before the script will be able to use it.

To enable RAW-mode (YUY2) via a USB Camera, instead of MJPEG, you'll need to add `--raw` to the command line, and probably limit the resolution to around 480p.

###### Please return to the parent folder for more details on how to run and configure

## Setting up auto-boot

There is a service file included in the raspberry_pi folder that sets the raspberry pi up to auto-boot.  You will need to modify it a tiny bit with the settings to launch by default, such as specifying the stream ID and camera settings, such as --rpicam or --rpi or --hdmi, etc.

To edit the file, you can use VIM.
```
cd ~
cd raspberry_ninja
cd raspberry_pi
sudo vi raspininja.service
```
To use VIM, press `i` to enter text edit mode.  `:wq` will let you save and exit.

Once done editing the file, you can set it up to auto launch on load and to start running immediately.
```
sudo cp raspininja.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable raspininja
sudo systemctl restart raspininja
```
To check if there were any errors, you can run the status command:
```
sudo systemctl status raspininja
```

Things should now auto-boot on system boot, and restart if things crash.  


## Optimizing the Pi to reduce packet loss

Before: ![image](https://user-images.githubusercontent.com/2575698/146271521-ed9f8742-d584-4214-938c-687388b658bf.png)

After: ![image](https://user-images.githubusercontent.com/2575698/146271560-852984cb-6cd0-47d2-a03d-c2e78358652a.png)

The Raspberry Pi doesn't have the greatest WiFi adapter, and even the Ethernet has some issues, so it needs some added love to keep up.  By applying some optimizations to the Raspbian OS, you can increase stability, resulting in less packet loss, and in turn, a more stable frame rate.

The following changes resulted in a rather sharp improvement in frame rate stability; if you find more tweaks, please submit them! :D

Okay, the first optimization was with my pi4 that has active cooling; I locked the CPU cores at a fixed 1500mhz.
```
arm_freq=1500
force_turbo=1
```
To do that, I added the above to `/boot/config.txt`

You'll need to adjust the arm_freq to match what your device can handle; 700 and up, depending on model and cooling. A stable CPU seems to help, and a bit more CPU overhead can help too. 

Next,  added the following to this file:  `/boot/cmdline.txt`
```
isolcpus=0
```
This removes core 0 from user access, and allows it to be dedicated as a core for the wifi stack. Or so that's my understanding.  This won't work with a single-core raspberry Pi I guess, and may hinder h264-software based encoding options, but it did make an improvement (x264 vs rpicam)

I also added a bunch of buffers to the gstreamer-python code; some did more harm then good, but overall no great impact.  I left them in to just make me feel better, but you can set limits on them if there are problems. These should be updated on Github now, so be sure to pull the most recent code.

Also, if using Ethernet, to avoid packet loss on the Pi4 when connected to gigabit, run the following: 
```
sudo ethtool -s eth0 speed 100 duplex full autoneg off
```
This reduces the speed to 100mbps, instead of gigabit, but it also can dramatically reduce packet loss on a Raspberry Pi. 100mbps is more than enough anyways.
You may want to have the command auto-run on boot, just to be safe, but if you're not using Ethernet, it may not be needed. 

Finally, just to add some buffering onto the Viewer side as well, in Chrome (edge/electron), I added &buffer=300 to the view link.  The VDO.Ninja player has like 40 to 70ms already added, but increasing it to 300 or so will help pre-empt any jitter delays, avoiding sudden frame loss. This is not required, but seems to help a bit at the cost of added latency.  You may want to increase it upwards of 1000ms to see if it helps further, or go without any added buffer entirely.

If using the buffer option, the view link might look like this `https://vdo.ninja/?password=false&view=9324925&buffer=300`

The buffer command is compatible with OBS v27.2 on PC and newer, but not earlier versions on PC.




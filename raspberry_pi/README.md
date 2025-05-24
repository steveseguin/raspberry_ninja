
<img src="https://user-images.githubusercontent.com/2575698/127804804-7ee38ebd-6f98-4242-af34-ac9ef0d9a82e.png" width="400">

## Installation on a Raspberry Pi

It is recommended to use the provided Raspberry Pi image, as the install process is otherwise quite challenging.  If using an image, you will want to update the code afterwards to ensure you're running the newest version. You can also try a simple install script or a complex build script, depending on whether you want old or new functionality available.

### Simple install script:

The simple installer will work on existing RPI OS systems, without needing to compile anything, however this will result in older versions of Gstreamer being installed without all the plugins, bug-fixes, and codecs being available. That said, I'd probably recommend this to most users over the pre-built image these days, and especially over the full-build-from-scratch script.

Gstreamer v1.18 is likely to be what Raspberry Pi OS will come with when using the simple installer, which is OK, but does miss out on some advanced features found in Gstreamer 1.22. I'd avoid older versions of Gstreamer if at all posssible though, found on legacy versions of Raspberry Pi OS / Raspbian. 

The simple installer [can be found here.](https://github.com/steveseguin/raspberry_ninja/blob/main/raspberry_pi/simpleinstall.md)

### Installing from the provided image

Download and extract the image file from the following zip file:
[https://drive.google.com/file/d/19hKnokApp31UnqaPbc_-llpTuA5d_oGW/view?usp=share_link ](https://drive.google.com/file/d/1vWkznU544qkRsal1GyIj4YZ-O2pNFCfh/view?usp=sharing)

This image is based on an official clean Bullseye Lite OS 64-bit image, but with Raspberry.Ninja, Gstreamer v1.22, Libcamera, Arducam-drivers, WHIP/WHEP GST plugins, Ffmpeg, Rust, AV1, and SRT support included. It was built on October 6th 2023 using the available installer script. Since it is a 64-bit version, it may not boot onto a Raspberry Pi 1 and probably many, if not all, Raspberry Pi 2 models. It has no GUI (no desktop) and is terminal-line only.

```
Username: vdo  
Password: ninja
```

To install, write the image to a SD / microSD card (or compatible USB 3.0 drive if using a RPI 4/5). At least 16GB is needed for the image and it's recommended that the drive be fast. One user reported they had reduced frame loss when switching from a slow uSD card to a USB 3.0 SSD.

On Windows, you can use Win32DiskImager (https://sourceforge.net/projects/win32diskimager/) to write this image to a disk.  If you need to format your SD card first, you can use the SD Card Formatter (https://www.sdcard.org/downloads/formatter/).

Note: balenaEtcher also works for writing the image, but using the official Raspberry Pi image writer may have problems. The Raspberry Pi image writer does make it easy to setup WiFi during the install though, so give it a try if you want.

#### Setting up and connecting the image

Before loading the uSD card into your RPi, you can configure some basic settings on the drive itself via Windows/Mac/Linux.

You can setup the WiFi by creating a copy of `X:/boot/wpa_supplicant.conf.sample` named `wpa_supplicant.conf`.  Editing that file, change the ssid and psk lines with your WiFi's SSID and password.  This will ensure it auto connects to your WiFi on first boot.

You can also open `X:/boot/config.txt` in notepad to uncomment a line to enable support for the HDMI to CSI adapter.  There's a file also called `setup_c779.sh` in the raspberry_pi folder that also needs to be run once booted in, if using the C779 HDMI to CSI adapter at least. Probably not needed with the B10X boards, but can't confirm.  You will want to run it before connecting any input to the HDMI input port.

To connect, use a display and keyboard, or you can SSH into it as SSH on port 22 if enabled.  If you didn't configure the WiFi, you connect either via USB or Ethernet instead. Refer to the Raspberry Pi documentation for more help on that topic.

Note: By default the provided image will have SSH enabled, so if security is a concern, disable SSH. It is also suggested that you change the username and password to something more secure. I woudld also suggest not installing any BTC wallets on this image or anything like that, as security can't be guaranteed.

note: You might be able to also setup WiFi during the image write step, rather than after, when using the official Raspberry Pi image writer tool.

#### Login info for the image

Login information for the supplied image is:
```
username: vdo
password: ninja
```

.. On some older/vanilla versions of the Raspberry_Ninja images, the username/password could be:
```
username: pi
password: raspberry
```

You can then run `sudo raspi-config` from the command-line to configure the Pi as needed. If using the Raspberry Pi camera or another CSI-based camera, you'll want to make sure it's enabled there if using any CSI-based device.

You will probably want to also update the pi with `sudo apt-get update && sudo apt-get upgrade`, to snure it's up to date.  You can also run `sudo raspi-config` and update the RPi that way, along with updating the bootloader if desired (on a pi4 at least).

Note: There is NO graphical user interface (GUI / Desktop) installed with the provided images; only a terminal. I can offer a version with a GUI in the future if popular in request.

### Building the image from scratch instead

If you do not want to use the provided image, you can try to build and install from scratch, but be prepared to lose a weekend on it. Please see the install script provided, but others exist online that might be better. Gstreamer 1.14 can be made to work with VDO.Ninja, but GStreamer 1.16 or newer is generally recommend; emphasis on the newer.

The official image setup for the Raspberry Pi is here: https://www.raspberrypi.org/documentation/installation/installing-images/windows.md

The `installer.sh` file in this folder contains the general idea on how to install an updated version of Gstreamer on a Raspberry Pi. Expect to waste a week of time on it, chasing compiling issues I'm sure.

The simple installer script, that uses package manager builds of required libs, can be [found here instead](https://github.com/steveseguin/raspberry_ninja/blob/main/raspberry_pi/simpleinstall.md), if you give up trying to build the newest versions.

## Running the Raspberry Ninja code for the first time

Once connected to you Pi, you can pull the most recent Raspberry Ninja code files from this Github repo to the disk using:
```
cd ~
sudo rm raspberry_ninja -r
git clone https://github.com/steveseguin/raspberry_ninja.git
```
In the above code, we're just deleting the old copy of Raspberry Ninja and re-downloading it from scratch, just to be safe.

I don't have time to update images all the time, perhaps just a couple times a year, so it's very important you update the publish.py to the newest version. Especially if having issues. There are new updates about every month or so that improve the user experience and fixes bugs.

After cloning the code repository, if you have any problems or wish to update to the newest code in the future, you can just run `git pull` from your raspberry_ninja folder. This should download the most recent code without needing to delete everything. You will need to clear or stash any changes before pulling though; `git reset --hard` will undo past changes. `git stash` is a method to store past changes; see Google on more info there though.

Finally, you can now try running the publishing script using:
```
cd raspberry_ninja
python3 publish.py --test
```
This runs the script in a test mode that ensures the very basics are working and setup.  You should see a test pattern if you open the view link that is shown on screen. 

Once that works, next you might try something like the following to see if any connected camera works
```
python3 publish.py --libcamera --noaudio
```
You also may need to change the command line settings, depending on the camera / sensor / input connected.  While I try to have things auto work with just `python3 publish.py`, sometimes you need to pass specific parameters to tell the script what actually will work. A list of avialable options can be listed using the `--help` option:

```python3 publish.py --help```

I'm on discord at https://discord.vdo.ninja (in the #raspberry.ninja channel there), if you need help with this part.

### Camera considerations

If using an **original Raspberry Pi Zero**, an official Raspberry Pi CSI camera is probably the best bet, as using a USB-based camera will likely not perform that well. USB works pretty okay on a Raspberry Pi 4, as it has enough excess CPU cores to handle decoding motion jpeg, audio encoding, and the network overhead, but the Pi Zero original does not.

On a Pi Zero W original, 640x360p30 works fairly well via a USB camera. At 1080p though, frame rates drop down to around 5 to 10-fps though (10-fps with omx, but glitches a bit).  With an official CSI camera, 1080p30 is possible on a Pi Zero W original, but you might get the occassional frame hiccup still.

Some USB devices may struggle with audio/video syncronization. Video normally is low latency, but audio can sometimes drift a second or two behind the video with USB audio devices. We're trying to understand what causes this issue still; dropping the video resolution/frame rate can sometimes help though. It also doesn't seem to manifest itself when using Firefox as the viewer; just Chromium-based browsers.

If you are using a Raspberry Pi 4, then you should be pretty good to go at this point, even at 1080p30 MJPEG over USB 2.0 seems to work well there. You might contend with audio/video sycronization issues if using a USB camera/audio source still, but hopefully that issue can be resolved shortly. 

If you are using a Raspberry Pi 2 or 3, you might want to limit the resolution to 720p, at least if using a USB camera source. I can get 1080p30 on a Raspberry Pi 2 at fairly high bitrates, when running a stable version of the operating system with Gstreamer v1.22; this wasn't the case with older versions or nightly-built versions.

If using the CSI camera, the hardware encoder often works quite well, although it might still be best to limit the resolution to 720p30 or 360p30 if using an older raspberry pi zero w. The Raspberry Pi Zero 2 however works quite well at 1080p30 with the official Raspberry Pi cameras. 

**Important Note about Raspberry Pi 5**: The Raspberry Pi 5 does not have hardware video encoding support (no v4l2h264enc or omxh264enc). When using the `--rpi` parameter on a RPi5, the script will automatically detect this and fall back to software encoding (x264enc). This may impact performance compared to earlier Pi models with hardware encoders. For best results on RPi5, consider using `--x264` or `--openh264` parameters explicitly.

To enable the CSI camera on older versions of Raspberry Pi OS (Raspbian), you may need to add `--rpicam` to the command-line, as the default is USB MPJEG. With newer versions of Raspberry Pi OS, you may instead need to use `--libcamera --rpi` instead (or just --libcamera).  If you don't have audio connected, you might also need to add `--noaudio`, as sometimes that can cause issues.

If using a third-party CSI-based camera, it is strongly recommended you check compatilbility ahead of time. If you need to install a "driver" to have it work, I'd advise against using it. Drivers may not be compatible with the Gstreamer version used by Raspberry Ninja, or at the very least, can make setup and debugging a real nightmare.  Most Arducam cameras now seem to be driverless, with just a small change to the boot config file needed only, but this isn't the case for all Arducams or cameras from other providers.

If using a Camlink, you may need to use `--camlink`, or `--raw --rpi`, or perhaps just `--raw`, (such as if using a Raspberry Pi 5)

You may need to run `sudo raspi-config` ane enable the CSI camera inteface before the script will be able to use it. Some CSI cameras must be run with `--v4l2` instead, and some others require custom drivers to be installed first. Sticking with the official raspberry pi cameras is your best bet, but the $40 HDMI-to-CSI adapter and some knock off Raspberry Pi CSI cameras often will work pretty well too.

To enable RAW-mode (YUY2) via a USB Camera, instead of MJPEG, you'll need to add `--raw` to the command line, and probably limit the resolution to around 480p. 

If using an HDMI adapter as a camera source, you may need to adjust things at a code level to account for the color-profiles of your camera source. `--bt601` is an option for one stanard profile, with the default profile set at `coloimetry=2:4:5:4` for a Raspberry Pi. 10-bit and interlaced video probably isn't a good idea to attempt to use, and if possible setting the HDMI output of your camera to 8-bit 1080p24,25 or 30 is the highest you should probably go.

Raspberry Pis (models 1-4) only support up to 1080p30 FPS with the hardware encoder. The Raspberry Pi 5 doesn't have a hardware encoder, so you will be using software encoders instead. When using the `--rpi` parameter on a RPi5, the script automatically detects this and switches to software encoding. Setting a faster preset, if using x264 for example, will allow a Raspberry Pi 5 to output potentially even faster frame rates and resolutions, but at the cost of compression and video quality. 

One user who had issues mentioned they had to disable "Legacy Camera" mode in the raspi-config settings app to have their Pi camera be detected; this should be already off by default, but if you enabled it, I suppose try turning it off.

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

note: If using an Nvidia Jetson, please see its folder on github here for its service file.

## a proper Power Supply is very important

Raspberry Pi devices do not run on the normal 5.0V, like what a cell phone charger puts out. They are designed to run on 5.1V, with the Raspberry Pi 5 actually using even higher voltages.

Many instability issues can be resolved by using an official Raspberry Pi power adapter, which output 5.1V and have rather thick cables to ensure enough power delivery. 

## Details about cameras and performance

Using a CSI-based camera with a Raspberry Pi will currently give better results than a USB-based one; or at least. The official Raspberry Pi cameras can work with `--rpicam`, and the results are quite good. Some other knock off cameras can still be hardware encoded, but may need to be specified with `--v4l2`, which doesn't work quite as well as the official source element. Still, the results are often good up to 1080p30.

There are some non-supported cameras that use the CSI port, like the Arducam Sony IMX327 sensor-based cameras, as those may not have any proper driver support added. You can get those to work if they offer Gstreamer-based drivers though, however installing them may prove quite challenging. I'll provide pre-built images that support such devices when I have them working.

Lastly, unless using the RPi Compute Module, any HDMI to CSI adapter for the RPi will be limited to 25-fps.  With a 4-lane camera and the compute module, you might be able to do 1080p30 with HDMI to SCI adapters.  HDMI to CSI adapters do not include audio, unless you route the audio from the adapter to the I2S pins, which may require some tinkering to setup.


## Legacy camera support

If you want to use v4l2src and all the legacy camera options with your updated Rasbperry Pi OS, you can enable it via `sudo raspi-config` -> interfacing options -> enable Legacy camera mode.

Things like the HDMI to CSI adapter probably won't work without the legacy mode enabled. Things are moving to libcamera it seems, but it's leaving behind quite a lot also, so if libcamera isn't working for, the past isn't such a bad place.

## Optimizing the Pi to reduce packet loss

Before: ![image](https://user-images.githubusercontent.com/2575698/146271521-ed9f8742-d584-4214-938c-687388b658bf.png)

After: ![image](https://user-images.githubusercontent.com/2575698/146271560-852984cb-6cd0-47d2-a03d-c2e78358652a.png)

The Raspberry Pi doesn't have the greatest WiFi adapter, and even the Ethernet has some issues, so it needs some added love to keep up.  By applying some optimizations to the Raspbian OS, you can increase stability, resulting in less packet loss, and in turn, a more stable frame rate. (Some of these changes are already applied to the provided Raspberry Pi image (v3), but they will need to be manually applied if building from scratch.)

The following changes resulted in a rather sharp improvement in frame rate stability; if you find more tweaks, please submit them! :D

Okay, the first optimization was with my pi4 that has active cooling; I locked the CPU cores into performance mode with the force_turbo flag.
```
force_turbo=1
```
To do that, I added the above to `/boot/config.txt`.

You'll might need to adjust your arm_freq to match what your device can handle also, depending on model and cooling. A stable CPU seems to help.

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
You can make this change apply on boot by editing `/etc/rc.local` and adding `ethtool --change enp1s0 speed 100 duplex full autoneg off` before the `exit 0` line.

This reduces the speed to 100mbps, instead of gigabit, but it also can dramatically reduce packet loss on a Raspberry Pi. 100mbps is more than enough anyways.
You may want to have the command auto-run on boot, just to be safe, but if you're not using Ethernet, it may not be needed. 

You can further optimize the system by disabling Bluetooth and disabling network sleep mode.  For details on what you can try there, see this guide: 
https://forums.raspberrypi.com/viewtopic.php?t=138312&start=50#p1094659   You might want to keep audio on and other deviations from those instructions, if bothering to follow it at all.

Finally, just to add some buffering onto the Viewer side as well, in Chrome (edge/electron), I added &buffer=300 to the view link.  The VDO.Ninja player has like 40 to 70ms already added, but increasing it to 300 or so will help pre-empt any jitter delays, avoiding sudden frame loss. This is not required, but seems to help a bit at the cost of added latency.  You may want to increase it upwards of 1000ms to see if it helps further, or go without any added buffer entirely.

If using the buffer option, the view link might look like this `https://vdo.ninja/?password=false&view=9324925&buffer=300`

The buffer command is compatible with OBS v27.2 on PC and newer, but not earlier versions on PC.

### Firmware

Updating the firmware for the Raspberry Pi 4 might help with some USB controller or networking issues. 
```
# check if newest version is needed
sudo rpi-eeprom-update

# If not up to date, then we can update
sudo raspi-config
# Advanced Options -> Bootloader Version -> Latest
# Reboot when prompted
```
You can also try updating the firmware/system for other RPI boards using
```
sudo apt update
sudo apt full-upgrade
sudo reboot
```
### LED indicator light

You can add an LED to your Raspberry Pi board, using pin 12 (6 down from the top right corner) and the ground pin near the bottom.

It's possible to change this pin in the code to something else; feedback welcomed.

`--led` is the argument to use.

Light is lit dimly when the script is running, but there are no outbound connections.

The liht glows brighter though when there is at least one outbound connection active (or not yet timed out).

It's important to use a resister, 470-ohms is typically recommended, in series with the LED to avoid burning out the GPIO pin on your Raspberry Pi.  It's not recommended in general to connect an LED to the Raspberry Pi directly in this way, so proceed at your own risk.

![image](https://user-images.githubusercontent.com/2575698/183547942-1d47e174-ccde-4594-9338-a7ce35108441.png)

### Problem with Raspberry Pi Camera and Pi Zero 2

I ran into an issue where the RPI Camera (v1.3 and v2.x) were not working on my Raspberry Pi Zero 2.

Typically you'd check `sudo raspi-config` and make sure the camera is enabled via the interface options.  If that doens't work, you'd then check to make sure the cable on the camera board is not loose.

None of those worked, but adding the following to the `/boot/config.txt` and rebooting file fixed things.
```
start_file=start_x.elf
fixup_file=fixup_x.dat
```

### Arducams and third party non-official camers

You may need to update the /boot/config.txt file (`sudo vim /boot/config.txt`) for your specific camera.  ie: `dtoverlay=imx290` or `dtoverlay=arducam-pivariety`, then reboot

If using an Arducam Pivariety IMX462 (like I am), you don't need the pivariety daughterboard; just the camera directly into the Pi.  Most Arducams should work automatically or with a single line change (in my case, adding `dtoverlay=imx290`), but a couple others might still need some further work.

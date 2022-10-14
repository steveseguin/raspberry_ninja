# A version for the Nvidia Jetson

This is very much like the RPI version, but uses the Nvidia Jetson (Nano/NX/AGX).  The Nvidia Jetson tends to have more power and likely will give better results; it is more expensive though.  1080p30 should be quite easy for an Nvidia Jetson to handle, which can't be said for a Raspberry Pi.

### Installing from an Image

While you can probably install Raspberry_ninja onto any Linux flavour, Nvidia's Jetpack Ubuntu version contains the drivers needed to make use of the hardware encoder. I provide some pre-built images, that are setup with all the depedencies needed to run Raspberry_Ninja, but you can use the official image and DIY also.

#### Instalilng on Jetson without original Nvidia image?

If you aren't using the Nvidia Jetson image, or you've messed things up, you can download the gst-files provided by Nvidia on that image here, [libgstnvidia.zip](https://github.com/steveseguin/raspberry_ninja/blob/main/nvidia_jetson/libgstnvidia.zip?raw=true), as a zip:


Assuming you bypass any related errors in the install script, you'll need to extract and copy those files to this folder, once the install script finishes:
`/usr/local/lib/aarch64-linux-gnu/gstreamer-1.0$`

You can also try copying those files to the following folder, before running the script, and hope the script detects them correctly without errors:
`/usr/lib/aarch64-linux-gnu/gstreamer-1.0/`

#### Steve provided builds

The newest builds for Jetson devices require just 16-GB uSD card.  The older ones required 32-GB, but those are for Jetsons running older firmware only.

You can use Win32DiskImager (https://sourceforge.net/projects/win32diskimager/) to write this image to a disk.  If you need to format your SD card first, you can use the SD Card Formatter (https://www.sdcard.org/downloads/formatter/).

If you have problems with Win32DiskImager, [Bletcher](https://www.balena.io/etcher/) might be an option? 

##### Newest Jetson Nano image below, updated June 6th, 2022.

[https://drive.google.com/file/d/19furxqmPBb2FLWqAxd4ZfIVPNimNDztt/view?usp=sharing](https://drive.google.com/file/d/19furxqmPBb2FLWqAxd4ZfIVPNimNDztt/view?usp=sharing)


The above image was built on a Jetson Nano 2GB developer kit, model A02, with up-to-date firmware.  It may work with other Jetson models.

- It might work with other Jetson systems.
- GStreamer 1.20.2 installed.
- It's is sized down to a 12-GB system drive, ~2-GB zipped, so a 16-GB SD/Drive is needed.
- username is `vdo` and the password is `ninja`
- comes with Chromium still installed

If the Jetson fails to boot after installing it, try an older image, provided below, or considering updating the firmware on your Jetson to something newer.  If nothing else works, you can build Raspberry_ninja from scratch using the installer.sh file, located in the `nvidia_jetson` folder.

Steve is also available on Discord at discord.vdo.ninja to help support.

##### Older image compatible with Jetson A02 with old firmware
The follow **Jetson Nano-2GB image**, build with Gstreamer 1.19.2, is out of date, but might work on older Jetson boards if problems occur with the newer ones. Requires a large 32-GB SD card or a 64-GB card.

```
https://drive.google.com/file/d/1WTsW_dWkggGhQXa8p9yOIz3E4tYcl6ee/view?usp=sharing
```
The username and password to sign in to the image is:
```
username: ninja
password: vdo
```

##### Older image compatible built on a Jetson Xavier NX with old firmware

This is another old image, built on the Xavier NX. Try a newer image before giving this a go.
```
https://drive.google.com/file/d/1gMB4CDnnbFmIhsbYMqrAjluhn7oS7a03/view?usp=sharing
```

The username and password to sign in to the image is:
```
username: ninja
password: vdo
```

* These older Steve-provided builds may not come with Chromium installed


### Once you have logged in

Once you have logged in, at the terminal you can download the repo by running:

```
git clone https://github.com/steveseguin/raspberry_ninja/
```

#### Nvidia provided builds

The official Nvidia Jetson builds are running Ubuntu 18, with Gstreamer 1.14. This version is too old to run VDO.Ninja correctly, so it's recommend that at least Gstreamer 1.16 is used. You can use the provided installer.sh script to upgrade the official Nvidia images with a newer Gstreamer version.  The installer.sh script expects a FRESH image install and it may need some dependencies tweaks over time.

The link to the **official Nvidia images** are here: https://developer.nvidia.com/embedded/downloads

After the Jetson is running, you have connect to the Jetson and pull the raspberry_ninja code and finalize the setup.

```
git clone https://github.com/steveseguin/raspberry_ninja/
cd raspberry_ninja
cd nvidia_jetson
chmod +x installer.sh
sudo ./installer.sh
```
You may need to babysit the installation, and it could take a couple hours if things go smoothly. 


#### Auto-start service on boot

You can refer to Raspberry Pi service script below for a sample start-up script for the Jetson
https://github.com/steveseguin/raspberry_ninja/blob/main/raspberry_pi/raspininja.service

The setup and installation instructions for the start-up script are similar, which can be found here:
https://github.com/steveseguin/raspberry_ninja/tree/main/raspberry_pi#setting-up-auto-boot

The follow bits of the service script may need to be modified or removed if you face issues:
```
User=vdo
Group=vdo
Environment=XDG_RUNTIME_DIR=/run/user/1000
ExecStartPre=vcgencmd get_camera
```

#### Details on Nvidia's Gstreamer implementation

Details on the Nvidia encoder and pipeline options:
https://docs.nvidia.com/jetson/l4t/index.html#page/Tegra%20Linux%20Driver%20Package%20Development%20Guide/accelerated_gstreamer.html#wwpID0E0A40HA

![image](https://user-images.githubusercontent.com/2575698/127804472-073ce656-babc-450a-a7a5-754493ad1fd8.png)

![image](https://user-images.githubusercontent.com/2575698/127804558-1560ad4d-6c2a-4791-92ca-ca50d2eacc2d.png)

### PROBLEMS

##### Just doens't work

If you have an error or things just don't work, saying "START PIPE" but nothing happens, make sure the correct device is specified

video0 or video1 or whatever should align with the location of your video device.  
```PIPELINE_DESC = "v4l2src device=/dev/video1 io-mode=2 ! image/jpeg,framerate ...```

Using ```$ gst-device-monitor-1.0``` can help you list available devices and their location

![image](https://user-images.githubusercontent.com/2575698/128388731-335aaf3d-5f31-4185-b9f2-b7b8fe748d6b.png)

#### other problems

Make sure the camera/media device supports MJPEG output, else see the script file for examples of other options.  Things may not work if your device needs be changed up, but MJPEG is pretty common.

#### nvjpegdec not found

Make sure you've correctly installed the install script or that you have moved the nvidia-provided gstreamer plugins into the correct folder. The Nvidia version of Raspberry Ninja is currently for the Jetson; not desktops.

# A version for the Nvidia Jetson

This is very much like the RPI version, but uses the Nvidia Jetson (Nano/NX/AGX) and the official Nvidia Jetson Ubuntu 18 system image.
https://developer.nvidia.com/embedded/downloads

Trying to upgrade Gstreamer to 1.16 or newer involves nothing but endless pain and suffering, so I'm sticking with the officially supported 1.14. It needs libnice to be added for webRTC support to be available still, and the install script provided attempts to do that.

Even the newest Gstreamer version still have incomplete compatilbity with VDO.Ninja, so this Python scripts uses the legacy-compatible API interface offered by VDO.Ninja; it's enough to still get a basic video/audio stream though to at least one viewer. Potentially more.

Details on the Nvidia encoder and pipeline options:
https://docs.nvidia.com/jetson/l4t/index.html#page/Tegra%20Linux%20Driver%20Package%20Development%20Guide/accelerated_gstreamer.html#wwpID0E0A40HA

![image](https://user-images.githubusercontent.com/2575698/127804981-22787b8f-53c2-4e0d-b3ff-d768be597536.png) ![image](https://user-images.githubusercontent.com/2575698/127804578-c949f689-9bfb-409f-8c6f-6f23ff338abb.png)

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

#### nvjpegdec notg found

Make sure you've correctly installed the install script provided.  Go thru it line by line of the install script to make sure it all works if you need to.  Also, this install script assumes a brand new and clean Jetson image; please at least update first or grab a spare uSD card to try a clean image.

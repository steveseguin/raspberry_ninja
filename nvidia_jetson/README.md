# A version for the Nvidia Jetson

This is very much like the RPI version, but uses the Nvidia Jetson (Nano/NX/AGX).  The Nvidia Jetson tends to have more power and likely will give better results; it is more expensive though.

### Installing from an Image

While you can probably install Raspberry_ninja onto any Linux flavour, Nvidia's Jetpack Ubuntu version contains the drivers needed to make use of the hardware encoder. I provide some pre-built images, that are setup with all the depedencies needed to run Raspberry_Ninja, but you can use the official image and DIY also.

#### Steve provided builds
You can use Win32DiskImager to write this image to a disk.  If you need to format your SD card first, you can use the SD Card Formatter app.  Links are in google.

Jetson Nano 2GB image, with Gstreamer 1.19.2 setup and ready to go:
https://vdoninja.s3.amazonaws.com/jetson_2gb_ninja.zip

```
username: ninja
password: vdo
```

#### Nvidia provided builds

The official Nvidia Jetson builds are running Ubuntu 18, with Gstreamer 1.14.  Gstreamer 1.14 is capable of running the "basic" version of Raspberry Ninja, but not the advanced versions. You can use the provided advanced_install.sh script to upgrade the official Nvidia images with a newer Gstreamer version.  The advanced_install.sh expects a FRESH image install and it may need some dependencies tweaks over time.

The link to the official Nvidia images are here: https://developer.nvidia.com/embedded/downloads

If you wish to just use Gstreamer 1.14 and not run the advanced versions of Raspberry_ninja, you may still need to install websockets for python.  For example, something like this:
```
sudo apt-get update
sudo apt-get install python3-pip -y
sudo apt-get install websockets -y
```

##### Details on Nvidia's Gstreamer implementation

Details on the Nvidia encoder and pipeline options:
https://docs.nvidia.com/jetson/l4t/index.html#page/Tegra%20Linux%20Driver%20Package%20Development%20Guide/accelerated_gstreamer.html#wwpID0E0A40HA

![image](https://user-images.githubusercontent.com/2575698/127804981-22787b8f-53c2-4e0d-b3ff-d768be597536.png) ![image](https://user-images.githubusercontent.com/2575698/127804578-c949f689-9bfb-409f-8c6f-6f23ff338abb.png)

![image](https://user-images.githubusercontent.com/2575698/127804472-073ce656-babc-450a-a7a5-754493ad1fd8.png)

![image](https://user-images.githubusercontent.com/2575698/127804558-1560ad4d-6c2a-4791-92ca-ca50d2eacc2d.png)

### Adding audio

Running the following from the command line will give us access to audio device IDs
 ```
 pactl list | grep -A2 'Source #' | grep 'Name: ' | cut -d" " -f2
 ```
 resulting in..
```
alsa_input.usb-MACROSILICON_2109-02.analog-stereo
alsa_output.platform-sound.analog-stereo.monitor
alsa_input.platform-sound.analog-stereo
```
Our HDMI audio source is the first in the list, so that is our device name.

We can then modify our Gstreamer Pipeline in the server.py file, to add audio:
```
PIPELINE_DESC = "v4l2src device=/dev/video0 io-mode=2 ! image/jpeg,framerate=30/1,width=1920,height=1080 ! jpegparse ! nvjpegdec ! video/x-raw ! nvvidconv ! video/x-raw(memory:NVMM) ! omxh264enc bitrate="+bitrate+"000 ! video/x-h264, stream-format=(string)byte-stream ! h264parse ! rtph264pay config-interval=-1 ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! webrtcbin stun-server=stun://stun4.l.google.com:19302 name=sendrecv pulsesrc device=alsa_input.usb-MACROSILICON_2109-02.analog-stereo ! audioconvert ! audioresample ! queue ! opusenc ! rtpopuspay ! queue ! application/x-rtp,media=audio,encoding-name=OPUS,payload=96 ! sendrecv. "
```
Note how we used device = OUR_AUDIO_DEVICE_NAME

Finally, we can run the script as so:
```
python3 server.py
```
If you run it with sudo, you might get a permissions error.

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

Make sure you've correctly installed the install script provided.  Go thru it line by line of the install script to make sure it all works if you need to.  Also, this install script assumes a brand new and clean Jetson image; please at least update first or grab a spare uSD card to try a clean image.

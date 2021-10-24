# <img src="https://user-images.githubusercontent.com/2575698/107161314-f6523f80-6969-11eb-9e9b-9135554b87b5.png"  width="50" />  Raspberry Ninja
Turn your Raspberry Pi or Nvidia Jetson into a ninja-cam with hardware-acceleration enabled! This lets you publish live streaming video and audio directly to your web browser or OBS instance using VDO.Ninja.  Achieve very low streaming latency over the Internet or a LAN; all for free.

### Preface

The core concepts and code used in this project can be reused for other projects; most Linux systems, and a large variety of embedded systems; potentially even smartphones. There's a focus of supporting Raspberry Pis and Nvidia Jetson systems, which includes offering pre-built images and install scripts. Other Linux system users should still be able to use the code, but setup support will be limited.

Youtube video demoing: https://youtu.be/J0qqXxHNU_c

![image](https://user-images.githubusercontent.com/2575698/127951812-b799a6e6-f77e-4749-8ef1-15221b842805.png) 

Please note, as an alternative to this low-level approach to publishing with a Rpi, please consider using something like a Chromebook, especially if not connecting over a wired LAN network. Packet loss isn't tolerated well with this script yet, so you need a prestine connection for things to work well. 

If you wish to play a video back, using a Raspberry pi, try this "kiosk" mode image that can be found here: https://awesomeopensource.com/project/futurice/chilipie-kiosk. Raspberry Pis seem to handle video playback in Chromium-based browsers pretty well; it's just the encoding they don't do well in browser yet.

### Setup for a Raspberry Pi

See the `raspberry_pi` sub-folder for instructions on installing and setting up a Raspberry Pi. [Jump there now](raspberry_pi/README.md)

A Raspberry Pi works fairly well with a CSI-connected camera, but USB-based cameras currently struggle a bit with them. As a result, consider buying an Nvidia Jetson Nano 2GB instead of a Raspberry Pi 4 if looking to jump into this all. 
### Setup for an Nvidia Jetson

Please see the `nvidia_jetson` folder for details on installation. [Jump there now](nvidia_jetson/README.md)

![image](https://user-images.githubusercontent.com/2575698/127804651-fc8ce68e-3510-4cd0-9d5a-1953c6aac0d8.png) 

Nvidia Jetsons work well with USB-connected cameras and have a selection of compatible CSI-cameras well. You may need to buy WiFi adapter if it is not included.

### Setup for Linux Desktops

#### Requirements:

You'll want to install Gstreamer 1.16 or newer; emphasis on the newer.  You'll need to ensure `libnice`, `srtp`, `sctp`, and `webrtcbin` are part of that install, along with any media codecs you intend to use.

Python3 is also required, along with `websockets`.  If you have PIP installed, `pip3 install websockets` can get you going there.

### Usage

You should be able to run the script simply with `python3 publish.py`, however lots of options are available for customizing as desired.

```
$ python3 publish.py

usage: publish.py [-h] [--streamid STREAMID] [--server SERVER]
                  [--bitrate BITRATE] [--width WIDTH] [--height HEIGHT]
                  [--framerate FRAMERATE] [--test] [--hdmi] [--v4l2 V4L2]
                  [--rpicam] [--nvidiacsi] [--alsa ALSA] [--pulse PULSE]
                  [--raw] [--h264] [--nvidia] [--rpi] [--novideo] [--noaudio]
                  [--pipeline PIPELINE]

optional arguments:
  -h, --help            show this help message and exit
  --streamid STREAMID   Stream ID of the peer to connect to
  --server SERVER       Handshake server to use, eg:
                        "wss://wss.vdo.ninja:443"
  --bitrate BITRATE     Sets the video bitrate. This is not adaptive, so
                        packet loss and insufficient bandwidth will cause
                        frame loss
  --width WIDTH         Sets the video width. Make sure that your input
                        supports it.
  --height HEIGHT       Sets the video height. Make sure that your input
                        supports it.
  --framerate FRAMERATE
                        Sets the video framerate. Make sure that your input
                        supports it.
  --test                Use test sources.
  --hdmi                Try to setup a HDMI dongle
  --v4l2 V4L2           Sets the V4L2 input device.
  --rpicam              Sets the RaspberryPi input device.
  --nvidiacsi           Sets the input to the nvidia csi port.
  --alsa ALSA           Use alsa audio input.
  --pulse PULSE         Use pulse audio (or pipewire) input.
  --raw                 Opens the V4L2 device with raw capabilities.
  --h264                For PC, instead of VP8, use x264.
  --nvidia              Creates a pipeline optimised for nvidia hardware.
  --rpi                 Creates a pipeline optimised for raspberry pi hadware.
  --novideo             Disables video input.
  --noaudio             Disables audio input.
  --pipeline PIPELINE   A full custom pipeline

```

##### Changing video input sources

Using `gst-device-monitor-1.0` will list available devices and their 'caps', or settings.  This can help determine what GStreamer pipeline changes need to be made in the script or getting info about what video format options are available for your device.

To help further debug, `gst-launch-1.0` can be used to test a pipeline out before adding it to the script. For for added reference, here is an example Pipeline for the Rasbperry Pi to enable UVC-based MJPEG video capture support is:
```
gst-launch-1.0 v4l2src device=/dev/video0 io-mode=2 ! image/jpeg,framerate=30/1,width=1920,height=1080 ! jpegparse ! nvjpegdec ! video/x-raw ! nvvidconv ! "video/x-raw(memory:NVMM)" ! omxh264enc ! "video/x-h264, stream-format=(string)byte-stream" ! h264parse ! rtph264pay config-interval=-1 ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! fakesink
```
Notice how we used device = OUR_AUDIO_DEVICE_NAME to specify the audio device we want to use, and we configure the device to read and decode JPEG, as that is what our device in this case supports.

The Raspberry_Ninja publish.py script automatically tries to create a pipeline for you, based on the command line arguments passed, but you can override that at a code level with your own pipeline if easier as well.

#### Adding an audio source

The script will use the default system ALSA audio output device, although you can override that using the command line arguments or via manually setting a gstreamer pipeline at the code level.

To get details of available audio devices, assuming pulseaudio is installed, running the following from the command line will give us access to audio device IDs
 ```
 pactl list | grep -A2 'Source #' | grep 'Name: ' | cut -d" " -f2
 ```
 resulting in..
```
alsa_input.usb-MACROSILICON_2109-02.analog-stereo
alsa_output.platform-sound.analog-stereo.monitor
alsa_input.platform-sound.analog-stereo
```
In this example, an HDMI audio source is the first in the list, so that is our device name. Your device name will likely vary.

Pulse audio and ALSA audio command-line arguments can be passed to setup audio, without needing to tweak Gstreamer pipelines manually. The defaults I think will use the system ALSA default device.

### How to Run:

Ensure the pi/jetson is connected to the Internet, via Ethernet is recommended for best performance.  You'll also very likely need to ensure a camera and/or microphone input are connected; this can also be a USB UVC device, supported CSI-based camera, or other selectable media inputs. It technically might be possible to even select a pipe to stream from, although this is a fairly advanced option.

Run using:
`python3 publish.py --streamid SomeStreamID --bitrate 4000`

In Chrome, open this link to view:
`https://vdo.ninja/?password=false&view=SomeStreamID`

One viewer at a time can work at the moment, although I am hoping to address this limitation shortly.

If you run with sudo, you might get a permissions error when using audio.

### Hardware options

There's plenty of options for the Rasbperry Pi and Nvidia Jetson when it comes to cameras and HDMI adapters.

If low-light is important to you, the Sony IMX327 and IMX462 series of sensors might appeal to you. They are generally designed for security camera applications, but with the use of an IR Filter, you can make them adequate for use a standard video cameras.

https://www.uctronics.com/arducam-for-raspberry-pi-ultra-low-light-camera-1080p-hd-wide-angle-pivariety-camera-module-based-on-1-2-7inch-2mp-starvis-sensor-imx462-compatible-with-raspberry-pi-isp-and-gstreamer-plugin.html

https://www.amazon.ca/VEYE-MIPI-327E-forRaspberry-Jetson-XavierNX-YT0-95-4I/dp/B08QJ1BBM1

https://www.e-consystems.com/usb-cameras/sony-starvis-imx462-ultra-low-light-camera.asp

You can buy IR Filters, or you can buy lenses that come with IR filters, if needed, for pretty cheap. 
https://fulekan.aliexpress.com/store/1862644

As per HDMI adapters, a 1080p30 USB 2.0 HDMI to MJPEG adapter can usually be had for $10 to $20, although there are many fake offerings out there. I've tested a $12 MACROSILICON HDMI to USB adapter, and it works pretty well, although finding a legitimate one might be tricky. 

### Note:

- Installation from source is pretty slow and problematic on a rpi; using system images makes using this so much easier.

- Please use the provided backup server for development and testing purposes; that wss server is `wss:/apibackup.obs.ninja:443` and for viewing: `https://backup.vdo.ninja`

- Passwords must be DISABLED explicitly as this code does not yet have the required crypto logic added yet. Things will not playback if you leave off `&password=false`

- The current code does not dynamically adjust resolution to combat frame loss; rather it will just drop frames. As a result, having a high quality connection between sender and viewer is required. Consider lowering the bitrate or resolution if problems persist.


### TODO:

- Add an option for dynamic resolution, based on packet loss indicators. (advanced)

- Add the ability to record an incoming stream directly to disk (blocked by Gstreamer not supporting this yet)

- Add support for passwords and group rooms (steve)

- Make easier to use for novice users; perhaps adding a local web-interface or config file accessible via an SD card reader via Windows. These options could then allow for setting of wifi passwords, device, settings, stream IDs, etc, without needing to SSH in or using nano/vim. (moderate)

### Further Reading:

Details on WebRTC mechanics, Gstreamer, debugging issues, and discussion of Hardware encoders:
 https://cloud.google.com/solutions/gpu-accelerated-streaming-using-webrtc

# <img src="https://user-images.githubusercontent.com/2575698/107161314-f6523f80-6969-11eb-9e9b-9135554b87b5.png"  width="50" />  Raspberry Ninja [wip] 
Turn your Raspberry Pi into a Ninja-cam with hardware-acceleration enabled!  Publish live streaming video to OBS.Ninja. 
### Preface

This code is more a proof of concept at the moment; I wouldn't recommend using things as is for production projects. The core concepts and code used in this project can be reused for other projects, including Nvidia Jetsons, smartphone applications, and for ingesting streams into OBS.Ninja from other video distribution systems.

It be a goal of mine to have http://butcanitrunninja.com/ and https://runs.ninja point to a repo which lists all the different devices and systems that have been made compatible with OBS.Ninja. By the end of 2021, I suspect it would be feasble to have dozens of devices supported, including professional streaming devices like Tricasters.

Please note, as an alternative to this low-level approach to publishing with a Rpi, please consider using Chromium on a raspberry pi to publish instead.  It will likely be software-based video encoding, so the resolution will be limited in comparison, but it will likely be more stable and easier to work with.  A Raspberry pi image that boots into a "kiosk" mode can be found here: https://awesomeopensource.com/project/futurice/chilipie-kiosk ; it probably is a good choice is using a Raspberry Pi 4 so newer.

### Installation

It is recommended to use the provided raspberry pi image, as the install process is otherwise quite challenging.

Download and extract the image file:
https://drive.google.com/file/d/1NchpcHYHcNMvjm7NaBf84ZH0xKgLomXR/view?usp=sharing

Write the image to an SD cards; at least 8GB in size, using the appropriate tool:
https://www.raspberrypi.org/documentation/installation/installing-images/windows.md

SSH is enabled on port 22 if needed.

Login information for the device is:
```
username: pi
password: raspberry
```
And in case you need to connect it to wifi, it's preconfigured to connect to a default wifi network:
```
ssid: raspberry
password: password
```
If you do not want to use the provided image, you can try to install from scratch, but be prepared to a weekend on it. Please see the install script.

The install script is not fully functional right now -- I would love to have someone organize it to run with a fixed version, perhaps gstreamer 1.18, as running master (as I am currently) causes it to break from week to week.  It was working in a few months ago, but I don't have the time to maintain it.

### How to Run:

Ensure the pi is connected to the Internet, via Ethernet recommended.  You will also need an official raspberry pi camera; v1 or v2 will probably work.

Run using:
`python3 server.py --streamid SomeStreamID`

In Chrome, open this link to view:
`https://backup.obs.ninja/?password=false&view=SomeStreamID`

Once done, you need to stop and start the Python script again to connect a new viewer.  One viewer at a time can work at the moment. Hoping to address this limitation with future updates.

### Note:

Installation from source is pretty slow and problematic; using system images makes using this so much easier.

Currently just one viewer can watch a stream before the script needs to be restarted to free up the camera and encoder. A work-in-progress issue.

Please use the provided backup server for development and testing purposes.

Passwords must be DISABLED explicitly as this code does not yet have the required crypto logic added.

### Further Reading:

Details on WebRTC mechanics, Gstreamer, debugging issues, and discussion of Hardware encoders:
 https://cloud.google.com/solutions/gpu-accelerated-streaming-using-webrtc


### Contributions Requested

Adding disconnection event management with garbage collection

Adding support for Multiple viewers using a single encoding pipeline

Nvidia Jetson Build

Organizing the install bash script into something that isn't a complete mess.

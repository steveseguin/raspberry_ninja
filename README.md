# Raspberry Ninja [wip - not quite ready for use yet]
Turn your Raspberry Pi into a Ninja-cam with hardware-acceleration enabled!  Publish live streaming video to OBS.Ninja.

### Installation

It is recommended to use the provided raspberry pi image, as the install process is otherwise quite challenging.

-- link to image here --
username: pi
password: raspberry

If installing from scratch, please see the install script.

### How to Run:

Ensure the pi is connected to the Internet, via Ethernet recommended.

Run using:
`python3 publish.py SomeStreamID`

In Chrome, open this link to view:
`https://backup.obs.ninja/?password=false&view=SomeStreamID`

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

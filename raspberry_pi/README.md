## Installation on a Raspberry Pi

It is recommended to use the provided raspberry pi image, as the install process is otherwise quite challenging.

Download and extract the image file:
https://drive.google.com/file/d/1NchpcHYHcNMvjm7NaBf84ZH0xKgLomXR/view?usp=sharing

Write the image to an SD cards; at least 8GB in size, using the appropriate tool. 
(I'd recommend using balenaEtcher, as the official Raspberry Pi image writer may have problems with the image.)
https://www.raspberrypi.org/documentation/installation/installing-images/windows.md

SSH is enabled on port 22 if needed.

Login information for the device is:
```
username: pi
password: raspberry
```
It's recommend that you connect over Ethernet, but USB works I think, too. Connecting to a Raspberry Pi can be searched for on Google though.

Once connected, you can use the existing server.py file, or you can pull the repo for the newest code version:

```
git clone https://github.com/steveseguin/raspberry_ninja.git
```
The newest code supports streaming over the Internet, rather than just a LAN, so be sure to update if you need that functionality.

* If you do not want to use the provided image, you can try to install from scratch, but be prepared to lose a weekend on it. Please see the install script provided, but others exist online that might be better. Gstreamer 1.14 is required as a minimum, but future versions of this script will probably require at least 1.16.

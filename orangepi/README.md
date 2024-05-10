
<img width="360" src="https://github.com/steveseguin/raspberry_ninja/assets/5319910/63a664aa-acab-4a7e-a836-524b9a4460fb">

## Installation on a Orange Pi

It is recommended to use Orange Pi 5 and Orange Pi 5 Plus, since other model i did test yet.

#### Installing from the provided image

There are no preinstalled image since I don't have time to create it. However, you can download the prebuilt OS from manufaturer website orangepi.org and start to use it

*notes: This guide I think was based on Debian, but it should also work with Ubuntu and maybe other Linux flavours.  For the OP5+, the HDMI input works when using `--raw` as a publish.py parameter, but if not, check to see if the HDMI input is listed when running `gst-device-monitor-1.0`. I can confirm it is listed and works fine with `Armbian_24.2.3_Orangepi5-plus_bookworm_legacy_5.10.160_minimal.img.xz` as of May 10th 2024.  You can use the `--v4l2` parameter to change which video device ID to use, if there is more than one video device connected.

#### Setting up and connecting

Run command to update the board, be sure that python3 and pip are installed

``sudo apt update && sudo apt upgrade -y``

For newer Debian bookworm (ie: newer) versions, either run this or use a virtual environment to ocontinue
``sudo rm /usr/lib/python3.11/EXTERNALLY-MANAGED ``

Install Python PIP

``sudo apt install python3-pip``

#### Installing from scratch

Install some required lib

``sudo apt-get install -y libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev libgstreamer-plugins-bad1.0-dev gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav gstreamer1.0-tools gstreamer1.0-x gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-gtk3 gstreamer1.0-qt5 gstreamer1.0-pulseaudio gstreamer1.0-nice gstreamer1.0-plugins-base-apps git``

Install websocket module

``pip3 install websockets``

You may also need to install PyGObject, such as if running Ubuntu

```
sudo apt-get install -y libcairo-dev
sudo apt-get install python3-dev cmake meson libgirepository1.0-dev ## these may not be needed
pip3 install PyGObject
```

To download Raspberry.Ninja

```
cd ~
git clone https://github.com/steveseguin/raspberry_ninja
cd raspberry_ninja # change into the raspberry_ninja directory
```

## Running things

After all, run the command to test stream, which should show colored bars and play static noise.

``python3 publish.py --test``

If successful, configure command-line as needed, removing `--test`, and customizing as needed.

### Camera considerations

I have tested with RK Camera using the MIPI connector and also USB Webcam, both run well, you just need to edit the file publish.py 

If you use MIPI RKCamera , edit to /dev/video11

If you use USB Camera, edit to /dev/video0 

I found out that /dev/video1 is the HDMI Input but you will need to enter orangepi-config to enable hdmirx first, then it can be use with any HDMI Input, even in high resolution

Orange Pi 5 Plus with usb webcam
![opi5plus-webcam](https://github.com/steveseguin/raspberry_ninja/assets/5319910/25934ec7-da3a-4cff-96ac-5a723840caf4)


### Setting up auto-boot
There is a service file included in the raspberry_pi folder that sets the raspberry pi up to auto-boot. You will need to modify it a tiny bit with the settings to launch by default, such as specifying the stream ID.

To edit the file, you can use VIM.
```
cd ~
cd raspberry_ninja
cd orangepi
sudo vi raspininja.service
```
To use VIM, press i to enter text edit mode. :wq will let you save and exit.

Change the stream ID and anything else.

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

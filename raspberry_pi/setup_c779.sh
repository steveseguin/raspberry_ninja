## This configures the C779 HDMI to CSI adapter for use.

## First, Setup /boot/config.txt ; you will need to uncomment or add a line near the bottom of the file and then save then file.
# ie: dtoverlay=tc358743, dtoverlay=tc358743-audio, dtoverlay=tc358743,4lane=1 or whatever your board/requirements support
## Second, ensure you have enough CMA memory
dmesg | grep cma
# If you have less than 96M, add some more
## cma=96M can be added to /boot/cmdline.txt if needed (leave no blank last line)
## Third, enable the camera module. More recently, you'll need to enable the legacy camera mode to continue.
sudo raspi-config
# -> `-'Interfacing Options' -> '[Legacy] Camera' -> enable and "Finish"
## REBOOT
sudo reboot

wget https://raw.githubusercontent.com/steveseguin/CSI2_device_config/master/1080P50EDID.txt
v4l2-ctl --set-edid=file=1080P50EDID.txt
## If you get an error at this step, check the community forum here: https://forums.raspberrypi.com//viewtopic.php?f=38&t=281972
# https://raw.githubusercontent.com/steveseguin/CSI2_device_config/master/1080P60EDID.txt
# v4l2-ctl --set-edid=file=1080P60EDID.txt ## Only if using a RPi Compute Module, since a basic rpi lacks enough data lanes
## PLUG IN HDMI PLUG NOW
v4l2-ctl --set-dv-bt-timings query
# v4l2-ctl --log-status
v4l2-ctl --query-dv-timings
## Should show the correct resolution output of your camera
## Please note; camera's HDMI output should be in 8-bit color mode, with no more than 1080p50 set, inless using compute module 

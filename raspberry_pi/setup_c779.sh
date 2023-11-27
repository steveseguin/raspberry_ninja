## This configures the C779 HDMI to CSI adapter for use.
## You can also find a guide with your board's manufacture, such as https://wiki.geekworm.com/C779-Software

## First, Setup /boot/config.txt ; you will need to uncomment or add a line near the bottom of the file and then save then file.
# ie: dtoverlay=tc358743, dtoverlay=tc358743-audio, dtoverlay=tc358743,4lane=1 or whatever your board/requirements support
# You may also need "dtoverlay=vc4-kms-v3d" or "dtoverlay=vc4-fkms-v3d" added also. 
########## For reference, my own RPi4 2023 config.txt for the C779 looks like:
##     arm_64bit=1
##     disable_overscan=1
##     [all]
##     dtoverlay=vc4-fkms-v3d
##     max_framebuffers=2
##     dtoverlay=tc358743
####################

## Second, ensure you have enough CMA memory; this probabably isn't an issue, but still...
dmesg | grep cma
# If you have less than 96M, add some more
## cma=96M can be added to /boot/cmdline.txt if needed (leave no blank last line)

## Third, enable the camera module. More recently, you'll need to enable the legacy camera mode to continue.
sudo raspi-config
# -> `-'Interfacing Options' -> '[Legacy] Camera' -> enable and "Finish"
## Fourth, unplug any HDMI input from the board; we will plug an HDMI source in later
## REBOOT
sudo reboot

## you can make your own EDID file; 1080P25 / 1080P30 and even in some cases 1080P60 are possible (but not all!)
wget https://raw.githubusercontent.com/steveseguin/CSI2_device_config/master/1080P50EDID.txt
v4l2-ctl --set-edid=file=1080P50EDID.txt # load it
## If you get an error at this step, check the community forum here: https://forums.raspberrypi.com//viewtopic.php?f=38&t=281972
# https://raw.githubusercontent.com/steveseguin/CSI2_device_config/master/1080P60EDID.txt
# v4l2-ctl --set-edid=file=1080P60EDID.txt ## Only if using a RPi Compute Module, since a basic rpi lacks enough data lanes

## PLUG IN HDMI NOW - and make sure the source (camera or whatever) can support the resolution and frame rate you specified in the EDID
v4l2-ctl --set-dv-bt-timings query
# v4l2-ctl --log-status
v4l2-ctl --query-dv-timings
## Should show the correct resolution output of your camera
## Please note; camera's HDMI output should be in 8-bit color mode, with no more than 1080p50 set, inless using compute module 

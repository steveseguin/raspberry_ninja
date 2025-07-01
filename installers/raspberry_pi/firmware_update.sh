# check if newest version is needed
sudo rpi-eeprom-update

# If not up to date, then we can update
sudo raspi-config
# Advanced Options -> Bootloader Version -> Latest
# Reboot when prompted

## For non RPI4 systems, you can try instead, or also.
sudo apt update
sudo apt full-upgrade
sudo reboot

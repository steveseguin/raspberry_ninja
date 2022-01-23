# check if newest version is needed
sudo rpi-eeprom-update

# If not up to date, then we can update
sudo raspi-config
# Advanced Options -> Bootloader Version -> Latest
# Reboot when prompted

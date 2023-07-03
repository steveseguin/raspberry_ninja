
![opi5-camera-rk](https://github.com/steveseguin/raspberry_ninja/assets/5319910/63a664aa-acab-4a7e-a836-524b9a4460fb)

## Installation on a Orange Pi

It is recommended to use Orange Pi 5 and Orange Pi 5 Plus, since other model i did test yet.

#### Installing from the provided image

There are no preinstalled image since I don't have time to create it. However, you can download the prebuilt OS from manufaturer website orangepi.org and start to use it

#### Setting up and connecting

Run command to update the board, be sure that python3 and pip are installed

`apt update && apt upgrade -y`
`apt install python-pip`

#### Installing from scratch


## Running things


### Camera considerations

I have tested with RK Camera using the MIPI connector and also USB Webcam, both run well, you just need to edit the file publish.py 

If you use MIPI RKCamera , edit to /dev/video11
If you use USB Camera, edit to /dev/video0 

Since /dev/video1 is the HDMI Input but i don't have material to test it

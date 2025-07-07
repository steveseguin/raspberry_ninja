# This will install the driver for the Theta Z1 USB camera with 4K 360 h264 output
## to use run:
## sudo chmod +x theta_z1_install.sh
## ./theta_z1_install.sh

## note: One user said they had to run the installer twice before it all worked?

# Install the Z1 drivers; not really UVC compatible tho
cd ~
git clone https://github.com/ricohapi/libuvc-theta.git
sudo apt install libjpeg-dev
cd libuvc-theta
mkdir build
cd build
cmake ..
make
sudo make install

# Create a gstreamer plugin for the Z1, to bypass need for uvc
cd ~
git clone https://github.com/steveseguin/gst_theta_uvc
cd gst_theta_uvc
cd thetauvc
make

# Copy the plugin to the gstreamer plugin folder so we can use it
sudo cp gstt*so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
# confirm its installed
gst-inspect-1.0 | grep "theta"

# run raspberry_ninja with the z1 enabled
cd ~
cd raspberry_ninja
# Transcodes the inbound compressed stream. Recommended
python3 publish.py --z1

## or if crazy, use the below option for direct-publish, which uses like 150-mbps upload by default.  Only practical over a wired LAN I'd say.
# python3 publish.py --z1passthru  



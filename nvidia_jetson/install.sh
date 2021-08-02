sudo add-apt-repository universe
sudo add-apt-repository multiverse
sudo apt-get update
sudo apt-get install gstreamer1.0-tools gstreamer1.0-alsa \
	          gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
		              gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
			                    gstreamer1.0-libav -y
sudo apt-get install libgstreamer1.0-dev \
	          libgstreamer-plugins-base1.0-dev \
		              libgstreamer-plugins-good1.0-dev \
			                    libgstreamer-plugins-bad1.0-dev -y

gst-inspect-1.0 --version

sudo apt-get install python3
sudo apt-get install python3-pip
sudo pip3 install websockets

sudo apt-get remove meson -y
pip3 uninstall meson
pip3 install --user meson

sudo rm -r libnice || true
git clone https://github.com/libnice/libnice.git
cd libnice
git checkout 0.1.15
git pull origin master
python3 -m meson build
sudo ninja -C build
sudo ninja -C build install
sudo ldconfig
sudo cp /usr/lib/aarch64-linux-gnu/gstreamer-1.0/* /usr/lib/aarch64-linux-gnu/gstreamer-1.0/
gst-inspect-1.0 | grep "nice"

# python3 server.py streamID123
# https://backup.vdo.ninja/?view=streamID123&password=false

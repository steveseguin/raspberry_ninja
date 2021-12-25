#ninja@ninja-desktop:~$ chmod +x test.sh
#ninja@ninja-desktop:~$ sudo ./test.sh

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get dist-upgrade -y

sudo apt-get install ubuntu-release-upgrader-core -y

sudo apt-get remove --purge chromium-browser chromium-browser-l10n -y
sudo dpkg --purge --force-all libopencv-dev  ## this seems needed for the Jetson Nano 4GB ?
sudo apt purge unity
sudo apt-get --fix-broken install -y

sudo rm /etc/update-manager/release-upgrades
sudo do-release-upgrade

for f in /etc/apt/sources.list.d/*; do
  sudo sed -i 's/^\#\s*//' $f
done

sudo apt-get install python3-pip -y
sudo apt-get install git -y
sudo apt-get install cmake -y
sudo apt-get install build-essential yasm cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev -y
sudo pip3 install scikit-build
sudo pip3 install ninja 
sudo pip3 install websockets
pip3 install python-rtmidi

sudo apt-get install apt-transport-https ca-certificates -y


#sudo apt-get remove python-gi-dev -y
#sudo apt-get install python3-gi -y

sudo apt-get install ccache curl bison flex \
	libasound2-dev libbz2-dev libcap-dev libdrm-dev libegl1-mesa-dev \
	libfaad-dev libgl1-mesa-dev libgles2-mesa-dev libgmp-dev libgsl0-dev \
	libjpeg-dev libmms-dev libmpg123-dev libogg-dev libopus-dev \
	liborc-0.4-dev libpango1.0-dev libpng-dev librtmp-dev \
	libtheora-dev libtwolame-dev libvorbis-dev libwebp-dev \
	libjpeg8-dev libgif-dev pkg-config zlib1g-dev libmp3lame-dev \
	libmpeg2-4-dev libopencore-amrnb-dev libopencore-amrwb-dev libcurl4-openssl-dev \
	libsidplay1-dev libx264-dev libusb-1.0 pulseaudio libpulse-dev -y

sudo apt-get install woof -y
sudo apt-get install libatk1.0-dev -y
sudo apt-get install -y libgdk-pixbuf2.0-dev
sudo apt-get install libffi6 libffi-dev -y
sudo apt-get install -y libselinux-dev
sudo apt-get install -y libmount-dev
sudo apt-get install libelf-dev -y
sudo apt-get install libdbus-1-dev -y

export GIT_SSL_NO_VERIFY=1
export PATH=$PATH:/usr/local/bin

#sudo apt-get install --reinstall python3 python3-minimal

cd ~
mkdir nvgst
sudo cp /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstomx.so ./nvgst/
sudo cp /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnv* ./nvgst/


sudo apt-get remove gstreamer1.0* -y
sudo rm /usr/lib/aarch64-linux-gnu/gstreamer-1.0/ -r
sudo rm -rf /usr/lib/gst*
sudo rm -rf /usr/bin/gst*
sudo rm -rf /usr/include/gstreamer-1.0

sudo apt install policykit-1-gnome
/usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1
sudo apt-get install libssl-dev -y
   

cd ~
git clone https://github.com/mesonbuild/meson.git
cd meson
git checkout 0.59.2  ## 1.6.2 is an older vesrion; should be compatible with 1.16.3 though, and bug fixes!!
git fetch --all
sudo python3 setup.py install


sudo apt-get install libwebrtc-audio-processing-dev -y
cd ~
wget http://freedesktop.org/software/pulseaudio/webrtc-audio-processing/webrtc-audio-processing-0.3.1.tar.xz
tar xvf webrtc-audio-processing-0.3.1.tar.xz
cd webrtc-audio-processing-0.3.1
./configure 
make
sudo make install
sudo ldconfig

cd ~
git clone --depth 1 https://chromium.googlesource.com/webm/libvpx
cd libvpx
git pull
make distclean
./configure --disable-examples --disable-tools --disable-unit_tests --disable-docs --enable-shared
sudo make -j4
sudo make install
sudo ldconfig
sudo libtoolize


cd ~
wget https://download.gnome.org/sources/glib/2.70/glib-2.70.0.tar.xz
sudo rm glib-2.70.0 -r || true
tar -xvf glib-2.70.0.tar.xz
cd glib-2.70.0
mkdir build
cd build
meson --prefix=/usr/local -Dman=false ..
sudo ninja
sudo ninja install
sudo ldconfig
sudo libtoolize


cd ~
git clone https://github.com/sctplab/usrsctp.git
cd usrsctp
mkdir build
sudo meson build  --prefix=/usr/local
sudo ninja -C build install -j4
sudo ldconfig
sudo libtoolize


cd ~
wget https://download.gnome.org/sources/gobject-introspection/1.70/gobject-introspection-1.70.0.tar.xz
sudo rm  gobject-introspection-1.70.0 -r || true
tar -xvf gobject-introspection-1.70.0.tar.xz
cd gobject-introspection-1.70.0
mkdir build
cd build
sudo meson --prefix=/usr/local --buildtype=release  ..
sudo ninja
sudo ninja install
sudo ldconfig
sudo libtoolize

cd ~
git clone https://github.com/libnice/libnice.git
cd libnice
mkdir build
cd build
meson --prefix=/usr/local --buildtype=release ..
sudo ninja
sudo ninja install
sudo ldconfig
sudo libtoolize


sudo apt-get install -y wayland-protocols
sudo apt-get install -y libxkbcommon-dev
sudo apt-get install -y libepoxy-dev
sudo apt-get install -y libatk-bridge2.0

cd ~
git clone https://github.com/cisco/libsrtp
cd libsrtp
./configure --enable-openssl --prefix=/usr/local
make -j4
sudo make shared_library
sudo make install -j4
sudo ldconfig
sudo libtoolize


#cd ~
#git clone https://github.com/GStreamer/gst-build
#cd gst-build
#git checkout 1.18.5 ### Old method
#git fetch --all
#sudo meson builddir -Dpython=enabled  -Dgtk_doc=disabled  -Dexamples=disabled -Dbuildtype=release 
#sudo ninja -C builddir
#sudo ninja -C builddir install -j4
#sudo ldconfig
#sudo libtoolize

cd ~
git clone https://github.com/GStreamer/gstreamer
cd gstreamer
git checkout main  ## New Method, but may need you to update dependencies.  Tested with 1.19.2 at least. not newer
git fetch --all
sudo meson builddir -Dpython=enabled  -Dgtk_doc=disabled  -Dexamples=disabled -Dbuildtype=release
sudo ninja -C builddir
sudo ninja -C builddir install -j4
sudo ldconfig
sudo libtoolize

# export PATH=$PATH:/usr/local/bin
sudo cp ~/nvgst/libgstnvarguscamerasrc.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstnvivafilter.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstnvv4l2camerasrc.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstnvvideocuda.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstomx.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstnvjpeg.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstnvvidconv.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstnvvideosink.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstnvtee.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstnvvideo4linux2.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ~/nvgst/libgstnvvideosinks.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/

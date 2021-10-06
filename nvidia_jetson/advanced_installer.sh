sudo apt-get update

sudo apt-get install python3-pip -y
sudo apt-get install git -y
sudo apt-get install cmake -y
sudo apt-get install build-essential yasm cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev -y
sudo pip3 install scikit-build
sudo pip3 install ninja   

sudo apt-get install apt-transport-https ca-certificates -y

sudo apt install python-gi-dev

sudo apt-get install ccache curl bison flex \
	libasound2-dev libbz2-dev libcap-dev libdrm-dev libegl1-mesa-dev \
	libfaad-dev libgl1-mesa-dev libgles2-mesa-dev libgmp-dev libgsl0-dev \
	libjpeg-dev libmms-dev libmpg123-dev libogg-dev libopus-dev \
	liborc-0.4-dev libpango1.0-dev libpng-dev librtmp-dev \
	libtheora-dev libtwolame-dev libvorbis-dev libwebp-dev \
	libjpeg8-dev libgif-dev pkg-config zlib1g-dev libmp3lame-dev \
	libmpeg2-4-dev libopencore-amrnb-dev libopencore-amrwb-dev libcurl4-openssl-dev \
	libsidplay1-dev libx264-dev libusb-1.0 pulseaudio libpulse-dev -y
	


export GIT_SSL_NO_VERIFY=1

cd ~
git clone https://github.com/mesonbuild/meson.git
cd meson
sudo python3 setup.py install
   
cd ~
mkdir nvgst
sudo cp /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstomx.so ./nvgst/
sudo cp /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnv* ./nvgst/
   
sudo rm -rf /usr/bin/gst-*
sudo rm -rf /usr/include/gstreamer-1.0

sudo apt install policykit-1-gnome
/usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1
sudo apt-get install libssl-dev -y
   


cd ~
[ ! -d abseil-cpp ] && git clone https://github.com/abseil/abseil-cpp.git
cd abseil-cpp
git pull
sudo cmake .
sudo make install
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
make -j4
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
git clone https://github.com/cisco/libsrtp
cd libsrtp
./configure --enable-openssl --prefix=/usr/local
make -j4
sudo make shared_library
sudo make install -j4
sudo ldconfig
sudo libtoolize


cd ~
git clone https://github.com/GStreamer/gst-build
cd gst-build
git checkout 1.18.5  ## 1.6.2 is an older vesrion; should be compatible with 1.16.3 though, and bug fixes!!
git fetch --all
sudo meson builddir -Dpython=enabled  -Dgtk_doc=disabled  -Dexamples=disabled -Dbuildtype=release -Dintrospection=disabled --prefix=/usr/local 
sudo ninja -C builddir
sudo ninja -C builddir install -j4
sudo ldconfig
sudo libtoolize


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

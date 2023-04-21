### This has has been tested on April 21st, 2023 on a Nano 2GB /w jetpack 4 firmware updated

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get --fix-broken install -y
sudo apt-get install git -y

## reboot as needed

## If running Ubuntu 18 (default with Jetson nano), we need a newer version Python; v3.6 -> +3.8,
# Why? Gstreamer newer than ~ v1.62 needs a newer Python, and 

sudo apt-get remove chrom* -y  ## we need to remove chrome else it will prevent us from upgrading

 ## Stopping and removing the swap file; we need the space probably to do an upgrade
sudo swapoff -a  ## Stopping and removing the swap file; we need the space probably to do an upgrade
sudo rm swapfile 
sudo apt-get autoremove -y

 ## allow the release upgrade
sudo truncate -s 0 /etc/update-manager/release-upgrades
sudo echo "[DEFAULT]" | sudo tee -a  /etc/update-manager/release-upgrades
sudo echo "Prompt=normal" | sudo tee -a  /etc/update-manager/release-upgrades


sudo apt-get full-upgrade -y  ## start upgrading our operating system

##  reboot as needed

sudo do-release-upgrade -y

##  reboot as needed

sudo swapon -a ## turn swap back on

## Once we have our distro ugpraded to something compatible with Python 3.8, we can now move on

sudo apt-get install cmake -y
sudo apt-get install build-essential yasm cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev -y
sudo pip3 install scikit-build
sudo pip3 install ninja
sudo pip3 install websockets

sudo apt-get install python3 python3-pip -y
sudo apt-get autoremove -y
sudo apt-get install apt-transport-https ca-certificates -y

pip3 install python-rtmidi

#sudo apt-get remove python-gi-dev -y
#sudo apt-get install python3-gi -y
sudo apt-get install -y python3-rtmidi

sudo apt-get install ccache curl bison flex \
        libasound2-dev libbz2-dev libcap-dev libdrm-dev libegl1-mesa-dev \
        libfaad-dev libgl1-mesa-dev libgles2-mesa-dev libgmp-dev libgsl0-dev \
        libjpeg-dev libmms-dev libmpg123-dev libogg-dev libopus-dev \
        liborc-0.4-dev libpango1.0-dev libpng-dev librtmp-dev \
        libtheora-dev libtwolame-dev libvorbis-dev libwebp-dev \
        libjpeg8-dev libgif-dev pkg-config zlib1g-dev libmp3lame-dev \
        libmpeg2-4-dev libopencore-amrnb-dev libopencore-amrwb-dev libcurl4-openssl-dev \
        libsidplay1-dev libx264-dev libusb-1.0 pulseaudio libpulse-dev -y
		
# Get the required libraries
sudo apt-get install autotools-dev automake autoconf \
	autopoint libxml2-dev zlib1g-dev libglib2.0-dev \
	pkg-config bison flex  gtk-doc-tools libasound2-dev \
	libgudev-1.0-dev libxt-dev libvorbis-dev libcdparanoia-dev \
	libpango1.0-dev libtheora-dev libvisual-0.4-dev iso-codes \
	libgtk-3-dev libraw1394-dev libiec61883-dev libavc1394-dev \
	libv4l-dev libcairo2-dev libcaca-dev libspeex-dev libpng-dev \
	libshout3-dev libjpeg-dev libaa1-dev libflac-dev libdv4-dev \
	libtag1-dev libwavpack-dev libpulse-dev libsoup2.4-dev libbz2-dev \
	libcdaudio-dev libdc1394-22-dev ladspa-sdk libass-dev \
	libcurl4-gnutls-dev libdca-dev libdvdnav-dev \
	libexempi-dev libexif-dev libfaad-dev libgme-dev libgsm1-dev \
	libiptcdata0-dev libkate-dev libmms-dev \
	libmodplug-dev libmpcdec-dev libofa0-dev libopus-dev \
	librsvg2-dev librtmp-dev \
	libsndfile1-dev libsoundtouch-dev libspandsp-dev libx11-dev \
	libxvidcore-dev libzbar-dev libzvbi-dev liba52-0.7.4-dev \
	libcdio-dev libdvdread-dev libmad0-dev libmp3lame-dev \
	libmpeg2-4-dev libopencore-amrnb-dev libopencore-amrwb-dev \
	libsidplay1-dev libtwolame-dev libx264-dev libusb-1.0 \
	python-gi-dev yasm python3-dev libgirepository1.0-dev -y

sudo apt-get install -y tar gtk-doc-tools libasound2-dev \
	libmpeg2-4-dev libopencore-amrnb-dev libopencore-amrwb-dev \
	freeglut3 weston wayland-protocols pulseaudio libpulse-dev libssl-dev -y


sudo apt-get install build-essential cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev -y
sudo pip3 install scikit-build
sudo pip3 install ninja 
sudo pip3 install websockets
pip3 install python-rtmidi

sudo apt-get install vim -y

sudo apt-get install apt-transport-https ca-certificates -y


#sudo apt-get remove python-gi-dev -y
#sudo apt-get install python3-gi -y

sudo apt-get install ccache curl bison flex \
	libasound2-dev libbz2-dev libcap-dev libdrm-dev libegl1-mesa-dev \
	libfaad-dev libgl1-mesa-dev libgles2-mesa-dev libgmp-dev libgsl0-dev \
	libjpeg-dev libmms-dev libmpg123-dev libogg-dev libopus-dev \
	liborc-0.4-dev libpango1.0-dev libpng-dev librtmp-dev \
	libtheora-dev libtwolame-dev libvorbis-dev libwebp-dev \
	libgif-dev pkg-config zlib1g-dev libmp3lame-dev \
	libmpeg2-4-dev libopencore-amrnb-dev libopencore-amrwb-dev libcurl4-openssl-dev \
	libsidplay1-dev libx264-dev libusb-1.0 pulseaudio libpulse-dev \
	libomxil-bellagio-dev libfreetype6-dev checkinstall fonts-freefont-ttf -y
	
sudo apt-get install libatk1.0-dev -y
sudo apt-get install -y libgdk-pixbuf2.0-dev
sudo apt-get install libffi6 libffi-dev -y
sudo apt-get install -y libselinux-dev
sudo apt-get install -y libmount-dev
sudo apt-get install libelf-dev -y
sudo apt-get install libdbus-1-dev -y
sudo apt-get install woof -y

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
#git checkout 0.61.5 
#git fetch --all
sudo python3 setup.py install


cd ~
git clone https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing.git
cd webrtc-audio-processing
meson . build -Dprefix=$PWD/install
ninja -C build -j1
ninja -C build install
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
git clone https://github.com/mirror/x264
cd x264
./configure --prefix=/usr --enable-shared --disable-cli
make
make install
sudo make install

cd ~
git clone https://github.com/Haivision/srt
sudo apt-get install tclsh pkg-config cmake libssl-dev build-essential -y
./configure
make
sudo make install 

cd ~
wget https://download.gnome.org/sources/glib/2.75/glib-2.75.2.tar.xz
sudo rm glib-2.75.2 -r || true
tar -xvf glib-2.75.2.tar.xz
cd glib-2.75.2
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
wget https://download.gnome.org/sources/gobject-introspection/1.75/gobject-introspection-1.75.4.tar.xz
sudo rm  gobject-introspection-1.75.4 -r || true
tar -xvf gobject-introspection-1.75.4.tar.xz
cd gobject-introspection-1.75.4
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
[ ! -d gstreamer ] && git clone git://anongit.freedesktop.org/git/gstreamer/gstreamer
cd gstreamer
git pull
sudo rm -r build || true
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

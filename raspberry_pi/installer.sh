
## starting with a brand new official bullseye 32bit image

sudo chmod 777 /etc/resolv.conf
sudo echo "nameserver 1.1.1.1" >> /etc/resolv.conf
sudo chmod 644 /etc/resolv.conf
sudo chattr -V +i /etc/resolv.conf ### lock access
# sudo chattr -i /etc/resolv.conf ### to re-enable write access
sudo systemctl restart systemd-resolved.service

export GIT_SSL_NO_VERIFY=1
export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/usr/lib/gstreamer-1.0
export LD_LIBRARY_PATH=/usr/local/lib/

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get full-upgrade -y 
sudo apt-get dist-upgrade -y
sudo apt-get install vim -y
# sudo rpi-update  ## use at your own risk, if you need it

### REBOOT

# sudo raspi-config ##  --> Interface Options --> I2C  <++++++++++++++++++++ enable i2c

### https://docs.arducam.com/Raspberry-Pi-Camera/Native-camera/Quick-Start-Guide/  (imx417/imx519)
## https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README
## pivariety IMX462 ? see: https://forums.raspberrypi.com/viewtopic.php?t=331213&p=1992004#p1991478

### You may need to increase the swap size if pi zero2 or slower/smaller to avoid system crashes with compiling 
sudo dphys-swapfile swapoff
# sudo echo "CONF_SWAPSIZE=1024" >> /etc/dphys-swapfile
sudo vi /etc/dphys-swapfile
CONF_SWAPSIZE=1024 ## to to file
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
###############################

sudo apt-get install python3 git python3-pip -y
sudo apt-get install build-essential cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev -y
sudo pip3 install scikit-build
sudo pip3 install ninja 
sudo pip3 install websockets
pip3 install python-rtmidi

sudo apt-get install apt-transport-https ca-certificates -y

sudo apt-get remove python-gi-dev -y
sudo apt-get install python3-gi -y
sudo apt-get install python3-pyqt5 -y

sudo apt-get install ccache curl bison flex \
	libasound2-dev libbz2-dev libcap-dev libdrm-dev libegl1-mesa-dev \
	libfaad-dev libgl1-mesa-dev libgles2-mesa-dev libgmp-dev libgsl0-dev \
	libjpeg-dev libmms-dev libmpg123-dev libogg-dev \
	liborc-0.4-dev libpango1.0-dev libpng-dev librtmp-dev \
	libgif-dev pkg-config libmp3lame-dev \
	libopencore-amrnb-dev libopencore-amrwb-dev libcurl4-openssl-dev \
	libsidplay1-dev libx264-dev libusb-1.0 pulseaudio libpulse-dev \
	libomxil-bellagio-dev libfreetype6-dev checkinstall fonts-freefont-ttf -y

sudo apt-get install libcamera-dev
sudo apt-get install libatk1.0-dev -y
sudo apt-get install -y libgdk-pixbuf2.0-dev
sudo apt-get install libffi6 libffi-dev -y
sudo apt-get install -y libselinux-dev
sudo apt-get install -y libmount-dev
sudo apt-get install libelf-dev -y
sudo apt-get install libdbus-1-dev -y

sudo apt-get install autotools-dev automake autoconf \
	autopoint libxml2-dev zlib1g-dev libglib2.0-dev \
	gtk-doc-tools \
	libgudev-1.0-dev libxt-dev libvorbis-dev libcdparanoia-dev \
	libtheora-dev libvisual-0.4-dev iso-codes \
	libgtk-3-dev libraw1394-dev libiec61883-dev libavc1394-dev \
	libv4l-dev libcairo2-dev libcaca-dev libspeex-dev \
	libshout3-dev libaa1-dev libflac-dev libdv4-dev \
	libtag1-dev libwavpack-dev libsoup2.4-dev \
	libcdaudio-dev libdc1394-22-dev ladspa-sdk libass-dev \
	libcurl4-gnutls-dev libdca-dev libdvdnav-dev \
	libexempi-dev libexif-dev libgme-dev libgsm1-dev \
	libiptcdata0-dev libkate-dev \
	libmodplug-dev libmpcdec-dev libofa0-dev libopus-dev \
	librsvg2-dev \
	libsndfile1-dev libsoundtouch-dev libspandsp-dev libx11-dev \
	libxvidcore-dev libzbar-dev libzvbi-dev liba52-0.7.4-dev \
	libcdio-dev libdvdread-dev libmad0-dev \
	libmpeg2-4-dev \
	libtwolame-dev \
	yasm python3-dev libgirepository1.0-dev -y

sudo apt-get install -y tar freeglut3 weston libssl-dev policykit-1-gnome -y
sudo apt-get install libwebrtc-audio-processing-dev libvpx-dev -y

### MESON - specific version
cd ~
git clone https://github.com/mesonbuild/meson.git
cd meson
git checkout 0.64.1 ## everything after this is version 1.x?
git fetch --all
sudo python3 setup.py install

pip3 install pycairo

# AAC - optional (needed for rtmp only really)
cd ~
git clone --depth 1 https://github.com/mstorsjo/fdk-aac.git
cd fdk-aac 
autoreconf -fiv 
./configure 
make -j4 
sudo make install

# AV1 - optional
cd ~
git clone --depth 1 https://code.videolan.org/videolan/dav1d.git
cd dav1d
mkdir build
cd build
meson .. 
ninja 
sudo ninja install
sudo ldconfig
sudo libtoolize

# HEVC - optional
cd ~
git clone --depth 1 https://github.com/ultravideo/kvazaar.git
cd kvazaar
./autogen.sh
./configure
make -j4
sudo make install

sudo apt-get -y install \
    doxygen \
    graphviz \
    imagemagick \
    libavcodec-dev \
    libavdevice-dev \
    libavfilter-dev \
    libavformat-dev \
    libavutil-dev \
    libmp3lame-dev \
    libopencore-amrwb-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-net-dev \
    libsdl2-ttf-dev \
    libsnappy-dev \
    libsoxr-dev \
    libssh-dev \
    libtool \
    libv4l-dev \
    libva-dev \
    libvdpau-dev \
    libvo-amrwbenc-dev \
    libvorbis-dev \
    libwebp-dev \
    libx265-dev \
    libxcb-shape0-dev \
    libxcb-shm0-dev \
    libxcb-xfixes0-dev \
    libxcb1-dev \
    libxml2-dev \
    lzma-dev \
    texinfo \
    libaom-dev \
    libsrt-gnutls-dev \
    zlib1g-dev \
    libgmp-dev \
    libzimg-dev

# SRT - optional
cd ~
sudo apt-get install tclsh pkg-config cmake build-essential -y
git clone https://github.com/Haivision/srt
cd srt
./configure
make
sudo make install
sudo ldconfig

### FFMPEG
cd ~
[ ! -d FFmpeg ] && git clone https://github.com/FFmpeg/FFmpeg.git
cd FFmpeg
git pull
make distclean 
sudo ./configure \
	--extra-cflags="-I/usr/local/include" \
	--arch=armhf \
	--extra-ldflags="-L/usr/local/lib" \
        --extra-libs="-lpthread -lm -latomic" \
	--enable-libaom \
	--enable-libsrt \
	--enable-librtmp \
	--enable-libopus \
	--enable-gmp \
	--enable-version3 \
	--enable-libdrm \
	--enable-shared  \
	--enable-pic \
	--enable-libvpx \
	--enable-libvorbis \
	--enable-libfdk-aac \
	--enable-libvpx \
	--target-os=linux \
	--enable-gpl  \
	--enable-pthreads \
	--enable-libkvazaar \
	--enable-hardcoded-tables \
        --enable-libopencore-amrwb \
        --enable-libopencore-amrnb \
	--enable-nonfree \
	--enable-libmp3lame \
	--enable-libfreetype \
	--enable-libx264 \
	--enable-libx265 \
	--enable-libwebp \
	--enable-mmal \
	--enable-indev=alsa \
	--enable-outdev=alsa \
	--enable-libsnappy \
	--enable-libxml2 \
	--enable-libssh \
	--enable-libsoxr \
	--disable-vdpau \
	--enable-libdav1d  \
	--enable-libass \
        --disable-mmal \
        --enable-omx \
        --enable-omx-rpi \
        --arch=armel \
	--enable-openssl 
libtoolize
make -j4
libtoolize
sudo make install -j4
sudo ldconfig

export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/usr/lib/gstreamer-1.0
export LD_LIBRARY_PATH=/usr/local/lib/
cd ~
wget https://download.gnome.org/sources/glib/2.76/glib-2.76.1.tar.xz -O glib.tar.xz
tar -xvf glib.tar.xz 
cd glib-2.76.1
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

export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/usr/lib/gstreamer-1.0
export LD_LIBRARY_PATH=/usr/local/lib/
cd ~
wget https://download.gnome.org/sources/gobject-introspection/1.76/gobject-introspection-1.76.1.tar.xz -O gobject.tar.xz
sudo rm  gobject-introspection-1.76.1 -r || true
tar -xvf gobject.tar.xz
cd gobject-introspection-1.76.1
mkdir build
cd build
sudo meson --prefix=/usr/local --buildtype=release  ..
sudo ninja
sudo ninja install
sudo ldconfig
sudo libtoolize

systemctl --user enable pulseaudio.socket
sudo apt-get install -y wayland-protocols
sudo apt-get install -y libxkbcommon-dev
sudo apt-get install -y libepoxy-dev
sudo apt-get install -y libatk-bridge2.0


export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/usr/lib/gstreamer-1.0
export LD_LIBRARY_PATH=/usr/local/lib/
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
[ ! -d gstreamer ] && git clone git://anongit.freedesktop.org/git/gstreamer/gstreamer
export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/usr/lib/gstreamer-1.0
export LD_LIBRARY_PATH=/usr/local/lib/
cd gstreamer
git pull
sudo rm -r build || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr/local -Dbuildtype=release -Dgst-plugins-base:gl_winsys=egl -Ddoc=disabled -Dtests=disabled -Dexamples=disabled -Dges=disabled -Dgst-examples:*=disabled -Ddevtools=disabled ..
cd ..
sudo ninja -C build install -j4
sudo ldconfig

### Vanilla LibCamera -- We run it after gstreamer so it detects it and installs the right plugins.
export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/usr/lib/gstreamer-1.0
export LD_LIBRARY_PATH=/usr/local/lib/
sudo apt-get install libyaml-dev python3-yaml python3-ply python3-jinja2 -y
cd ~
git clone https://git.libcamera.org/libcamera/libcamera.git
cd libcamera
meson setup build
sudo ninja -C build install -j4 ## too many cores and you'll crash a raspiberry pi zero 2
sudo ldconfig
cd ~

# modprobe bcm2835-codecfg

## see https://raspberry.ninja for further system optimizations and settings

systemctl --user restart pulseaudio.socket

## If things still don't work, run it all again, a section at a time, making sure it all passes

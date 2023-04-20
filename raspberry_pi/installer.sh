sudo chmod 777 /etc/resolv.conf
sudo echo "nameserver 1.1.1.1" >> /etc/resolv.conf
sudo chmod 644 /etc/resolv.conf
sudo chattr -V +i /etc/resolv.conf ### lock access
# sudo chattr -i /etc/resolv.conf ### to re-enable write access
sudo systemctl restart systemd-resolved.service

export GIT_SSL_NO_VERIFY=1

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get full-upgrade -y 
sudo apt-get dist-upgrade -y
sudo apt-get install vim -y

## sudo raspi-config # ENABLE THE CAMERA

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

# Lib Camera depedencies
sudo apt-get install libyaml-dev python3-yaml python3-ply python3-jinja2 libudev-dev libevent-dev libsdl2-dev qtbase5-dev libqt5core5a libqt5gui5 libqt5widgets5 qttools5-dev-tools libtiff-dev libexif-dev libjpeg-dev libevent-dev texlive y

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

sudo apt-get install policykit-1-gnome -y
/usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1

sudo dphys-swapfile swapoff
# sudo echo "CONF_SWAPSIZE=1024" >> /etc/dphys-swapfile
sudo vi /etc/dphys-swapfile
CONF_SWAPSIZE=1024 ## to to file
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

### MESON 
cd ~
git clone https://github.com/mesonbuild/meson.git
cd meson
git checkout 0.64.1 ## everything after this is version 1.x?
git fetch --all
sudo python3 setup.py install

pip3 install pycairo
sudo apt-get install flex bison -y
sudo apt-get install libwebrtc-audio-processing-dev -y

cd ~
git clone https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing.git
cd webrtc-audio-processing
meson . build -Dprefix=$PWD/install
ninja -C build -j1
ninja -C build install
sudo ldconfig

# https://docs.arducam.com/Raspberry-Pi-Camera/Pivariety-Camera/Quick-Start-Guide/
cd ~
wget -O install_pivariety_pkgs.sh https://github.com/ArduCAM/Arducam-Pivariety-V4L2-Driver/releases/download/install_script/install_pivariety_pkgs.sh
sudo chmod +x install_pivariety_pkgs.sh
./install_pivariety_pkgs.sh -p libcamera_dev
./install_pivariety_pkgs.sh -p libcamera_apps
# Added "dtoverlay=arducam-pivariety,media-controller=0" to the last line of /boot/config.txt if using an arudcam

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
git clone --depth 1 https://github.com/mstorsjo/fdk-aac.git
cd fdk-aac 
autoreconf -fiv 
./configure 
make -j4 
sudo make install

#AV1
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

#HEVC
cd ~
git clone --depth 1 https://github.com/ultravideo/kvazaar.git
cd kvazaar
./autogen.sh
./configure
make -j4
sudo make install

#AP1
cd ~
git clone --depth 1 https://aomedia.googlesource.com/aom
cd aom
mkdir build
cd build
cmake -G "Unix Makefiles" AOM_SRC -DENABLE_NASM=on -DPYTHON_EXECUTABLE="$(which python3)" -DCMAKE_C_FLAGS="-mfpu=vfp -mfloat-abi=hard" ..
sed -i 's/ENABLE_NEON:BOOL=ON/ENABLE_NEON:BOOL=OFF/' CMakeCache.txt
make -j1 # too many cores used and it will crash a pi zero 2; memory usage issue?
sudo make install
sudo ldconfig
sudo libtoolize

#zimg
cd ~
git clone --recursive https://github.com/sekrit-twc/zimg.git
cd zimg
sh autogen.sh
./configure
make
sudo make install
sudo ldconfig
sudo libtoolize

sudo apt-get -y install \
    autoconf \
    automake \
    build-essential \
    cmake \
    doxygen \
    git \
    graphviz \
    imagemagick \
    libasound2-dev \
    libass-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavfilter-dev \
    libavformat-dev \
    libavutil-dev \
    libfreetype6-dev \
    libgmp-dev \
    libmp3lame-dev \
    libopencore-amrnb-dev \
    libopencore-amrwb-dev \
    libopus-dev \
    librtmp-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-net-dev \
    libsdl2-ttf-dev \
    libsnappy-dev \
    libsoxr-dev \
    libssh-dev \
    libssl-dev \
    libtool \
    libv4l-dev \
    libva-dev \
    libvdpau-dev \
    libvo-amrwbenc-dev \
    libvorbis-dev \
    libwebp-dev \
    libx264-dev \
    libx265-dev \
    libxcb-shape0-dev \
    libxcb-shm0-dev \
    libxcb-xfixes0-dev \
    libxcb1-dev \
    libxml2-dev \
    lzma-dev \
    texinfo \
    wget \
    yasm \
    libaom-dev \
    libsrt-gnutls-dev \
    zlib1g-dev


# SRT
cd ~
sudo apt-get install tclsh pkg-config cmake libssl-dev build-essential -y
git clone https://github.com/Haivision/srt
cd srt
./configure
make
sudo make install

sudo apt-get install libdrm-dev libgmp-dev -y
cd ~
[ ! -d FFmpeg ] && git clone https://github.com/FFmpeg/FFmpeg.git
cd FFmpeg
git pull
make distclean 
sudo ./configure --extra-cflags="-I/usr/local/include" --arch=armhf --extra-ldflags="-L/usr/local/lib" --enable-libopencore-amrnb --enable-libzimg --enable-libaom --enable-libsrt --enable-librtmp --enable-libopus --enable-libopencore-amrwb --enable-gmp --enable-version3 --enable-libdrm --enable-shared  --enable-pic --enable-libvpx --enable-libvorbis --enable-libfdk-aac --enable-libvpx --target-os=linux --enable-gpl  --enable-pthreads --enable-libkvazaar --enable-hardcoded-tables --enable-nonfree --enable-libmp3lame --enable-libfreetype --enable-libx264 --enable-libx265 --enable-libwebp --enable-mmal --enable-indev=alsa --enable-outdev=alsa --enable-libsnappy --enable-libxml2 --enable-libssh --enable-libsoxr --disable-vdpau --enable-libdav1d  --enable-libass --extra-ldflags="-latomic"
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

### Vanilla LibCamera
##export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/usr/lib/gstreamer-1.0
##export LD_LIBRARY_PATH=/usr/local/lib/
##cd ~
##git clone https://git.libcamera.org/libcamera/libcamera.git
##cd libcamera
##meson setup build
##sudo ninja -C build install -j1 ## too many cores and you'll crash a raspiberry pi zero 2

## ARDUCAM compatible Libcamera; 
##export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/usr/lib/gstreamer-1.0
##export LD_LIBRARY_PATH=/usr/local/lib/
# https://docs.arducam.com/Raspberry-Pi-Camera/Pivariety-Camera/Quick-Start-Guide/
##cd ~
##wget -O install_pivariety_pkgs.sh https://github.com/ArduCAM/Arducam-Pivariety-V4L2-Driver/releases/download/install_script/install_pivariety_pkgs.sh
##sudo chmod +x install_pivariety_pkgs.sh
##./install_pivariety_pkgs.sh -p libcamera_dev
##./install_pivariety_pkgs.sh -p libcamera_apps
### Added "dtoverlay=arducam-pivariety,media-controller=0" to the last line of /boot/config.txt if using an arudcam

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
sudo ninja -C build install -j1
sudo ldconfig

# modprobe bcm2835-codecfg

systemctl --user restart pulseaudio.socket
sudo rpi-update

## If things still don't work, run it all again, a section at a time, making sure it all passes

### This has has been tested on April 21st, 2023 on a Nano 2GB /w jetpack 4 firmware updated
## Manual involvement is needed at steps...

cd ~
mkdir nvgst
sudo cp /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstomx.so ./nvgst/
sudo cp /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnv* ./nvgst/

sudo mv /var/lib/dpkg/info/ /var/lib/dpkg/backup/
sudo mkdir /var/lib/dpkg/info/

sudo apt-get update
sudo apt autoremove -y

sudo apt-get -f install
sudo mv /var/lib/dpkg/info/* /var/lib/dpkg/backup/
sudo rm -rf /var/lib/dpkg/info
sudo mv /var/lib/dpkg/backup/ /var/lib/dpkg/info/

sudo apt-get upgrade -y
sudo apt-get install git -y

sudo apt-get remove chrom* -y  ## we need to remove chrome else it will prevent us from upgrading

 ## allow the release upgrade
sudo truncate -s 0 /etc/update-manager/release-upgrades
sudo echo "[DEFAULT]" | sudo tee -a  /etc/update-manager/release-upgrades
sudo echo "Prompt=lts" | sudo tee -a  /etc/update-manager/release-upgrades

sudo apt dist-upgrade -y
reboot

do-release-upgrade -f DistUpgradeViewNonInteractive
lsb_release -a  ## should be 20.04 or newer now

##  reboot as needed

# sudo swapon -a ## turn swap back on

## Once we have our distro ugpraded to something compatible with Python 3.8, we can now move on

sudo apt-get install build-essential yasm cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev -y
sudo apt-get install python3 python3-pip -y
sudo apt-get autoremove -y
sudo apt-get install apt-transport-https ca-certificates -y
sudo apt-get install -y python3-rtmidi

sudo pip3 install scikit-build
sudo pip3 install ninja
sudo pip3 install websockets


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

sudo apt-get install -y tar freeglut3 libssl-dev policykit-1-gnome -y
sudo apt-get install libwebrtc-audio-processing-dev libvpx-dev -y

export GIT_SSL_NO_VERIFY=1
export PATH=$PATH:/usr/local/bin

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
    zlib1g-dev \
    libgmp-dev \
    tclsh \
    libvpx-dev

# SRT - optional
cd ~
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
	--enable-omx \
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
        --arch=armel \
	--enable-openssl 
libtoolize
make -j4
libtoolize
sudo make install -j4
sudo ldconfig

sudo apt-get remove gstreamer1.0* -y
sudo rm /usr/lib/aarch64-linux-gnu/gstreamer-1.0/ -r
sudo rm -rf /usr/lib/gst*
sudo rm -rf /usr/bin/gst*
sudo rm -rf /usr/include/gstreamer-1.0

sudo apt-get install -y policykit-1-gnome
sudo apt-get install -y wayland-protocols
sudo apt-get install -y libxkbcommon-dev
sudo apt-get install -y libepoxy-dev
sudo apt-get install -y libatk-bridge2.0

export PATH=$PATH:/usr/local/bin
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

export PATH=$PATH:/usr/local/bin
cd ~
git clone https://github.com/sctplab/usrsctp.git
cd usrsctp
mkdir build
sudo meson build  --prefix=/usr/local
sudo ninja -C build install -j4
sudo ldconfig
sudo libtoolize

export PATH=$PATH:/usr/local/bin
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

export PATH=$PATH:/usr/local/bin
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

export PATH=$PATH:/usr/local/bin
cd ~
git clone https://github.com/cisco/libsrtp
cd libsrtp
./configure --enable-openssl --prefix=/usr/local
make -j4
sudo make shared_library
sudo make install -j4
sudo ldconfig
sudo libtoolize

export PATH=$PATH:/usr/local/bin
cd ~
[ ! -d gstreamer ] && git clone git://anongit.freedesktop.org/git/gstreamer/gstreamer
cd gstreamer
git pull
sudo rm -r build || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr/local -Dbuildtype=release -Dgst-plugins-base:gl_winsys=egl -Ddoc=disabled -Dtests=disabled -Dexamples=disabled -Dges=disabled -Dgst-examples:*=disabled -Ddevtools=disabled ..
cd ..
sudo ninja -C build install -j4
sudo ldconfig

export PATH=$PATH:/usr/local/bin
sudo apt-get install libyaml-dev python3-yaml python3-ply python3-jinja2 -y
cd ~
git clone https://git.libcamera.org/libcamera/libcamera.git
cd libcamera
meson setup build
sudo ninja -C build install -j4 ## too many cores and you'll crash a raspiberry pi zero 2
sudo ldconfig
cd ~

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
sudo rm /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnvcompositor.so # isn't compatible anymore

###################################










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

sudo chmod 777 /etc/resolv.conf
sudo echo "nameserver 1.1.1.1" >> /etc/resolv.conf
sudo chmod 644 /etc/resolv.conf
sudo chattr -V +i /etc/resolv.conf ### lock access
# sudo chattr -i /etc/resolv.conf ### to re-enable write access
sudo systemctl restart systemd-resolved.service

export GIT_SSL_NO_VERIFY=1

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get dist-upgrade -y
sudo apt-get install vim -y

sudo apt-get install python3 git python3-pip -y
sudo apt-get install build-essential cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev -y
sudo pip3 install scikit-build
sudo pip3 install ninja 
sudo pip3 install websockets
sudo pip3 install rtmidi python-rtmidi

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


# Get the required libraries
sudo apt-get install -y --force-yes autotools-dev automake autoconf \
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
	libiptcdata0-dev libkate-dev libmimic-dev libmms-dev \
	libmodplug-dev libmpcdec-dev libofa0-dev libopus-dev \
	librsvg2-dev librtmp-dev libschroedinger-dev libslv2-dev \
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
git clone --depth 1 https://github.com/mstorsjo/fdk-aac.git
cd fdk-aac 
autoreconf -fiv 
./configure 
make -j4 
sudo make install


sudo apt-get install libdrm-dev -y
cd ~
[ ! -d FFmpeg ] && git clone https://github.com/FFmpeg/FFmpeg.git
cd FFmpeg
git pull
make distclean 
sudo ./configure --extra-cflags="-I/usr/local/include" --extra-ldflags="-L/usr/local/lib" --enable-libopencore-amrnb  --enable-librtmp --enable-libopus --enable-libopencore-amrwb --enable-gmp --enable-version3 --enable-libdrm --enable-shared  --enable-pic --enable-libvpx --enable-libfdk-aac --target-os=linux --enable-gpl --enable-omx --enable-omx-rpi --enable-pthreads --enable-hardcoded-tables  --enable-omx --enable-nonfree --enable-libfreetype --enable-libx264 --enable-libmp3lame --enable-mmal --enable-indev=alsa --enable-outdev=alsa --disable-vdpau --extra-ldflags="-latomic"
libtoolize
make -j4
libtoolize
sudo make install -j4
sudo ldconfig

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

systemctl --user enable pulseaudio.socket
sudo apt-get install -y wayland-protocols
sudo apt-get install -y libxkbcommon-dev
sudo apt-get install -y libepoxy-dev
sudo apt-get install -y libatk-bridge2.0


cd ~
[ ! -d src ] && mkdir src
cd src
[ ! -d gstreamer ] && mkdir gstreamer
cd gstreamer

[ ! -d gstreamer ] && git clone git://anongit.freedesktop.org/git/gstreamer/gstreamer
[ ! -d gst-plugins-base ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-plugins-base
[ ! -d gst-plugins-good ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-plugins-good
[ ! -d gst-plugins-bad ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-plugins-bad
[ ! -d gst-plugins-ugly ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-plugins-ugly
[ ! -d gst-omx ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-omx
[ ! -d gst-python ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-python
[ ! -d gst-rtsp-server ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-rtsp-server
[ ! $RPI ] && [ ! -d gstreamer-vaapi ] && git clone git://anongit.freedesktop.org/git/gstreamer/gstreamer-vaapi


export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/usr/lib/gstreamer-1.0
export LD_LIBRARY_PATH=/usr/local/lib/


cd gstreamer
git pull
sudo rm -r build || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr/local -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
cd ..
sudo ninja -C build install -j4
cd ..

cd gst-plugins-base
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr/local -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
cd ..
sudo ninja -C build install -j4
cd ..

cd gst-plugins-good
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr/local -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled 
cd ..
sudo ninja -C build install -j4
cd ..

cd gst-plugins-ugly
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr/local -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
cd ..
sudo ninja -C build install -j4
cd ..


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


cd gst-plugins-bad
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
sudo meson build --prefix=/usr/local -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled -Dexamples=disabled -Dx11=disabled -Dglx=disabled -Dopengl=disabled -D target=rpi -D header_path=/opt/vc/include/IL/ 
sudo ninja -C build install -j4
cd ..

cd gst-python
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
sudo meson build --prefix=/usr/local -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
sudo ninja -C build install -j4
cd ..

cd gst-omx
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
sudo meson build -D target=rpi -D header_path=/opt/vc/include/IL/ --prefix=/usr/local -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled -Dexamples=disabled -Dx11=disabled -Dglx=disabled -Dopengl=disabled
sudo ninja -C build install -j4
cd ..
sudo ldconfig

modprobe bcm2835-codecfg

systemctl --user restart pulseaudio.socket
sudo rpi-update

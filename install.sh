## last tested on Nov 6, 2020

sudo apt-get update -y
sudo apt-get upgrade -y 
sudo apt-get update -y

sudo apt-get install vim -y
#!/bin/bash --debugger
set -e

if grep -q BCM2708 /proc/cpuinfo; then
    echo "RPI BUILD!"
    RPI="1"
fi

grep -q BCM2 /proc/cpuinfo && sudo apt-get update && sudo apt-get upgrade -y

#echo "deb http://www.deb-multimedia.org buster main non-free" >> /etc/apt/sources.list
#apt-get update -oAcquire::AllowInsecureRepositories=true
#apt-get install deb-multimedia-keyring -y

#sudo dpkg --remove libnice-dev libsrtp2-dev libusrsctp-dev
sudo apt autoremove -y
sudo apt-get install libomxil-bellagio-dev libfreetype6-dev libmp3lame-dev checkinstall libx264-dev fonts-freefont-ttf libasound2-dev meson -y

# Create a log file of the build as well as displaying the build on the tty as it runs
exec > >(tee build_gstreamer.log)
exec 2>&1

# Update and Upgrade the Pi, otherwise the build may fail due to inconsistencies
grep -q BCM2708 /proc/cpuinfo && sudo apt-get update && sudo apt-get upgrade -y --force-yes

sudo apt-get remove libtag1-vanilla -y
sudo apt-get install g++ git scons libqt4-dev libqt4-sql-sqlite libportmidi-dev \
  libopusfile-dev libshout3-dev libtag1-dev libprotobuf-dev protobuf-compiler \
  libusb-1.0-0-dev libfftw3-dev libmad0-dev \
  portaudio19-dev libchromaprint-dev librubberband-dev libsqlite3-dev \
  libid3tag0-dev libflac-dev libsndfile1-dev libupower-glib-dev liblilv-dev -y
sudo apt-get install libjack-dev libjack0 portaudio19-dev -y # because of Bug #1464120
sudo apt-get install libfaad-dev libmp4v2-dev -y # required for M4A support
sudo apt-get install libmp3lame-dev -y
sudo apt-get install cmake -y

# Get the required libraries
sudo apt-get install -y --force-yes build-essential autotools-dev automake autoconf \
                                    libtool autopoint libxml2-dev zlib1g-dev libglib2.0-dev \
                                    pkg-config bison flex python3 git gtk-doc-tools libasound2-dev \
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

sudo apt-get install -y build-essential autotools-dev automake autoconf checkinstall \
                                    libtool autopoint libxml2-dev zlib1g-dev libglib2.0-dev \
                                    pkg-config bison flex python3 wget tar gtk-doc-tools libasound2-dev \
                                    libgudev-1.0-dev libvorbis-dev libcdparanoia-dev \
                                    libtheora-dev libvisual-0.4-dev iso-codes \
                                    libraw1394-dev libiec61883-dev libavc1394-dev \
                                    libv4l-dev libcaca-dev libspeex-dev libpng-dev \
                                    libshout3-dev libjpeg-dev libflac-dev libdv4-dev \
                                    libtag1-dev libwavpack-dev libsoup2.4-dev libbz2-dev \
                                    libcdaudio-dev libdc1394-22-dev ladspa-sdk libass-dev \
                                    libcurl4-gnutls-dev libdca-dev libdvdnav-dev \
                                    libexempi-dev libexif-dev libfaad-dev libgme-dev libgsm1-dev \
                                    libiptcdata0-dev libkate-dev libmimic-dev libmms-dev \
                                    libmodplug-dev libmpcdec-dev libofa0-dev libopus-dev \
                                    librtmp-dev libsndfile1-dev libsoundtouch-dev libspandsp-dev \
                                    libxvidcore-dev libvpx-dev libzvbi-dev liba52-0.7.4-dev \
                                    libcdio-dev libdvdread-dev libmad0-dev libmp3lame-dev \
                                    libmpeg2-4-dev libopencore-amrnb-dev libopencore-amrwb-dev \
                                    libsidplay1-dev libtwolame-dev libx264-dev libusb-1.0 \
                                    python-gi-dev yasm python3-dev libgirepository1.0-dev \
                                    freeglut3 weston wayland-protocols pulseaudio libpulse-dev libssl-dev -y

sudo apt-get install autotools-dev gnome-pkg-tools libtool libffi-dev libelf-dev \
        libpcre3-dev desktop-file-utils libselinux1-dev libgamin-dev dbus \
        dbus-x11 shared-mime-info libxml2-utils \
        libssl-dev libreadline-dev libsqlite3-dev -y

sudo apt-get install ccache git curl bison flex yasm python3-pip \
        libasound2-dev libbz2-dev libcap-dev libdrm-dev libegl1-mesa-dev \
        libfaad-dev libgl1-mesa-dev libgles2-mesa-dev libgmp-dev libgsl0-dev \
        libjpeg-dev libmms-dev libmpg123-dev libogg-dev libopus-dev \
        liborc-0.4-dev libpango1.0-dev libpng-dev libpulse-dev librtmp-dev \
        libtheora-dev libtwolame-dev libvorbis-dev libvpx-dev libwebp-dev \
        pkg-config unzip zlib1g-dev -y

sudo apt-get install libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev -y

cd ~
[ ! -d meson ] && git clone https://github.com/mesonbuild/meson.git
cd meson
sudo python3 setup install

cd ~
[ ! -d glib ] && git clone https://github.com/GNOME/glib.git 
cd glib
git pull || true
sudo rm -r build || true
[ ! -d build ] && mkdir build
sudo meson build
sudo ninja -C build install -j4
sudo ldconfig

cd ~
[ ! -d fdk-aac ] && git clone https://github.com/mstorsjo/fdk-aac
cd fdk-aac
git pull
./autogen.sh --prefix=/usr --enable-shared --enable-compile-warnings=no
./configure
libtoolize
make -j4
libtoolize
sudo make install -j4
sudo ldconfig

cd ~
sudo rm -r libnice || true
[ ! -d libnice ] && git clone https://github.com/libnice/libnice.git -b 0.1.16
cd libnice
############  NEW CODE, but invalild
#git pull
#sudo meson builddir
#sudo ninja -C builddir
#sudo ninja -C builddir install
############### OLD Method that fails for me now
#git checkout -b release/0.1.16 origin/master
#cd agent
#rm agent-priv.h
#rm connecheck.c
#rm outputstream.c
#wget https://gitlab.freedesktop.org/libnice/libnice/uploads/eea94598d97de9d18a5e5a8c135a0767/agent-priv.h
#wget https://gitlab.freedesktop.org/libnice/libnice/uploads/52e70b46da7c2396db56ea59f314a1a5/conncheck.c
#wget https://gitlab.freedesktop.org/libnice/libnice/uploads/a237b809e0b9f14c9fc1706a707e85ea/outputstream.c
#cd ..
libtoolize
./autogen.sh --prefix=/usr --with-gstreamer --enable-static --enable-static-plugins --enable-shared --without-gstreamer-0.10 --disable-gtk-doc --enable-compile-warnings=minimum --with-crypto-library=auto   
libtoolize
make -j4
sudo make install -j4
sudo ldconfig
cd gst
sudo make install
sudo cp /usr/lib/gstreamer-1.0/* /usr/lib/arm-linux-gnueabihf/gstreamer-1.0/

sudo apt-get remove libsrtp-dev -y
cd ~
[ ! -d libsrtp ] && git clone https://github.com/cisco/libsrtp/
cd libsrtp
git pull
./configure --prefix=/usr --enable-openssl
make -j4
sudo make install -j4

cd ~
[ ! -d abseil-cpp ] && git clone https://github.com/abseil/abseil-cpp.git
cd abseil-cpp
git pull
sudo cmake .
sudo make install
sudo ldconfig

cd ~
[ ! -d webrtc-audio-processing ] && git clone git://anongit.freedesktop.org/pulseaudio/webrtc-audio-processing
cd webrtc-audio-processing
git pull
sudo rm -r build
[ ! -d build ] && mkdir build
sudo meson build || true
sudo ninja -C build install -j4 || true

sudo apt-get remove libsctp-dev -y
cd ~
[ ! -d usrsctp ] && git clone https://github.com/sctplab/usrsctp
cd usrsctp
git pull
./bootstrap
libtoolize
./configure --prefix=/usr
libtoolize
make -j4
sudo make install -j4


cd ~
git clone --depth 1 https://github.com/mstorsjo/fdk-aac.git ~/ffmpeg-libraries/fdk-aac \
  && cd ~/ffmpeg-libraries/fdk-aac \
  && autoreconf -fiv \
  && ./configure \
  && make -j4 \
  && sudo make install

cd ~
git clone --depth 1 https://chromium.googlesource.com/webm/libvpx ~/ffmpeg-libraries/libvpx \
  && cd ~/ffmpeg-libraries/libvpx \
  && make distclean \
  && ./configure --disable-examples --disable-tools --disable-unit_tests --disable-docs --enable-shared \
  && make -j4 \
  && sudo make install

sudo ldconfig



git clone -b release-2.9.3 https://github.com/sekrit-twc/zimg.git ~/ffmpeg-libraries/zimg \
  && cd ~/ffmpeg-libraries/zimg \
  && sh autogen.sh \
  && ./configure \
  && make \
  && sudo make install

cd ~
[ ! -d FFmpeg ] && git clone https://github.com/FFmpeg/FFmpeg.git
cd FFmpeg
git pull
make distclean 
#sudo ./configure --enable-shared  --enable-pic --enable-libvpx --enable-libfdk-aac --target-os=linux --enable-gpl --enable-omx --enable-omx-rpi --enable-nonfree --enable-libfreetype --enable-libx264 --enable-libmp3lame --enable-mmal --enable-indev=alsa --enable-outdev=alsa --disable-vdpau --extra-ldflags="-latomic"
sudo ./configure --extra-cflags="-I/usr/local/include" --extra-ldflags="-L/usr/local/lib" --enable-libopencore-amrnb  --enable-librtmp --enable-libopus --enable-libopencore-amrwb --enable-gmp --enable-version3 --enable-libdrm --enable-shared  --enable-pic --enable-libvpx --enable-libfdk-aac --target-os=linux --enable-gpl --enable-omx --enable-omx-rpi --enable-pthreads --enable-hardcoded-tables  --enable-omx --enable-nonfree --enable-libfreetype --enable-libx264 --enable-libmp3lame --enable-mmal --enable-indev=alsa --enable-outdev=alsa --disable-vdpau --extra-ldflags="-latomic"
libtoolize
make -j4
libtoolize
sudo make install -j4
sudo ldconfig

# get the repos if they're not already there
cd $HOME
[ ! -d src ] && mkdir src
cd src
[ ! -d gstreamer ] && mkdir gstreamer
cd gstreamer

# get repos if they are not there yet
[ ! -d gstreamer ] && git clone git://anongit.freedesktop.org/git/gstreamer/gstreamer
[ ! -d gst-plugins-base ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-plugins-base
[ ! -d gst-plugins-good ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-plugins-good
[ ! -d gst-plugins-bad ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-plugins-bad
[ ! -d gst-plugins-ugly ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-plugins-ugly
[ ! -d gst-libav ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-libav
[ ! -d gst-omx ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-omx
[ ! -d gst-python ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-python
[ ! -d gst-rtsp-server ] && git clone git://anongit.freedesktop.org/git/gstreamer/gst-rtsp-server
[ ! $RPI ] && [ ! -d gstreamer-vaapi ] && git clone git://anongit.freedesktop.org/git/gstreamer/gstreamer-vaapi



export LD_LIBRARY_PATH=/usr/local/lib/
# checkout branch (default=master) and build & install
cd gstreamer
git pull
sudo rm -r build || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
cd ..
sudo ninja -C build install -j4
cd ..

cd gst-plugins-base
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
cd ..
sudo ninja -C build install -j4
cd ..

cd gst-plugins-good
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
cd ..
sudo ninja -C build install -j4
cd ..

cd gst-plugins-ugly
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
cd ..
sudo ninja -C build install -j4
cd ..

cd gst-libav
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
sudo meson build --prefix=/usr -D buildtype=release -D gst_debug=false -D gtk_doc=disabled  -D target=rpi -D header_path=/opt/vc/include/IL/
sudo ninja -C build install -j4
cd ..

cd gst-plugins-bad
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
sudo meson build --prefix=/usr -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled -Dexamples=disabled -Dx11=disabled -Dglx=disabled -Dopengl=disabled -D target=rpi -D header_path=/opt/vc/include/IL/ 
sudo ninja -C build install -j4
cd ..

cd gst-rtsp-server
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
cd build
sudo meson --prefix=/usr -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
cd ..
sudo ninja -C build install -j4
cd ..



# python bindings
cd gst-python
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
sudo meson build --prefix=/usr -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled
sudo ninja -C build install -j4
cd ..

# omx support
cd gst-omx
git pull
sudo rm -r build  || true
[ ! -d build ] && mkdir build
#export LDFLAGS='-L/opt/vc/lib' \
#CFLAGS='-I/opt/vc/include -I/opt/vc/include/IL -I/opt/vc/include/interface/vcosse/pthreads -I/opt/vc/include/interface/vmcs_host/linux -I/opt/vc/include/IL' \
#CPPFLAGS='-I/opt/vc/include -I/opt/vc/include/IL -I/opt/vc/include/interface/vcos/pthreads -I/opt/vc/include/interface/vmcs_host/linux -I/opt/vc/include/IL'
sudo meson build -D target=rpi -D header_path=/opt/vc/include/IL/ --prefix=/usr -Dbuildtype=release -Dgst_debug=false -Dgtk_doc=disabled -Dexamples=disabled -Dx11=disabled -Dglx=disabled -Dopengl=disabled
#make CFLAGS+="-Wno-error -Wno-redundant-decls" LDFLAGS+="-L/opt/vc/lib"
sudo ninja -C build install -j4
cd ..


[ ! -d gst-rpicamsrc ] && git clone https://github.com/thaytan/gst-rpicamsrc.git
cd gst-rpicamsrc
git pull
sudo meson build --prefix=/usr
libtoolize
sudo ninja -C build install
libtoolize
./autogen
libtoolize
make
sudo make install
cd ~

sudo ldconfig

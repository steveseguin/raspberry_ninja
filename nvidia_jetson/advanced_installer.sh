sudo apt-get update

sudo apt-get install python3-pip -y
sudo apt-get install git -y
sudo apt-get install cmake -y
sudo apt-get install build-essential yasm cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev -y
sudo pip3 install scikit-build
sudo pip3 install ninja   

sudo apt-get install apt-transport-https ca-certificates -y

export GIT_SSL_NO_VERIFY=1

cd ~
git clone https://github.com/mesonbuild/meson.git
cd meson
sudo python3 setup.py install
   
sudo rm -rf /usr/bin/gst-*
sudo rm -rf /usr/include/gstreamer-1.0
sudo apt install policykit-1-gnome
/usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1
sudo apt-get install libssl-dev -y
   
cd ~
git clone --depth 1 https://chromium.googlesource.com/webm/libvpx
cd libvpx
git pull
make distclean
./configure --disable-examples --disable-tools --disable-unit_tests --disable-docs --enable-shared
make -j4
sudo make install
sudo ldconfig


cd ~
git clone https://github.com/GNOME/glib.git
cd glib
mkdir build
sudo meson build
sudo ninja -C build install -j4
sudo ldconfig

cd ~
mkdir -p build
cd build
git clone https://git.videolan.org/git/ffmpeg/nv-codec-headers.git
cd nv-codec-headers && sudo make install

cd ~
git clone https://git.ffmpeg.org/ffmpeg.git


cd ~
git clone https://github.com/sctplab/usrsctp.git
cd usrsctp
mkdir build
sudo meson build  -Dbuildtype=release --prefix=/usr/local
sudo ninja -C build install -j4


cd ~
wget https://download.gnome.org/sources/gobject-introspection/1.70/gobject-introspection-1.70.0.tar.xz
sudo rm  gobject-introspection-1.70.0 -r || true
tar -xvf gobject-introspection-1.70.0.tar.xz
cd gobject-introspection-1.70.0
mkdir build
cd build
sudo meson --prefix=/usr/local --buildtype=release ..
sudo ninja
sudo ninja install
sudo ldconfig
sudo libtoolize
  

cd ~
git clone https://github.com/cisco/libsrtp
cd libsrtp
sudo meson build
sudo meson compile -C build
sudo meson install -C build

cd ~
git clone https://github.com/GStreamer/gst-build
cd gst-build
sudo meson builddir -Dpython=enabled  -Dgtk_doc=disabled  -Dexamples=disabled -Dbuildtype=release -Dintrospection=disabled --prefix=/usr/local 
sudo ninja -C builddir
sudo ninja -C builddir install

cd ~
mkdir nvgst
sudo cp /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstomx.so ./nvgst/
sudo cp /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnv* ./nvgst/
sudo cp ./nvgst/libgstnv* /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo cp ./nvgst/libgstomx.so /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/

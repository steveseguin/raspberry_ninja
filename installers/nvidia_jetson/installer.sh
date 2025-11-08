#!/usr/bin/env bash
set -euo pipefail

JOBS=${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc || echo 4)}
PYTHON_VERSION=${PYTHON_VERSION:-3.11.9}
MESON_VERSION=${MESON_VERSION:-1.4.1}
GSTREAMER_VERSION=${GSTREAMER_VERSION:-1.26.7}
GSTREAMER_SERIES="${GSTREAMER_VERSION%.*}"
GLIB_VERSION=${GLIB_VERSION:-2.80.5}
GOBJECT_INTROSPECTION_VERSION=${GOBJECT_INTROSPECTION_VERSION:-1.80.1}
GLIB_SERIES="${GLIB_VERSION%.*}"
GOBJECT_INTROSPECTION_SERIES="${GOBJECT_INTROSPECTION_VERSION%.*}"
LIBCAMERA_TAG=${LIBCAMERA_TAG:-v0.3.2}
SRT_TAG=${SRT_TAG:-v1.5.3}
LIBSRTP_TAG=${LIBSRTP_TAG:-v2.6.0}
LIBNICE_TAG=${LIBNICE_TAG:-0.1.21}
LIBVPX_VERSION=${LIBVPX_VERSION:-1.13.1}
DAV1D_VERSION=${DAV1D_VERSION:-1.3.0}
KVAZAAR_VERSION=${KVAZAAR_VERSION:-2.3.0}
FFMPEG_TAG=${FFMPEG_TAG:-n7.0}
X264_GIT_REF=${X264_GIT_REF:-stable}
PYTHON_PREFIX=${PYTHON_PREFIX:-/usr/local}
PYTHON_BIN="${PYTHON_PREFIX}/bin/python${PYTHON_VERSION%.*}"
INCLUDE_DISTRO_UPGRADE=${INCLUDE_DISTRO_UPGRADE:-0}

prepend_env_path() {
	local var="$1"
	local value="$2"
	local current="${!var:-}"
	if [[ -z "${current}" ]]; then
		printf -v "${var}" '%s' "${value}"
	elif [[ ":${current}:" != *":${value}:"* ]]; then
		printf -v "${var}" '%s' "${value}:${current}"
	fi
	export "${var}"
}

DEBIAN_FRONTEND=${DEBIAN_FRONTEND:-noninteractive}
export DEBIAN_FRONTEND

prepend_env_path PATH "${PYTHON_PREFIX}/bin"
prepend_env_path PATH "/usr/local/sbin"
prepend_env_path PATH "/usr/local/bin"
prepend_env_path PKG_CONFIG_PATH "/usr/local/lib/pkgconfig"
prepend_env_path PKG_CONFIG_PATH "/usr/local/share/pkgconfig"
prepend_env_path LD_LIBRARY_PATH "/usr/local/lib"
prepend_env_path LIBRARY_PATH "/usr/local/lib"
prepend_env_path CMAKE_PREFIX_PATH "/usr/local"
prepend_env_path PYTHONPATH "${PYTHON_PREFIX}/lib/python${PYTHON_VERSION%.*}/site-packages"

### Updated for 2024 builds targeting Jetson Nano 2GB/4GB with JetPack 4 base images
## Manual involvement is needed at steps...

cd ~
mkdir -p nvgst
if [[ -d /usr/lib/aarch64-linux-gnu/gstreamer-1.0 ]]; then
	sudo cp -a /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstomx.so ./nvgst/ || true
	sudo cp -a /usr/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnv* ./nvgst/ || true
fi

if [[ "${INCLUDE_DISTRO_UPGRADE}" == "1" ]]; then
	echo "[info] Running distro-upgrade block (INCLUDE_DISTRO_UPGRADE=1)."
	sudo apt-get update
	sudo apt autoremove -y || true
	sudo apt-get -f install || true
	sudo apt-get upgrade -y
	sudo apt-get dist-upgrade -y
else
	echo "[info] Skipping legacy distro upgrade steps (default). Set INCLUDE_DISTRO_UPGRADE=1 to enable."
	sudo apt-get update
fi

APT_BUILD_PACKAGES=(
	apt-transport-https
	autoconf
	automake
	autopoint
	autotools-dev
	bison
	build-essential
	ca-certificates
	ccache
	checkinstall
	cmake
	curl
	flex
	git
	libgdbm-compat-dev
	libgdbm-dev
	libboost-dev
	libncurses5-dev
	libncursesw5-dev
	libnss3-dev
	libgnutls28-dev
	libkmod-dev
	libreadline-dev
	libsqlite3-dev
	libtiff5-dev
	libudev-dev
	libtool
	pkg-config
	python3
	python3-dev
	python3-pip
	python3-rtmidi
	tar
	tk-dev
	unzip
	uuid-dev
	wget
	yasm
)

APT_MEDIA_PACKAGES=(
	desktop-file-utils
	doxygen
	fonts-freefont-ttf
	freeglut3
	graphviz
	gtk-doc-tools
	imagemagick
	iso-codes
	ladspa-sdk
	libaa1-dev
	liba52-0.7.4-dev
	libaom-dev
	libasound2-dev
	libass-dev
	libatk-bridge2.0-dev
	libatk1.0-dev
	libavc1394-dev
	libavcodec-dev
	libavdevice-dev
	libavfilter-dev
	libavformat-dev
	libavutil-dev
	libbz2-dev
	libc6
	libc6-dev
	libcaca-dev
	libcairo2-dev
	libcdaudio-dev
	libcdio-dev
	libcdparanoia-dev
	libcap-dev
	libcurl4-openssl-dev
	libdca-dev
	libdbus-1-dev
	libdc1394-22-dev
	libdrm-dev
	libdv4-dev
	libdvdnav-dev
	libdvdread-dev
	libdw-dev
	libegl1-mesa-dev
	libelf-dev
	libepoxy-dev
	libexempi-dev
	libexif-dev
	libfaad-dev
	libffi-dev
	libflac-dev
	libfreetype6-dev
	libgdk-pixbuf2.0-dev
	libgif-dev
	libgirepository1.0-dev
	libgl1-mesa-dev
	libglib2.0-dev
	libgles2-mesa-dev
	libgtk-3-dev
	libgme-dev
	libgmp-dev
	libgsl0-dev
	libgsm1-dev
	libgudev-1.0-dev
	libgupnp-igd-1.0-dev
	libiec61883-dev
	libraw1394-dev
	libiptcdata0-dev
	libjpeg-dev
	libjson-glib-dev
	libkate-dev
	liblzma-dev
	libmad0-dev
	libmodplug-dev
	libmms-dev
	libmount-dev
	libmp3lame-dev
	libmpcdec-dev
	libmpg123-dev
	libmpeg2-4-dev
	libnuma-dev
	libnuma1
	libogg-dev
	libomxil-bellagio-dev
	libopencore-amrnb-dev
	libopencore-amrwb-dev
	libopus-dev
	liborc-0.4-dev
	libofa0-dev
	libpango1.0-dev
	libpng-dev
	libpulse-dev
	librsvg2-dev
	librtmp-dev
	libsdl2-dev
	libsdl2-image-dev
	libsdl2-mixer-dev
	libsdl2-net-dev
	libsdl2-ttf-dev
	libselinux-dev
	libshout3-dev
	libsidplay1-dev
	libsnappy-dev
	libsoxr-dev
	libsoup2.4-dev
	libsoundtouch-dev
	libsndfile1-dev
	libspandsp-dev
	libspeex-dev
	libssh-dev
	libssl-dev
	libtag1-dev
	libtheora-dev
	libtwolame-dev
	libunwind-dev
	libusb-1.0-0-dev
	libva-dev
	libv4l-dev
	libvdpau-dev
	libvisual-0.4-dev
	libvo-amrwbenc-dev
	libvorbis-dev
	libvorbisidec-dev
	libopenjp2-7-dev
	libvpx-dev
	libwavpack-dev
	libwebrtc-audio-processing-dev
	libwebp-dev
	libx11-dev
	libx264-dev
	libx265-dev
	libxcb-shape0-dev
	libxcb-shm0-dev
	libxcb-xfixes0-dev
	libxcb1-dev
	libxt-dev
	libxkbcommon-dev
	libxml2-dev
	libxvidcore-dev
	libyaml-dev
	libzbar-dev
	libzvbi-dev
	zlib1g-dev
	policykit-1-gnome
	pulseaudio
	python3-jinja2
	python3-ply
	python3-yaml
	shared-mime-info
	texinfo
	tclsh
	wayland-protocols
)

sudo apt-get install -y "${APT_BUILD_PACKAGES[@]}"
sudo apt-get install -y "${APT_MEDIA_PACKAGES[@]}"
sudo apt-get autoremove -y

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1 || [[ "$("${PYTHON_BIN}" -V 2>/dev/null)" != "Python ${PYTHON_VERSION}" ]]; then
	cd ~
	rm -rf "Python-${PYTHON_VERSION}" python.tgz
	wget "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz" -O python.tgz
	tar -xf python.tgz
	cd "Python-${PYTHON_VERSION}"
	./configure --prefix="${PYTHON_PREFIX}" --enable-optimizations --with-lto --enable-shared
	make -j"${JOBS}"
	sudo make altinstall
	sudo ldconfig
	cd ~
	rm -rf "Python-${PYTHON_VERSION}" python.tgz
fi

sudo "${PYTHON_BIN}" -m ensurepip --upgrade
sudo "${PYTHON_BIN}" -m pip install --upgrade pip setuptools wheel
sudo "${PYTHON_BIN}" -m pip install --upgrade scikit-build ninja websockets jinja2 PyYAML mako ply
export GIT_SSL_NO_VERIFY=1

### MESON - specific version
sudo "${PYTHON_BIN}" -m pip install --upgrade "meson==${MESON_VERSION}"
sudo "${PYTHON_BIN}" -m pip install --upgrade pycairo

# AAC - optional (needed for rtmp only really)
cd ~
rm -rf fdk-aac
git clone --depth 1 https://github.com/mstorsjo/fdk-aac.git
cd fdk-aac
autoreconf -fiv
./configure --prefix=/usr/local
make -j"${JOBS}"
sudo make install
sudo ldconfig

# AV1 - optional
cd ~
rm -rf dav1d
git clone --depth 1 --branch "${DAV1D_VERSION}" https://code.videolan.org/videolan/dav1d.git
cd dav1d
meson setup build --buildtype=release --prefix=/usr/local \
	-Denable_tools=false \
	-Denable_tests=false \
	-Denable_docs=false \
	-Denable_examples=false
ninja -C build -j "${JOBS}"
sudo ninja -C build -j "${JOBS}" install
sudo ldconfig

# HEVC - optional
cd ~
rm -rf kvazaar
git clone --depth 1 --branch "v${KVAZAAR_VERSION}" https://github.com/ultravideo/kvazaar.git
cd kvazaar
git submodule update --init --recursive || true
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local -DBUILD_SHARED_LIBS=ON
cmake --build build -j"${JOBS}"
sudo cmake --install build
sudo ldconfig

# H.264 - from source for latest optimisations
cd ~
rm -rf x264
git clone --depth 1 --branch "${X264_GIT_REF}" https://code.videolan.org/videolan/x264.git
cd x264
./configure --prefix=/usr/local --enable-pic --enable-shared --enable-strip
make -j"${JOBS}"
sudo make install
sudo ldconfig

# VP8/VP9 - multi-thread capable build
cd ~
rm -rf libvpx
git clone --depth 1 --branch "v${LIBVPX_VERSION}" https://github.com/webmproject/libvpx.git
cd libvpx
./configure --prefix=/usr/local --enable-vp8 --enable-vp9 --enable-shared --enable-pic --enable-multithread --enable-runtime-cpu-detect --disable-examples --disable-unit-tests --disable-docs
make -j"${JOBS}"
sudo make install
sudo ldconfig

# SRT - optional
cd ~
rm -rf srt
git clone --branch "${SRT_TAG}" --depth 1 https://github.com/Haivision/srt.git
cd srt
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local -DENABLE_SHARED=ON -DENABLE_STATIC=OFF
cmake --build build -j"${JOBS}"
sudo cmake --install build
sudo ldconfig

### FFMPEG
cd ~
[ ! -d FFmpeg ] && git clone --branch "${FFMPEG_TAG}" --depth 1 https://github.com/FFmpeg/FFmpeg.git
cd FFmpeg
git fetch --tags
git checkout "${FFMPEG_TAG}"
make distclean || true
./configure \
	--prefix=/usr/local \
	--arch=aarch64 \
	--extra-cflags="-I/usr/local/include" \
	--extra-ldflags="-L/usr/local/lib" \
	--extra-libs="-lpthread -lm -latomic" \
	--enable-gpl \
	--enable-version3 \
	--enable-nonfree \
	--enable-shared \
	--disable-static \
	--enable-pthreads \
	--enable-libfdk-aac \
	--enable-libx264 \
	--enable-libx265 \
	--enable-libvpx \
	--enable-libdav1d \
	--enable-libkvazaar \
	--enable-libaom \
	--enable-libsrt \
	--enable-librtmp \
	--enable-libopus \
	--enable-libvorbis \
	--enable-libmp3lame \
	--enable-libass \
	--enable-libfreetype \
	--enable-libwebp \
	--enable-libsnappy \
	--enable-libsoxr \
	--enable-libssh \
	--enable-libxml2 \
	--enable-libdrm \
	--enable-libopencore-amrnb \
	--enable-libopencore-amrwb \
	--enable-libvo-amrwbenc \
	--enable-libpulse \
	--enable-omx \
	--enable-indev=alsa \
	--enable-outdev=alsa \
	--enable-hardcoded-tables \
	--enable-openssl
make -j"${JOBS}"
sudo make install
sudo ldconfig

sudo apt-get remove gstreamer1.0* -y
sudo rm -rf /usr/lib/aarch64-linux-gnu/gstreamer-1.0/
sudo rm -rf /usr/lib/gst*
sudo rm -rf /usr/bin/gst*
sudo rm -rf /usr/include/gstreamer-1.0
sudo rm -rf /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/

cd ~
rm -rf "glib-${GLIB_VERSION}" glib.tar.xz
wget "https://download.gnome.org/sources/glib/${GLIB_SERIES}/glib-${GLIB_VERSION}.tar.xz" -O glib.tar.xz
tar -xvf glib.tar.xz 
cd "glib-${GLIB_VERSION}"
mkdir build
cd build
meson --prefix=/usr/local -Dman=false ..
ninja -j "${JOBS}"
sudo ninja -j "${JOBS}" install
sudo ldconfig

cd ~
rm -rf usrsctp
git clone --depth 1 https://github.com/sctplab/usrsctp.git
cd usrsctp
git fetch --tags
git checkout master
rm -rf build
meson setup build --prefix=/usr/local --buildtype=release
ninja -C build -j "${JOBS}"
sudo ninja -C build -j "${JOBS}" install
sudo ldconfig

cd ~
rm -f gobject.tar.xz
wget "https://download.gnome.org/sources/gobject-introspection/${GOBJECT_INTROSPECTION_SERIES}/gobject-introspection-${GOBJECT_INTROSPECTION_VERSION}.tar.xz" -O gobject.tar.xz
sudo rm -rf "gobject-introspection-${GOBJECT_INTROSPECTION_VERSION}" || true
tar -xvf gobject.tar.xz
cd "gobject-introspection-${GOBJECT_INTROSPECTION_VERSION}"
rm -rf build
meson setup build --prefix=/usr/local --buildtype=release
ninja -C build -j "${JOBS}"
sudo ninja -C build -j "${JOBS}" install
sudo ldconfig
systemctl --user enable pulseaudio.socket || true

cd ~
rm -rf libnice
git clone --branch "${LIBNICE_TAG}" --depth 1 https://gitlab.freedesktop.org/libnice/libnice.git
cd libnice
git fetch --tags
git checkout "${LIBNICE_TAG}"
rm -rf build
meson setup build --prefix=/usr/local --buildtype=release
ninja -C build -j "${JOBS}"
sudo ninja -C build -j "${JOBS}" install
sudo ldconfig

cd ~
rm -rf libsrtp
git clone --branch "${LIBSRTP_TAG}" --depth 1 https://github.com/cisco/libsrtp.git
cd libsrtp
git fetch --tags
git checkout "${LIBSRTP_TAG}"
./configure --enable-openssl --enable-pic --prefix=/usr/local
make -j"${JOBS}"
sudo make shared_library
sudo make install -j"${JOBS}"
sudo ldconfig

cd ~
rm -rf gstreamer
git clone https://gitlab.freedesktop.org/gstreamer/gstreamer.git
cd gstreamer
git checkout "refs/tags/${GSTREAMER_VERSION}"
git submodule update --init --recursive
rm -rf build
meson setup build --prefix=/usr/local --buildtype=release \
	-Dgst-plugins-base:gl_winsys=egl \
	-Ddoc=disabled \
	-Dtests=disabled \
	-Dexamples=disabled \
	-Dges=disabled \
	-Ddevtools=disabled \
	-Dauto_features=enabled \
	-Dintrospection=enabled \
	-Dlibav=disabled \
	-Dgst-plugins-good:qt5=disabled \
	-Dgst-plugins-good:qt6=disabled \
	-Dgst-plugins-good:rpicamsrc=disabled \
	-Dgstreamer:libunwind=disabled \
	-Dgstreamer:libdw=disabled \
	-Dgstreamer:dbghelp=disabled \
	-Dgstreamer:ptp-helper=disabled \
	-Dgst-plugins-bad:va=disabled \
	-Dgst-plugins-bad:mse=disabled \
	-Dgst-plugins-bad:build-gir=false \
	-Dgst-plugins-base:gl-gir=false
ninja -C build -j "${JOBS}"
sudo ninja -C build -j "${JOBS}" install
sudo ldconfig
cd ~
rm -rf libcamera
git clone https://git.libcamera.org/libcamera/libcamera.git
cd libcamera
git fetch --tags
git checkout "${LIBCAMERA_TAG}"
git submodule update --init --recursive
rm -rf build
meson setup build --buildtype=release --prefix=/usr/local
ninja -C build -j "${JOBS}"
sudo ninja -C build -j "${JOBS}" install ## too many cores and you'll crash a raspiberry pi zero 2
sudo ldconfig
cd ~

sudo mkdir -p /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0
for plugin in \
	libgstnvarguscamerasrc.so \
	libgstnvivafilter.so \
	libgstnvv4l2camerasrc.so \
	libgstnvvideocuda.so \
	libgstomx.so \
	libgstnvjpeg.so \
	libgstnvvidconv.so \
	libgstnvvideosink.so \
	libgstnvtee.so \
	libgstnvvideo4linux2.so \
	libgstnvvideosinks.so; do
	if [[ -f "${HOME}/nvgst/${plugin}" ]]; then
		sudo cp "${HOME}/nvgst/${plugin}" /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/
	fi
done
sudo rm -f /usr/local/lib/aarch64-linux-gnu/gstreamer-1.0/libgstnvcompositor.so # isn't compatible anymore

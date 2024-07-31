#!/bin/bash
set -e

echo "Installs NDI support for Raspberry.Ninja running on Windows WSL2"

NDI_VERSION="6"
NDI_INSTALLER="Install_NDI_SDK_v${NDI_VERSION}_Linux.tar.gz"
NDI_URL="https://downloads.ndi.tv/SDK/NDI_SDK_Linux/${NDI_INSTALLER}"
TMP_DIR=$(mktemp -d)

echo "Installing NDI SDK version ${NDI_VERSION}"

cd $TMP_DIR

echo "Downloading NDI SDK..."
curl -LO $NDI_URL

echo "Extracting NDI SDK..."
tar -xzf $NDI_INSTALLER

echo "Running NDI installer..."
yes | PAGER="cat" sh "./Install_NDI_SDK_v${NDI_VERSION}_Linux.sh"

echo "Installing NDI libraries..."
sudo cp -P "NDI SDK for Linux/lib/x86_64-linux-gnu/"* /usr/local/lib/
sudo ldconfig

echo "Creating compatibility symlink..."
sudo ln -sf /usr/local/lib/libndi.so.${NDI_VERSION} /usr/local/lib/libndi.so.5

echo "Cleaning up driver installation..."
cd - > /dev/null
rm -rf $TMP_DIR

echo "Installing Gstreamer NDI Plugin build dependencies..."
sudo apt-get update
sudo apt-get install build-essential cmake libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev -y
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.bashrc

echo "Building Gstreamer NDI Plugin..."
git clone https://github.com/steveseguin/gst-plugin-ndi.git
cd gst-plugin-ndi
cargo build --release
sudo install target/release/libgstndi.so /usr/lib/x86_64-linux-gnu/gstreamer-1.0/
sudo ldconfig
gst-inspect-1.0 ndi
 
echo "NDI SDK installation complete."

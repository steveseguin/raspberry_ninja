#!/bin/bash
set -e

echo "Universal NDI support installer for Linux systems"
echo "Supports Ubuntu, Debian, CentOS, RHEL, Fedora, openSUSE, Arch, and more"

NDI_VERSION="6"
NDI_INSTALLER="Install_NDI_SDK_v${NDI_VERSION}_Linux.tar.gz"
NDI_URL="https://downloads.ndi.tv/SDK/NDI_SDK_Linux/${NDI_INSTALLER}"
TMP_DIR=$(mktemp -d)

# Detect architecture
ARCH=$(uname -m)
case $ARCH in
    x86_64)
        LIB_ARCH="x86_64-linux-gnu"
        GST_LIB_DIR="/usr/lib/x86_64-linux-gnu/gstreamer-1.0"
        ;;
    aarch64|arm64)
        LIB_ARCH="aarch64-linux-gnu"
        GST_LIB_DIR="/usr/lib/aarch64-linux-gnu/gstreamer-1.0"
        ;;
    armv7l|armhf)
        LIB_ARCH="arm-linux-gnueabihf"
        GST_LIB_DIR="/usr/lib/arm-linux-gnueabihf/gstreamer-1.0"
        ;;
    *)
        echo "Warning: Unsupported architecture $ARCH, defaulting to x86_64"
        LIB_ARCH="x86_64-linux-gnu"
        GST_LIB_DIR="/usr/lib/x86_64-linux-gnu/gstreamer-1.0"
        ;;
esac

# Detect distribution and package manager
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$ID
        VERSION_ID=${VERSION_ID:-""}
    elif [ -f /etc/redhat-release ]; then
        DISTRO="rhel"
    elif [ -f /etc/debian_version ]; then
        DISTRO="debian"
    else
        DISTRO="unknown"
    fi
    echo "Detected distribution: $DISTRO"
}

# Install packages based on distribution
install_dependencies() {
    echo "Installing build dependencies..."
    
    case $DISTRO in
        ubuntu|debian)
            sudo apt-get update
            sudo apt-get install -y build-essential cmake curl git pkg-config \
                libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
            ;;
        fedora)
            sudo dnf install -y gcc gcc-c++ cmake curl git pkgconfig \
                gstreamer1-devel gstreamer1-plugins-base-devel
            GST_LIB_DIR="/usr/lib64/gstreamer-1.0"
            ;;
        centos|rhel)
            # Enable EPEL for additional packages
            if ! rpm -q epel-release &>/dev/null; then
                sudo yum install -y epel-release || sudo dnf install -y epel-release
            fi
            sudo yum install -y gcc gcc-c++ cmake curl git pkgconfig \
                gstreamer1-devel gstreamer1-plugins-base-devel || \
            sudo dnf install -y gcc gcc-c++ cmake curl git pkgconfig \
                gstreamer1-devel gstreamer1-plugins-base-devel
            GST_LIB_DIR="/usr/lib64/gstreamer-1.0"
            ;;
        opensuse*|sles)
            sudo zypper install -y gcc gcc-c++ cmake curl git pkg-config \
                gstreamer-devel gstreamer-plugins-base-devel
            GST_LIB_DIR="/usr/lib64/gstreamer-1.0"
            ;;
        arch|manjaro)
            sudo pacman -Sy --noconfirm base-devel cmake curl git pkgconf \
                gstreamer gst-plugins-base
            GST_LIB_DIR="/usr/lib/gstreamer-1.0"
            ;;
        alpine)
            sudo apk update
            sudo apk add build-base cmake curl git pkgconfig \
                gstreamer-dev gst-plugins-base-dev
            GST_LIB_DIR="/usr/lib/gstreamer-1.0"
            ;;
        *)
            echo "Warning: Unknown distribution. Attempting generic installation..."
            echo "Please ensure you have: gcc, cmake, curl, git, pkg-config, gstreamer development headers"
            read -p "Continue anyway? [y/N] " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                exit 1
            fi
            ;;
    esac
}

# Check and install Rust/Cargo
install_rust() {
    echo "Checking for Rust installation..."
    
    if command -v rustc &> /dev/null && command -v cargo &> /dev/null; then
        echo "Rust and Cargo are already installed:"
        rustc --version
        cargo --version
        
        # Check if Rust is reasonably recent (1.70+)
        RUST_VERSION=$(rustc --version | cut -d' ' -f2 | cut -d'.' -f1-2)
        if [ "$(printf '%s\n' "1.70" "$RUST_VERSION" | sort -V | head -n1)" = "1.70" ]; then
            echo "Rust version is sufficient."
            return 0
        else
            echo "Rust version is too old, updating..."
        fi
    else
        echo "Rust/Cargo not found. Installing..."
    fi
    
    # Install or update Rust using rustup
    if command -v rustup &> /dev/null; then
        echo "Updating Rust via rustup..."
        rustup update stable
    else
        echo "Installing Rust via rustup..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
        
        # Source the cargo environment
        if [ -f "$HOME/.cargo/env" ]; then
            . "$HOME/.cargo/env"
        fi
    fi
    
    # Verify installation
    if command -v rustc &> /dev/null && command -v cargo &> /dev/null; then
        echo "Rust installation successful:"
        rustc --version
        cargo --version
    else
        echo "Error: Rust installation failed"
        exit 1
    fi
}

# Create fallback GStreamer plugin directory if it doesn't exist
ensure_gstreamer_dir() {
    if [ ! -d "$GST_LIB_DIR" ]; then
        echo "GStreamer plugin directory not found at $GST_LIB_DIR"
        # Try common alternatives
        ALTERNATIVE_DIRS=(
            "/usr/lib/gstreamer-1.0"
            "/usr/lib64/gstreamer-1.0" 
            "/usr/local/lib/gstreamer-1.0"
            "/usr/lib/$LIB_ARCH/gstreamer-1.0"
        )
        
        for dir in "${ALTERNATIVE_DIRS[@]}"; do
            if [ -d "$dir" ]; then
                echo "Using alternative GStreamer directory: $dir"
                GST_LIB_DIR="$dir"
                return 0
            fi
        done
        
        echo "Creating GStreamer plugin directory: $GST_LIB_DIR"
        sudo mkdir -p "$GST_LIB_DIR"
    fi
}

# Main installation process
main() {
    echo "Installing NDI SDK version ${NDI_VERSION}"
    
    # Detect system
    detect_distro
    
    # Install dependencies
    install_dependencies
    
    # Install Rust if needed
    install_rust
    
    # Download and install NDI SDK
    cd "$TMP_DIR"
    echo "Downloading NDI SDK..."
    curl -LO "$NDI_URL"
    
    echo "Extracting NDI SDK..."
    tar -xzf "$NDI_INSTALLER"
    
    echo "Running NDI installer..."
    yes | PAGER="cat" sh "./Install_NDI_SDK_v${NDI_VERSION}_Linux.sh"
    
    echo "Installing NDI libraries..."
    if [ -d "NDI SDK for Linux/lib/$LIB_ARCH" ]; then
        sudo cp -P "NDI SDK for Linux/lib/$LIB_ARCH/"* /usr/local/lib/
    else
        echo "Warning: Architecture-specific NDI libraries not found, trying x86_64..."
        sudo cp -P "NDI SDK for Linux/lib/x86_64-linux-gnu/"* /usr/local/lib/
    fi
    sudo ldconfig
    
    echo "Creating compatibility symlink..."
    sudo ln -sf /usr/local/lib/libndi.so.${NDI_VERSION} /usr/local/lib/libndi.so.5
    
    echo "Cleaning up NDI installation..."
    cd - > /dev/null
    rm -rf "$TMP_DIR"
    
    echo "Building GStreamer NDI Plugin..."
    
    # Ensure GStreamer directory exists
    ensure_gstreamer_dir
    
    # Clone and build the plugin
    PLUGIN_DIR="gst-plugin-ndi"
    if [ -d "$PLUGIN_DIR" ]; then
        echo "Updating existing plugin repository..."
        cd "$PLUGIN_DIR"
        git pull
    else
        echo "Cloning plugin repository..."
        git clone https://github.com/steveseguin/gst-plugin-ndi.git
        cd "$PLUGIN_DIR"
    fi
    
    cargo build --release
    
    echo "Installing GStreamer NDI plugin..."
    sudo install target/release/libgstndi.so "$GST_LIB_DIR/"
    sudo ldconfig
    
    echo "Testing GStreamer NDI plugin..."
    if gst-inspect-1.0 ndi &>/dev/null; then
        echo "✓ GStreamer NDI plugin installed successfully!"
        gst-inspect-1.0 ndi | head -5
    else
        echo "⚠ Warning: GStreamer NDI plugin test failed. Manual verification may be needed."
    fi
    
    cd ..
    
    echo ""
    echo "🎉 NDI SDK installation complete!"
    echo ""
    echo "Installed components:"
    echo "  ✓ NDI SDK v${NDI_VERSION}"
    echo "  ✓ Rust $(rustc --version | cut -d' ' -f2)"
    echo "  ✓ GStreamer NDI plugin"
    echo ""
    echo "You may need to restart your terminal or run: source ~/.cargo/env"
}

# Run main function
main
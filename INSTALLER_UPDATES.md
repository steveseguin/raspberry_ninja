# Installer Script Updates

## Recommended Changes

### All Installers

1. **Add Python cryptography module**:
   ```bash
   pip3 install cryptography
   ```

2. **Make Python version detection dynamic**:
   ```bash
   # Instead of hardcoding /usr/lib/python3.11/EXTERNALLY-MANAGED
   PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
   sudo rm /usr/lib/python${PYTHON_VERSION}/EXTERNALLY-MANAGED 2>/dev/null || true
   ```

3. **Add error checking**:
   ```bash
   set -e  # Exit on error
   set -x  # Print commands
   ```

### Raspberry Pi Specific

1. **Fix FFmpeg architecture flags**:
   ```bash
   # Remove conflicting --arch flags
   --arch=arm64  # for 64-bit
   # or
   --arch=armhf  # for 32-bit
   # Not both!
   ```

2. **Increase swap for Pi Zero 2**:
   ```bash
   # Detect Pi model and adjust swap
   PI_MODEL=$(cat /proc/device-tree/model)
   if [[ "$PI_MODEL" == *"Zero 2"* ]]; then
       CONF_SWAPSIZE=2048
   else
       CONF_SWAPSIZE=1024
   fi
   ```

3. **Add missing dependencies for our fixes**:
   ```bash
   # For better JPEG handling
   sudo apt-get install -y libjpeg-turbo8-dev
   
   # For better threading
   sudo apt-get install -y libatomic1
   ```

### Ubuntu Specific

1. **Add GStreamer plugins-rs for WHIP/WHEP**:
   ```bash
   # Check if plugins-rs is available in repos
   sudo apt-get install -y gstreamer1.0-plugins-rs || {
       echo "WHIP/WHEP plugins not available in repos"
       echo "Consider building from source for WHIP support"
   }
   ```

2. **Add development headers**:
   ```bash
   sudo apt-get install -y \
       libgstreamer1.0-dev \
       libgstreamer-plugins-base1.0-dev \
       libgstreamer-plugins-bad1.0-dev
   ```

### Nvidia Jetson Specific

1. **Simplify installation**:
   - Consider creating separate installers for different Jetpack versions
   - Don't force Ubuntu upgrade unless necessary

2. **Add L4T version detection**:
   ```bash
   L4T_VERSION=$(cat /etc/nv_tegra_release | grep -oP 'R\K[0-9]+')
   if [ "$L4T_VERSION" -lt "32" ]; then
       echo "Warning: L4T version too old, consider upgrading Jetpack"
   fi
   ```

## New Unified Installer Template

```bash
#!/bin/bash
set -e  # Exit on error

# Detect system
detect_system() {
    if [ -f /etc/nv_tegra_release ]; then
        echo "nvidia_jetson"
    elif [ -f /proc/device-tree/model ] && grep -q "Raspberry Pi" /proc/device-tree/model; then
        echo "raspberry_pi"
    else
        echo "generic_linux"
    fi
}

SYSTEM_TYPE=$(detect_system)
echo "Detected system: $SYSTEM_TYPE"

# Common dependencies
install_common_deps() {
    sudo apt-get update
    sudo apt-get install -y \
        python3 python3-pip \
        git wget curl \
        build-essential cmake
        
    # Python packages
    pip3 install --user \
        websockets \
        cryptography \
        python-rtmidi
}

# GStreamer installation
install_gstreamer() {
    case $SYSTEM_TYPE in
        raspberry_pi)
            # Build from source for latest features
            install_gstreamer_from_source
            ;;
        *)
            # Use system packages
            sudo apt-get install -y \
                gstreamer1.0-tools \
                gstreamer1.0-plugins-base \
                gstreamer1.0-plugins-good \
                gstreamer1.0-plugins-bad \
                gstreamer1.0-plugins-ugly \
                gstreamer1.0-libav \
                gstreamer1.0-nice \
                libgstreamer1.0-dev \
                libgstreamer-plugins-base1.0-dev
            ;;
    esac
}

# Main installation
main() {
    echo "Starting Raspberry Ninja installation..."
    
    install_common_deps
    install_gstreamer
    
    # System-specific setup
    case $SYSTEM_TYPE in
        raspberry_pi)
            setup_raspberry_pi
            ;;
        nvidia_jetson)
            setup_nvidia_jetson
            ;;
        *)
            echo "Generic Linux setup complete"
            ;;
    esac
    
    echo "Installation complete!"
    echo "Run 'python3 publish.py --help' to get started"
}

main "$@"
```

## Testing Recommendations

1. **Create CI/CD pipeline** to test installers on:
   - Raspberry Pi OS (32-bit and 64-bit)
   - Ubuntu 20.04, 22.04, 24.04
   - Jetpack 4.6 and 5.x

2. **Add installer verification script**:
   ```bash
   python3 -c "import websockets, cryptography; print('Python modules OK')"
   gst-inspect-1.0 --version
   gst-inspect-1.0 webrtcbin
   ```

3. **Add rollback functionality** for failed installations

## Quick Fixes for Users

For users experiencing issues with current installers:

```bash
# Fix missing cryptography
pip3 install --user cryptography

# Fix Python 3.11 hardcoding on other versions
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
sudo rm /usr/lib/python${PYTHON_VERSION}/EXTERNALLY-MANAGED 2>/dev/null || true

# Verify GStreamer installation
gst-inspect-1.0 | grep -E "webrtcbin|vpx|opus|nice"
```
# Raspberry Ninja Installation Guide

This guide provides installation instructions for Raspberry Ninja on various platforms.

## Universal Installer (Recommended)

For the easiest installation experience across all platforms, use our universal installer:

```bash
curl -sSL https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/installers/install.sh | bash
```

Or run locally:
```bash
chmod +x install.sh
./install.sh
```

The universal installer provides:
- Automatic platform detection
- Interactive configuration wizard
- Dependency installation
- Auto-start setup
- Configuration file management

## Quick Install (Recommended for Most Systems)

This method works for Ubuntu 22+, Debian 12+, Raspberry Pi OS, and other modern Debian-based distributions:

```bash
# Update system packages
sudo apt-get update && sudo apt upgrade -y

# For Debian 12-based systems, you may need to remove this file or use a virtual environment
sudo rm /usr/lib/python3.11/EXTERNALLY-MANAGED

# Install Python pip
sudo apt-get install python3-pip -y

# Install GStreamer and dependencies
sudo apt-get install -y \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev \
    libgstreamer-plugins-bad1.0-dev \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-tools \
    gstreamer1.0-x \
    python3-pyqt5 \
    python3-opengl \
    gstreamer1.0-alsa \
    gstreamer1.0-gl \
    gstreamer1.0-qt5 \
    gstreamer1.0-gtk3 \
    gstreamer1.0-pulseaudio \
    gstreamer1.0-nice \
    gstreamer1.0-plugins-base-apps

# Install Python dependencies
pip3 install --break-system-packages websockets cryptography

# Optional dependencies
sudo apt-get install -y libcairo-dev
pip3 install PyGObject
pip3 install aiohttp --break-system-packages

# Clone and run Raspberry Ninja
git clone https://github.com/steveseguin/raspberry_ninja.git
cd raspberry_ninja
python3 publish.py --test
```

## Platform-Specific Installers

For platform-specific installations with hardware optimization and additional features:

- **[Raspberry Pi](./raspberry_pi/README.md)** - Optimized for Raspberry Pi hardware with CSI camera support
- **[Ubuntu Desktop](./ubuntu/README.md)** - Full desktop Linux installation with GUI support
- **[Nvidia Jetson](./nvidia_jetson/README.md)** - Hardware acceleration for Jetson boards
- **[Orange Pi](./orangepi/README.md)** - Support for Orange Pi boards
- **[macOS](./mac/readme.md)** - Installation for Mac computers
- **[Windows (WSL)](./wsl/README.md)** - Running on Windows via WSL2

## Verifying Installation

After installation, test your setup:

```bash
# Test with virtual sources
python3 publish.py --test

# List available video devices
gst-device-monitor-1.0

# Check GStreamer version
gst-launch-1.0 --version
```

## Common Issues

1. **Python Package Management**: Modern Debian/Ubuntu systems use PEP 668. Either:
   - Use `--break-system-packages` flag with pip
   - Use a Python virtual environment
   - Remove the EXTERNALLY-MANAGED file (not recommended for production)

2. **Missing Dependencies**: If you encounter GStreamer errors, ensure all plugins are installed:
   ```bash
   sudo apt-get install gstreamer1.0-plugins-* gstreamer1.0-libav
   ```

3. **Permission Issues**: Some hardware devices may require adding your user to specific groups:
   ```bash
   sudo usermod -a -G video,audio $USER
   # Log out and back in for changes to take effect
   ```

## Next Steps

After installation:
- Run `python3 publish.py --help` to see all available options
- Check the main [README](../README.md) for usage examples
- Configure auto-start on boot if needed
- Set up your camera and audio devices

For detailed documentation and troubleshooting, visit the [Raspberry Ninja GitHub repository](https://github.com/steveseguin/raspberry_ninja).
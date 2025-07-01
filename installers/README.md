# Platform-Specific Installers

This directory contains platform-specific installation guides and scripts for advanced users who need hardware-specific optimizations.

## 🚀 Most Users Should Use the Universal Installer

```bash
# From the repository root:
./install.sh
```

Or use the one-liner:
```bash
curl -sSL https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh | bash
```

The universal installer automatically detects your platform and handles everything for you.

## 📁 Platform-Specific Guides

These guides are for users who need:
- Hardware-specific optimizations
- Custom configurations
- Manual control over the installation process

### Available Platforms:

- **[raspberry_pi/](./raspberry_pi/)** - Raspberry Pi specific optimizations
  - CSI camera support
  - GPIO features
  - Hardware encoding on Pi 4

- **[nvidia_jetson/](./nvidia_jetson/)** - Nvidia Jetson optimizations
  - NVENC hardware encoding
  - DeepStream integration
  - CSI camera support

- **[ubuntu/](./ubuntu/)** - Desktop Ubuntu/Debian
  - Full desktop integration
  - Multiple camera support

- **[orangepi/](./orangepi/)** - Orange Pi boards
  - Board-specific fixes
  - Hardware encoding where available

- **[mac/](./mac/)** - macOS installation
  - Homebrew-based setup
  - macOS-specific adaptations

- **[wsl/](./wsl/)** - Windows Subsystem for Linux
  - WSL2 configuration
  - Windows integration tips

## 📋 Manual Installation Steps

If you prefer complete manual control:

1. **Install GStreamer** (1.16 or newer)
2. **Install Python 3** and pip
3. **Install Python packages**: `websockets`, `cryptography`, `aiohttp`
4. **Clone this repository**
5. **Run**: `python3 publish.py --test`

See each platform's README for specific package names and commands.
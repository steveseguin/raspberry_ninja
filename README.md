<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**

- [<img src='https://github.com/user-attachments/assets/db676147-1888-44fe-a5a0-5c04921d2c06' height="50"> Raspberry Ninja](#img-srchttpsgithubcomuser-attachmentsassetsdb676147-1888-44fe-a5a0-5c04921d2c06-height50-raspberry-ninja)
  - [🚀 Quick Start](#-quick-start)
  - [📖 What is Raspberry Ninja?](#-what-is-raspberry-ninja)
    - [Key Features:](#key-features)
    - [Perfect for:](#perfect-for)
  - [💻 Supported Platforms](#-supported-platforms)
  - [📥 Installation](#-installation)
    - [Option 1: Universal Installer (Recommended)](#option-1-universal-installer-recommended)
    - [Option 2: Manual Installation](#option-2-manual-installation)
    - [Option 3: Quick Dependencies Only](#option-3-quick-dependencies-only)
  - [🎬 Basic Usage](#-basic-usage)
    - [Test your setup:](#test-your-setup)
    - [Stream with auto-generated ID:](#stream-with-auto-generated-id)
    - [Stream to specific ID:](#stream-to-specific-id)
    - [Join a room:](#join-a-room)
    - [View your stream:](#view-your-stream)
  - [📚 Documentation](#-documentation)
  - [🛠️ Common Use Cases](#-common-use-cases)
    - [IRL Streaming](#irl-streaming)
    - [Security Camera](#security-camera)
    - [Multi-Camera Production](#multi-camera-production)
  - [❓ Troubleshooting](#-troubleshooting)
  - [🤝 Contributing](#-contributing)
  - [📞 Support](#-support)
  - [📜 License](#-license)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# <img src='https://github.com/user-attachments/assets/db676147-1888-44fe-a5a0-5c04921d2c06' height="50"> Raspberry Ninja

**Turn any device into a low-latency streaming camera for VDO.Ninja**

## 🚀 Quick Start

```bash
curl -sSL https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh | bash
```

That's it! The installer will guide you through everything.

## 📖 What is Raspberry Ninja?

Raspberry Ninja transforms your Raspberry Pi, Nvidia Jetson, or any Linux/Mac/Windows computer into a professional streaming device that works seamlessly with [VDO.Ninja](https://vdo.ninja). 

### Key Features:
- 🎥 **Ultra-low latency** streaming (under 100ms)
- 🔧 **Hardware acceleration** on supported devices
- 📹 **Multi-stream recording** from VDO.Ninja rooms
- 🎮 **Works with OBS** and other streaming software
- 🆓 **Completely free** and open source

### Perfect for:
- IRL streaming setups
- Remote cameras for production
- Security/monitoring systems
- Educational streaming
- Live event coverage

## 💻 Supported Platforms

- **Raspberry Pi** (all models, best with Pi 4/5)
- **Nvidia Jetson** (Nano, Xavier, Orin)
- **Orange Pi** and other SBCs
- **Ubuntu/Debian Linux**
- **Windows** (via WSL2)
- **macOS**

## 📥 Installation

### Option 1: Universal Installer (Recommended)

Our intelligent installer auto-detects your platform and guides you through setup:

```bash
# Download and run
wget https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh
chmod +x install.sh
./install.sh
```

Choose from three installation types:
1. **Basic** - Just install dependencies (most users)
2. **Configured** - Create a reusable config file
3. **Auto-start** - Set up as a boot service

### Option 2: Manual Installation

For advanced users who want platform-specific optimizations:

- [Raspberry Pi Guide](installers/raspberry_pi/README.md) - Optimized for Pi hardware
- [Nvidia Jetson Guide](installers/nvidia_jetson/README.md) - NVENC acceleration
- [Ubuntu/Debian Guide](installers/ubuntu/README.md) - Desktop Linux
- [Windows WSL Guide](installers/wsl/README.md) - Windows subsystem
- [macOS Guide](installers/mac/readme.md) - Mac installation

### Option 3: Quick Dependencies Only

For Debian/Ubuntu systems:

```bash
sudo apt update && sudo apt install -y \
    python3-pip gstreamer1.0-tools gstreamer1.0-nice \
    gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly \
    gstreamer1.0-plugins-good gstreamer1.0-libav \
    python3-gi python3-gi-cairo gir1.2-gstreamer-1.0

pip3 install websockets cryptography aiohttp
```

## 🎬 Basic Usage

### Test your setup:
```bash
python3 publish.py --test
```

### Stream with auto-generated ID:
```bash
python3 publish.py
```

### Stream to specific ID:
```bash
python3 publish.py --streamid mycamera1
```

### Join a room:
```bash
python3 publish.py --room myroom
```

### View your stream:
Open https://vdo.ninja/?view=YOUR_STREAM_ID in any browser

## 📚 Documentation

- [Quick Start Guide](QUICK_START.md) - Get streaming in under 60 seconds
- [Command Line Options](docs/CLI_REFERENCE.md) - All available parameters
- [Hardware Setup](docs/HARDWARE.md) - Camera and audio configuration
- [Recording Guide](docs/RECORDING.md) - Save streams locally
- [Advanced Features](docs/ADVANCED.md) - NDI, RTMP, HLS, and more

## 🛠️ Common Use Cases

### IRL Streaming
```bash
python3 publish.py --streamid irl --bitrate 4000 --width 1920 --height 1080
```

### Security Camera
```bash
python3 publish.py --streamid camera1 --room security --framerate 15 --bitrate 1000
```

### Multi-Camera Production
```bash
# Camera 1
python3 publish.py --streamid cam1 --room production

# Camera 2 (on another device)
python3 publish.py --streamid cam2 --room production

# View all cameras at: https://vdo.ninja/?room=production
```

## ❓ Troubleshooting

- **No camera detected?** Run `v4l2-ctl --list-devices` to see available cameras
- **High CPU usage?** Lower bitrate/resolution or use hardware encoding
- **Connection issues?** Check firewall and try `--server wss://apibackup.vdo.ninja:443`

## 🤝 Contributing

Contributions welcome! Please check our [Contributing Guide](CONTRIBUTING.md).

## 📞 Support

- **Discord**: [VDO.Ninja Discord](https://discord.vdo.ninja) (#raspberry-ninja channel)
- **Issues**: [GitHub Issues](https://github.com/steveseguin/raspberry_ninja/issues)

## 📜 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file.

---

<p align="center">
Made with ❤️ by <a href="https://github.com/steveseguin">Steve Seguin</a> and contributors
</p>
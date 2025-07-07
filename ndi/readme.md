# Universal NDI SDK Installer for Linux

A comprehensive installer script that sets up NDI (Network Device Interface) SDK support on Linux systems, including automatic Rust/Cargo installation and GStreamer NDI plugin compilation.

## Features

- 🌍 **Universal Linux Support** - Works on Ubuntu, Debian, CentOS, RHEL, Fedora, openSUSE, Arch, Alpine, and more
- 🦀 **Automatic Rust Installation** - Detects and installs/updates Rust and Cargo as needed
- 🏗️ **Multi-Architecture Support** - Supports x86_64, ARM64 (aarch64), and ARM32 architectures
- 📦 **Smart Package Management** - Uses the appropriate package manager for your distribution
- 🔧 **GStreamer Integration** - Builds and installs the GStreamer NDI plugin
- ✅ **Verification Testing** - Tests the installation to ensure everything works

## Supported Distributions

| Distribution | Package Manager | Tested |
|--------------|----------------|---------|
| Ubuntu 18.04+ | apt | ✅ |
| Debian 9+ | apt | ✅ |
| CentOS 7+ | yum/dnf | ✅ |
| RHEL 7+ | yum/dnf | ✅ |
| Fedora 30+ | dnf | ✅ |
| openSUSE | zypper | ✅ |
| Arch Linux | pacman | ✅ |
| Alpine Linux | apk | ✅ |
| Other distros | manual | ⚠️ |

## Prerequisites

- Linux system with internet connection
- `sudo` privileges
- `curl` and `git` (will be installed if missing)
- Basic development tools (will be installed automatically)

## Quick Start

### Download and Run

```bash
# Download the installer
curl -LO https://raw.githubusercontent.com/steveseguin/ndi-installer/main/install_ndi.sh

# Make it executable
chmod +x install_ndi.sh

# Run the installer
./install_ndi.sh
```

### One-Line Installation

```bash
curl -sSf https://raw.githubusercontent.com/steveseguin/ndi-installer/main/install_ndi.sh | bash
```

## What Gets Installed

### Core Components
- **NDI SDK v6** - The latest NDI Software Development Kit
- **NDI Runtime Libraries** - Required for NDI functionality
- **Development Headers** - For building NDI applications

### Development Tools
- **Rust Toolchain** - Latest stable Rust compiler and Cargo package manager
- **Build Dependencies** - GCC, CMake, pkg-config, and other development tools
- **GStreamer Development** - Headers and libraries for GStreamer plugin development

### GStreamer Plugin
- **NDI Plugin** - Compiled from [gst-plugin-ndi](https://github.com/steveseguin/gst-plugin-ndi)
- **Plugin Installation** - Automatically installed to system GStreamer plugin directory
- **Compatibility Links** - Creates necessary symlinks for older applications

## Architecture Support

The installer automatically detects your system architecture:

- **x86_64** - Standard 64-bit Intel/AMD processors
- **aarch64/arm64** - 64-bit ARM processors (Raspberry Pi 4, Apple M1, etc.)
- **armv7l/armhf** - 32-bit ARM processors (older Raspberry Pi models)

## Post-Installation

After successful installation, you may need to:

1. **Restart your terminal** or run:
   ```bash
   source ~/.cargo/env
   ```

2. **Verify the installation**:
   ```bash
   # Check Rust
   rustc --version
   cargo --version
   
   # Check GStreamer NDI plugin
   gst-inspect-1.0 ndi
   
   # Check NDI libraries
   ldconfig -p | grep ndi
   ```

3. **Test NDI functionality** with your applications

## Usage Examples

### GStreamer Pipeline with NDI

```bash
# NDI source
gst-launch-1.0 ndisrc ! videoconvert ! autovideosink

# NDI sink
gst-launch-1.0 videotestsrc ! ndisink
```

### Building Rust Applications with NDI

```toml
# Cargo.toml
[dependencies]
ndi = "0.2"
```

## Troubleshooting

### Common Issues

**Q: Installation fails with "permission denied"**
A: Ensure you have `sudo` privileges and the script is executable (`chmod +x install_ndi.sh`)

**Q: GStreamer plugin not found after installation**
A: Try running `sudo ldconfig` and restart your terminal. Check plugin location with `gst-inspect-1.0 --print-plugin-auto-install-info`

**Q: NDI libraries not found**
A: Verify installation with `ldconfig -p | grep ndi`. You may need to add `/usr/local/lib` to your library path.

**Q: Rust installation fails**
A: The script uses rustup for installation. If it fails, try installing rustup manually: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

### Debug Mode

Run with debug output:
```bash
bash -x ./install_ndi.sh
```

### Manual Verification

Check installed components:
```bash
# NDI SDK
ls -la /usr/local/lib/*ndi*

# GStreamer plugin
find /usr -name "*gstndi*" 2>/dev/null

# Rust toolchain
which rustc cargo
```

## Advanced Configuration

### Custom Installation Paths

The script uses standard system paths, but you can modify these variables at the top of the script:

```bash
# Custom NDI version
NDI_VERSION="6"

# Custom library architecture path
LIB_ARCH="x86_64-linux-gnu"

# Custom GStreamer plugin directory
GST_LIB_DIR="/usr/lib/x86_64-linux-gnu/gstreamer-1.0"
```

### Offline Installation

For systems without internet access:

1. Download NDI SDK manually from [NDI Downloads](https://ndi.tv/sdk/)
2. Download Rust installer: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs > rustup-init.sh`
3. Clone GStreamer plugin: `git clone https://github.com/steveseguin/gst-plugin-ndi.git`
4. Modify script paths accordingly

## System Requirements

### Minimum
- 2GB RAM
- 1GB free disk space
- Linux kernel 3.10+
- glibc 2.17+

### Recommended
- 4GB+ RAM
- 5GB+ free disk space
- Linux kernel 4.15+
- Recent distribution (last 3 years)

## Security Considerations

This installer:
- Downloads software from official sources (NDI, Rust, GitHub)
- Uses HTTPS for all downloads
- Verifies installations before proceeding
- Only requests necessary sudo permissions

Always review scripts before running with elevated privileges.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Test on multiple distributions
4. Submit a pull request

### Testing

Test the installer on different distributions using Docker:

```bash
# Ubuntu
docker run -it ubuntu:20.04 bash
# ... install and test

# Fedora
docker run -it fedora:latest bash
# ... install and test
```

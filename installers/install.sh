#!/bin/bash

# Raspberry Ninja Universal Installer
# Supports: Raspberry Pi, Orange Pi, Nvidia Jetson, Ubuntu, Debian, WSL
# This script provides an interactive installation and setup experience

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Global variables
PLATFORM=""
DISTRO=""
VERSION=""
ARCH=""
IS_WSL=false
IS_RASPBERRY_PI=false
IS_ORANGE_PI=false
IS_JETSON=false
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONFIG_FILE="$HOME/.raspberry_ninja/config.json"
SERVICE_NAME="raspberry-ninja"

# Print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

print_header() {
    echo
    print_color "$BLUE" "=========================================="
    print_color "$BLUE" "       Raspberry Ninja Installer"
    print_color "$BLUE" "=========================================="
    echo
}

# Detect platform and system information
detect_platform() {
    print_color "$YELLOW" "Detecting system platform..."
    
    # Check if running in WSL
    if grep -qi microsoft /proc/version; then
        IS_WSL=true
        PLATFORM="WSL"
    fi
    
    # Get architecture
    ARCH=$(uname -m)
    
    # Get distribution info
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        DISTRO=$ID
        VERSION=$VERSION_ID
    fi
    
    # Check for Raspberry Pi
    if [ -f /proc/device-tree/model ]; then
        MODEL=$(tr -d '\0' < /proc/device-tree/model)
        if [[ $MODEL == *"Raspberry Pi"* ]]; then
            IS_RASPBERRY_PI=true
            PLATFORM="Raspberry Pi"
        elif [[ $MODEL == *"Orange Pi"* ]]; then
            IS_ORANGE_PI=true
            PLATFORM="Orange Pi"
        fi
    fi
    
    # Check for Nvidia Jetson
    if [ -f /etc/nv_tegra_release ] || [ -f /sys/module/tegra_fuse/parameters/tegra_chip_id ]; then
        IS_JETSON=true
        PLATFORM="Nvidia Jetson"
    fi
    
    # Default to generic Linux if not detected
    if [ -z "$PLATFORM" ]; then
        PLATFORM="Linux"
    fi
    
    print_color "$GREEN" "✓ Detected: $PLATFORM ($DISTRO $VERSION) on $ARCH"
    echo
}

# Check if running as root
check_root() {
    if [ "$EUID" -eq 0 ]; then 
        print_color "$YELLOW" "⚠ Running as root. Some operations may create files owned by root."
        print_color "$YELLOW" "  It's recommended to run this script as a regular user with sudo access."
        echo
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Update system packages
update_system() {
    print_color "$YELLOW" "Updating system packages..."
    
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get upgrade -y
    elif command -v dnf &> /dev/null; then
        sudo dnf update -y
    elif command -v yum &> /dev/null; then
        sudo yum update -y
    else
        print_color "$RED" "✗ Package manager not supported. Please update system manually."
        return 1
    fi
    
    print_color "$GREEN" "✓ System updated"
}

# Install platform-specific dependencies
install_dependencies() {
    print_color "$YELLOW" "Installing dependencies for $PLATFORM..."
    
    # Common dependencies for Debian-based systems
    if command -v apt-get &> /dev/null; then
        # Handle Python package management on newer systems
        if [ -f /usr/lib/python3.*/EXTERNALLY-MANAGED ]; then
            print_color "$YELLOW" "Detected PEP 668 system. Using --break-system-packages flag."
            PIP_FLAGS="--break-system-packages"
        else
            PIP_FLAGS=""
        fi
        
        # Core dependencies
        sudo apt-get install -y \
            python3-pip \
            git \
            wget \
            curl \
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
            gstreamer1.0-alsa \
            gstreamer1.0-gl \
            gstreamer1.0-gtk3 \
            gstreamer1.0-pulseaudio \
            gstreamer1.0-nice \
            libcairo2-dev \
            libgirepository1.0-dev \
            python3-gi \
            python3-gi-cairo \
            gir1.2-gstreamer-1.0 \
            gir1.2-gst-plugins-base-1.0
        
        # Platform-specific packages
        if [ "$IS_RASPBERRY_PI" = true ]; then
            print_color "$YELLOW" "Installing Raspberry Pi specific packages..."
            sudo apt-get install -y \
                libraspberrypi-bin \
                libraspberrypi-dev \
                rpicam-apps-lite || true  # rpicam-apps might not be available on older systems
            
            # Add user to video group
            sudo usermod -a -G video $USER
        fi
        
        if [ "$IS_JETSON" = true ]; then
            print_color "$YELLOW" "Installing Jetson specific packages..."
            sudo apt-get install -y \
                nvidia-l4t-gstreamer \
                deepstream-6.0 || true  # Deepstream might not be needed
        fi
        
        # Python packages
        print_color "$YELLOW" "Installing Python packages..."
        pip3 install $PIP_FLAGS websockets cryptography aiohttp PyGObject
        
    else
        print_color "$RED" "✗ Unsupported package manager. Please install dependencies manually."
        return 1
    fi
    
    print_color "$GREEN" "✓ Dependencies installed"
}

# Detect available cameras
detect_cameras() {
    print_color "$YELLOW" "Detecting available cameras..."
    
    CAMERAS=()
    
    # Check for V4L2 devices
    if [ -d /dev ]; then
        for device in /dev/video*; do
            if [ -e "$device" ]; then
                # Try to get device name
                if command -v v4l2-ctl &> /dev/null; then
                    name=$(v4l2-ctl -d "$device" --info 2>/dev/null | grep "Card type" | cut -d: -f2 | xargs)
                    if [ -n "$name" ]; then
                        CAMERAS+=("$device - $name")
                    else
                        CAMERAS+=("$device")
                    fi
                else
                    CAMERAS+=("$device")
                fi
            fi
        done
    fi
    
    # Check for Raspberry Pi camera
    if [ "$IS_RASPBERRY_PI" = true ]; then
        if command -v libcamera-hello &> /dev/null; then
            if libcamera-hello --list-cameras &> /dev/null; then
                CAMERAS+=("libcamera - Raspberry Pi Camera Module")
            fi
        elif command -v raspistill &> /dev/null; then
            if vcgencmd get_camera &> /dev/null | grep -q "detected=1"; then
                CAMERAS+=("raspicam - Legacy Raspberry Pi Camera")
            fi
        fi
    fi
    
    if [ ${#CAMERAS[@]} -eq 0 ]; then
        print_color "$YELLOW" "No cameras detected. You can still use test sources."
    else
        print_color "$GREEN" "✓ Found ${#CAMERAS[@]} camera(s):"
        for cam in "${CAMERAS[@]}"; do
            echo "  - $cam"
        done
    fi
    echo
}

# Create configuration
create_config() {
    print_color "$YELLOW" "Setting up configuration..."
    
    # Create config directory
    mkdir -p "$(dirname "$CONFIG_FILE")"
    
    # Interactive setup
    echo
    print_color "$BLUE" "=== Raspberry Ninja Configuration ==="
    echo
    
    # Stream ID
    read -p "Enter your stream ID (leave empty for random): " STREAM_ID
    
    # Room name
    read -p "Enter room name (optional): " ROOM_NAME
    
    # Server
    print_color "$YELLOW" "Select VDO.Ninja server:"
    echo "1) vdo.ninja (default)"
    echo "2) wss.vdo.ninja"
    echo "3) apibackup.vdo.ninja"
    echo "4) Custom server"
    read -p "Choice [1-4]: " server_choice
    
    case $server_choice in
        2) SERVER="wss://wss.vdo.ninja:443" ;;
        3) SERVER="wss://apibackup.vdo.ninja:443" ;;
        4) read -p "Enter custom server URL: " SERVER ;;
        *) SERVER="wss://vdo.ninja:443" ;;
    esac
    
    # Video settings
    read -p "Video bitrate in kbps [2000]: " BITRATE
    BITRATE=${BITRATE:-2000}
    
    read -p "Video width [1280]: " WIDTH
    WIDTH=${WIDTH:-1280}
    
    read -p "Video height [720]: " HEIGHT
    HEIGHT=${HEIGHT:-720}
    
    read -p "Framerate [30]: " FRAMERATE
    FRAMERATE=${FRAMERATE:-30}
    
    # Camera selection
    print_color "$YELLOW" "Select video source:"
    echo "1) Test source (recommended for first run)"
    echo "2) USB camera (/dev/video0)"
    echo "3) Raspberry Pi camera (libcamera)"
    echo "4) Custom pipeline"
    read -p "Choice [1-4]: " camera_choice
    
    case $camera_choice in
        2) VIDEO_SOURCE="v4l2" ;;
        3) VIDEO_SOURCE="libcamera" ;;
        4) 
            read -p "Enter custom video pipeline: " CUSTOM_VIDEO_PIPELINE
            VIDEO_SOURCE="custom"
            ;;
        *) VIDEO_SOURCE="test" ;;
    esac
    
    # Audio settings
    read -p "Enable audio? (Y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        AUDIO_ENABLED="false"
    else
        AUDIO_ENABLED="true"
    fi
    
    # Create config file
    cat > "$CONFIG_FILE" << EOF
{
    "stream_id": "$STREAM_ID",
    "room": "$ROOM_NAME",
    "server": "$SERVER",
    "bitrate": $BITRATE,
    "width": $WIDTH,
    "height": $HEIGHT,
    "framerate": $FRAMERATE,
    "video_source": "$VIDEO_SOURCE",
    "custom_video_pipeline": "$CUSTOM_VIDEO_PIPELINE",
    "audio_enabled": $AUDIO_ENABLED,
    "platform": "$PLATFORM",
    "auto_start": false
}
EOF
    
    print_color "$GREEN" "✓ Configuration saved to $CONFIG_FILE"
    echo
}

# Setup auto-start service
setup_autostart() {
    print_color "$YELLOW" "Setting up auto-start service..."
    
    read -p "Enable auto-start on boot? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Create systemd service
        sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null << EOF
[Unit]
Description=Raspberry Ninja Streaming Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/publish.py --config $CONFIG_FILE
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
        
        # Enable and start service
        sudo systemctl daemon-reload
        sudo systemctl enable $SERVICE_NAME.service
        
        print_color "$GREEN" "✓ Auto-start service created"
        
        read -p "Start the service now? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            sudo systemctl start $SERVICE_NAME.service
            print_color "$GREEN" "✓ Service started"
            echo
            print_color "$YELLOW" "Check service status with: sudo systemctl status $SERVICE_NAME"
            print_color "$YELLOW" "View logs with: sudo journalctl -u $SERVICE_NAME -f"
        fi
        
        # Update config to reflect auto-start
        if command -v jq &> /dev/null; then
            jq '.auto_start = true' "$CONFIG_FILE" > "$CONFIG_FILE.tmp" && mv "$CONFIG_FILE.tmp" "$CONFIG_FILE"
        fi
    fi
    echo
}

# Test installation
test_installation() {
    print_color "$YELLOW" "Testing installation..."
    
    read -p "Run a test stream? (Y/n): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        print_color "$YELLOW" "Starting test stream for 10 seconds..."
        timeout 10 python3 "$SCRIPT_DIR/publish.py" --test || true
        echo
        print_color "$GREEN" "✓ Test completed"
    fi
}

# Print summary and next steps
print_summary() {
    echo
    print_color "$BLUE" "=========================================="
    print_color "$BLUE" "        Installation Complete!"
    print_color "$BLUE" "=========================================="
    echo
    print_color "$GREEN" "✓ Platform: $PLATFORM"
    print_color "$GREEN" "✓ Configuration: $CONFIG_FILE"
    
    if systemctl is-enabled $SERVICE_NAME &> /dev/null; then
        print_color "$GREEN" "✓ Auto-start: Enabled"
    fi
    
    echo
    print_color "$YELLOW" "Next steps:"
    echo "1. Test your setup:"
    echo "   python3 publish.py --config $CONFIG_FILE"
    echo
    echo "2. View all options:"
    echo "   python3 publish.py --help"
    echo
    echo "3. Manual streaming:"
    echo "   python3 publish.py --streamid YOUR_ID"
    echo
    
    if [ -n "$STREAM_ID" ]; then
        echo "4. View your stream at:"
        echo "   https://vdo.ninja/?view=$STREAM_ID"
        if [ -n "$ROOM_NAME" ]; then
            echo "   or join room: https://vdo.ninja/?room=$ROOM_NAME"
        fi
    fi
    
    echo
    print_color "$YELLOW" "For help, visit: https://github.com/steveseguin/raspberry_ninja"
    echo
}

# Main installation flow
main() {
    print_header
    detect_platform
    check_root
    
    # Confirm installation
    print_color "$YELLOW" "This will install Raspberry Ninja on your $PLATFORM system."
    read -p "Continue? (Y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        print_color "$RED" "Installation cancelled."
        exit 0
    fi
    
    # Run installation steps
    update_system
    install_dependencies
    detect_cameras
    create_config
    setup_autostart
    test_installation
    print_summary
    
    # Remind about group membership
    if [ "$IS_RASPBERRY_PI" = true ] || [ "$IS_JETSON" = true ]; then
        print_color "$YELLOW" "Note: You may need to log out and back in for video group membership to take effect."
    fi
}

# Run main function
main
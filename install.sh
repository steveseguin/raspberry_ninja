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
# Determine script directory - handle both piped and direct execution
if [ -n "${BASH_SOURCE[0]}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
else
    # When piped, we need to find or clone the repository
    SCRIPT_DIR=""
fi

# We'll set CONFIG_FILE after we know the actual directory
CONFIG_FILE=""
SERVICE_NAME="raspberry-ninja"
SETUP_AUTOSTART=false
install_type=""
NON_INTERACTIVE=false

# Check for command line arguments
for arg in "$@"; do
    case $arg in
        --non-interactive|-y|--yes)
            NON_INTERACTIVE=true
            ;;
        --help|-h)
            echo "Raspberry Ninja Installer"
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --non-interactive, -y  Run in non-interactive mode"
            echo "  --help, -h            Show this help message"
            exit 0
            ;;
    esac
done

# Check if we're running in non-interactive mode (piped input)
if [ ! -t 0 ] && [ ! -e /dev/tty ]; then
    NON_INTERACTIVE=true
fi

# Print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Safe read function that works with piped input
safe_read() {
    local prompt="$1"
    local options="$2"
    local default_value="$3"
    
    if [ "$NON_INTERACTIVE" = true ]; then
        if [ -n "$default_value" ]; then
            REPLY="$default_value"
            print_color "$YELLOW" "Non-interactive mode: Using default value '$default_value'"
        else
            print_color "$RED" "Error: Non-interactive mode requires default values"
            exit 1
        fi
    else
        if [ -n "$options" ]; then
            read -p "$prompt" $options < /dev/tty
        else
            read -p "$prompt" < /dev/tty
        fi
    fi
}

print_header() {
    echo
    print_color "$BLUE" "=========================================="
    print_color "$BLUE" "       Raspberry Ninja Installer"
    print_color "$BLUE" "=========================================="
    echo
    
    if [ "$NON_INTERACTIVE" = true ]; then
        print_color "$YELLOW" "Running in NON-INTERACTIVE mode"
        print_color "$YELLOW" "Only basic dependency installation will be performed."
        print_color "$YELLOW" ""
        print_color "$YELLOW" "For full setup with configuration and auto-start:"
        print_color "$YELLOW" "  wget https://raw.githubusercontent.com/steveseguin/raspberry_ninja/main/install.sh"
        print_color "$YELLOW" "  chmod +x install.sh"
        print_color "$YELLOW" "  ./install.sh"
        echo
    fi
}

# Find or setup the raspberry_ninja directory
setup_repository() {
    if [ -z "$SCRIPT_DIR" ]; then
        # We're running from curl, need to find or clone the repo
        print_color "$YELLOW" "Checking for Raspberry Ninja repository..."
        
        # Check if we're already in the repo
        if [ -f "$(pwd)/publish.py" ]; then
            SCRIPT_DIR="$(pwd)"
            print_color "$GREEN" "✓ Already in Raspberry Ninja repository at: $SCRIPT_DIR"
        elif [ -f "$(pwd)/raspberry_ninja/publish.py" ]; then
            SCRIPT_DIR="$(pwd)/raspberry_ninja"
            print_color "$GREEN" "✓ Found existing installation at: $SCRIPT_DIR"
        else
            # Need to clone the repository to current directory
            print_color "$YELLOW" "Raspberry Ninja repository not found. Installing to current directory..."
            
            # Clone to current directory
            INSTALL_DIR="$(pwd)/raspberry_ninja"
            
            # Clone the repository
            print_color "$YELLOW" "Cloning repository to $INSTALL_DIR..."
            if command -v git &> /dev/null; then
                # Check if directory already exists
                if [ -d "$INSTALL_DIR" ]; then
                    SCRIPT_DIR="$INSTALL_DIR"
                    print_color "$YELLOW" "Directory $INSTALL_DIR already exists. Checking for updates..."
                    
                    # Check if it's a git repository
                    if [ -d "$INSTALL_DIR/.git" ]; then
                        # Pull latest changes
                        cd "$INSTALL_DIR"
                        if git pull origin main; then
                            print_color "$GREEN" "✓ Updated to latest version"
                        else
                            print_color "$YELLOW" "⚠ Could not update (may have local changes)"
                        fi
                        cd - > /dev/null
                    else
                        print_color "$YELLOW" "⚠ Not a git repository, using as-is"
                    fi
                    
                    # Verify it's a valid installation
                    if [ -f "$SCRIPT_DIR/publish.py" ]; then
                        print_color "$GREEN" "✓ Using existing installation at: $SCRIPT_DIR"
                    else
                        print_color "$YELLOW" "⚠ Directory exists but publish.py not found. Attempting fresh clone..."
                        # Try to clone into a temp dir and move files
                        TEMP_DIR="$(mktemp -d)"
                        if git clone https://github.com/steveseguin/raspberry_ninja.git "$TEMP_DIR/raspberry_ninja"; then
                            cp -r "$TEMP_DIR/raspberry_ninja/"* "$INSTALL_DIR/" 2>/dev/null || true
                            cp -r "$TEMP_DIR/raspberry_ninja/".* "$INSTALL_DIR/" 2>/dev/null || true
                            rm -rf "$TEMP_DIR"
                            print_color "$GREEN" "✓ Repository files copied to: $SCRIPT_DIR"
                        else
                            rm -rf "$TEMP_DIR"
                            print_color "$RED" "✗ Failed to get repository files"
                            exit 1
                        fi
                    fi
                else
                    if git clone https://github.com/steveseguin/raspberry_ninja.git "$INSTALL_DIR"; then
                        SCRIPT_DIR="$INSTALL_DIR"
                        print_color "$GREEN" "✓ Repository cloned successfully to: $SCRIPT_DIR"
                        
                        # Verify the clone worked
                        if [ -f "$SCRIPT_DIR/publish.py" ]; then
                            print_color "$GREEN" "✓ Verified: publish.py found in $SCRIPT_DIR"
                        else
                            print_color "$RED" "✗ Error: Repository cloned but publish.py not found"
                            exit 1
                        fi
                    else
                        print_color "$RED" "✗ Failed to clone repository"
                        print_color "$RED" "  Please check your internet connection and try again"
                        exit 1
                    fi
                fi
            else
                print_color "$RED" "✗ Git is not installed. This should not happen."
                exit 1
            fi
        fi
    else
        # SCRIPT_DIR was already set (running from downloaded script)
        # Verify it's actually the raspberry_ninja directory
        if [ ! -f "$SCRIPT_DIR/publish.py" ]; then
            # Not in the right directory, find or clone
            print_color "$YELLOW" "Current directory is not the Raspberry Ninja repository..."
            
            # Check if raspberry_ninja exists in current directory
            if [ -f "$(pwd)/raspberry_ninja/publish.py" ]; then
                SCRIPT_DIR="$(pwd)/raspberry_ninja"
                print_color "$GREEN" "✓ Found existing installation at: $SCRIPT_DIR"
            else
                # Need to clone the repository to current directory
                print_color "$YELLOW" "Cloning Raspberry Ninja to current directory..."
                
                # Clone to current directory
                INSTALL_DIR="$(pwd)/raspberry_ninja"
                
                # Clone the repository
                print_color "$YELLOW" "Cloning repository to $INSTALL_DIR..."
                if command -v git &> /dev/null; then
                    # Check if directory already exists
                    if [ -d "$INSTALL_DIR" ]; then
                        SCRIPT_DIR="$INSTALL_DIR"
                        print_color "$YELLOW" "Directory $INSTALL_DIR already exists. Checking for updates..."
                        
                        # Check if it's a git repository
                        if [ -d "$INSTALL_DIR/.git" ]; then
                            # Pull latest changes
                            cd "$INSTALL_DIR"
                            if git pull origin main; then
                                print_color "$GREEN" "✓ Updated to latest version"
                            else
                                print_color "$YELLOW" "⚠ Could not update (may have local changes)"
                            fi
                            cd - > /dev/null
                        else
                            print_color "$YELLOW" "⚠ Not a git repository, using as-is"
                        fi
                        
                        # Verify it's a valid installation
                        if [ -f "$SCRIPT_DIR/publish.py" ]; then
                            print_color "$GREEN" "✓ Using existing installation at: $SCRIPT_DIR"
                        else
                            print_color "$YELLOW" "⚠ Directory exists but publish.py not found. Attempting fresh clone..."
                            # Try to clone into a temp dir and move files
                            TEMP_DIR="$(mktemp -d)"
                            if git clone https://github.com/steveseguin/raspberry_ninja.git "$TEMP_DIR/raspberry_ninja"; then
                                cp -r "$TEMP_DIR/raspberry_ninja/"* "$INSTALL_DIR/" 2>/dev/null || true
                                cp -r "$TEMP_DIR/raspberry_ninja/".* "$INSTALL_DIR/" 2>/dev/null || true
                                rm -rf "$TEMP_DIR"
                                print_color "$GREEN" "✓ Repository files copied to: $SCRIPT_DIR"
                            else
                                rm -rf "$TEMP_DIR"
                                print_color "$RED" "✗ Failed to get repository files"
                                exit 1
                            fi
                        fi
                    else
                        if git clone https://github.com/steveseguin/raspberry_ninja.git "$INSTALL_DIR"; then
                            SCRIPT_DIR="$INSTALL_DIR"
                            print_color "$GREEN" "✓ Repository cloned successfully to: $SCRIPT_DIR"
                        else
                            print_color "$RED" "✗ Failed to clone repository"
                            print_color "$RED" "  Please check your internet connection and try again"
                            exit 1
                        fi
                    fi
                else
                    print_color "$RED" "✗ Git is not installed. This should not happen."
                    exit 1
                fi
            fi
        fi
    fi
    
    # Now set the config file location
    CONFIG_FILE="$SCRIPT_DIR/config.json"
    
    # Final verification
    if [ ! -f "$SCRIPT_DIR/publish.py" ]; then
        print_color "$RED" "✗ Error: publish.py not found in $SCRIPT_DIR"
        print_color "$RED" "  Something went wrong during setup"
        exit 1
    fi
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
        safe_read "Continue anyway? (y/N): " "-n 1 -r" "N"
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
        
        # Try the normal installation first
        if pip3 install $PIP_FLAGS websockets cryptography aiohttp PyGObject 2>/dev/null; then
            print_color "$GREEN" "✓ Python packages installed successfully"
        else
            # Fallback: Fix broken pip installations
            print_color "$YELLOW" "Standard pip installation failed. Attempting to fix..."
            
            # Remove broken pip symlinks if they exist
            if [ -L /usr/local/bin/pip3 ] && [ ! -e /usr/local/bin/pip3 ]; then
                print_color "$YELLOW" "Removing broken pip3 symlink..."
                sudo rm -f /usr/local/bin/pip3
            fi
            if [ -L /usr/local/bin/pip ] && [ ! -e /usr/local/bin/pip ]; then
                print_color "$YELLOW" "Removing broken pip symlink..."
                sudo rm -f /usr/local/bin/pip
            fi
            
            # Ensure python3-pip is installed
            if ! dpkg -l python3-pip &> /dev/null; then
                print_color "$YELLOW" "Installing python3-pip package..."
                sudo apt-get install -y python3-pip
            fi
            
            # Find the correct pip command
            PIP_CMD=""
            
            # First try python3 -m pip
            if python3 -m pip --version &> /dev/null; then
                PIP_CMD="python3 -m pip"
                print_color "$GREEN" "✓ Using python3 -m pip"
            # Then try direct pip3 command
            elif command -v pip3 &> /dev/null && pip3 --version &> /dev/null; then
                PIP_CMD="pip3"
                print_color "$GREEN" "✓ Using pip3"
            # Try /usr/bin/pip3
            elif [ -x /usr/bin/pip3 ] && /usr/bin/pip3 --version &> /dev/null; then
                PIP_CMD="/usr/bin/pip3"
                print_color "$GREEN" "✓ Using /usr/bin/pip3"
            else
                # Last resort - bootstrap pip
                print_color "$YELLOW" "Bootstrapping pip..."
                curl -sS https://bootstrap.pypa.io/get-pip.py | python3 || true
                if python3 -m pip --version &> /dev/null; then
                    PIP_CMD="python3 -m pip"
                    print_color "$GREEN" "✓ pip bootstrapped successfully"
                else
                    print_color "$RED" "✗ Failed to install pip. Please install manually."
                    return 1
                fi
            fi
            
            # Ensure pip is up to date
            print_color "$YELLOW" "Updating pip..."
            $PIP_CMD install --upgrade pip $PIP_FLAGS || true
            
            # Install Python packages with the fixed pip
            print_color "$YELLOW" "Installing Python packages..."
            $PIP_CMD install $PIP_FLAGS websockets cryptography aiohttp PyGObject
        fi
        
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
    
    # Config file is now in the script directory, no need to create a separate folder
    
    # Check for non-interactive mode
    if [ "$NON_INTERACTIVE" = true ]; then
        # In non-interactive mode, do basic installation only
        install_type="1"
        print_color "$YELLOW" "Non-interactive mode: Performing basic installation only"
        print_color "$GREEN" "✓ Dependencies installed. You can now run:"
        echo "   python3 publish.py --help"
        return
    fi
    
    # Ask what the user wants to do
    echo
    print_color "$BLUE" "=== Installation Type ==="
    echo
    print_color "$YELLOW" "What would you like to do?"
    echo "1) Basic installation (just install dependencies)"
    echo "2) Configure for manual use (install + create config file)"
    echo "3) Full setup with auto-start (install + config + boot service)"
    safe_read "Choice [1-3]: " "" "1"
    install_type="$REPLY"
    
    case $install_type in
        1)
            # Basic installation - skip configuration
            print_color "$GREEN" "✓ Dependencies installed. You can now run:"
            echo "   python3 publish.py --help"
            return
            ;;
        2)
            # Manual configuration
            SETUP_AUTOSTART=false
            ;;
        3)
            # Full setup with auto-start
            SETUP_AUTOSTART=true
            ;;
        *)
            # Default to basic
            print_color "$GREEN" "✓ Dependencies installed. You can now run:"
            echo "   python3 publish.py --help"
            return
            ;;
    esac
    
    # Interactive setup for options 2 and 3
    echo
    print_color "$BLUE" "=== Raspberry Ninja Configuration ==="
    echo
    
    # Stream ID
    safe_read "Enter your stream ID (leave empty for random): " "" ""
    STREAM_ID="$REPLY"
    
    # Room name
    safe_read "Enter room name (optional): " "" ""
    ROOM_NAME="$REPLY"
    
    # Server
    print_color "$YELLOW" "Select handshake server:"
    echo "1) wss://wss.vdo.ninja:443 (Primary server - recommended)"
    echo "2) wss://apibackup.vdo.ninja:443 (Backup server)"
    echo "3) Custom server"
    safe_read "Choice [1-3]: " "" "1"
    server_choice="$REPLY"
    
    case $server_choice in
        2) SERVER="wss://apibackup.vdo.ninja:443" ;;
        3) 
            echo "Enter custom handshake server URL"
            echo "Format: wss://your-server.com:443"
            safe_read "Server URL: " "" "wss://wss.vdo.ninja:443"
            SERVER="$REPLY" 
            ;;
        *) SERVER="wss://wss.vdo.ninja:443" ;;
    esac
    
    # Ask about advanced settings
    safe_read "Configure advanced video settings? (y/N): " "-n 1 -r" "N"
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Video settings
        safe_read "Video bitrate in kbps [2000]: " "" "2000"
        BITRATE="${REPLY:-2000}"
        
        safe_read "Video width [1280]: " "" "1280"
        WIDTH="${REPLY:-1280}"
        
        safe_read "Video height [720]: " "" "720"
        HEIGHT="${REPLY:-720}"
        
        safe_read "Framerate [30]: " "" "30"
        FRAMERATE="${REPLY:-30}"
    else
        # Use defaults
        BITRATE=2000
        WIDTH=1280
        HEIGHT=720
        FRAMERATE=30
    fi
    
    # Camera selection
    print_color "$YELLOW" "Select video source:"
    echo "1) Test source (recommended for first run)"
    echo "2) USB camera (/dev/video0)"
    echo "3) Raspberry Pi camera (libcamera)"
    echo "4) Custom pipeline"
    safe_read "Choice [1-4]: " "" "1"
    camera_choice="$REPLY"
    
    case $camera_choice in
        2) VIDEO_SOURCE="v4l2" ;;
        3) VIDEO_SOURCE="libcamera" ;;
        4) 
            safe_read "Enter custom video pipeline: " "" ""
            CUSTOM_VIDEO_PIPELINE="$REPLY"
            VIDEO_SOURCE="custom"
            ;;
        *) VIDEO_SOURCE="test" ;;
    esac
    
    # Audio settings
    safe_read "Enable audio? (Y/n): " "-n 1 -r" "Y"
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
    # Skip if user chose option 2 (manual configuration only)
    if [ "$SETUP_AUTOSTART" = false ]; then
        return
    fi
    
    print_color "$YELLOW" "Setting up auto-start service..."
    
    # For option 3, ask for confirmation
    safe_read "Enable auto-start on boot? (Y/n): " "-n 1 -r" "Y"
    echo
    
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        # Verify config file exists
        if [ ! -f "$CONFIG_FILE" ]; then
            print_color "$RED" "✗ Config file not found at: $CONFIG_FILE"
            print_color "$RED" "  Cannot create service without configuration"
            return
        fi
        
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
        
        print_color "$GREEN" "✓ Auto-start service created and enabled"
        
        # Print service information
        echo
        print_color "$BLUE" "=== Service Information ==="
        print_color "$YELLOW" "Service name: $SERVICE_NAME"
        print_color "$YELLOW" "Service file: /etc/systemd/system/$SERVICE_NAME.service"
        print_color "$YELLOW" "Config file: $CONFIG_FILE"
        print_color "$YELLOW" "Working directory: $SCRIPT_DIR"
        echo
        
        safe_read "Start the service now? (Y/n): " "-n 1 -r" "Y"
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            if sudo systemctl start $SERVICE_NAME.service; then
                print_color "$GREEN" "✓ Service started successfully"
                
                # Wait a moment for service to initialize
                sleep 2
                
                # Check if service is running
                if systemctl is-active --quiet $SERVICE_NAME.service; then
                    print_color "$GREEN" "✓ Service is running"
                else
                    print_color "$RED" "⚠ Service may have failed to start"
                    print_color "$YELLOW" "Check logs with: sudo journalctl -u $SERVICE_NAME -n 50"
                fi
            else
                print_color "$RED" "✗ Failed to start service"
            fi
            echo
        fi
        
        # Print management commands
        print_color "$BLUE" "=== Service Management Commands ==="
        print_color "$YELLOW" "View status:    sudo systemctl status $SERVICE_NAME"
        print_color "$YELLOW" "Stop service:   sudo systemctl stop $SERVICE_NAME"
        print_color "$YELLOW" "Start service:  sudo systemctl start $SERVICE_NAME"
        print_color "$YELLOW" "Restart:        sudo systemctl restart $SERVICE_NAME"
        print_color "$YELLOW" "View logs:      sudo journalctl -u $SERVICE_NAME -f"
        print_color "$YELLOW" "Disable boot:   sudo systemctl disable $SERVICE_NAME"
        print_color "$YELLOW" "Enable boot:    sudo systemctl enable $SERVICE_NAME"
        
        # Update config to reflect auto-start
        if command -v jq &> /dev/null; then
            jq '.auto_start = true' "$CONFIG_FILE" > "$CONFIG_FILE.tmp" && mv "$CONFIG_FILE.tmp" "$CONFIG_FILE"
        fi
    fi
    echo
}

# Test installation
test_installation() {
    # Skip test for basic installation
    if [ "$install_type" = "1" ]; then
        return
    fi
    
    print_color "$YELLOW" "Testing installation..."
    
    safe_read "Run a test stream? (Y/n): " "-n 1 -r" "Y"
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
    
    if [ "$install_type" = "1" ]; then
        # Basic installation summary
        print_color "$GREEN" "✓ Dependencies: Installed"
        echo
        print_color "$YELLOW" "Quick Start Examples:"
        echo
        
        # Check if we need to cd into the directory
        if [ "$(pwd)" != "$SCRIPT_DIR" ]; then
            echo "First, navigate to the installation directory:"
            echo "   cd $SCRIPT_DIR"
            echo
        fi
        
        echo "1. Test with virtual sources:"
        echo "   python3 publish.py --test"
        echo
        echo "2. Stream with default settings:"
        echo "   python3 publish.py"
        echo
        echo "3. Stream to a specific ID:"
        echo "   python3 publish.py --streamid YOUR_CUSTOM_ID"
        echo
        echo "4. Join a room:"
        echo "   python3 publish.py --room YOUR_ROOM_NAME"
        echo
        echo "5. View all options:"
        echo "   python3 publish.py --help"
    else
        # Configuration-based installation summary
        print_color "$GREEN" "✓ Configuration: $CONFIG_FILE"
        
        if systemctl is-enabled $SERVICE_NAME &> /dev/null; then
            print_color "$GREEN" "✓ Auto-start: Enabled"
            
            # Check if service is currently running
            if systemctl is-active --quiet $SERVICE_NAME.service; then
                print_color "$GREEN" "✓ Service Status: Running"
            else
                print_color "$YELLOW" "⚠ Service Status: Not running"
            fi
        fi
        
        echo
        print_color "$YELLOW" "Configuration & Service Details:"
        echo "• Config file: $CONFIG_FILE"
        echo "• Working directory: $SCRIPT_DIR"
        echo "• Edit config: nano $CONFIG_FILE"
        
        if systemctl is-enabled $SERVICE_NAME &> /dev/null; then
            echo "• Service name: $SERVICE_NAME"
            echo "• Service file: /etc/systemd/system/$SERVICE_NAME.service"
            echo
            print_color "$YELLOW" "Service Commands:"
            echo "• Check status: sudo systemctl status $SERVICE_NAME"
            echo "• View logs: sudo journalctl -u $SERVICE_NAME -f"
            echo "• Restart: sudo systemctl restart $SERVICE_NAME"
            echo "• Stop: sudo systemctl stop $SERVICE_NAME"
        fi
        
        echo
        print_color "$YELLOW" "Test your setup:"
        echo "1. Manual test:"
        echo "   cd $SCRIPT_DIR"
        echo "   python3 publish.py --config $CONFIG_FILE"
        echo
        echo "2. View all options:"
        echo "   python3 publish.py --help"
        echo
        echo "3. Manual streaming without config:"
        echo "   python3 publish.py --streamid YOUR_ID"
        echo
        
        if [ -n "$STREAM_ID" ]; then
            echo "4. View your stream at:"
            echo "   https://vdo.ninja/?view=$STREAM_ID"
            if [ -n "$ROOM_NAME" ]; then
                echo "   or join room: https://vdo.ninja/?room=$ROOM_NAME"
            fi
            echo
            echo "Note: Your stream connects to the handshake server at: $SERVER"
        fi
    fi
    
    echo
    print_color "$YELLOW" "For help, visit: https://github.com/steveseguin/raspberry_ninja"
    echo
    print_color "$BLUE" "Raspberry Ninja is installed in: $SCRIPT_DIR"
    echo
}

# Main installation flow
main() {
    print_header
    detect_platform
    check_root
    
    # Confirm installation
    print_color "$YELLOW" "This will install Raspberry Ninja on your $PLATFORM system."
    safe_read "Continue? (Y/n): " "-n 1 -r" "Y"
    echo
    if [[ $REPLY =~ ^[Nn]$ ]]; then
        print_color "$RED" "Installation cancelled."
        exit 0
    fi
    
    # Run installation steps
    update_system
    
    # Install git first if needed
    if ! command -v git &> /dev/null; then
        print_color "$YELLOW" "Installing git..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get install -y git
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y git
        elif command -v yum &> /dev/null; then
            sudo yum install -y git
        fi
    fi
    
    # Now we can setup the repository
    setup_repository
    
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
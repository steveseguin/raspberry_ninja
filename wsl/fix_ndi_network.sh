#!/bin/bash
# Fix NDI discovery between WSL2 and Windows host

echo "Fixing NDI network visibility between WSL2 and Windows..."

# Get WSL2 IP address
WSL_IP=$(ip addr show eth0 | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
echo "WSL2 IP: $WSL_IP"

# Get Windows host IP (WSL2 uses it as default gateway)
WIN_IP=$(ip route show | grep default | awk '{print $3}')
echo "Windows host IP: $WIN_IP"

echo ""
echo "SOLUTION 1: Use NDI Access Manager (Recommended)"
echo "------------------------------------------------"
echo "1. On Windows, open NDI Access Manager"
echo "2. Go to the 'Advanced' tab"
echo "3. Add WSL IP to 'Extra IPs': $WSL_IP"
echo "4. Click 'OK' and restart NDI applications"

echo ""
echo "SOLUTION 2: Use mDNS relay"
echo "--------------------------"
echo "Install avahi in WSL to relay mDNS between WSL and Windows:"
echo "sudo apt-get install avahi-daemon avahi-utils"
echo "sudo service avahi-daemon start"

echo ""
echo "SOLUTION 3: Direct IP Connection"
echo "---------------------------------"
echo "Some NDI viewers allow direct IP connection."
echo "Try connecting directly to: $WSL_IP"

echo ""
echo "SOLUTION 4: Use NDI Proxy"
echo "-------------------------"
echo "Run NDI Proxy on Windows to bridge the networks."

echo ""
echo "TESTING NDI OUTPUT"
echo "------------------"
echo "To test if NDI is working in WSL:"
echo "gst-launch-1.0 videotestsrc ! ndisink ndi-name='WSL-Test'"
echo ""
echo "Then check if 'WSL-Test' appears in your Windows NDI viewer."

# Create a test script
cat > test_ndi_output.sh << 'EOF'
#!/bin/bash
echo "Creating test NDI stream 'WSL-NDI-Test'..."
echo "Check your Windows NDI viewer for this stream."
echo "Press Ctrl+C to stop."
gst-launch-1.0 videotestsrc pattern=ball ! video/x-raw,width=640,height=480,framerate=30/1 ! ndisink ndi-name="WSL-NDI-Test"
EOF

chmod +x test_ndi_output.sh

echo ""
echo "Created test_ndi_output.sh - run it to test NDI visibility"
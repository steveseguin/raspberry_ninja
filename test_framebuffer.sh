#!/bin/bash

# Create test script to reproduce the framebuffer issue
cat << 'EOF' > /tmp/test_framebuffer.py
import sys
import os
import time

# First, let's check what's happening with the GStreamer WebRTC jitterbuffer
os.environ['GST_DEBUG'] = 'webrtcbin:6,rtpjitterbuffer:6'

# Test framebuffer mode
print("Testing framebuffer mode with --h264...")
os.system("cd /app && python3 publish.py --framebuffer test_stream --h264 --noaudio --debug 2>&1 | tee /tmp/framebuffer_debug.log")
EOF

# Run the test in the container
docker run --rm -v $(pwd):/host debian11-gst118 bash -c "
cd /app
# Install websockets if not already installed
pip3 install websockets asyncio 2>/dev/null || true

# Check GStreamer WebRTC plugin
echo '=== Checking WebRTC plugin ==='
gst-inspect-1.0 webrtcbin

echo -e '\n=== Checking jitterbuffer implementation ==='
gst-inspect-1.0 rtpjitterbuffer

# Look at the WebRTC source code
echo -e '\n=== Checking WebRTC source location ==='
dpkg -L gstreamer1.0-plugins-bad | grep webrtc

# Copy test script and run
cp /host/test_framebuffer.sh /tmp/
python3 /tmp/test_framebuffer.py
"
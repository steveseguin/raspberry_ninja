#!/usr/bin/env python3
"""
Test script to reproduce the GStreamer 1.18 jitterbuffer issue
"""
import subprocess
import sys

# First, let's check GStreamer 1.18 source code for the error
print("=== Checking GStreamer 1.18 WebRTC source ===")

# The error occurs at gstwebrtcbin.c:5657 in on_rtpbin_new_jitterbuffer
# Let's examine what's happening there

cmd = """docker run --rm debian11-gst118 bash -c '
# Find the WebRTC source file
apt-get update -qq && apt-get install -y -qq gstreamer1.0-plugins-bad-dbg 2>/dev/null

# Check if we can find debug symbols or source
echo "=== Looking for WebRTC source/debug info ==="
dpkg -L gstreamer1.0-plugins-bad | grep webrtc

# Check the exact GStreamer bad plugins version
echo -e "\n=== GStreamer bad plugins version ==="
dpkg -l | grep gstreamer1.0-plugins-bad

# Let\'s create a minimal test case
echo -e "\n=== Creating minimal test case ==="
cat > /tmp/test_webrtc.py << EOF
import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

Gst.init(None)

# Create a simple WebRTC pipeline with framebuffer output
pipeline_str = "videotestsrc ! video/x-raw,width=640,height=480,framerate=30/1 ! videoconvert ! x264enc tune=zerolatency ! rtph264pay ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! webrtcbin name=sendrecv"

try:
    pipeline = Gst.parse_launch(pipeline_str)
    print("Pipeline created successfully")
    
    # Get webrtcbin element
    webrtc = pipeline.get_by_name("sendrecv")
    print(f"WebRTC element: {webrtc}")
    
    # Set to playing state
    pipeline.set_state(Gst.State.PLAYING)
    print("Pipeline set to PLAYING")
    
    # This is where the jitterbuffer would be created
    # when a remote stream is added
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
EOF

python3 /tmp/test_webrtc.py
'
"""

subprocess.run(cmd, shell=True)

# Now let's check the actual error in the source
print("\n=== Analyzing the jitterbuffer error ===")

cmd2 = """docker run --rm debian11-gst118 bash -c '
# The error "code should not be reached" typically means there\'s an unhandled case
# in a switch statement or similar construct

# Let\'s check what changed between 1.18 and 1.20
echo "=== GStreamer 1.18.4 WebRTC limitations ==="
echo "The error at gstwebrtcbin.c:5657 suggests an unhandled case in on_rtpbin_new_jitterbuffer"
echo "This is likely related to:"
echo "1. Missing handling for certain RTP payload types"
echo "2. Incomplete implementation of jitterbuffer setup for WebRTC"
echo "3. Missing support for certain codec configurations"

# Create a test that specifically triggers the framebuffer path
cat > /tmp/test_framebuffer.py << EOF
import os
import sys

# Simulate the publish.py framebuffer scenario
print("Testing framebuffer mode scenario...")

# The issue occurs when:
# 1. WebRTC negotiation completes
# 2. Remote stream starts flowing
# 3. rtpbin tries to create a jitterbuffer
# 4. The jitterbuffer creation hits an unhandled case

# This suggests the issue is with how GStreamer 1.18 handles
# the specific RTP configuration used by VDO.Ninja

print("\\nPossible causes:")
print("1. GStreamer 1.18 WebRTC implementation is incomplete")
print("2. Missing support for certain RTP extensions")
print("3. Incompatible jitterbuffer configuration")
print("4. Missing handling for data channels alongside media streams")
EOF

python3 /tmp/test_framebuffer.py
'
"""

subprocess.run(cmd2, shell=True)
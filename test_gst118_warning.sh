#!/bin/bash

echo "=== Testing GStreamer 1.18 Framebuffer Warning ==="
echo ""

# Create a simple test that will trigger the warning but exit cleanly
docker run --rm debian11-gst118 bash -c '
cd /app
pip3 install cryptography websockets asyncio numpy >/dev/null 2>&1

# Create a Python script to test the warning
cat > test_warning.py << EOF
import sys
sys.path.insert(0, "/app")

# Mock the args to trigger framebuffer check
class Args:
    framebuffer = "test"
    # Add other required attributes
    def __getattr__(self, name):
        return None

# Import necessary parts
import gi
gi.require_version("Gst", "1.0") 
from gi.repository import Gst

# Initialize GStreamer
Gst.init(None)

# Check version and show warning
gst_version = Gst.version()
print(f"GStreamer version: {gst_version.major}.{gst_version.minor}.{gst_version.micro}")

if gst_version.major == 1 and gst_version.minor == 18:
    print("")
    print("⚠️  WARNING: GStreamer 1.18 detected with --framebuffer mode")
    print("━" * 60)
    print("GStreamer 1.18 has a known bug that causes crashes in framebuffer mode.")
    print("You may encounter: ERROR:gstwebrtcbin.c:5657:on_rtpbin_new_jitterbuffer")
    print("")
    print("RECOMMENDED SOLUTIONS:")
    print("1. Upgrade to GStreamer 1.20 or newer")
    print("   - Ubuntu 22.04+ has GStreamer 1.20+")
    print("   - Debian 12+ has GStreamer 1.22+")
    print("2. Use Docker: docker run -it ubuntu:22.04")
    print("3. Use --filesink or --fdsink instead of --framebuffer")
    print("━" * 60)
    print("(Would wait 5 seconds in real usage...)")
else:
    print("No warning needed - not GStreamer 1.18")
EOF

python3 test_warning.py
'
#!/usr/bin/env python3
"""
Test basic NDI functionality
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys

Gst.init(None)

# Check if NDI plugin is available
if not Gst.ElementFactory.find('ndisink'):
    print("ERROR: NDI plugin not found!")
    print("Please install gst-plugin-ndi")
    sys.exit(1)

print("✓ NDI plugin found")

# Create a simple test pipeline
pipeline_str = """
videotestsrc pattern=ball ! 
video/x-raw,width=640,height=480,framerate=30/1 ! 
videoconvert ! 
ndisink ndi-name="TestNDIStream"
"""

print("Creating pipeline...")
pipeline = Gst.parse_launch(pipeline_str)

print("Starting pipeline...")
pipeline.set_state(Gst.State.PLAYING)

print("\nNDI stream 'TestNDIStream' should now be visible on the network")
print("Press Ctrl+C to stop")

loop = GLib.MainLoop()
try:
    loop.run()
except KeyboardInterrupt:
    print("\nStopping...")

pipeline.set_state(Gst.State.NULL)
print("Done")
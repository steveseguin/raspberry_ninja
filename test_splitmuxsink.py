#!/usr/bin/env python3
"""Test splitmuxsink directly"""
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import time

Gst.init(None)

# Create a simple test pipeline
pipeline = Gst.Pipeline.new("test-pipeline")

# Create test source
videotestsrc = Gst.ElementFactory.make("videotestsrc", None)
videotestsrc.set_property("is-live", True)

# Create x264 encoder
x264enc = Gst.ElementFactory.make("x264enc", None)
x264enc.set_property("tune", "zerolatency")
x264enc.set_property("key-int-max", 30)  # keyframe every second at 30fps

# Create h264parse
h264parse = Gst.ElementFactory.make("h264parse", None)
h264parse.set_property("config-interval", -1)

# Create splitmuxsink
splitmuxsink = Gst.ElementFactory.make("splitmuxsink", None)
splitmuxsink.set_property("location", "test_segment_%05d.ts")
splitmuxsink.set_property("max-size-time", 2 * Gst.SECOND)
splitmuxsink.set_property("muxer-factory", "mpegtsmux")
splitmuxsink.set_property("send-keyframe-requests", True)

# Add to pipeline
pipeline.add(videotestsrc)
pipeline.add(x264enc)
pipeline.add(h264parse)
pipeline.add(splitmuxsink)

# Link elements
if not videotestsrc.link(x264enc):
    print("Failed to link videotestsrc to x264enc")
    exit(1)
if not x264enc.link(h264parse):
    print("Failed to link x264enc to h264parse")
    exit(1)
if not h264parse.link(splitmuxsink):
    print("Failed to link h264parse to splitmuxsink")
    exit(1)

# Monitor splitmuxsink signals
def on_format_location(splitmux, fragment_id):
    filename = f"test_segment_{fragment_id:05d}.ts"
    print(f"Format location: {filename}")
    return filename

splitmuxsink.connect("format-location", on_format_location)

# Start pipeline
print("Starting pipeline...")
pipeline.set_state(Gst.State.PLAYING)

# Check state
ret, state, pending = pipeline.get_state(5 * Gst.SECOND)
print(f"Pipeline state: {state.value_name}")

ret, state, pending = splitmuxsink.get_state(1 * Gst.SECOND)
print(f"Splitmuxsink state: {state.value_name}")

# Run for 10 seconds
print("Recording for 10 seconds...")
time.sleep(10)

# Stop
print("Stopping...")
pipeline.set_state(Gst.State.NULL)

# Check what was created
import glob
files = glob.glob("test_segment_*.ts")
print(f"\nCreated {len(files)} segments:")
for f in sorted(files):
    import os
    size = os.path.getsize(f)
    print(f"  {f}: {size:,} bytes")
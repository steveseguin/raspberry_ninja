#!/usr/bin/env python3
"""
Test VP8 pipeline to verify it's producing output
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys

Gst.init(None)

def on_message(bus, message):
    t = message.type
    if t == Gst.MessageType.EOS:
        print("End of stream")
        loop.quit()
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"Error: {err}, {debug}")
        loop.quit()
    elif t == Gst.MessageType.STATE_CHANGED:
        if message.src.get_name() == "pipeline":
            old_state, new_state, pending_state = message.parse_state_changed()
            print(f"Pipeline state changed from {old_state.value_nick} to {new_state.value_nick}")

def pad_probe_callback(pad, info):
    """Count buffers passing through"""
    global buffer_count
    buffer_count += 1
    if buffer_count % 30 == 0:  # Every second at 30fps
        print(f"Buffers passed: {buffer_count}")
    return Gst.PadProbeReturn.OK

# Create pipeline
pipeline_str = (
    "videotestsrc ! "
    "video/x-raw,width=640,height=480,framerate=30/1 ! "
    "videoconvert ! "
    "vp8enc deadline=1 target-bitrate=1000000 name=encoder ! "
    "fakesink name=sink"
)

print(f"Testing pipeline: {pipeline_str}")

pipeline = Gst.parse_launch(pipeline_str)
bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_message)

# Get the encoder and check properties
encoder = pipeline.get_by_name("encoder")
if encoder:
    print(f"Encoder found: {encoder.get_name()}")
    try:
        target_br = encoder.get_property("target-bitrate")
        print(f"Target bitrate: {target_br}")
    except Exception as e:
        print(f"Could not get target-bitrate: {e}")

# Add probe to count buffers
sink = pipeline.get_by_name("sink")
if sink:
    sinkpad = sink.get_static_pad("sink")
    buffer_count = 0
    sinkpad.add_probe(Gst.PadProbeType.BUFFER, pad_probe_callback)

# Start pipeline
print("Starting pipeline...")
ret = pipeline.set_state(Gst.State.PLAYING)
if ret == Gst.StateChangeReturn.FAILURE:
    print("Failed to start pipeline")
    sys.exit(1)

# Run for 5 seconds
loop = GLib.MainLoop()
GLib.timeout_add_seconds(5, lambda: loop.quit())

try:
    loop.run()
except KeyboardInterrupt:
    pass

print(f"\nTotal buffers processed: {buffer_count}")
print(f"Expected ~150 buffers for 5 seconds at 30fps")

# Cleanup
pipeline.set_state(Gst.State.NULL)
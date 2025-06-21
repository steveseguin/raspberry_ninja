#!/usr/bin/env python3
"""Test NDI with direct sink (no combiner)"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys

Gst.init(None)

# Create a simple test pipeline with direct NDI output (no combiner)
pipeline_str = """
    videotestsrc pattern=ball ! 
    video/x-raw,width=640,height=480,framerate=30/1 ! 
    queue name=q1 max-size-buffers=0 max-size-time=0 max-size-bytes=0 ! 
    ndisink name=sink ndi-name="TestNDIDirect" sync=false async=false
"""

print("Creating pipeline with DIRECT NDI sink (no combiner)...")
pipeline = Gst.parse_launch(pipeline_str)

# Get elements
q1 = pipeline.get_by_name('q1')
sink = pipeline.get_by_name('sink')

# Monitor video queue
video_count = 0
last_count = 0
stuck_checks = 0

def video_probe(pad, info):
    global video_count
    video_count += 1
    if video_count % 100 == 0:
        level = q1.get_property('current-level-buffers')
        print(f"Video: {video_count} buffers, Queue: {level}")
    return Gst.PadProbeReturn.OK

# Check if stuck
def check_stuck():
    global last_count, stuck_checks
    if video_count == last_count:
        stuck_checks += 1
        print(f"WARNING: No new buffers in 5s (check #{stuck_checks})")
        if stuck_checks >= 3:
            print("Pipeline appears stuck. Exiting.")
            loop.quit()
            return False
    else:
        stuck_checks = 0
    last_count = video_count
    return True

# Add probes
src_pad = q1.get_static_pad('src')
src_pad.add_probe(Gst.PadProbeType.BUFFER, video_probe)

# Bus handler
def on_bus_message(bus, message):
    t = message.type
    if t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"ERROR: {err}, {debug}")
        loop.quit()
    return True

bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_bus_message)

# Start
print("Starting pipeline...")
ret = pipeline.set_state(Gst.State.PLAYING)
print(f"Set state returned: {ret}")

# Check state
ret, state, pending = pipeline.get_state(5 * Gst.SECOND)
print(f"Pipeline state: {state}")

# Add stuck checker
GLib.timeout_add_seconds(5, check_stuck)

# Main loop
loop = GLib.MainLoop()
try:
    loop.run()
except KeyboardInterrupt:
    print(f"\nStopping... Total buffers: {video_count}")
finally:
    pipeline.set_state(Gst.State.NULL)
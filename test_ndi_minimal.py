#!/usr/bin/env python3
"""Minimal test to debug NDI freezing issue"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import sys

Gst.init(None)

# Create a simple test pipeline with NDI output
pipeline_str = """
    videotestsrc pattern=ball ! 
    video/x-raw,width=640,height=480,framerate=30/1 ! 
    queue name=q1 ! 
    ndisinkcombiner name=combiner latency=800000000 min-upstream-latency=1000000000 start-time-selection=1 ! 
    ndisink name=sink ndi-name="TestNDI" sync=true async=false enable-last-sample=false
    
    audiotestsrc wave=sine freq=440 ! 
    audio/x-raw,rate=48000,channels=2 ! 
    queue name=q2 ! 
    combiner.
"""

print("Creating pipeline...")
pipeline = Gst.parse_launch(pipeline_str)

# Get elements
q1 = pipeline.get_by_name('q1')
q2 = pipeline.get_by_name('q2')
sink = pipeline.get_by_name('sink')

# Monitor video queue
video_count = 0
def video_probe(pad, info):
    global video_count
    video_count += 1
    if video_count % 100 == 0:
        level = q1.get_property('current-level-buffers')
        print(f"Video: {video_count} buffers, Queue: {level}")
    return Gst.PadProbeReturn.OK

# Monitor audio queue  
audio_count = 0
def audio_probe(pad, info):
    global audio_count
    audio_count += 1
    if audio_count % 100 == 0:
        level = q2.get_property('current-level-buffers')
        print(f"Audio: {audio_count} buffers, Queue: {level}")
    return Gst.PadProbeReturn.OK

# Add probes
src_pad = q1.get_static_pad('src')
src_pad.add_probe(Gst.PadProbeType.BUFFER, video_probe)

src_pad2 = q2.get_static_pad('src')
src_pad2.add_probe(Gst.PadProbeType.BUFFER, audio_probe)

# Bus handler
def on_bus_message(bus, message):
    t = message.type
    if t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"ERROR: {err}, {debug}")
        loop.quit()
    elif t == Gst.MessageType.EOS:
        print("EOS")
        loop.quit()
    elif t == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        print(f"WARNING: {err}, {debug}")
    return True

bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_bus_message)

# Start
print("Starting pipeline...")
ret = pipeline.set_state(Gst.State.PLAYING)
print(f"Set state returned: {ret}")

# Check state
ret, state, pending = pipeline.get_state(Gst.CLOCK_TIME_NONE)
print(f"Pipeline state: {state}")

# Main loop
loop = GLib.MainLoop()
try:
    loop.run()
except KeyboardInterrupt:
    print("\nStopping...")
    pipeline.set_state(Gst.State.NULL)
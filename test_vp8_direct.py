#!/usr/bin/env python3
"""
Test VP8 encoding directly with WebRTC
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC, GLib
import time

Gst.init(None)

# Create a simple pipeline with VP8 encoding
pipeline_str = """
videotestsrc pattern=ball ! 
video/x-raw,width=640,height=480,framerate=30/1 ! 
clockoverlay ! 
tee name=t ! 
queue ! videoconvert ! autovideosink sync=false 
t. ! queue ! 
vp8enc deadline=1 target-bitrate=1000000 cpu-used=4 end-usage=cbr ! 
rtpvp8pay ! 
application/x-rtp,media=video,encoding-name=VP8,payload=96 ! 
webrtcbin name=sendrecv bundle-policy=max-bundle
"""

print("Creating pipeline...")
pipeline = Gst.parse_launch(pipeline_str)
webrtc = pipeline.get_by_name('sendrecv')

# Monitor encoder properties
vp8enc = pipeline.get_by_name('vp8enc')
if not vp8enc:
    # Try to find it
    it = pipeline.iterate_elements()
    while True:
        ret, elem = it.next()
        if ret == Gst.IteratorResult.DONE:
            break
        if ret == Gst.IteratorResult.OK and elem and elem.get_factory().get_name() == 'vp8enc':
            vp8enc = elem
            break

if vp8enc:
    print(f"VP8 encoder found: {vp8enc.get_name()}")
    print(f"  deadline: {vp8enc.get_property('deadline')}")
    print(f"  target-bitrate: {vp8enc.get_property('target-bitrate')}")
    print(f"  cpu-used: {vp8enc.get_property('cpu-used')}")
    print(f"  end-usage: {vp8enc.get_property('end-usage')}")
else:
    print("WARNING: VP8 encoder not found!")

# Monitor pipeline messages
def on_message(bus, message):
    t = message.type
    if t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"Error: {err}, {debug}")
        loop.quit()
    elif t == Gst.MessageType.WARNING:
        err, debug = message.parse_warning()
        print(f"Warning: {err}, {debug}")
    elif t == Gst.MessageType.QOS:
        # Quality of Service message - indicates performance issues
        live, running_time, stream_time, timestamp, duration = message.parse_qos()
        print(f"QOS: live={live}, running_time={running_time}, stream_time={stream_time}")
    elif t == Gst.MessageType.STATE_CHANGED:
        if message.src == pipeline:
            old_state, new_state, pending = message.parse_state_changed()
            print(f"Pipeline state: {old_state.value_nick} -> {new_state.value_nick}")

bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_message)

# Monitor frame dropping
dropped_frames = 0
def check_qos():
    global dropped_frames
    # Check encoder QoS
    if vp8enc:
        # Get QoS stats from element
        stats = vp8enc.get_property('qos')
        if stats:
            print(f"VP8 encoder QoS: {stats}")
    
    # Check sink for dropped frames
    sink = pipeline.get_by_name('autovideosink0-actual-sink-xvimage')
    if not sink:
        it = pipeline.iterate_sinks()
        while True:
            ret, elem = it.next()
            if ret == Gst.IteratorResult.DONE:
                break
            if ret == Gst.IteratorResult.OK and elem:
                sink = elem
                break
    
    if sink:
        try:
            # Get render stats
            stats = sink.get_property('stats')
            if stats and 'dropped' in stats:
                new_dropped = stats['dropped']
                if new_dropped > dropped_frames:
                    print(f"Frames dropped: {new_dropped - dropped_frames}")
                    dropped_frames = new_dropped
        except:
            pass
    
    return True

# Start monitoring after pipeline starts
GLib.timeout_add_seconds(2, check_qos)

print("Starting pipeline...")
ret = pipeline.set_state(Gst.State.PLAYING)
if ret == Gst.StateChangeReturn.FAILURE:
    print("Failed to start pipeline")
    exit(1)

print("\nPipeline running. Look for:")
print("- QOS messages indicating performance issues")
print("- Frame drops")
print("- State changes")
print("\nPress Ctrl+C to stop")

loop = GLib.MainLoop()
try:
    loop.run()
except KeyboardInterrupt:
    print("\nStopping...")

pipeline.set_state(Gst.State.NULL)
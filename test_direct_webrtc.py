#!/usr/bin/env python3
"""
Direct WebRTC test to isolate the issue
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC, GLib
import json

Gst.init(None)

# Simple pipeline with visible feedback
pipeline_str = """
videotestsrc pattern=smpte ! 
video/x-raw,width=640,height=480,framerate=30/1 ! 
videoconvert ! 
clockoverlay ! 
tee name=t ! 
queue ! videoconvert ! autovideosink sync=false 
t. ! queue ! 
vp8enc deadline=1 target-bitrate=1000000 keyframe-max-dist=30 ! 
rtpvp8pay ! 
application/x-rtp,media=video,encoding-name=VP8,payload=96 ! 
webrtcbin name=sendrecv bundle-policy=max-bundle
"""

print("Creating pipeline with local preview...")
print(pipeline_str)

pipeline = Gst.parse_launch(pipeline_str)
webrtc = pipeline.get_by_name('sendrecv')

# Set STUN server
webrtc.set_property('stun-server', 'stun://stun.l.google.com:19302')

# Track stats
def on_stats(promise, webrtc, unused):
    promise.wait()
    stats = promise.get_reply()
    if stats:
        stats_str = stats.to_string()
        print(f"\n=== WebRTC Stats ===")
        # Extract key metrics
        if "packets-sent" in stats_str:
            try:
                packets = stats_str.split("packets-sent=(guint64)")[1].split(",")[0]
                print(f"Packets sent: {packets}")
            except:
                pass
        if "bytes-sent" in stats_str:
            try:
                bytes_sent = stats_str.split("bytes-sent=(guint64)")[1].split(",")[0]
                print(f"Bytes sent: {bytes_sent}")
            except:
                pass
        print("===================\n")

def check_stats():
    promise = Gst.Promise.new_with_change_func(on_stats, webrtc, None)
    webrtc.emit('get-stats', None, promise)
    return True

# Monitor pipeline state
def on_message(bus, message):
    t = message.type
    if t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"Error: {err}, {debug}")
        loop.quit()
    elif t == Gst.MessageType.STATE_CHANGED:
        if message.src == pipeline:
            old_state, new_state, pending = message.parse_state_changed()
            print(f"Pipeline state: {old_state.value_nick} -> {new_state.value_nick}")
    elif t == Gst.MessageType.EOS:
        print("End of stream")
        loop.quit()

bus = pipeline.get_bus()
bus.add_signal_watch()
bus.connect("message", on_message)

# Monitor pad activity
def on_pad_added(element, pad):
    print(f"Pad added: {pad.get_name()}")

webrtc.connect('pad-added', on_pad_added)

# ICE state monitoring
def on_ice_connection_state(element, pspec):
    state = webrtc.get_property('ice-connection-state')
    print(f"ICE connection state: {state}")

def on_connection_state(element, pspec):
    state = webrtc.get_property('connection-state')
    print(f"WebRTC connection state: {state}")

webrtc.connect('notify::ice-connection-state', on_ice_connection_state)
webrtc.connect('notify::connection-state', on_connection_state)

print("Starting pipeline...")
ret = pipeline.set_state(Gst.State.PLAYING)
if ret == Gst.StateChangeReturn.FAILURE:
    print("Failed to start pipeline")
    exit(1)

# Schedule stats checking
GLib.timeout_add_seconds(3, check_stats)

print("\nPipeline is running. You should see:")
print("1. A test pattern in a local window")
print("2. WebRTC stats every 3 seconds")
print("3. State changes as they occur")
print("\nPress Ctrl+C to stop")

loop = GLib.MainLoop()
try:
    loop.run()
except KeyboardInterrupt:
    print("\nStopping...")

pipeline.set_state(Gst.State.NULL)
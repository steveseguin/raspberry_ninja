#!/usr/bin/env python3
"""Test HLS recording directly without WebRTC"""
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import time

Gst.init(None)

# Create pipeline
pipeline = Gst.Pipeline.new("hls-test")

# Video source and encoding
videotestsrc = Gst.ElementFactory.make("videotestsrc", None)
videotestsrc.set_property("is-live", True)
videotestsrc.set_property("pattern", 0)  # SMPTE pattern

x264enc = Gst.ElementFactory.make("x264enc", None)
x264enc.set_property("tune", "zerolatency")
x264enc.set_property("key-int-max", 30)  # keyframe every second

h264parse = Gst.ElementFactory.make("h264parse", None)
h264parse.set_property("config-interval", -1)

# Audio source and encoding
audiotestsrc = Gst.ElementFactory.make("audiotestsrc", None)
audiotestsrc.set_property("is-live", True)
audiotestsrc.set_property("wave", 0)  # Sine wave

audioconvert = Gst.ElementFactory.make("audioconvert", None)
audioresample = Gst.ElementFactory.make("audioresample", None)
aacenc = Gst.ElementFactory.make("avenc_aac", None)
aacparse = Gst.ElementFactory.make("aacparse", None)

# Splitmuxsink
splitmuxsink = Gst.ElementFactory.make("splitmuxsink", None)
splitmuxsink.set_property("location", "direct_test_%05d.ts")
splitmuxsink.set_property("max-size-time", 3 * Gst.SECOND)
splitmuxsink.set_property("muxer-factory", "mpegtsmux")

# Add elements
for elem in [videotestsrc, x264enc, h264parse, audiotestsrc, audioconvert, audioresample, aacenc, aacparse, splitmuxsink]:
    pipeline.add(elem)

# Link video chain
if not videotestsrc.link(x264enc):
    print("Failed to link videotestsrc to x264enc")
if not x264enc.link(h264parse):
    print("Failed to link x264enc to h264parse")
if not h264parse.link(splitmuxsink):
    print("Failed to link h264parse to splitmuxsink")
else:
    print("✓ Video chain linked to splitmuxsink")

# Link audio chain
if not audiotestsrc.link(audioconvert):
    print("Failed to link audiotestsrc to audioconvert")
if not audioconvert.link(audioresample):
    print("Failed to link audioconvert to audioresample")
if not audioresample.link(aacenc):
    print("Failed to link audioresample to aacenc")
if not aacenc.link(aacparse):
    print("Failed to link aacenc to aacparse")
if not aacparse.link(splitmuxsink):
    print("Failed to link aacparse to splitmuxsink")
else:
    print("✓ Audio chain linked to splitmuxsink")

# Monitor new segments
def on_format_location(sink, fragment_id):
    filename = f"direct_test_{fragment_id:05d}.ts"
    print(f"New segment: {filename}")
    return filename

splitmuxsink.connect("format-location", on_format_location)

# Start pipeline
print("\nStarting pipeline...")
ret = pipeline.set_state(Gst.State.PLAYING)
print(f"Pipeline set_state result: {ret.value_name}")

# Check states
ret, state, pending = pipeline.get_state(2 * Gst.SECOND)
print(f"Pipeline state: {state.value_name}")

ret, state, pending = splitmuxsink.get_state(1 * Gst.SECOND)
print(f"Splitmuxsink state: {state.value_name}")

# Run for 10 seconds
print("\nRecording for 10 seconds...")
time.sleep(10)

# Stop
print("Stopping...")
pipeline.set_state(Gst.State.NULL)

# Check results
import glob
files = glob.glob("direct_test_*.ts")
print(f"\n✓ Created {len(files)} segments")
if files:
    # Check first segment
    import subprocess
    result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_streams', files[0]], 
                          capture_output=True, text=True)
    if 'codec_type=video' in result.stdout and 'codec_type=audio' in result.stdout:
        print("✓ First segment contains both audio and video")
    else:
        print("✗ First segment missing audio or video")
#!/usr/bin/env python3
"""Test proper pad linking to splitmuxsink"""
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

x264enc = Gst.ElementFactory.make("x264enc", None)
x264enc.set_property("tune", "zerolatency")
x264enc.set_property("key-int-max", 30)

h264parse = Gst.ElementFactory.make("h264parse", None)
h264parse.set_property("config-interval", -1)

# Audio source and encoding
audiotestsrc = Gst.ElementFactory.make("audiotestsrc", None)
audiotestsrc.set_property("is-live", True)

audioconvert = Gst.ElementFactory.make("audioconvert", None)
audioresample = Gst.ElementFactory.make("audioresample", None)
aacenc = Gst.ElementFactory.make("avenc_aac", None)
aacparse = Gst.ElementFactory.make("aacparse", None)

# Splitmuxsink
splitmuxsink = Gst.ElementFactory.make("splitmuxsink", None)
splitmuxsink.set_property("location", "pad_test_%05d.ts")
splitmuxsink.set_property("max-size-time", 3 * Gst.SECOND)
splitmuxsink.set_property("muxer-factory", "mpegtsmux")

# Add elements
for elem in [videotestsrc, x264enc, h264parse, audiotestsrc, audioconvert, audioresample, aacenc, aacparse, splitmuxsink]:
    pipeline.add(elem)

# Link video chain up to h264parse
videotestsrc.link(x264enc)
x264enc.link(h264parse)

# Link audio chain up to aacparse
audiotestsrc.link(audioconvert)
audioconvert.link(audioresample)
audioresample.link(aacenc)
aacenc.link(aacparse)

# Now use proper pad linking for splitmuxsink
# Video - use 'video' pad name
video_src_pad = h264parse.get_static_pad('src')
video_sink_pad = splitmuxsink.request_pad_simple('video')
if video_sink_pad:
    ret = video_src_pad.link(video_sink_pad)
    print(f"Video pad link result: {ret} ({ret == Gst.PadLinkReturn.OK})")
else:
    print("Failed to get video sink pad")

# Audio - use 'audio_%u' pad name
audio_src_pad = aacparse.get_static_pad('src')
audio_sink_pad = splitmuxsink.request_pad_simple('audio_%u')
if audio_sink_pad:
    ret = audio_src_pad.link(audio_sink_pad)
    print(f"Audio pad link result: {ret} ({ret == Gst.PadLinkReturn.OK})")
else:
    print("Failed to get audio sink pad")

# Monitor segments
def on_format_location(sink, fragment_id):
    filename = f"pad_test_{fragment_id:05d}.ts"
    print(f"New segment: {filename}")
    return filename

splitmuxsink.connect("format-location", on_format_location)

# Start pipeline
print("\nStarting pipeline...")
pipeline.set_state(Gst.State.PLAYING)

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
import subprocess
files = glob.glob("pad_test_*.ts")
print(f"\n✓ Created {len(files)} segments")
if files:
    # Check first segment
    result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_streams', files[0]], 
                          capture_output=True, text=True)
    video_count = result.stdout.count('codec_type=video')
    audio_count = result.stdout.count('codec_type=audio')
    print(f"✓ First segment: {video_count} video stream(s), {audio_count} audio stream(s)")
    if video_count > 0 and audio_count > 0:
        print("✓ SUCCESS: Both audio and video are muxed!")
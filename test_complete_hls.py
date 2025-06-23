#!/usr/bin/env python3
"""Complete HLS test simulating WebRTC input"""
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import time
import os
import datetime

Gst.init(None)

class HLSRecorder:
    def __init__(self):
        self.pipe = Gst.Pipeline.new("hls-recorder")
        self.use_splitmuxsink = True
        self.use_internal_mux = True
        self.setup_pipeline()
        
    def log(self, msg):
        print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")
        
    def setup_pipeline(self):
        # Simulate WebRTC video input
        videotestsrc = Gst.ElementFactory.make("videotestsrc", None)
        videotestsrc.set_property("is-live", True)
        videotestsrc.set_property("pattern", 18)  # Ball pattern
        
        # Video processing (simulating H264 from WebRTC)
        videoconvert = Gst.ElementFactory.make("videoconvert", None)
        x264enc = Gst.ElementFactory.make("x264enc", None)
        x264enc.set_property("tune", "zerolatency")
        x264enc.set_property("key-int-max", 60)  # 2 sec keyframes
        
        rtph264pay = Gst.ElementFactory.make("rtph264pay", None)
        rtph264depay = Gst.ElementFactory.make("rtph264depay", None)
        h264parse = Gst.ElementFactory.make("h264parse", None)
        h264parse.set_property("config-interval", -1)
        
        # Video queue
        video_queue = Gst.ElementFactory.make("queue", "video_queue")
        video_queue.set_property("max-size-time", 500000000)
        
        # Simulate WebRTC audio input
        audiotestsrc = Gst.ElementFactory.make("audiotestsrc", None)
        audiotestsrc.set_property("is-live", True)
        
        # Audio processing (simulating Opus from WebRTC)
        audioconvert = Gst.ElementFactory.make("audioconvert", None)
        audioresample = Gst.ElementFactory.make("audioresample", None)
        opusenc = Gst.ElementFactory.make("opusenc", None)
        rtpopuspay = Gst.ElementFactory.make("rtpopuspay", None)
        rtpopusdepay = Gst.ElementFactory.make("rtpopusdepay", None)
        opusdec = Gst.ElementFactory.make("opusdec", None)
        
        # Transcode to AAC for HLS
        audioconvert2 = Gst.ElementFactory.make("audioconvert", None)
        audioresample2 = Gst.ElementFactory.make("audioresample", None)
        aacenc = Gst.ElementFactory.make("avenc_aac", None)
        aacparse = Gst.ElementFactory.make("aacparse", None)
        
        # Audio queue
        audio_queue = Gst.ElementFactory.make("queue", "audio_queue")
        audio_queue.set_property("max-size-time", 500000000)
        
        # Setup HLS recording
        timestamp = int(time.time())
        base_filename = f"complete_test_{timestamp}"
        
        # Create splitmuxsink
        self.hlssink = Gst.ElementFactory.make("splitmuxsink", None)
        self.hlssink.set_property("location", f"{base_filename}_%05d.ts")
        self.hlssink.set_property("max-size-time", 5 * Gst.SECOND)
        self.hlssink.set_property("send-keyframe-requests", True)
        self.hlssink.set_property("muxer-factory", "mpegtsmux")
        
        # Create M3U8 playlist
        self.playlist_filename = f"{base_filename}.m3u8"
        with open(self.playlist_filename, 'w') as f:
            f.write("#EXTM3U\\n#EXT-X-VERSION:3\\n#EXT-X-TARGETDURATION:5\\n#EXT-X-MEDIA-SEQUENCE:0\\n\\n")
        
        # Monitor segments
        def on_format_location(sink, fragment_id):
            filename = f"{base_filename}_{fragment_id:05d}.ts"
            self.log(f"📁 New HLS segment: {filename}")
            # Update playlist
            with open(self.playlist_filename, 'a') as f:
                f.write(f"#EXTINF:5.0,\\n{filename}\\n")
            return filename
            
        self.hlssink.connect("format-location", on_format_location)
        
        # Add all elements
        elements = [
            videotestsrc, videoconvert, x264enc, rtph264pay, rtph264depay, h264parse, video_queue,
            audiotestsrc, audioconvert, audioresample, opusenc, rtpopuspay, rtpopusdepay, opusdec,
            audioconvert2, audioresample2, aacenc, aacparse, audio_queue,
            self.hlssink
        ]
        for elem in elements:
            self.pipe.add(elem)
            
        # Link video chain
        videotestsrc.link(videoconvert)
        videoconvert.link(x264enc)
        x264enc.link(rtph264pay)
        rtph264pay.link(rtph264depay)  # Simulate RTP transport
        rtph264depay.link(h264parse)
        h264parse.link(video_queue)
        
        # Link audio chain
        audiotestsrc.link(audioconvert)
        audioconvert.link(audioresample)
        audioresample.link(opusenc)
        opusenc.link(rtpopuspay)
        rtpopuspay.link(rtpopusdepay)  # Simulate RTP transport
        rtpopusdepay.link(opusdec)
        opusdec.link(audioconvert2)
        audioconvert2.link(audioresample2)
        audioresample2.link(aacenc)
        aacenc.link(aacparse)
        aacparse.link(audio_queue)
        
        # Now link to splitmuxsink using proper pad requests
        # Video
        video_src_pad = video_queue.get_static_pad('src')
        video_sink_pad = self.hlssink.request_pad_simple('video')
        if video_sink_pad:
            ret = video_src_pad.link(video_sink_pad)
            if ret == Gst.PadLinkReturn.OK:
                self.log("✅ Video connected to splitmuxsink")
            else:
                self.log(f"Failed to link video: {ret}")
        else:
            self.log("Failed to get video pad from splitmuxsink")
            
        # Audio
        audio_src_pad = audio_queue.get_static_pad('src')
        audio_sink_pad = self.hlssink.request_pad_simple('audio_%u')
        if audio_sink_pad:
            ret = audio_src_pad.link(audio_sink_pad)
            if ret == Gst.PadLinkReturn.OK:
                self.log("✅ Audio connected to splitmuxsink")
            else:
                self.log(f"Failed to link audio: {ret}")
        else:
            self.log("Failed to get audio pad from splitmuxsink")
            
        # Sync splitmuxsink with pipeline
        self.hlssink.sync_state_with_parent()
        self.log("Splitmuxsink synced with parent pipeline")
        
    def start(self):
        self.log("🎬 Starting HLS recording...")
        ret = self.pipe.set_state(Gst.State.PLAYING)
        self.log(f"Pipeline set_state result: {ret.value_name}")
        
        # Check states
        ret, state, pending = self.pipe.get_state(2 * Gst.SECOND)
        self.log(f"Pipeline state: {state.value_name}")
        
        ret, state, pending = self.hlssink.get_state(1 * Gst.SECOND)
        self.log(f"Splitmuxsink state: {state.value_name}")
        
    def stop(self):
        self.log("Stopping pipeline...")
        self.pipe.set_state(Gst.State.NULL)
        
# Run test
recorder = HLSRecorder()
recorder.start()

print("\\nRecording for 20 seconds...")
time.sleep(20)

recorder.stop()

# Check results
import glob
files = glob.glob("complete_test_*.ts")
print(f"\\n✓ Created {len(files)} segments")
if files:
    import subprocess
    # Check multiple segments
    for f in sorted(files)[:3]:
        result = subprocess.run(['ffprobe', '-v', 'quiet', '-show_streams', f], 
                              capture_output=True, text=True)
        video_count = result.stdout.count('codec_type=video')
        audio_count = result.stdout.count('codec_type=audio')
        size = os.path.getsize(f)
        print(f"  {f}: {size:,} bytes - {video_count}V/{audio_count}A")
        
print(f"\\n✓ M3U8 playlist: {recorder.playlist_filename}")
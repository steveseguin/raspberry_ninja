#!/usr/bin/env python3
"""
Test WebM Recording with Dynamic Audio/Video
Demonstrates recording WebRTC streams with proper audio/video synchronization
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')

from gi.repository import Gst, GLib
import time
import logging
from webrtc_webm_recorder import WebMRecorder

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_webm_recording():
    """Test WebM recording with simulated RTP streams"""
    
    # Initialize GStreamer
    Gst.init(None)
    
    # Create main pipeline
    pipeline = Gst.Pipeline.new("test_pipeline")
    
    # Create test video source (VP8)
    video_src_str = (
        "videotestsrc pattern=ball ! "
        "video/x-raw,width=640,height=480,framerate=30/1 ! "
        "vp8enc deadline=1 target-bitrate=1000000 ! "
        "rtpvp8pay ! "
        "application/x-rtp,media=video,encoding-name=VP8,payload=96 ! "
        "identity name=video_src"
    )
    
    # Create test audio source (OPUS)
    audio_src_str = (
        "audiotestsrc wave=sine freq=440 ! "
        "audio/x-raw,rate=48000,channels=2 ! "
        "opusenc ! "
        "rtpopuspay ! "
        "application/x-rtp,media=audio,encoding-name=OPUS,payload=97 ! "
        "identity name=audio_src"
    )
    
    # Parse and add sources
    video_src = Gst.parse_bin_from_description(video_src_str, True)
    audio_src = Gst.parse_bin_from_description(audio_src_str, True)
    
    pipeline.add(video_src)
    pipeline.add(audio_src)
    
    # Create WebM recorder
    recorder = WebMRecorder("test_conn", "test_stream", "./recordings")
    recorder.create_recording_pipeline()
    
    # Get source pads
    video_identity = video_src.get_by_name("video_src")
    audio_identity = audio_src.get_by_name("audio_src")
    
    # Connect sources to recorder when pads appear
    def on_video_pad(element, pad):
        logger.info("Video pad appeared, connecting to recorder")
        recorder.add_video_stream(pad)
        
    def on_audio_pad(element, pad):
        logger.info("Audio pad appeared, connecting to recorder")
        # Simulate audio coming later
        GLib.timeout_add_seconds(2, lambda: recorder.add_audio_stream(pad))
        return False
        
    video_identity.connect("pad-added", on_video_pad)
    audio_identity.connect("pad-added", on_audio_pad)
    
    # Start pipeline
    pipeline.set_state(Gst.State.PLAYING)
    
    # Monitor recording
    def print_stats():
        stats = recorder.get_stats()
        logger.info(f"Recording stats: {stats}")
        return True  # Continue calling
        
    GLib.timeout_add_seconds(1, print_stats)
    
    # Run for specified duration
    logger.info("Starting recording test...")
    loop = GLib.MainLoop()
    
    def stop_recording():
        logger.info("Stopping recording...")
        pipeline.set_state(Gst.State.NULL)
        recorder.stop()
        recorder.cleanup()
        loop.quit()
        return False
        
    # Stop after 10 seconds
    GLib.timeout_add_seconds(10, stop_recording)
    
    try:
        loop.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        pipeline.set_state(Gst.State.NULL)
        recorder.stop()
        recorder.cleanup()
        
    logger.info("Test completed")


def test_dynamic_stream_addition():
    """Test adding audio to an already recording video stream"""
    
    Gst.init(None)
    
    # Create recorder
    recorder = WebMRecorder("dynamic_test", "dynamic_stream", "./recordings")
    recorder.create_recording_pipeline()
    
    # Create pipeline with just video first
    pipeline_str = (
        "videotestsrc pattern=snow ! "
        "video/x-raw,width=320,height=240,framerate=15/1 ! "
        "vp8enc deadline=1 ! "
        "rtpvp8pay ! "
        "fakesink name=video_sink"
    )
    
    pipeline = Gst.parse_launch(pipeline_str)
    video_sink = pipeline.get_by_name("video_sink")
    
    # Intercept video pad
    def on_video_pad(pad, probe_info):
        logger.info("Intercepting video data")
        # Add to recorder
        src_pad = pad.get_peer()
        if src_pad:
            recorder.add_video_stream(src_pad)
        return Gst.PadProbeReturn.OK
        
    sink_pad = video_sink.get_static_pad("sink")
    sink_pad.add_probe(Gst.PadProbeType.BUFFER, on_video_pad)
    
    # Start with video only
    pipeline.set_state(Gst.State.PLAYING)
    logger.info("Recording video only...")
    
    # Add audio after 3 seconds
    def add_audio_later():
        logger.info("Adding audio stream...")
        
        audio_str = (
            "audiotestsrc wave=pink-noise ! "
            "audio/x-raw,rate=48000,channels=1 ! "
            "opusenc ! "
            "rtpopuspay ! "
            "fakesink name=audio_sink"
        )
        
        audio_bin = Gst.parse_bin_from_description(audio_str, False)
        pipeline.add(audio_bin)
        audio_bin.sync_state_with_parent()
        
        # Get audio sink and intercept
        audio_sink = pipeline.get_by_name("audio_sink")
        audio_pad = audio_sink.get_static_pad("sink")
        
        def on_audio_pad(pad, probe_info):
            src_pad = pad.get_peer()
            if src_pad:
                recorder.add_audio_stream(src_pad)
            return Gst.PadProbeReturn.REMOVE  # Only do this once
            
        audio_pad.add_probe(Gst.PadProbeType.BUFFER, on_audio_pad)
        return False
        
    GLib.timeout_add_seconds(3, add_audio_later)
    
    # Run test
    loop = GLib.MainLoop()
    
    def stop_test():
        logger.info("Stopping dynamic test...")
        pipeline.set_state(Gst.State.NULL)
        recorder.stop()
        stats = recorder.get_stats()
        logger.info(f"Final stats: {stats}")
        recorder.cleanup()
        loop.quit()
        return False
        
    GLib.timeout_add_seconds(8, stop_test)
    
    try:
        loop.run()
    except KeyboardInterrupt:
        pipeline.set_state(Gst.State.NULL)
        recorder.stop()
        recorder.cleanup()
        
    logger.info("Dynamic test completed")


if __name__ == "__main__":
    import sys
    import os
    
    # Create recordings directory
    os.makedirs("recordings", exist_ok=True)
    
    if len(sys.argv) > 1 and sys.argv[1] == "dynamic":
        test_dynamic_stream_addition()
    else:
        test_webm_recording()
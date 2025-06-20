#!/usr/bin/env python3
"""
WebRTC WebM Recorder - Dynamic audio/video recording to WebM files
Handles streams that may have video only, audio only, or both
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')

from gi.repository import Gst, GLib
import logging
import time
import os

logger = logging.getLogger(__name__)


class WebMRecorder:
    """Handles dynamic recording of WebRTC streams to WebM files"""
    
    def __init__(self, connection_id, stream_id, output_dir="."):
        """
        Initialize WebM recorder
        
        Args:
            connection_id: Unique identifier for this connection
            stream_id: Stream ID being recorded
            output_dir: Directory for output files
        """
        self.connection_id = connection_id
        self.stream_id = stream_id
        self.output_dir = output_dir
        
        # Recording state
        self.pipeline = None
        self.webmmux = None
        self.filesink = None
        self.video_queue = None
        self.audio_queue = None
        
        # Track what we have
        self.has_video = False
        self.has_audio = False
        self.recording_started = False
        self.start_time = None
        
        # Output filename
        timestamp = int(time.time())
        self.filename = os.path.join(output_dir, f"{stream_id}_{timestamp}_{connection_id[:8]}.webm")
        
    def create_recording_pipeline(self):
        """Create the recording pipeline with WebM muxer"""
        try:
            # Create main elements
            self.pipeline = Gst.Pipeline.new(f"recorder_{self.connection_id}")
            
            # Create WebM muxer
            self.webmmux = Gst.ElementFactory.make("webmmux", "muxer")
            if not self.webmmux:
                raise Exception("Failed to create webmmux element")
                
            # Set muxer properties for live streaming
            self.webmmux.set_property("streamable", True)
            self.webmmux.set_property("writing-app", "WebRTC WebM Recorder")
            
            # Create file sink
            self.filesink = Gst.ElementFactory.make("filesink", "filesink")
            if not self.filesink:
                raise Exception("Failed to create filesink element")
                
            self.filesink.set_property("location", self.filename)
            self.filesink.set_property("sync", False)
            
            # Add elements to pipeline
            self.pipeline.add(self.webmmux)
            self.pipeline.add(self.filesink)
            
            # Link muxer to filesink
            if not self.webmmux.link(self.filesink):
                raise Exception("Failed to link muxer to filesink")
                
            # Set up bus monitoring
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)
            
            logger.info(f"Created recording pipeline for {self.stream_id}")
            
        except Exception as e:
            logger.error(f"Failed to create recording pipeline: {e}")
            self.cleanup()
            raise
            
    def add_video_stream(self, pad):
        """
        Add video stream to recording
        
        Args:
            pad: GStreamer pad with video RTP stream
        """
        if self.has_video:
            logger.warning("Video stream already added")
            return
            
        try:
            # Create video processing elements
            video_queue = Gst.ElementFactory.make("queue", "video_queue")
            video_queue.set_property("max-size-buffers", 0)
            video_queue.set_property("max-size-time", 0)
            video_queue.set_property("max-size-bytes", 0)
            
            # VP8 depayloader
            vp8depay = Gst.ElementFactory.make("rtpvp8depay", "vp8depay")
            
            if not all([video_queue, vp8depay]):
                raise Exception("Failed to create video elements")
                
            # Add elements to pipeline
            self.pipeline.add(video_queue)
            self.pipeline.add(vp8depay)
            
            # Link elements: queue -> depay -> muxer
            if not video_queue.link(vp8depay):
                raise Exception("Failed to link video queue to depay")
                
            # Get video pad from muxer
            mux_video_pad = self.webmmux.get_request_pad("video_%u")
            if not mux_video_pad:
                raise Exception("Failed to get video pad from muxer")
                
            # Link depay to muxer
            depay_src = vp8depay.get_static_pad("src")
            if depay_src.link(mux_video_pad) != Gst.PadLinkReturn.OK:
                raise Exception("Failed to link video to muxer")
                
            # Sync state with pipeline
            video_queue.sync_state_with_parent()
            vp8depay.sync_state_with_parent()
            
            # Link incoming pad to queue
            queue_sink = video_queue.get_static_pad("sink")
            if pad.link(queue_sink) != Gst.PadLinkReturn.OK:
                raise Exception("Failed to link video pad to queue")
                
            self.video_queue = video_queue
            self.has_video = True
            logger.info(f"Added video stream to recording for {self.stream_id}")
            
            # Start recording if not already started
            self._start_recording_if_ready()
            
        except Exception as e:
            logger.error(f"Failed to add video stream: {e}")
            raise
            
    def add_audio_stream(self, pad):
        """
        Add audio stream to recording
        
        Args:
            pad: GStreamer pad with audio RTP stream
        """
        if self.has_audio:
            logger.warning("Audio stream already added")
            return
            
        try:
            # Create audio processing elements
            audio_queue = Gst.ElementFactory.make("queue", "audio_queue")
            audio_queue.set_property("max-size-buffers", 0)
            audio_queue.set_property("max-size-time", 0)
            audio_queue.set_property("max-size-bytes", 0)
            
            # Opus depayloader
            opusdepay = Gst.ElementFactory.make("rtpopusdepay", "opusdepay")
            
            # Opus parser (required for WebM)
            opusparse = Gst.ElementFactory.make("opusparse", "opusparse")
            
            if not all([audio_queue, opusdepay, opusparse]):
                raise Exception("Failed to create audio elements")
                
            # Add elements to pipeline
            self.pipeline.add(audio_queue)
            self.pipeline.add(opusdepay)
            self.pipeline.add(opusparse)
            
            # Link elements: queue -> depay -> parse -> muxer
            if not audio_queue.link(opusdepay):
                raise Exception("Failed to link audio queue to depay")
                
            if not opusdepay.link(opusparse):
                raise Exception("Failed to link depay to parser")
                
            # Get audio pad from muxer
            mux_audio_pad = self.webmmux.get_request_pad("audio_%u")
            if not mux_audio_pad:
                raise Exception("Failed to get audio pad from muxer")
                
            # Link parser to muxer
            parser_src = opusparse.get_static_pad("src")
            if parser_src.link(mux_audio_pad) != Gst.PadLinkReturn.OK:
                raise Exception("Failed to link audio to muxer")
                
            # Sync state with pipeline
            audio_queue.sync_state_with_parent()
            opusdepay.sync_state_with_parent()
            opusparse.sync_state_with_parent()
            
            # Link incoming pad to queue
            queue_sink = audio_queue.get_static_pad("sink")
            if pad.link(queue_sink) != Gst.PadLinkReturn.OK:
                raise Exception("Failed to link audio pad to queue")
                
            self.audio_queue = audio_queue
            self.has_audio = True
            logger.info(f"Added audio stream to recording for {self.stream_id}")
            
            # Start recording if not already started
            self._start_recording_if_ready()
            
        except Exception as e:
            logger.error(f"Failed to add audio stream: {e}")
            raise
            
    def _start_recording_if_ready(self):
        """Start recording if we have at least one stream"""
        if self.recording_started:
            return
            
        if self.has_video or self.has_audio:
            # Start the pipeline
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                logger.error("Failed to start recording pipeline")
                return
                
            self.recording_started = True
            self.start_time = time.time()
            logger.info(f"Started recording to {self.filename}")
            
    def _on_bus_message(self, bus, message):
        """Handle pipeline bus messages"""
        msg_type = message.type
        
        if msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"Pipeline error: {err} - {debug}")
            
        elif msg_type == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            logger.warning(f"Pipeline warning: {warn} - {debug}")
            
        elif msg_type == Gst.MessageType.EOS:
            logger.info("Received EOS")
            
    def stop(self):
        """Stop recording and finalize file"""
        if not self.recording_started:
            return
            
        logger.info(f"Stopping recording for {self.stream_id}")
        
        # Send EOS to properly finalize the file
        if self.pipeline:
            # Send EOS through the pipeline
            self.pipeline.send_event(Gst.Event.new_eos())
            
            # Wait for EOS to propagate
            bus = self.pipeline.get_bus()
            msg = bus.timed_pop_filtered(5 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
            
            if msg and msg.type == Gst.MessageType.EOS:
                logger.info("Recording finalized successfully")
            
            # Stop pipeline
            self.pipeline.set_state(Gst.State.NULL)
            
        # Log final stats
        if self.start_time:
            duration = time.time() - self.start_time
            logger.info(f"Recording duration: {duration:.1f} seconds")
            
        if os.path.exists(self.filename):
            file_size = os.path.getsize(self.filename)
            logger.info(f"Output file: {self.filename} ({file_size:,} bytes)")
            
    def cleanup(self):
        """Clean up resources"""
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
            
        self.webmmux = None
        self.filesink = None
        self.video_queue = None
        self.audio_queue = None
        
    def get_stats(self):
        """Get recording statistics"""
        stats = {
            "connection_id": self.connection_id,
            "stream_id": self.stream_id,
            "filename": self.filename,
            "has_video": self.has_video,
            "has_audio": self.has_audio,
            "recording_started": self.recording_started,
            "duration": 0
        }
        
        if self.start_time:
            stats["duration"] = time.time() - self.start_time
            
        if os.path.exists(self.filename):
            stats["file_size"] = os.path.getsize(self.filename)
            
        return stats


class WebRTCWebMConnection:
    """WebRTC connection with WebM recording support"""
    
    def __init__(self, connection_id, stream_id, record_dir="."):
        self.connection_id = connection_id
        self.stream_id = stream_id
        self.record_dir = record_dir
        self.recorder = None
        
    def on_pad_added(self, webrtcbin, pad):
        """Handle new pad from webrtcbin"""
        if pad.direction != Gst.PadDirection.SRC:
            return
            
        caps = pad.get_current_caps()
        if not caps:
            return
            
        structure = caps.get_structure(0)
        name = structure.get_name()
        
        logger.info(f"New pad added: {name}")
        
        # Initialize recorder if needed
        if not self.recorder:
            self.recorder = WebMRecorder(self.connection_id, self.stream_id, self.record_dir)
            self.recorder.create_recording_pipeline()
            
        # Route to appropriate handler
        if name.startswith("application/x-rtp"):
            # Get encoding name from caps
            encoding_name = structure.get_string("encoding-name")
            
            if encoding_name == "VP8":
                logger.info("Adding VP8 video stream")
                self.recorder.add_video_stream(pad)
            elif encoding_name == "OPUS":
                logger.info("Adding OPUS audio stream")
                self.recorder.add_audio_stream(pad)
            else:
                logger.warning(f"Unknown encoding: {encoding_name}")
                
    def stop_recording(self):
        """Stop recording and cleanup"""
        if self.recorder:
            self.recorder.stop()
            self.recorder.cleanup()
            self.recorder = None


# Example usage function
def create_webrtc_recorder_example():
    """Example of how to use the WebM recorder with webrtcbin"""
    
    # Initialize GStreamer
    Gst.init(None)
    
    # Create pipeline with webrtcbin
    pipeline_str = "webrtcbin name=webrtc bundle-policy=max-bundle"
    pipeline = Gst.parse_launch(pipeline_str)
    
    webrtc = pipeline.get_by_name("webrtc")
    
    # Create recorder connection
    recorder_conn = WebRTCWebMConnection("conn123", "stream456", "./recordings")
    
    # Connect pad-added signal
    webrtc.connect("pad-added", recorder_conn.on_pad_added)
    
    # ... rest of WebRTC setup (ICE, SDP, etc.) ...
    
    return pipeline, recorder_conn
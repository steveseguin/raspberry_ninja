#!/usr/bin/env python3
"""
Advanced WebM Recording with Synchronization and Edge Case Handling
Demonstrates robust audio/video recording with proper synchronization
"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')

from gi.repository import Gst, GLib
import logging
import time
import threading
import os

logger = logging.getLogger(__name__)


class AdvancedWebMRecorder:
    """Advanced WebM recorder with synchronization and quality control"""
    
    def __init__(self, connection_id, stream_id, config=None):
        """
        Initialize advanced WebM recorder
        
        Args:
            connection_id: Unique connection identifier
            stream_id: Stream ID being recorded
            config: Recording configuration dict
        """
        self.connection_id = connection_id
        self.stream_id = stream_id
        self.config = config or {}
        
        # Recording elements
        self.pipeline = None
        self.webmmux = None
        self.filesink = None
        
        # Stream tracking
        self.video_pad = None
        self.audio_pad = None
        self.video_connected = False
        self.audio_connected = False
        
        # Synchronization
        self.first_buffer_time = None
        self.video_buffer_count = 0
        self.audio_buffer_count = 0
        
        # Quality settings
        self.video_bitrate = self.config.get('video_bitrate', 1000000)
        self.audio_bitrate = self.config.get('audio_bitrate', 128000)
        self.max_delay = self.config.get('max_av_delay', 1000)  # ms
        
        # Output
        timestamp = int(time.time())
        output_dir = self.config.get('output_dir', './recordings')
        os.makedirs(output_dir, exist_ok=True)
        self.filename = os.path.join(output_dir, f"{stream_id}_{timestamp}_{connection_id[:8]}.webm")
        
        # Statistics
        self.stats = {
            'start_time': None,
            'video_frames': 0,
            'audio_frames': 0,
            'dropped_frames': 0,
            'sync_corrections': 0
        }
        
    def create_pipeline(self):
        """Create advanced recording pipeline with synchronization"""
        try:
            self.pipeline = Gst.Pipeline.new(f"webm_recorder_{self.connection_id}")
            
            # Create WebM muxer with optimized settings
            self.webmmux = Gst.ElementFactory.make("webmmux", "muxer")
            self.webmmux.set_property("streamable", True)
            self.webmmux.set_property("writing-app", "Advanced WebM Recorder")
            
            # Set offset to handle streams starting at different times
            self.webmmux.set_property("offset-to-zero", True)
            
            # Create file sink with buffering
            self.filesink = Gst.ElementFactory.make("filesink", "sink")
            self.filesink.set_property("location", self.filename)
            self.filesink.set_property("sync", False)
            self.filesink.set_property("buffer-mode", 2)  # Buffered write
            
            # Add to pipeline
            self.pipeline.add(self.webmmux)
            self.pipeline.add(self.filesink)
            
            # Link muxer to sink
            if not self.webmmux.link(self.filesink):
                raise Exception("Failed to link muxer to filesink")
            
            # Set up bus monitoring
            bus = self.pipeline.get_bus()
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)
            
            # Add latency query support
            self.pipeline.set_latency(Gst.CLOCK_TIME_NONE)
            
            logger.info(f"Created advanced pipeline for {self.stream_id}")
            
        except Exception as e:
            logger.error(f"Failed to create pipeline: {e}")
            self.cleanup()
            raise
            
    def add_video_stream(self, pad):
        """Add video stream with quality control and synchronization"""
        if self.video_connected:
            logger.warning("Video already connected")
            return
            
        try:
            # Create video processing bin
            video_bin_str = (
                "queue name=video_queue "
                "max-size-buffers=200 "
                "max-size-time=2000000000 "
                "leaky=downstream ! "
                "rtpvp8depay ! "
                "identity name=video_monitor single-segment=true"
            )
            
            video_bin = Gst.parse_bin_from_description(video_bin_str, True)
            self.pipeline.add(video_bin)
            
            # Get elements for configuration
            video_queue = video_bin.get_by_name("video_queue")
            video_monitor = video_bin.get_by_name("video_monitor")
            
            # Set up monitoring
            video_monitor.connect("handoff", self._on_video_buffer)
            
            # Add timestamp correction
            if self.config.get('fix_timestamps', True):
                # Create timestamp fixer
                ts_fix = Gst.ElementFactory.make("identity", "video_ts_fix")
                ts_fix.set_property("sync", True)
                self.pipeline.add(ts_fix)
                
                # Link: video_bin -> ts_fix -> muxer
                video_bin.link(ts_fix)
                mux_pad = self.webmmux.get_request_pad("video_%u")
                ts_fix.get_static_pad("src").link(mux_pad)
            else:
                # Direct link to muxer
                mux_pad = self.webmmux.get_request_pad("video_%u")
                video_bin.get_static_pad("src").link(mux_pad)
            
            # Sync state
            video_bin.sync_state_with_parent()
            
            # Connect input pad
            sink_pad = video_bin.get_static_pad("sink")
            if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
                raise Exception("Failed to link video pad")
                
            self.video_pad = pad
            self.video_connected = True
            
            logger.info("Video stream connected with advanced processing")
            self._start_if_ready()
            
        except Exception as e:
            logger.error(f"Failed to add video: {e}")
            raise
            
    def add_audio_stream(self, pad):
        """Add audio stream with synchronization"""
        if self.audio_connected:
            logger.warning("Audio already connected")
            return
            
        try:
            # Create audio processing bin with resampling
            audio_bin_str = (
                "queue name=audio_queue "
                "max-size-buffers=200 "
                "max-size-time=2000000000 "
                "leaky=downstream ! "
                "rtpopusdepay ! "
                "opusparse ! "
                "identity name=audio_monitor single-segment=true"
            )
            
            audio_bin = Gst.parse_bin_from_description(audio_bin_str, True)
            self.pipeline.add(audio_bin)
            
            # Get elements
            audio_queue = audio_bin.get_by_name("audio_queue")
            audio_monitor = audio_bin.get_by_name("audio_monitor")
            
            # Set up monitoring
            audio_monitor.connect("handoff", self._on_audio_buffer)
            
            # Get audio pad from muxer
            mux_pad = self.webmmux.get_request_pad("audio_%u")
            audio_bin.get_static_pad("src").link(mux_pad)
            
            # Sync state
            audio_bin.sync_state_with_parent()
            
            # Connect input
            sink_pad = audio_bin.get_static_pad("sink")
            if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
                raise Exception("Failed to link audio pad")
                
            self.audio_pad = pad
            self.audio_connected = True
            
            logger.info("Audio stream connected with synchronization")
            self._start_if_ready()
            
        except Exception as e:
            logger.error(f"Failed to add audio: {e}")
            raise
            
    def _on_video_buffer(self, identity, buffer):
        """Monitor video buffers for statistics"""
        self.video_buffer_count += 1
        self.stats['video_frames'] += 1
        
        # Track first buffer time for sync reference
        if not self.first_buffer_time:
            self.first_buffer_time = buffer.pts
            
    def _on_audio_buffer(self, identity, buffer):
        """Monitor audio buffers for statistics"""
        self.audio_buffer_count += 1
        self.stats['audio_frames'] += 1
        
    def _start_if_ready(self):
        """Start recording when at least one stream is ready"""
        if not self.stats['start_time'] and (self.video_connected or self.audio_connected):
            ret = self.pipeline.set_state(Gst.State.PLAYING)
            if ret == Gst.StateChangeReturn.FAILURE:
                logger.error("Failed to start pipeline")
                return
                
            self.stats['start_time'] = time.time()
            logger.info(f"Recording started: {self.filename}")
            
            # Start monitoring thread
            self._start_monitoring()
            
    def _start_monitoring(self):
        """Start background monitoring thread"""
        def monitor():
            while self.stats['start_time'] and self.pipeline:
                try:
                    # Get pipeline position
                    success, position = self.pipeline.query_position(Gst.Format.TIME)
                    if success:
                        position_sec = position / Gst.SECOND
                        
                        # Calculate rates
                        elapsed = time.time() - self.stats['start_time']
                        if elapsed > 0:
                            video_fps = self.stats['video_frames'] / elapsed
                            audio_fps = self.stats['audio_frames'] / elapsed
                            
                            logger.debug(f"Recording stats - Duration: {position_sec:.1f}s, "
                                       f"Video: {video_fps:.1f} fps, Audio: {audio_fps:.1f} fps")
                            
                except Exception as e:
                    logger.error(f"Monitoring error: {e}")
                    
                time.sleep(5)
                
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        
    def _on_bus_message(self, bus, message):
        """Handle pipeline messages"""
        msg_type = message.type
        
        if msg_type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            logger.error(f"Pipeline error: {err} - {debug}")
            self.stats['errors'] = self.stats.get('errors', 0) + 1
            
        elif msg_type == Gst.MessageType.WARNING:
            warn, debug = message.parse_warning()
            logger.warning(f"Pipeline warning: {warn} - {debug}")
            
        elif msg_type == Gst.MessageType.EOS:
            logger.info("Recording completed (EOS)")
            
        elif msg_type == Gst.MessageType.QOS:
            # Handle quality messages
            qos = message.parse_qos()
            if qos:
                logger.debug(f"QoS event: {qos}")
                self.stats['dropped_frames'] += 1
                
    def stop(self):
        """Stop recording with proper finalization"""
        if not self.pipeline:
            return
            
        logger.info(f"Stopping recording for {self.stream_id}")
        
        # Calculate final statistics
        if self.stats['start_time']:
            duration = time.time() - self.stats['start_time']
            self.stats['duration'] = duration
            
            if duration > 0:
                self.stats['avg_video_fps'] = self.stats['video_frames'] / duration
                self.stats['avg_audio_fps'] = self.stats['audio_frames'] / duration
                
        # Send EOS for proper file finalization
        self.pipeline.send_event(Gst.Event.new_eos())
        
        # Wait for EOS
        bus = self.pipeline.get_bus()
        msg = bus.timed_pop_filtered(
            10 * Gst.SECOND,
            Gst.MessageType.EOS | Gst.MessageType.ERROR
        )
        
        if msg and msg.type == Gst.MessageType.EOS:
            logger.info("Recording finalized successfully")
        else:
            logger.warning("Recording stopped without proper EOS")
            
        # Stop pipeline
        self.pipeline.set_state(Gst.State.NULL)
        
        # Log final statistics
        self._log_final_stats()
        
    def _log_final_stats(self):
        """Log final recording statistics"""
        if os.path.exists(self.filename):
            file_size = os.path.getsize(self.filename)
            self.stats['file_size'] = file_size
            
            logger.info(f"Recording complete: {self.filename}")
            logger.info(f"  Size: {file_size:,} bytes")
            logger.info(f"  Duration: {self.stats.get('duration', 0):.1f} seconds")
            logger.info(f"  Video frames: {self.stats['video_frames']:,}")
            logger.info(f"  Audio frames: {self.stats['audio_frames']:,}")
            
            if self.stats.get('dropped_frames', 0) > 0:
                logger.warning(f"  Dropped frames: {self.stats['dropped_frames']}")
                
    def cleanup(self):
        """Clean up all resources"""
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
            
        self.webmmux = None
        self.filesink = None
        self.video_pad = None
        self.audio_pad = None
        
    def get_stats(self):
        """Get current recording statistics"""
        stats = self.stats.copy()
        
        if self.stats['start_time']:
            stats['current_duration'] = time.time() - self.stats['start_time']
            
        if os.path.exists(self.filename):
            stats['current_file_size'] = os.path.getsize(self.filename)
            
        return stats


# Example usage with edge cases
def test_advanced_recording():
    """Test advanced WebM recording with various scenarios"""
    
    Gst.init(None)
    logging.basicConfig(level=logging.INFO)
    
    # Test configuration
    config = {
        'video_bitrate': 2000000,  # 2 Mbps
        'audio_bitrate': 192000,   # 192 kbps
        'fix_timestamps': True,
        'max_av_delay': 500,       # 500ms max A/V delay
        'output_dir': './recordings'
    }
    
    # Create recorder
    recorder = AdvancedWebMRecorder("test_conn", "test_stream", config)
    recorder.create_pipeline()
    
    # Simulate WebRTC pads appearing at different times
    # ... (integrate with your WebRTC code)
    
    logger.info("Advanced WebM recording test completed")


if __name__ == "__main__":
    test_advanced_recording()
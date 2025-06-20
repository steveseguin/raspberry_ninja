#!/usr/bin/env python3
"""
Room Recording WebM Patch
Demonstrates how to patch existing room recording to use WebM with audio/video muxing
"""

from webrtc_webm_recorder import WebMRecorder
import logging

logger = logging.getLogger(__name__)


def patch_webrtc_connection_for_webm(connection_class):
    """
    Monkey patch existing WebRTC connection class to use WebM recording
    
    This function modifies the _setup_recording method to use WebM instead of TS
    """
    
    # Store original method
    original_setup_recording = connection_class._setup_recording
    
    def _setup_recording_webm(self, pad, media_type):
        """Enhanced recording setup using WebM with audio/video muxing"""
        
        # Initialize WebM recorder if not exists
        if not hasattr(self, 'webm_recorder'):
            self.webm_recorder = WebMRecorder(
                self.connection_id,
                self.stream_id,
                getattr(self, 'record_dir', './recordings')
            )
            self.webm_recorder.create_recording_pipeline()
            logger.info(f"Created WebM recorder for {self.stream_id}")
        
        # Check media type from caps
        caps = pad.get_current_caps()
        if not caps:
            return
            
        structure = caps.get_structure(0)
        name = structure.get_name()
        
        if name.startswith("application/x-rtp"):
            encoding = structure.get_string("encoding-name")
            
            if encoding == "VP8":
                logger.info(f"Adding VP8 video to WebM for {self.stream_id}")
                self.webm_recorder.add_video_stream(pad)
                self.is_recording = True
                self.recording_filename = self.webm_recorder.filename
                
            elif encoding == "OPUS":
                if not self.pipeline_config.get('no_audio', False):
                    logger.info(f"Adding OPUS audio to WebM for {self.stream_id}")
                    self.webm_recorder.add_audio_stream(pad)
                    
            elif encoding == "H264":
                # For H264, we need to transcode to VP8 for WebM
                logger.warning(f"H264 detected, transcoding to VP8 for WebM")
                self._setup_h264_to_vp8_recording(pad)
            else:
                logger.warning(f"Unsupported encoding for WebM: {encoding}")
                # Fall back to original method
                original_setup_recording(self, pad, media_type)
    
    def _setup_h264_to_vp8_recording(self, pad):
        """Transcode H264 to VP8 for WebM recording"""
        # Create transcoding pipeline
        transcode_str = (
            "queue ! "
            "rtph264depay ! "
            "h264parse ! "
            "avdec_h264 ! "
            "videoconvert ! "
            "vp8enc deadline=1 cpu-used=4 ! "
            "webmmux name=webm_mux ! "
            f"filesink location={self.stream_id}_h264_to_vp8.webm"
        )
        
        transcode_bin = Gst.parse_bin_from_description(transcode_str, True)
        self.pipeline.add(transcode_bin)
        transcode_bin.sync_state_with_parent()
        
        sink = transcode_bin.get_static_pad('sink')
        pad.link(sink)
        
        logger.info(f"Set up H264 to VP8 transcoding for {self.stream_id}")
    
    # Store original stop method
    original_stop = connection_class.stop
    
    def stop_with_webm(self):
        """Enhanced stop that properly closes WebM files"""
        logger.info(f"Stopping connection with WebM cleanup for {self.connection_id}")
        
        # Stop WebM recorder if exists
        if hasattr(self, 'webm_recorder') and self.webm_recorder:
            self.webm_recorder.stop()
            stats = self.webm_recorder.get_stats()
            logger.info(f"WebM recording stats for {self.stream_id}: {stats}")
            self.webm_recorder.cleanup()
            self.webm_recorder = None
        
        # Call original stop
        original_stop(self)
    
    # Apply patches
    connection_class._setup_recording = _setup_recording_webm
    connection_class._setup_h264_to_vp8_recording = _setup_h264_to_vp8_recording
    connection_class.stop = stop_with_webm
    
    logger.info("Patched WebRTC connection class for WebM recording")


def create_webm_config(base_config):
    """
    Create WebM-specific configuration from base config
    
    Args:
        base_config: Base configuration dict
        
    Returns:
        Enhanced configuration for WebM recording
    """
    webm_config = base_config.copy()
    
    # Ensure recording is enabled
    webm_config['record'] = True
    
    # Set output directory
    if 'record_dir' not in webm_config:
        webm_config['record_dir'] = './recordings'
    
    # Enable audio recording by default
    webm_config['no_audio'] = webm_config.get('no_audio', False)
    
    # Set quality parameters
    webm_config['video_bitrate'] = webm_config.get('video_bitrate', 1000000)  # 1 Mbps
    webm_config['audio_bitrate'] = webm_config.get('audio_bitrate', 128000)   # 128 kbps
    
    return webm_config


# Example usage in existing code
def example_integration():
    """Show how to integrate WebM recording into existing room recording"""
    
    import sys
    import os
    
    # Add parent directory to path to import existing modules
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    try:
        # Import existing WebRTC connection class
        from webrtc_connection import WebRTCConnection
        
        # Apply WebM patch
        patch_webrtc_connection_for_webm(WebRTCConnection)
        
        # Now WebRTCConnection will use WebM recording automatically
        config = create_webm_config({
            'receive_only': True,
            'ice_servers': {
                'stun': 'stun:stun.l.google.com:19302'
            }
        })
        
        # Create connection - it will now use WebM
        connection = WebRTCConnection("test_id", "test_stream", config)
        connection.create_pipeline()
        
        logger.info("WebRTC connection created with WebM recording support")
        
    except ImportError as e:
        logger.error(f"Could not import WebRTCConnection: {e}")
        logger.info("This is an example - ensure webrtc_connection.py exists")


if __name__ == "__main__":
    example_integration()
#!/usr/bin/env python3
"""
Enhanced WebRTC Connection with WebM Recording
Demonstrates integration of dynamic WebM recording into existing WebRTC connections
"""

import asyncio
import json
import time
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')

from gi.repository import Gst, GstWebRTC, GstSdp
import logging
from webrtc_webm_recorder import WebMRecorder

logger = logging.getLogger(__name__)


class WebRTCConnectionWithWebM:
    """Enhanced WebRTC connection with WebM recording support"""
    
    def __init__(self, connection_id, stream_id, pipeline_config):
        """
        Initialize WebRTC connection with WebM recording
        
        Args:
            connection_id: Unique identifier for this connection
            stream_id: Stream ID being received/sent
            pipeline_config: Configuration for GStreamer pipeline
        """
        self.connection_id = connection_id
        self.stream_id = stream_id
        self.session_id = None
        self.pipeline_config = pipeline_config
        
        # WebRTC elements
        self.pipeline = None
        self.webrtc_bin = None
        
        # Connection state
        self.is_connected = False
        self.ice_connection_state = None
        self.ice_gathering_state = None
        
        # Callbacks
        self.on_ice_candidate = None
        self.on_answer_created = None
        self.on_state_change = None
        
        # WebM Recording
        self.webm_recorder = None
        self.record_dir = pipeline_config.get('record_dir', './recordings')
        
    def create_pipeline(self):
        """Create the GStreamer pipeline for this connection"""
        try:
            # For receiving streams (room recording case)
            if self.pipeline_config.get('receive_only', False):
                pipeline_str = "webrtcbin name=webrtc bundle-policy=max-bundle"
                self.pipeline = Gst.parse_launch(pipeline_str)
            else:
                # Use the provided pipeline string
                self.pipeline = Gst.parse_launch(self.pipeline_config['pipeline_string'])
            
            self.webrtc_bin = self.pipeline.get_by_name('webrtc')
            if not self.webrtc_bin:
                raise Exception("No webrtcbin found in pipeline")
            
            # Set up callbacks
            self._setup_webrtc_callbacks()
            
            # Set ICE servers if configured
            if 'ice_servers' in self.pipeline_config:
                self._configure_ice_servers(self.pipeline_config['ice_servers'])
            
            # Start pipeline
            self.pipeline.set_state(Gst.State.READY)
            logger.info(f"Pipeline created for connection {self.connection_id}")
            
        except Exception as e:
            logger.error(f"Failed to create pipeline: {e}")
            raise
            
    def _setup_webrtc_callbacks(self):
        """Set up WebRTC callbacks"""
        self.webrtc_bin.connect('on-ice-candidate', self._on_ice_candidate)
        self.webrtc_bin.connect('notify::ice-connection-state', self._on_ice_connection_state)
        self.webrtc_bin.connect('notify::ice-gathering-state', self._on_ice_gathering_state)
        self.webrtc_bin.connect('pad-added', self._on_pad_added)
        
    def _configure_ice_servers(self, ice_servers):
        """Configure STUN/TURN servers"""
        if 'stun' in ice_servers:
            self.webrtc_bin.set_property('stun-server', ice_servers['stun'])
        if 'turn' in ice_servers:
            self.webrtc_bin.set_property('turn-server', ice_servers['turn'])
            
    def handle_offer(self, sdp_offer):
        """Handle incoming SDP offer"""
        logger.info(f"Handling offer for connection {self.connection_id}")
        
        # Parse SDP
        res, sdpmsg = GstSdp.SDPMessage.new()
        GstSdp.sdp_message_parse_buffer(bytes(sdp_offer['sdp'].encode()), sdpmsg)
        offer = GstWebRTC.WebRTCSessionDescription.new(GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
        
        # Set remote description
        promise = Gst.Promise.new_with_change_func(self._on_offer_set, None, None)
        self.webrtc_bin.emit('set-remote-description', offer, promise)
        
    def _on_offer_set(self, promise, _, __):
        """Called when offer has been set"""
        # Create answer
        promise = Gst.Promise.new_with_change_func(self._on_answer_created_internal, None, None)
        self.webrtc_bin.emit('create-answer', None, promise)
        
    def _on_answer_created_internal(self, promise, _, __):
        """Internal handler for answer creation"""
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        
        if not answer:
            logger.error(f"Failed to create answer for {self.connection_id}")
            return
            
        # Set local description
        promise = Gst.Promise.new()
        self.webrtc_bin.emit('set-local-description', answer, promise)
        promise.interrupt()
        
        # Get SDP text
        sdp_text = answer.sdp.as_text()
        
        # Notify callback
        if self.on_answer_created:
            self.on_answer_created(self.connection_id, {
                'type': 'answer',
                'sdp': sdp_text
            })
            
        # Set pipeline to playing
        self.pipeline.set_state(Gst.State.PLAYING)
        
    def add_ice_candidate(self, candidate, sdp_mline_index):
        """Add ICE candidate"""
        self.webrtc_bin.emit('add-ice-candidate', sdp_mline_index, candidate)
        
    def _on_ice_candidate(self, webrtc, mline_index, candidate):
        """Handle outgoing ICE candidate"""
        if self.on_ice_candidate:
            self.on_ice_candidate(self.connection_id, {
                'candidate': candidate,
                'sdpMLineIndex': mline_index
            })
            
    def _on_ice_connection_state(self, webrtc, pspec):
        """Monitor ICE connection state"""
        state = webrtc.get_property('ice-connection-state')
        self.ice_connection_state = state
        logger.info(f"ICE connection state for {self.connection_id}: {state}")
        
        if state == GstWebRTC.WebRTCICEConnectionState.CONNECTED:
            self.is_connected = True
            if self.on_state_change:
                self.on_state_change(self.connection_id, 'connected')
        elif state == GstWebRTC.WebRTCICEConnectionState.FAILED:
            if self.on_state_change:
                self.on_state_change(self.connection_id, 'failed')
                
    def _on_ice_gathering_state(self, webrtc, pspec):
        """Monitor ICE gathering state"""
        state = webrtc.get_property('ice-gathering-state')
        self.ice_gathering_state = state
        logger.info(f"ICE gathering state for {self.connection_id}: {state}")
        
    def _on_pad_added(self, webrtc, pad):
        """Handle new media pad with WebM recording"""
        if pad.direction != Gst.PadDirection.SRC:
            return
            
        caps = pad.get_current_caps()
        if not caps:
            return
            
        structure = caps.get_structure(0)
        name = structure.get_name()
        logger.info(f"New pad added for {self.connection_id}: {name}")
        
        # For room recording, set up WebM recording
        if self.pipeline_config.get('record', False):
            self._setup_webm_recording(pad, structure)
            
    def _setup_webm_recording(self, pad, caps_structure):
        """Set up WebM recording for incoming streams"""
        # Initialize WebM recorder if not already created
        if not self.webm_recorder:
            self.webm_recorder = WebMRecorder(
                self.connection_id, 
                self.stream_id, 
                self.record_dir
            )
            self.webm_recorder.create_recording_pipeline()
            logger.info(f"Created WebM recorder for {self.stream_id}")
        
        # Check if this is RTP
        name = caps_structure.get_name()
        if name.startswith("application/x-rtp"):
            encoding_name = caps_structure.get_string("encoding-name")
            
            if encoding_name == "VP8":
                logger.info("Adding VP8 video stream to WebM recording")
                self.webm_recorder.add_video_stream(pad)
            elif encoding_name == "OPUS":
                logger.info("Adding OPUS audio stream to WebM recording")
                self.webm_recorder.add_audio_stream(pad)
            else:
                logger.warning(f"Unsupported encoding for WebM: {encoding_name}")
                
    def stop(self):
        """Stop the connection and recording"""
        logger.info(f"Stopping connection {self.connection_id}")
        
        # Stop WebM recording first
        if self.webm_recorder:
            self.webm_recorder.stop()
            stats = self.webm_recorder.get_stats()
            logger.info(f"Recording stats: {stats}")
            self.webm_recorder.cleanup()
            self.webm_recorder = None
        
        # Stop pipeline
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
            self.webrtc_bin = None
            
        self.is_connected = False
        
    def get_stats(self):
        """Get connection and recording statistics"""
        stats = {
            'connection_id': self.connection_id,
            'stream_id': self.stream_id,
            'is_connected': self.is_connected,
            'ice_connection_state': str(self.ice_connection_state) if self.ice_connection_state else None,
            'ice_gathering_state': str(self.ice_gathering_state) if self.ice_gathering_state else None
        }
        
        # Add recording stats if available
        if self.webm_recorder:
            stats['recording'] = self.webm_recorder.get_stats()
            
        return stats


# Example usage
async def example_usage():
    """Example of using WebRTC connection with WebM recording"""
    
    # Initialize GStreamer
    Gst.init(None)
    
    # Create connection with recording enabled
    config = {
        'receive_only': True,
        'record': True,
        'record_dir': './recordings',
        'ice_servers': {
            'stun': 'stun:stun.l.google.com:19302'
        }
    }
    
    connection = WebRTCConnectionWithWebM("conn_123", "stream_456", config)
    connection.create_pipeline()
    
    # Set up callbacks (example)
    def on_answer(conn_id, answer):
        print(f"Answer created for {conn_id}: {answer['type']}")
        
    def on_ice(conn_id, candidate):
        print(f"ICE candidate for {conn_id}: {candidate}")
        
    connection.on_answer_created = on_answer
    connection.on_ice_candidate = on_ice
    
    # ... Handle WebRTC signaling ...
    
    # After some time, stop recording
    await asyncio.sleep(30)
    connection.stop()


if __name__ == "__main__":
    asyncio.run(example_usage())
#!/usr/bin/env python3
"""
WebRTC Connection Class
Encapsulates a single WebRTC peer connection with its associated pipeline
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

logger = logging.getLogger(__name__)


class WebRTCConnection:
    """Manages a single WebRTC peer connection"""
    
    def __init__(self, connection_id, stream_id, pipeline_config):
        """
        Initialize a WebRTC connection
        
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
        self.on_pad_added = None
        self.on_state_change = None
        
        # Recording
        self.is_recording = False
        self.recording_filename = None
        
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
        """
        Handle incoming SDP offer
        
        Args:
            sdp_offer: SDP offer dict with 'type' and 'sdp' fields
        """
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
        """Handle new media pad"""
        if pad.direction != Gst.PadDirection.SRC:
            return
            
        caps = pad.get_current_caps()
        if not caps:
            return
            
        name = caps.get_structure(0).get_name()
        logger.info(f"New pad added for {self.connection_id}: {name}")
        
        # For room recording, set up recording pipeline
        if self.pipeline_config.get('record', False):
            self._setup_recording(pad, name)
        
        # Notify callback
        if self.on_pad_added:
            self.on_pad_added(self.connection_id, pad, name)
            
    def _setup_recording(self, pad, media_type):
        """Set up recording for incoming stream"""
        if "video" in media_type:
            if "h264" in media_type.lower():
                self._setup_h264_recording(pad)
            elif "vp8" in media_type.lower():
                self._setup_vp8_recording(pad)
        elif "audio" in media_type and not self.pipeline_config.get('no_audio', False):
            self._setup_audio_recording(pad)
            
    def _setup_h264_recording(self, pad):
        """Set up H264 recording pipeline"""
        timestamp = int(time.time())
        filename = f"{self.stream_id}_{timestamp}_{self.connection_id[:8]}.ts"
        
        # Create recording pipeline
        pipeline_str = (
            f"queue ! rtph264depay ! h264parse ! "
            f"mpegtsmux name=mux_{self.connection_id} ! "
            f"filesink location={filename}"
        )
        
        recording_bin = Gst.parse_bin_from_description(pipeline_str, True)
        self.pipeline.add(recording_bin)
        recording_bin.sync_state_with_parent()
        
        # Link pad
        sink = recording_bin.get_static_pad('sink')
        pad.link(sink)
        
        self.is_recording = True
        self.recording_filename = filename
        logger.info(f"Recording H264 to {filename}")
        
    def _setup_vp8_recording(self, pad):
        """Set up VP8 recording pipeline"""
        timestamp = int(time.time())
        filename = f"{self.stream_id}_{timestamp}_{self.connection_id[:8]}.ts"
        
        # Create recording pipeline
        pipeline_str = (
            f"queue ! rtpvp8depay ! "
            f"mpegtsmux name=mux_{self.connection_id} ! "
            f"filesink location={filename}"
        )
        
        recording_bin = Gst.parse_bin_from_description(pipeline_str, True)
        self.pipeline.add(recording_bin)
        recording_bin.sync_state_with_parent()
        
        # Link pad
        sink = recording_bin.get_static_pad('sink')
        pad.link(sink)
        
        self.is_recording = True
        self.recording_filename = filename
        logger.info(f"Recording VP8 to {filename}")
        
    def _setup_audio_recording(self, pad):
        """Set up audio recording to existing mux"""
        # Check if we have a mux already
        mux = self.pipeline.get_by_name(f"mux_{self.connection_id}")
        if not mux:
            logger.warning("No mux found for audio recording")
            return
            
        # Create audio pipeline
        pipeline_str = "queue ! rtpopusdepay ! opusparse"
        audio_bin = Gst.parse_bin_from_description(pipeline_str, True)
        self.pipeline.add(audio_bin)
        audio_bin.sync_state_with_parent()
        
        # Link to pad
        sink = audio_bin.get_static_pad('sink')
        pad.link(sink)
        
        # Link to mux
        src = audio_bin.get_static_pad('src')
        audio_pad = mux.get_request_pad('sink_%d')
        if audio_pad:
            src.link(audio_pad)
            logger.info("Added audio to recording")
            
    def stop(self):
        """Stop the connection and clean up"""
        logger.info(f"Stopping connection {self.connection_id}")
        
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
            self.webrtc_bin = None
            
        self.is_connected = False
        self.is_recording = False
        
    def get_stats(self):
        """Get connection statistics"""
        return {
            'connection_id': self.connection_id,
            'stream_id': self.stream_id,
            'is_connected': self.is_connected,
            'is_recording': self.is_recording,
            'recording_filename': self.recording_filename,
            'ice_connection_state': str(self.ice_connection_state) if self.ice_connection_state else None,
            'ice_gathering_state': str(self.ice_gathering_state) if self.ice_gathering_state else None
        }
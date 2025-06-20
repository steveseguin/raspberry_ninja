#!/usr/bin/env python3
"""
WebRTC Subprocess Handler with Matroska (MKV) Audio/Video Muxing
Based on recommendations from Gemini Pro 2.5 and o3-mini
Handles dynamic pad arrival and muxes audio+video into single MKV file
"""

import sys
import json
import gi
import time
import threading
import datetime
import os
from typing import Optional, Dict, Any

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp

# Initialize GStreamer
Gst.init(None)


class MKVWebRTCHandler:
    """Handles WebRTC pipeline with MKV muxing in a subprocess"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.stream_id = config.get('stream_id')
        self.mode = config.get('mode', 'view')
        self.room = config.get('room')
        self.record_file = config.get('record_file')
        self.record_audio = config.get('record_audio', False)
        
        # Pipeline state
        self.pipe = None
        self.webrtc = None
        self.session_id = None
        self.pipeline_start_time = None
        self.pipeline_started = False  # Track if pipeline has been started
        
        # Muxing elements
        self.muxer = None
        self.filesink = None
        self.output_filename = None
        
        # Track what's connected
        self.video_connected = False
        self.audio_connected = False
        self.first_pad_time = None
        
        # IPC communication
        self.running = True
        
        # ICE candidates queue
        self.ice_candidates = []
        self.generated_ice_candidates = []
        self.pending_renegotiation = None
        
        # Main loop
        self.main_loop = GLib.MainLoop()
        
        # Setup stdin monitoring
        self.setup_stdin_watch()
        
    def setup_stdin_watch(self):
        """Setup monitoring of stdin for messages"""
        # Create a channel for stdin
        self.stdin_channel = GLib.IOChannel.unix_new(sys.stdin.fileno())
        self.stdin_channel.set_encoding(None)
        self.stdin_channel.set_buffered(False)
        
        # Add watch for stdin
        GLib.io_add_watch(self.stdin_channel, GLib.IO_IN, self.on_stdin_data)
        
    def on_stdin_data(self, channel, condition):
        """Handle data from stdin"""
        try:
            line = sys.stdin.readline()
            if not line:
                self.log("EOF on stdin, shutting down")
                self.shutdown()
                return False
            
            msg = json.loads(line.strip())
            self.handle_message(msg)
            
        except json.JSONDecodeError as e:
            self.log(f"Invalid JSON: {e}", "error")
        except Exception as e:
            self.log(f"Error handling stdin: {e}", "error")
            
        return True  # Continue watching
        
    def log(self, message: str, level: str = "info"):
        """Send log message to parent process"""
        self.send_message({
            "type": "log",
            "level": level,
            "message": f"[{self.stream_id}] {message}"
        })
        
    def send_message(self, msg: Dict[str, Any]):
        """Send message to parent process"""
        try:
            print(json.dumps(msg), flush=True)
        except Exception as e:
            sys.stderr.write(f"Failed to send message: {e}\n")
            
    def handle_message(self, msg: Dict[str, Any]):
        """Handle messages from parent process"""
        msg_type = msg.get('type')
        
        # Start pipeline if not already started when we get first meaningful message
        if not self.pipeline_started and msg_type in ['offer', 'sdp']:
            self.log("Starting pipeline on first offer/sdp message")
            self.start_pipeline()
        
        if msg_type == 'start':
            self.start_pipeline()
        elif msg_type == 'offer' or msg_type == 'sdp':
            # Handle both message formats
            if msg_type == 'sdp':
                offer_data = {
                    'sdp': msg.get('sdp'),
                    'type': msg.get('sdp_type', 'offer')
                }
                self.session_id = msg.get('session_id')
            else:
                offer_data = msg.get('data', msg)
            self.handle_remote_offer(offer_data)
        elif msg_type == 'ice':
            # Handle ICE candidates
            if 'data' in msg:
                self.add_ice_candidate(msg['data'])
            else:
                # Direct format
                self.add_ice_candidate(msg)
        elif msg_type == 'stop':
            self.shutdown()
        else:
            self.log(f"Unknown message type: {msg_type}", "warning")
            
    def setup_muxer_and_sink(self):
        """Setup the Matroska muxer and file sink"""
        # Create muxer
        self.muxer = Gst.ElementFactory.make('matroskamux', 'muxer')
        if not self.muxer:
            self.log("Failed to create matroskamux", "error")
            return False
            
        # Set muxer properties for live streaming
        self.muxer.set_property('streamable', True)
        self.muxer.set_property('writing-app', 'Raspberry Ninja')
        
        # Create file sink
        self.filesink = Gst.ElementFactory.make('filesink', 'filesink')
        if not self.filesink:
            self.log("Failed to create filesink", "error")
            return False
            
        # Set output filename
        if self.record_file:
            self.output_filename = self.record_file.replace('.webm', '.mkv')
        else:
            timestamp = int(datetime.datetime.now().timestamp())
            self.output_filename = f"{self.room}_{self.stream_id}_{timestamp}.mkv"
            
        self.filesink.set_property('location', self.output_filename)
        self.filesink.set_property('sync', False)
        
        # Add to pipeline
        self.pipe.add(self.muxer)
        self.pipe.add(self.filesink)
        
        # Link muxer to filesink
        if not self.muxer.link(self.filesink):
            self.log("Failed to link muxer to filesink", "error")
            return False
            
        # Sync states
        self.muxer.sync_state_with_parent()
        self.filesink.sync_state_with_parent()
        
        self.log(f"🎬 Recording setup complete: {self.output_filename}")
        return True
        
    def start_pipeline(self):
        """Start the GStreamer pipeline"""
        if self.pipeline_started:
            self.log("Pipeline already started, skipping")
            return
            
        try:
            # Create pipeline
            self.pipe = Gst.Pipeline.new('webrtc-pipe')
            
            # Create webrtcbin
            self.webrtc = Gst.ElementFactory.make('webrtcbin', 'webrtc')
            self.webrtc.set_property('bundle-policy', GstWebRTC.WebRTCBundlePolicy.MAX_BUNDLE)
            
            # Connect signals
            self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)
            self.webrtc.connect('pad-added', self.on_pad_added)
            self.webrtc.connect('on-new-transceiver', self.on_new_transceiver)
            self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
            self.webrtc.connect('on-data-channel', self.on_data_channel)
            self.webrtc.connect('notify::ice-gathering-state', self.on_ice_gathering_state_notify)
            self.webrtc.connect('notify::ice-connection-state', self.on_ice_connection_state_notify)
            
            # Add to pipeline
            self.pipe.add(self.webrtc)
            
            # Configure STUN/TURN
            if 'stun_server' in self.config:
                self.webrtc.set_property('stun-server', self.config['stun_server'])
                self.log(f"STUN server: {self.config['stun_server']}")
                
            if 'turn_server' in self.config:
                self.webrtc.set_property('turn-server', self.config['turn_server'])
                self.log(f"TURN server configured")
                
            # Setup muxer and sink
            if not self.setup_muxer_and_sink():
                raise Exception("Failed to setup recording elements")
            
            # Start pipeline
            self.pipe.set_state(Gst.State.PLAYING)
            self.pipeline_start_time = time.time()
            self.pipeline_started = True  # Mark as started
            self.log("Pipeline started and playing")
            
            # Process any queued ICE candidates
            if self.ice_candidates:
                self.log(f"Processing {len(self.ice_candidates)} queued ICE candidates")
                for ice_data in self.ice_candidates:
                    self.add_ice_candidate(ice_data)
                self.ice_candidates.clear()
            
            # Send ready signal
            self.send_message({"type": "pipeline_ready"})
            
        except Exception as e:
            self.log(f"Failed to start pipeline: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            
    def on_pad_added(self, element, pad):
        """Handle new pad added to webrtcbin"""
        pad_name = pad.get_name()
        self.log(f"🎬 NEW PAD ADDED: {pad_name}")
        
        # Also log pad direction
        direction = pad.get_direction()
        self.log(f"   Direction: {direction.value_nick}")
        
        # Record first pad arrival time for synchronization
        if not self.first_pad_time:
            self.first_pad_time = time.time()
            self.log(f"First pad arrived, locking timeline")
        
        # Check if it's an RTP pad
        if not pad_name.startswith('src_'):
            return
            
        # Get pad caps to determine media type
        caps = pad.get_current_caps()
        if not caps:
            # Sometimes caps aren't immediately available, wait a bit
            GLib.timeout_add(100, self.check_pad_caps, pad)
            return
            
        self.process_pad_with_caps(pad, caps)
        
    def check_pad_caps(self, pad):
        """Check pad caps after a delay"""
        caps = pad.get_current_caps()
        if caps:
            self.process_pad_with_caps(pad, caps)
            return False  # Don't repeat
        return True  # Try again
        
    def process_pad_with_caps(self, pad, caps):
        """Process pad once caps are available"""
        structure = caps.get_structure(0)
        media_type = structure.get_value('media')
        
        self.log(f"Processing {media_type} pad: {pad.get_name()}")
        
        if media_type == 'video':
            self.handle_video_pad(pad, structure)
        elif media_type == 'audio':
            self.handle_audio_pad(pad, structure)
        else:
            self.log(f"Unknown media type: {media_type}", "warning")
            
    def handle_video_pad(self, pad, structure):
        """Handle video pad - connect to muxer"""
        if self.video_connected:
            self.log("Video already connected, ignoring additional video pad")
            return
            
        encoding_name = structure.get_string('encoding-name')
        width = structure.get_int('width')[1] if structure.has_field('width') else 'unknown'
        height = structure.get_int('height')[1] if structure.has_field('height') else 'unknown'
        
        self.log(f"📹 VIDEO STREAM: {encoding_name} @ {width}x{height}")
        
        # Create queue with properties for live streaming
        queue = Gst.ElementFactory.make('queue', 'video-queue')
        queue.set_property('max-size-time', 5 * Gst.SECOND)  # 5 second buffer
        queue.set_property('max-size-buffers', 0)
        queue.set_property('max-size-bytes', 0)
        
        # Create depayloader and parser based on codec
        if encoding_name == 'VP8':
            depay = Gst.ElementFactory.make('rtpvp8depay', 'video-depay')
            # VP8 doesn't need a parser for Matroska
            elements = [queue, depay]
        elif encoding_name == 'H264':
            depay = Gst.ElementFactory.make('rtph264depay', 'video-depay')
            parser = Gst.ElementFactory.make('h264parse', 'video-parse')
            elements = [queue, depay, parser]
        else:
            self.log(f"Unsupported video codec: {encoding_name}", "error")
            return
            
        # Add elements to pipeline
        for element in elements:
            self.pipe.add(element)
            
        # Link elements together
        for i in range(len(elements) - 1):
            if not elements[i].link(elements[i + 1]):
                self.log(f"Failed to link {elements[i].get_name()} to {elements[i + 1].get_name()}", "error")
                return
                
        # Request video pad from muxer
        mux_pad = self.muxer.request_pad_simple('video_%u')
        if not mux_pad:
            self.log("Failed to get video pad from muxer", "error")
            return
            
        # Link last element to muxer
        src_pad = elements[-1].get_static_pad('src')
        if src_pad.link(mux_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link video to muxer", "error")
            return
            
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
            
        # Link WebRTC pad to queue
        sink_pad = queue.get_static_pad('sink')
        if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link video pad to queue", "error")
            return
            
        self.video_connected = True
        self.log("✅ Video connected to muxer")
        
    def handle_audio_pad(self, pad, structure):
        """Handle audio pad - connect to muxer"""
        if self.audio_connected:
            self.log("Audio already connected, ignoring additional audio pad")
            return
            
        if not self.record_audio:
            self.log("Audio recording disabled, using fakesink")
            fakesink = Gst.ElementFactory.make('fakesink', None)
            self.pipe.add(fakesink)
            fakesink.sync_state_with_parent()
            pad.link(fakesink.get_static_pad('sink'))
            return
            
        encoding_name = structure.get_string('encoding-name')
        clock_rate = structure.get_int('clock-rate')[1] if structure.has_field('clock-rate') else 'unknown'
        
        self.log(f"🎤 AUDIO STREAM: {encoding_name} @ {clock_rate} Hz")
        
        # Create queue with properties for live streaming
        queue = Gst.ElementFactory.make('queue', 'audio-queue')
        queue.set_property('max-size-time', 2 * Gst.SECOND)  # 2 second buffer
        queue.set_property('max-size-buffers', 0)
        queue.set_property('max-size-bytes', 0)
        
        # Create processing chain based on codec
        if encoding_name == 'OPUS':
            # Opus: depay -> parse -> muxer
            depay = Gst.ElementFactory.make('rtpopusdepay', 'audio-depay')
            parser = Gst.ElementFactory.make('opusparse', 'audio-parse')
            elements = [queue, depay, parser]
            
        elif encoding_name in ['PCMU', 'PCMA']:
            # PCM needs transcoding to Opus as recommended by Gemini
            if encoding_name == 'PCMU':
                depay = Gst.ElementFactory.make('rtppcmudepay', 'audio-depay')
                decoder = Gst.ElementFactory.make('mulawdec', 'audio-decode')
            else:  # PCMA
                depay = Gst.ElementFactory.make('rtppcmadepay', 'audio-depay')
                decoder = Gst.ElementFactory.make('alawdec', 'audio-decode')
                
            convert = Gst.ElementFactory.make('audioconvert', 'audio-convert')
            resample = Gst.ElementFactory.make('audioresample', 'audio-resample')
            encoder = Gst.ElementFactory.make('opusenc', 'audio-encode')
            parser = Gst.ElementFactory.make('opusparse', 'audio-parse')
            
            elements = [queue, depay, decoder, convert, resample, encoder, parser]
            
        else:
            self.log(f"Unsupported audio codec: {encoding_name}", "error")
            return
            
        # Add elements to pipeline
        for element in elements:
            self.pipe.add(element)
            
        # Link elements together
        for i in range(len(elements) - 1):
            if not elements[i].link(elements[i + 1]):
                self.log(f"Failed to link {elements[i].get_name()} to {elements[i + 1].get_name()}", "error")
                return
                
        # Request audio pad from muxer
        mux_pad = self.muxer.request_pad_simple('audio_%u')
        if not mux_pad:
            self.log("Failed to get audio pad from muxer", "error")
            return
            
        # Link last element to muxer
        src_pad = elements[-1].get_static_pad('src')
        if src_pad.link(mux_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link audio to muxer", "error")
            return
            
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
            
        # Link WebRTC pad to queue
        sink_pad = queue.get_static_pad('sink')
        if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link audio pad to queue", "error")
            return
            
        self.audio_connected = True
        self.log("✅ Audio connected to muxer")
        
    def on_ice_connection_state_notify(self, element, pspec):
        """Monitor ICE connection state changes"""
        state = element.get_property('ice-connection-state')
        self.log(f"ICE connection state: {state.value_name}")
        
        # Log more details when connected
        if state == GstWebRTC.WebRTCICEConnectionState.CONNECTED:
            self.log("✅ ICE connected successfully!")
            # Request media when ICE is connected
            self.request_media()
        
    def on_ice_gathering_state_notify(self, element, pspec):
        """Monitor ICE gathering state changes"""
        state = element.get_property('ice-gathering-state')
        self.log(f"ICE gathering state: {state.value_name}")
        
    def on_ice_candidate(self, element, mline, candidate):
        """Handle local ICE candidate"""
        self.log(f"Generated ICE candidate for mlineindex {mline}")
        
        # Check if we have an open data channel to send through
        if hasattr(self, 'data_channel') and self.data_channel:
            try:
                state = self.data_channel.get_property('ready-state')
                if state == GstWebRTC.WebRTCDataChannelState.OPEN:
                    # Send through data channel
                    self.log("Sending ICE candidate through data channel")
                    ice_msg = {
                        "candidates": [{
                            "candidate": candidate,
                            "sdpMLineIndex": mline
                        }]
                    }
                    self.data_channel.send_string(json.dumps(ice_msg))
                    return
            except Exception as e:
                self.log(f"Error sending ICE via data channel: {e}", "error")
        
        # Fall back to sending via websocket (through parent process)
        ice_data = {
            'candidate': candidate,
            'sdpMLineIndex': mline
        }
        self.generated_ice_candidates.append(ice_data)
        self.send_message({
            "type": "ice_candidate",
            "data": ice_data
        })
        
    def add_ice_candidate(self, ice_data):
        """Add remote ICE candidate"""
        # Make sure pipeline is started
        if not self.pipeline_started or not self.webrtc:
            self.log("Pipeline not ready, queueing ICE candidate")
            self.ice_candidates.append(ice_data)
            return
            
        # Handle different formats
        if isinstance(ice_data, dict):
            candidate = ice_data.get('candidate')
            sdp_mline_index = ice_data.get('sdpMLineIndex', 0)
        else:
            candidate = ice_data
            sdp_mline_index = 0
            
        if candidate:
            self.webrtc.emit('add-ice-candidate', sdp_mline_index, candidate)
            self.log(f"Added ICE candidate for mline {sdp_mline_index}")
            
    def on_new_transceiver(self, element, transceiver):
        """Handle new transceiver creation"""
        self.log(f"New transceiver created")
        
        # Get transceiver details
        mline_index = transceiver.get_property('mlineindex')
        direction = transceiver.get_property('direction')
        kind = transceiver.get_property('kind') if hasattr(transceiver.props, 'kind') else 'unknown'
        
        self.log(f"   MLine Index: {mline_index}")
        self.log(f"   Kind: {kind}")
        self.log(f"   Current direction: {direction.value_nick if hasattr(direction, 'value_nick') else direction}")
        
        # For receiving, ensure transceiver direction is set correctly
        if self.mode == 'view' or self.mode == 'record':
            transceiver.set_property('direction', GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY)
            self.log(f"   Set transceiver direction to RECVONLY")
            
    def on_negotiation_needed(self, element):
        """Handle negotiation needed signal"""
        self.log("Negotiation needed signal received")
        
    def on_data_channel(self, element, channel):
        """Handle data channel creation"""
        self.log(f"Data channel created: {channel.get_property('label')}")
        self.data_channel = channel
        
        # Connect to state changes
        channel.connect('notify::ready-state', self.on_data_channel_state_change)
        
        # Connect to incoming messages
        channel.connect('on-message-string', self.on_data_channel_message)
        
        # Check if already open
        state = channel.get_property('ready-state')
        self.log(f"Data channel initial state: {state.value_name}")
        
        if state == GstWebRTC.WebRTCDataChannelState.OPEN:
            # Request media immediately
            GLib.timeout_add(100, self.request_media)
            
    def on_data_channel_state_change(self, channel, pspec):
        """Handle data channel state changes"""
        state = channel.get_property('ready-state')
        self.log(f"Data channel state changed: {state.value_name}")
        
        if state == GstWebRTC.WebRTCDataChannelState.OPEN:
            self.log("Data channel is now open")
            # Request media now that channel is open
            self.request_media()
            
    def on_data_channel_message(self, channel, msg):
        """Handle incoming data channel messages"""
        self.log(f"Data channel message received: {msg[:200]}..." if len(msg) > 200 else f"Data channel message received: {msg}")
        
        # Quick check if this might be a renegotiation offer
        if '"type":"offer"' in msg:
            self.log("DEBUG: Message contains offer type")
        
        try:
            self.log("DEBUG: Attempting to parse JSON")
            # Parse the message
            data = json.loads(msg)
            self.log("DEBUG: JSON parsed successfully")
            
            # Log what's in the data
            if 'description' in data:
                self.log(f"DEBUG: Found description field with type: {data.get('description', {}).get('type')}")
            
            # Check if it's an SDP offer
            if 'description' in data and data.get('description', {}).get('type') == 'offer':
                self.log("Received renegotiation offer via data channel")
                
                # Store the offer and handle it in the main thread
                sdp_text = data['description']['sdp']
                self.log(f"Scheduling renegotiation handling in main thread ({len(sdp_text)} chars)")
                
                # Use GLib.idle_add to handle in main thread context
                GLib.idle_add(self.handle_renegotiation_offer, sdp_text)
            elif 'candidates' in data:
                # Handle ICE candidates from data channel
                self.log(f"Received {len(data['candidates'])} ICE candidates via data channel")
                for candidate in data['candidates']:
                    if 'candidate' in candidate and 'sdpMLineIndex' in candidate:
                        self.webrtc.emit('add-ice-candidate', 
                                       candidate['sdpMLineIndex'], 
                                       candidate['candidate'])
                        
        except json.JSONDecodeError as e:
            # Not JSON, might be a different type of message
            self.log(f"JSONDecodeError in data channel message: {e}", "warning")
        except Exception as e:
            self.log(f"Error processing data channel message: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
        
    def request_media(self):
        """Request video and audio through data channel"""
        try:
            if not hasattr(self, 'data_channel'):
                self.log("No data channel available yet")
                return False
                
            data_channel = self.data_channel
            
            # Check if data channel is open
            state = data_channel.get_property('ready-state')
            if state != GstWebRTC.WebRTCDataChannelState.OPEN:
                self.log(f"Data channel not open yet, state: {state.value_name}")
                return False
                
            # Send request for video and audio
            self.log("Sending media request through data channel")
            request = {
                "video": True,
                "audio": True,
                "allowscreenvideo": True,
                "allowscreenaudio": True,
                "downloads": True,
                "iframe": True,
                "widget": True,
                "broadcast": False
            }
            
            request_json = json.dumps(request)
            data_channel.send_string(request_json)
            self.log(f"Media request sent: {request_json}")
            
        except Exception as e:
            self.log(f"Error requesting media: {e}", "error")
            
        return False  # Don't repeat
    
    def handle_renegotiation_offer(self, sdp_text):
        """Handle renegotiation offer in main thread context"""
        self.log("DEBUG: In handle_renegotiation_offer")
        
        # Check current state before handling
        if not self.webrtc:
            self.log("ERROR: webrtc element is None, cannot handle renegotiation", "error")
            return False
            
        try:
            current_state = self.webrtc.get_property('signaling-state')
            self.log(f"Current signaling state for renegotiation: {current_state.value_name}")
        except Exception as e:
            self.log(f"ERROR getting signaling state: {e}", "error")
            return False
        
        if current_state != GstWebRTC.WebRTCSignalingState.STABLE:
            self.log(f"WARNING: Not in stable state ({current_state.value_name}), deferring renegotiation")
            # Store the offer to handle later
            self.pending_renegotiation = sdp_text
            # Try again after a delay
            GLib.timeout_add(500, self.try_pending_renegotiation)
            return False
        
        self.log(f"Processing renegotiation offer ({len(sdp_text)} chars)")
        # Use the existing handle_offer method
        self.handle_offer(sdp_text)
        return False  # Remove from idle callbacks
    
    def try_pending_renegotiation(self):
        """Try to process pending renegotiation offer"""
        if not self.pending_renegotiation:
            return False  # Stop the timer
            
        current_state = self.webrtc.get_property('signaling-state')
        self.log(f"Trying pending renegotiation, current state: {current_state.value_name}")
        
        if current_state == GstWebRTC.WebRTCSignalingState.STABLE:
            self.log("Now in stable state, processing pending renegotiation")
            sdp_text = self.pending_renegotiation
            self.pending_renegotiation = None
            self.handle_offer(sdp_text)
            return False  # Stop the timer
        else:
            self.log("Still not in stable state, will retry")
            return True  # Continue the timer
        
    def handle_offer(self, sdp_text):
        """Handle SDP offer"""
        try:
            # Parse SDP
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                self.log(f"Failed to parse SDP: result={res}", "error")
                return
            
            # Log media sections in the offer
            num_media = sdp_msg.medias_len()
            self.log(f"Offer contains {num_media} media section(s):")
            has_video = False
            has_audio = False
            
            for i in range(num_media):
                media = sdp_msg.get_media(i)
                media_type = media.get_media()
                self.log(f"  Media {i}: {media_type}")
                if media_type == 'video':
                    has_video = True
                elif media_type == 'audio':
                    has_audio = True
                    
            if has_video or has_audio:
                self.log(f"Media offer received! Video: {has_video}, Audio: {has_audio}")
            else:
                self.log("Data-channel-only offer (no media yet)")
            
            # Create offer
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # Check current signaling state
            current_state = self.webrtc.get_property('signaling-state')
            self.log(f"Current signaling state before setting offer: {current_state.value_name}")
            
            # Set remote description with promise
            self.log("Setting remote description...")
            promise = Gst.Promise.new_with_change_func(
                self.on_offer_set, self.webrtc, None
            )
            self.webrtc.emit('set-remote-description', offer, promise)
            
        except Exception as e:
            self.log(f"Error handling offer: {e}", "error")
    
    def on_offer_set(self, promise, _, user_data):
        """Called when remote description is set"""
        try:
            self.log("Remote description set, creating answer...")
            promise.wait()
            
            # Create answer
            promise = Gst.Promise.new_with_change_func(
                self.on_answer_created, self.webrtc, None
            )
            self.webrtc.emit('create-answer', None, promise)
            
        except Exception as e:
            self.log(f"Error in on_offer_set: {e}", "error")
    
    def on_answer_created(self, promise, _, user_data):
        """Called when answer is created"""
        try:
            self.log("Answer created callback")
            promise.wait()
            reply = promise.get_reply()
            
            if not reply:
                self.log("No reply from create-answer", "error")
                return
                
            answer = reply.get_value('answer')
            if not answer:
                self.log("No answer in reply", "error")
                return
                
            # Set local description
            self.log("Setting local description...")
            promise = Gst.Promise.new()
            self.webrtc.emit('set-local-description', answer, promise)
            promise.interrupt()
            
            # Send answer
            text = answer.sdp.as_text()
            self.log(f"Sending answer (length: {len(text)} chars)")
            
            # Check if we have an open data channel to send through
            if hasattr(self, 'data_channel') and self.data_channel:
                try:
                    state = self.data_channel.get_property('ready-state')
                    if state == GstWebRTC.WebRTCDataChannelState.OPEN:
                        # Send through data channel
                        self.log("Sending answer through data channel")
                        answer_msg = {
                            "description": {
                                "type": "answer",
                                "sdp": text
                            }
                        }
                        if self.session_id:
                            answer_msg["session"] = self.session_id
                        self.data_channel.send_string(json.dumps(answer_msg))
                        # Don't send via websocket
                        return
                except Exception as e:
                    self.log(f"Error sending via data channel: {e}", "error")
            
            # Fall back to sending via websocket (through parent process)
            self.send_message({
                "type": "sdp",
                "sdp_type": "answer",
                "sdp": text,
                "session_id": self.session_id
            })
            
            # Process queued ICE candidates
            if self.ice_candidates:
                self.log(f"Processing {len(self.ice_candidates)} queued ICE candidates")
                while self.ice_candidates:
                    ice_data = self.ice_candidates.pop(0)
                    self.add_ice_candidate(ice_data)
                    
        except Exception as e:
            self.log(f"Error in on_answer_created: {e}", "error")
    
    def handle_remote_offer(self, offer_data):
        """Handle offer from remote peer"""
        try:
            self.log(f"Processing remote offer")
            
            # Extract SDP text
            offer_sdp = offer_data['sdp']
            
            # Use the new handle_offer method
            self.handle_offer(offer_sdp)
            
        except Exception as e:
            self.log(f"Error handling remote offer: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            
    def shutdown(self):
        """Shutdown the handler"""
        self.log("Shutting down...")
        
        # Log recording status
        if self.output_filename and os.path.exists(self.output_filename):
            size = os.path.getsize(self.output_filename)
            size_mb = size / (1024 * 1024)
            
            streams = []
            if self.video_connected:
                streams.append("video")
            if self.audio_connected:
                streams.append("audio")
            stream_info = "+".join(streams) if streams else "no streams"
            
            self.log(f"🛑 RECORDING STOPPED: {self.stream_id}")
            self.log(f"   Final file: {self.output_filename} ({size_mb:.2f} MB)")
            self.log(f"   Streams: {stream_info}")
        
        self.running = False
        
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            
        self.main_loop.quit()
        
    def run(self):
        """Run the main loop"""
        self.log("Starting GLib main loop...")
        self.main_loop.run()
        self.log("Main loop exited")


def main():
    """Main entry point"""
    try:
        # Read configuration from first line
        config_line = sys.stdin.readline()
        if not config_line:
            sys.stderr.write("No configuration received\n")
            return
            
        config = json.loads(config_line.strip())
        
        # Create handler
        handler = MKVWebRTCHandler(config)
        
        # Send ready signal after a small delay to ensure main loop is running
        GLib.timeout_add(100, lambda: handler.send_message({"type": "ready"}) or False)
        
        # Run main loop
        handler.run()
        
    except Exception as e:
        sys.stderr.write(f"Subprocess error: {e}\n")
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
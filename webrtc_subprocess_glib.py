#!/usr/bin/env python3
"""
WebRTC Subprocess Handler using GLib Main Loop
This runs as a subprocess and handles the GStreamer/WebRTC pipeline.
It communicates with the parent process via stdin/stdout using JSON messages.
"""

import sys
import json
import gi
import time
import threading
from typing import Optional, Dict, Any

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp


# Initialize GStreamer
Gst.init(None)


class GLibWebRTCHandler:
    """Handles WebRTC pipeline in a subprocess using GLib main loop"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.stream_id = config.get('stream_id')
        self.mode = config.get('mode', 'view')
        self.room = config.get('room')
        self.record_file = config.get('record_file')
        self.record_audio = config.get('record_audio', False)
        self.room_ndi = config.get('room_ndi', False)
        self.ndi_name = config.get('ndi_name')
        
        # Debug log the config
        self.log(f"DEBUG: Config received: record_audio={config.get('record_audio', 'NOT SET')}, room_ndi={config.get('room_ndi', False)}")
        
        self.pipe = None
        self.webrtc = None
        self.session_id = None
        
        # IPC communication
        self.running = True
        
        # ICE candidates queue
        self.ice_candidates = []
        self.generated_ice_candidates = []
        self.pipeline_start_time = None
        self.pending_renegotiation = None
        
        # Recording state
        self.recording_video = False
        self.recording_audio = False
        self.video_filename = None
        self.audio_filename = None
        
        
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
        """Log message with level"""
        log_entry = {
            "type": "log",
            "level": level,
            "message": f"[{self.stream_id}] {message}"
        }
        sys.stdout.write(json.dumps(log_entry) + '\n')
        sys.stdout.flush()
        
    def send_message(self, msg: Dict[str, Any]):
        """Send message to parent process"""
        sys.stdout.write(json.dumps(msg) + '\n')
        sys.stdout.flush()
        
    def handle_message(self, msg: Dict[str, Any]):
        """Handle message from parent process"""
        msg_type = msg.get('type')
        
        if msg_type == 'sdp':
            self.handle_sdp(msg)
        elif msg_type == 'ice':
            self.handle_ice(msg)
        elif msg_type == 'stop':
            self.shutdown()
        elif msg_type == 'session':
            self.session_id = msg.get('session_id')
            self.log(f"Session ID set: {self.session_id}")
        else:
            self.log(f"Unknown message type: {msg_type}", "warning")
            
    def handle_sdp(self, msg: Dict[str, Any]):
        """Handle SDP message"""
        sdp_type = msg.get('sdp_type')
        sdp_text = msg.get('sdp', '')
        session_id = msg.get('session_id')
        
        self.log(f"Received SDP {sdp_type} (length: {len(sdp_text)} chars, session: {session_id})")
        
        # Store session ID if provided
        if session_id:
            self.session_id = session_id
            self.log(f"Updated session ID from SDP message: {self.session_id}")
        
        if not self.pipe:
            self.log("Pipeline not created yet, creating now...")
            self.create_pipeline()
            
        if sdp_type == 'offer':
            self.handle_offer(sdp_text)
        else:
            self.log(f"Unexpected SDP type: {sdp_type}", "warning")
            
    def handle_offer(self, sdp_text: str):
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
                    mlineindex, candidate = self.ice_candidates.pop(0)
                    self.webrtc.emit('add-ice-candidate', mlineindex, candidate)
                    
        except Exception as e:
            self.log(f"Error in on_answer_created: {e}", "error")
            
    def handle_ice(self, msg: Dict[str, Any]):
        """Handle ICE candidate"""
        candidate = msg.get('candidate', '')
        sdpMLineIndex = msg.get('sdpMLineIndex', 0)
        
        if self.webrtc:
            # Add immediately if we can
            state = self.webrtc.get_property('signaling-state')
            if state != GstWebRTC.WebRTCSignalingState.STABLE:
                self.webrtc.emit('add-ice-candidate', sdpMLineIndex, candidate)
                self.log("Added ICE candidate")
            else:
                # Queue for later
                self.ice_candidates.append((sdpMLineIndex, candidate))
                self.log("Queued ICE candidate")
        else:
            # Queue for later
            self.ice_candidates.append((sdpMLineIndex, candidate))
            self.log("Queued ICE candidate (no webrtc yet)")
            
    def create_pipeline(self):
        """Create GStreamer pipeline"""
        self.log("Creating pipeline...")
        
        # Create pipeline
        self.pipe = Gst.Pipeline.new(f"webrtc-pipe-{self.stream_id}")
        
        # Create webrtcbin
        self.webrtc = Gst.ElementFactory.make('webrtcbin', 'webrtc')
        self.webrtc.set_property('bundle-policy', 'max-bundle')
        
        # Important: Set the transceiver direction properly for receiving
        self.webrtc.connect('on-new-transceiver', self.on_new_transceiver)
        
        # Connect signals
        self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)
        self.webrtc.connect('pad-added', self.on_pad_added)
        self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtc.connect('notify::connection-state', self.on_connection_state_notify)
        self.webrtc.connect('notify::ice-connection-state', self.on_ice_connection_state_notify)
        self.webrtc.connect('notify::ice-gathering-state', self.on_ice_gathering_state_notify)
        self.webrtc.connect('on-data-channel', self.on_data_channel)
        
        # Add to pipeline
        self.pipe.add(self.webrtc)
        
        # Configure STUN/TURN
        if 'stun_server' in self.config:
            self.webrtc.set_property('stun-server', self.config['stun_server'])
            self.log(f"STUN server: {self.config['stun_server']}")
            
        if 'turn_server' in self.config:
            self.webrtc.set_property('turn-server', self.config['turn_server'])
            self.log(f"TURN server configured")
            
        # Start pipeline
        self.pipe.set_state(Gst.State.PLAYING)
        self.log("Pipeline started")
        
    def on_ice_candidate(self, element, mlineindex, candidate):
        """Handle generated ICE candidate"""
        self.log(f"Generated ICE candidate for mlineindex {mlineindex}")
        
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
                            "sdpMLineIndex": mlineindex
                        }]
                    }
                    self.data_channel.send_string(json.dumps(ice_msg))
                    return
            except Exception as e:
                self.log(f"Error sending ICE via data channel: {e}", "error")
        
        # Fall back to sending via websocket (through parent process)
        self.send_message({
            "type": "ice",
            "candidate": candidate,
            "sdpMLineIndex": mlineindex,
            "session_id": self.session_id
        })
        
    def request_media(self):
        """Request video and audio through data channel"""
        try:
            # Get the data channel - it might be created by remote peer
            data_channel = None
            
            # Check for incoming data channels
            # In GStreamer, incoming data channels are handled differently
            # We need to connect to the on-data-channel signal
            if not hasattr(self, 'data_channel'):
                self.log("No data channel available yet")
                return
                
            data_channel = self.data_channel
            
            # Check if data channel is open
            state = data_channel.get_property('ready-state')
            if state != GstWebRTC.WebRTCDataChannelState.OPEN:
                self.log(f"Data channel not open yet, state: {state.value_name}")
                return
                
            # Send request for video and audio
            self.log("Sending media request through data channel")
            # Create the request message similar to VDO.Ninja
            request = {
                "video": True,
                "audio": True,
                "allowscreenvideo": True,
                "allowscreenaudio": True,
                "downloads": True,
                "iframe": True,
                "widget": True,
                "broadcast": False,
                "allowmidi": False,
                "allowdrawing": False,
                "allowwebp": False,
                "allowchunked": False,
                "allowresources": False
            }
            
            request_json = json.dumps(request)
            data_channel.send_string(request_json)
            self.log(f"Media request sent: {request_json}")
            
        except Exception as e:
            self.log(f"Error requesting media: {e}", "error")
            
    def on_data_channel(self, element, channel):
        """Handle incoming data channel"""
        self.log("Data channel created")
        self.data_channel = channel
        
        # Connect to state changes
        channel.connect('notify::ready-state', self.on_data_channel_state_change)
        
        # Connect to incoming messages
        channel.connect('on-message-string', self.on_data_channel_message)
        channel.connect('on-message-data', self.on_data_channel_message_data)
        
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
        """Handle incoming data channel text messages"""
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
                desc = data['description']
                if isinstance(desc, dict):
                    self.log(f"DEBUG: Found description object with type: {desc.get('type')}")
                else:
                    self.log(f"DEBUG: Found encrypted description string (length: {len(str(desc))})")
            
            # Check if it's an SDP offer
            if 'description' in data:
                desc = data['description']
                if isinstance(desc, dict) and desc.get('type') == 'offer':
                    self.log("Received renegotiation offer via data channel")
                    
                    # Store the offer and handle it in the main thread
                    sdp_text = desc['sdp']
                    self.log(f"Scheduling renegotiation handling in main thread ({len(sdp_text)} chars)")
                    
                    # Use GLib.idle_add to handle in main thread context
                    GLib.idle_add(self.handle_renegotiation_offer, sdp_text)
                elif isinstance(desc, str):
                    # This is an encrypted offer - we can't handle renegotiation with encryption
                    self.log("WARNING: Received encrypted SDP via data channel - renegotiation not supported with passwords enabled")
            elif 'candidates' in data:
                # Handle ICE candidates from data channel
                candidates = data['candidates']
                if isinstance(candidates, list):
                    self.log(f"Received {len(candidates)} ICE candidates via data channel")
                    for candidate in candidates:
                        if isinstance(candidate, dict) and 'candidate' in candidate and 'sdpMLineIndex' in candidate:
                            self.webrtc.emit('add-ice-candidate', 
                                           candidate['sdpMLineIndex'], 
                                           candidate['candidate'])
                elif isinstance(candidates, str):
                    # Encrypted candidates - can't process them
                    self.log(f"Received encrypted ICE candidates via data channel (length: {len(candidates)})")
                        
        except json.JSONDecodeError as e:
            # Not JSON, might be a different type of message
            self.log(f"JSONDecodeError in data channel message: {e}", "warning")
        except Exception as e:
            self.log(f"Error processing data channel message: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
        
    def on_data_channel_message_data(self, channel, data):
        """Handle incoming data channel binary messages"""
        self.log(f"Data channel binary message received: {len(data)} bytes")
        
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
            
    def on_pad_added(self, element, pad):
        """Handle new pad from webrtcbin"""
        pad_name = pad.get_name()
        self.log(f"New pad added: {pad_name}")
        self.log(f"DEBUG: on_pad_added called for element {element.get_name()}")
        
        # Get pad caps to determine media type
        caps = pad.get_current_caps()
        if not caps:
            caps = pad.query_caps(None)
            
        if caps and caps.get_size() > 0:
            structure = caps.get_structure(0)
            media_type = structure.get_name()
            caps_string = caps.to_string()
            self.log(f"Pad media type: {media_type}")
            self.log(f"Full caps: {caps_string}")
            
            # For RTP streams, we need to check the encoding-name to determine media type
            if media_type == 'application/x-rtp':
                encoding_name = structure.get_string('encoding-name')
                media = structure.get_string('media')
                self.log(f"RTP stream - encoding: {encoding_name}, media: {media}")
                
                if media == 'video' or (encoding_name and encoding_name.upper() in ['H264', 'VP8', 'VP9', 'AV1']):
                    self.handle_video_pad(pad)
                elif media == 'audio' or (encoding_name and encoding_name.upper() in ['OPUS', 'PCMU', 'PCMA']):
                    self.handle_audio_pad(pad)
                else:
                    self.log(f"Unknown RTP media type: media={media}, encoding={encoding_name}")
            elif 'video' in media_type:
                self.handle_video_pad(pad)
            elif 'audio' in media_type:
                self.handle_audio_pad(pad)
            elif 'application' in media_type:
                self.log("Data channel pad detected")
                # Data channel pad - don't need to connect it
            else:
                self.log(f"Unknown media type: {media_type}")
        else:
            self.log("Could not determine pad type")
            
    def handle_video_pad(self, pad):
        """Handle video pad - set up recording"""
        # Get codec info from caps
        caps = pad.get_current_caps()
        structure = caps.get_structure(0)
        encoding_name = structure.get_string('encoding-name')
        width = structure.get_int('width')[1] if structure.has_field('width') else 'unknown'
        height = structure.get_int('height')[1] if structure.has_field('height') else 'unknown'
        
        if self.room_ndi:
            self.log(f"📹 NDI OUTPUT START: Video stream from {self.stream_id}")
        else:
            self.log(f"📹 RECORDING START: Video stream from {self.stream_id}")
        self.log(f"   Codec: {encoding_name}, Resolution: {width}x{height}")
        
        # Create queue for buffering
        queue = Gst.ElementFactory.make('queue', None)
        
        # First, we need to depayload the RTP stream
        if encoding_name == 'VP8':
            depay = Gst.ElementFactory.make('rtpvp8depay', None)
            if self.room_ndi:
                # For NDI, we need to decode VP8
                decoder = Gst.ElementFactory.make('vp8dec', None)
            else:
                # Use WebM but with better settings for live streams
                mux = Gst.ElementFactory.make('webmmux', None)
                # Set properties for better live streaming
                mux.set_property('streamable', True)
                mux.set_property('min-index-interval', 1000000000)  # 1 second
                extension = 'webm'
        elif encoding_name == 'H264':
            depay = Gst.ElementFactory.make('rtph264depay', None)
            # Parse H264 stream
            h264parse = Gst.ElementFactory.make('h264parse', None)
            if self.room_ndi:
                # For NDI, we need to decode H264
                decoder = Gst.ElementFactory.make('avdec_h264', None)
            else:
                # For H264, we can use MP4
                mux = Gst.ElementFactory.make('mp4mux', None)
                extension = 'mp4'
        else:
            self.log(f"Unsupported video codec: {encoding_name}", "error")
            return
        
        if self.room_ndi:
            # Create NDI sink
            videoconvert = Gst.ElementFactory.make('videoconvert', None)
            ndisink = Gst.ElementFactory.make('ndisink', None)
            
            if not all([queue, depay, decoder, videoconvert, ndisink]):
                self.log("Failed to create NDI elements", "error")
                return
                
            # Set NDI properties
            ndisink.set_property('ndi-name', self.ndi_name or f"{self.stream_id}_video")
            self.log(f"   NDI stream name: {self.ndi_name or f'{self.stream_id}_video'}")
            
        else:
            # Recording mode
            filesink = Gst.ElementFactory.make('filesink', None)
            
            if not all([queue, depay, mux, filesink]):
                self.log("Failed to create recording elements", "error")
                return
        
        if self.room_ndi:
            # Add NDI elements to pipeline
            if encoding_name == 'VP8':
                elements = [queue, depay, decoder, videoconvert, ndisink]
            else:  # H264
                elements = [queue, depay, h264parse, decoder, videoconvert, ndisink]
                
            for element in elements:
                self.pipe.add(element)
                
            # Link NDI pipeline
            if encoding_name == 'VP8':
                # VP8: queue -> depay -> vp8dec -> videoconvert -> ndisink
                if not queue.link(depay):
                    self.log("Failed to link queue to depay", "error")
                    return
                if not depay.link(decoder):
                    self.log("Failed to link depay to decoder", "error")
                    return
                if not decoder.link(videoconvert):
                    self.log("Failed to link decoder to videoconvert", "error")
                    return
                if not videoconvert.link(ndisink):
                    self.log("Failed to link videoconvert to ndisink", "error")
                    return
            else:  # H264
                # H264: queue -> depay -> h264parse -> avdec_h264 -> videoconvert -> ndisink
                if not queue.link(depay):
                    self.log("Failed to link queue to depay", "error")
                    return
                if not depay.link(h264parse):
                    self.log("Failed to link depay to h264parse", "error")
                    return
                if not h264parse.link(decoder):
                    self.log("Failed to link h264parse to decoder", "error")
                    return
                if not decoder.link(videoconvert):
                    self.log("Failed to link decoder to videoconvert", "error")
                    return
                if not videoconvert.link(ndisink):
                    self.log("Failed to link videoconvert to ndisink", "error")
                    return
        else:
            # Recording mode
            # Set output filename
            if self.record_file:
                filename = self.record_file
            else:
                import datetime
                timestamp = int(datetime.datetime.now().timestamp())
                filename = f"{self.room}_{self.stream_id}_{timestamp}.{extension}"
                
            filesink.set_property('location', filename)
            self.log(f"   Output file: {filename}")
            
            # Add to pipeline
            elements = [queue, depay, mux, filesink]
            if encoding_name == 'H264' and 'h264parse' in locals():
                elements.insert(2, h264parse)
                
            for element in elements:
                self.pipe.add(element)
            
            # Muxer is already configured above
                
            # Link elements based on codec
            if encoding_name == 'VP8':
                # VP8: queue -> depay -> webmmux -> filesink
                if not queue.link(depay):
                    self.log("Failed to link queue to depay", "error")
                    return
                if not depay.link(mux):
                    self.log("Failed to link depay to mux", "error")
                    return
            else:  # H264
                # H264: queue -> depay -> h264parse -> mp4mux -> filesink
                if not queue.link(depay):
                    self.log("Failed to link queue to depay", "error")
                    return
                if not depay.link(h264parse):
                    self.log("Failed to link depay to h264parse", "error")
                    return
                if not h264parse.link(mux):
                    self.log("Failed to link h264parse to mux", "error")
                    return
                    
            if not mux.link(filesink):
                self.log("Failed to link mux to filesink", "error")
                return
        
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
        
        # Link pad to queue
        sink_pad = queue.get_static_pad('sink')
        if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link video pad to queue", "error")
            return
        
        # Add probe to monitor data flow
        pad.add_probe(Gst.PadProbeType.BUFFER, self.on_pad_probe, None)
        
        if self.room_ndi:
            self.log("   ✅ NDI video output pipeline connected and running")
        else:
            self.log("   ✅ Video recording pipeline connected and running")
            # Store recording info only for file recording
            self.recording_video = True
            self.video_filename = filename
        
    def on_pad_probe(self, pad, info, user_data):
        """Monitor data flow through pad"""
        if not hasattr(self, '_probe_counter'):
            self._probe_counter = 0
            self._last_probe_log = 0
            
        self._probe_counter += 1
        
        # Log every 100 buffers
        if self._probe_counter - self._last_probe_log >= 100:
            self.log(f"   📊 Video data flowing: {self._probe_counter} buffers processed")
            self._last_probe_log = self._probe_counter
            
        return Gst.PadProbeReturn.OK
        
    def handle_audio_pad(self, pad):
        """Handle audio pad"""
        # Get codec info from caps
        caps = pad.get_current_caps()
        structure = caps.get_structure(0)
        encoding_name = structure.get_string('encoding-name')
        clock_rate = structure.get_int('clock-rate')[1] if structure.has_field('clock-rate') else 'unknown'
        
        self.log(f"🎤 AUDIO STREAM DETECTED: {self.stream_id}")
        self.log(f"   Codec: {encoding_name}, Sample rate: {clock_rate} Hz")
        
        if self.room_ndi:
            self.log(f"   ℹ️  Audio handled separately in NDI mode")
            # Just fakesink audio in NDI mode as video NDI sink will handle audio/video
            fakesink = Gst.ElementFactory.make('fakesink', None)
            self.pipe.add(fakesink)
            fakesink.sync_state_with_parent()
            pad.link(fakesink.get_static_pad('sink'))
            return
        
        if not self.record_audio:
            self.log(f"   ⏸️  Audio recording disabled (use --audio flag to enable)")
            # Just fakesink audio
            fakesink = Gst.ElementFactory.make('fakesink', None)
            self.pipe.add(fakesink)
            fakesink.sync_state_with_parent()
            pad.link(fakesink.get_static_pad('sink'))
            return
            
            
        # Record audio
        self.log(f"🔴 RECORDING START: Audio stream from {self.stream_id}")
        
        # Create queue for buffering
        queue = Gst.ElementFactory.make('queue', None)
        # Set larger buffer for audio to handle async arrival
        queue.set_property('max-size-time', 10000000000)  # 10 seconds
        queue.set_property('max-size-buffers', 0)
        queue.set_property('max-size-bytes', 0)
        
        # For now, just record audio alongside video in separate files
        self.log("   ℹ️  Audio recording is currently saved separately from video")
        
        # Check if already recording audio
        if hasattr(self, 'audio_filename') and self.audio_filename:
            # Already recording audio, skip
            self.log("   ⚠️  Already recording audio, skipping duplicate pad")
            fakesink = Gst.ElementFactory.make('fakesink', None)
            self.pipe.add(fakesink)
            fakesink.sync_state_with_parent()
            pad.link(fakesink.get_static_pad('sink'))
            return
        
        # Create depayloader based on codec
        if encoding_name == 'OPUS':
            depay = Gst.ElementFactory.make('rtpopusdepay', None)
            # For audio, decode to raw and save as WAV for maximum compatibility
            decoder = Gst.ElementFactory.make('opusdec', None)
            audioconvert = Gst.ElementFactory.make('audioconvert', None)
            wavenc = Gst.ElementFactory.make('wavenc', None)
            extension = 'wav'
        else:
            self.log(f"   ⚠️  Unsupported audio codec: {encoding_name}, using fakesink")
            fakesink = Gst.ElementFactory.make('fakesink', None)
            self.pipe.add(fakesink)
            fakesink.sync_state_with_parent()
            pad.link(fakesink.get_static_pad('sink'))
            return
        
        # Create filesink
        filesink = Gst.ElementFactory.make('filesink', None)
        
        if not all([queue, depay, decoder, audioconvert, wavenc, filesink]):
            self.log("Failed to create audio elements", "error")
            return
            
        import datetime
        timestamp = int(datetime.datetime.now().timestamp())
        filename = f"{self.room}_{self.stream_id}_{timestamp}_audio.{extension}"
        filesink.set_property('location', filename)
        self.audio_filename = filename
        self.log(f"   Output file: {filename}")
        
        # Add elements to pipeline
        elements = [queue, depay, decoder, audioconvert, wavenc, filesink]
        for element in elements:
            self.pipe.add(element)
            
        # Link elements
        if not queue.link(depay):
            self.log("Failed to link queue to depay", "error")
            return
        if not depay.link(decoder):
            self.log("Failed to link depay to decoder", "error")
            return
        if not decoder.link(audioconvert):
            self.log("Failed to link decoder to audioconvert", "error")
            return
        if not audioconvert.link(wavenc):
            self.log("Failed to link audioconvert to wavenc", "error")
            return
        if not wavenc.link(filesink):
            self.log("Failed to link wavenc to filesink", "error")
            return
            
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
            
        # Link pad to queue
        sink_pad = queue.get_static_pad('sink')
        if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link audio pad to queue", "error")
            return
            
        # Add probe to monitor audio data flow
        self._audio_probe_counter = 0
        def audio_probe_cb(pad, info):
            self._audio_probe_counter += 1
            if self._audio_probe_counter % 100 == 0:
                self.log(f"   📊 Audio data flowing: {self._audio_probe_counter} buffers")
            return Gst.PadProbeReturn.OK
            
        pad.add_probe(Gst.PadProbeType.BUFFER, audio_probe_cb)
        
        self.log("   ✅ Audio recording pipeline connected and running")
        
        # Store recording info
        self.recording_audio = True
        self.audio_filename = filename
        
    def on_new_transceiver(self, element, transceiver):
        """Handle new transceiver creation"""
        self.log(f"New transceiver created: {transceiver}")
        
        # For receiving, ensure transceiver direction is set correctly
        if self.mode == 'view' or self.mode == 'record':
            transceiver.set_property('direction', GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY)
            self.log(f"Set transceiver direction to RECVONLY")
        
    def on_negotiation_needed(self, element):
        """Handle negotiation needed signal"""
        self.log("Negotiation needed signal received")
        # In viewer mode, we don't initiate offers
        
    def on_connection_state_notify(self, element, pspec):
        """Monitor connection state changes"""
        state = element.get_property('connection-state')
        self.log(f"WebRTC connection state: {state.value_name}")
        
    def on_ice_connection_state_notify(self, element, pspec):
        """Monitor ICE connection state changes"""
        state = element.get_property('ice-connection-state')
        self.log(f"ICE connection state: {state.value_name}")
        
        if state == GstWebRTC.WebRTCICEConnectionState.CONNECTED:
            self.log("ICE connection established successfully")
            # Request video/audio through data channel
            self.request_media()
            
            # Debug: Check if we have any sink pads
            self.log("DEBUG: Checking webrtcbin pads after ICE connected")
            try:
                # Check for src pads (incoming media)
                src_pads = []
                pad_iter = self.webrtc.iterate_src_pads()
                while True:
                    result, pad = pad_iter.next()
                    if result != Gst.IteratorResult.OK:
                        break
                    if pad:
                        src_pads.append(pad)
                
                self.log(f"  Found {len(src_pads)} src pads")
                for pad in src_pads:
                    self.log(f"  Src pad: {pad.get_name()}")
                    
                # Also check static pads
                for i in range(10):  # Check first 10 possible pad indices
                    pad = self.webrtc.get_static_pad(f"src_{i}")
                    if pad:
                        self.log(f"  Found static pad: src_{i}")
            except Exception as e:
                self.log(f"ERROR checking pads: {e}", "error")
        
    def on_ice_gathering_state_notify(self, element, pspec):
        """Monitor ICE gathering state changes"""
        state = element.get_property('ice-gathering-state')
        self.log(f"ICE gathering state: {state.value_name}")
        
    def shutdown(self):
        """Shutdown the handler"""
        self.log("Shutting down...")
        
        # Log recording status
        if hasattr(self, 'recording_video') and self.recording_video:
            self.log(f"🛑 RECORDING STOPPED: {self.stream_id}")
            if hasattr(self, 'video_filename') and self.video_filename:
                import os
                if os.path.exists(self.video_filename):
                    size = os.path.getsize(self.video_filename)
                    size_mb = size / (1024 * 1024)
                    self.log(f"   Final file: {self.video_filename} ({size_mb:.2f} MB)")
                else:
                    self.log(f"   Warning: Output file not found")
        
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
        handler = GLibWebRTCHandler(config)
        
        # Send ready signal
        handler.send_message({"type": "ready"})
        
        # Run main loop
        handler.run()
        
    except Exception as e:
        sys.stderr.write(f"Subprocess error: {e}\n")
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
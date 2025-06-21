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
        self.use_hls = config.get('use_hls', False)
        self.use_splitmuxsink = config.get('use_splitmuxsink', True)  # Use splitmuxsink for now
        
        # Debug log the config
        self.log(f"DEBUG: Config received: record_audio={config.get('record_audio', 'NOT SET')}, room_ndi={config.get('room_ndi', False)}, use_hls={config.get('use_hls', False)}")
        
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
        
        # NDI state
        self.ndi_combiner = None
        self.ndi_sink = None
        
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
            
    def prefer_codec(self, sdp: str, codec: str = 'h264') -> str:
        """Reorder codecs in SDP to prefer a specific codec"""
        if self.use_hls and codec == 'h264':
            self.log("Reordering SDP to prefer H264 codec")
        
        lines = sdp.split('\n')
        video_line_index = -1
        video_codecs = []
        codec_map = {}
        
        # First pass: find codec numbers
        for i, line in enumerate(lines):
            if line.startswith('m=video'):
                video_line_index = i
                # Extract codec numbers from m=video line
                parts = line.split('SAVPF')
                if len(parts) > 1:
                    video_codecs = parts[1].strip().split(' ')
            elif line.startswith('a=rtpmap:'):
                # Extract codec mappings
                codec_info = line[9:].split(' ')  # Remove 'a=rtpmap:'
                if len(codec_info) >= 2:
                    codec_num = codec_info[0]
                    codec_details = codec_info[1].upper()
                    
                    if 'VP8/90000' in codec_details:
                        codec_map['vp8'] = codec_num
                    elif 'VP9/90000' in codec_details:
                        codec_map['vp9'] = codec_num
                    elif 'H264/90000' in codec_details:
                        codec_map['h264'] = codec_num
                    elif 'AV1/90000' in codec_details or 'AV1X/90000' in codec_details:
                        codec_map['av1'] = codec_num
        
        # If we found the video line and the preferred codec
        if video_line_index >= 0 and codec.lower() in codec_map and video_codecs:
            preferred_codec_num = codec_map[codec.lower()]
            
            # Only reorder if the preferred codec exists and isn't already first
            if preferred_codec_num in video_codecs and video_codecs[0] != preferred_codec_num:
                self.log(f"   Moving {codec.upper()} (payload {preferred_codec_num}) to front of codec list")
                
                # Create new codec order with preferred codec first
                new_order = [preferred_codec_num]
                for c in video_codecs:
                    if c != preferred_codec_num:
                        new_order.append(c)
                
                # Reconstruct the m=video line
                parts = lines[video_line_index].split('SAVPF')
                lines[video_line_index] = parts[0] + 'SAVPF ' + ' '.join(new_order)
                
                self.log(f"   Original codec order: {' '.join(video_codecs)}")
                self.log(f"   New codec order: {' '.join(new_order)}")
        
        return '\n'.join(lines)
    
    def create_hls_playlist(self):
        """Create or update HLS m3u8 playlist file"""
        try:
            # Check how many segments exist
            import glob
            import os
            pattern = f"{self.base_filename}_*.ts"
            segments = sorted(glob.glob(pattern))
            
            playlist_content = "#EXTM3U\n"
            playlist_content += "#EXT-X-VERSION:3\n"
            playlist_content += "#EXT-X-TARGETDURATION:6\n"  # Slightly higher than segment duration
            playlist_content += "#EXT-X-MEDIA-SEQUENCE:0\n\n"
            
            # Add all existing segments
            for segment in segments:
                segment_name = os.path.basename(segment)
                # Assume 5 second duration for now
                playlist_content += f"#EXTINF:5.0,\n{segment_name}\n"
            
            # Write playlist
            with open(self.hls_playlist_path, 'w') as f:
                f.write(playlist_content)
                
        except Exception as e:
            self.log(f"Error creating HLS playlist: {e}", "error")
    
    def update_hls_playlist(self):
        """Update HLS playlist with new segments"""
        if hasattr(self, 'hls_playlist_path'):
            self.create_hls_playlist()
    
    def update_hls_playlist_timer(self):
        """Timer callback to update HLS playlist"""
        self.update_hls_playlist()
        return True  # Continue timer
    
    def handle_offer(self, sdp_text: str):
        """Handle SDP offer"""
        try:
            # If HLS mode, prefer H264 codec in SDP
            if self.use_hls:
                sdp_text = self.prefer_codec(sdp_text, 'h264')
            
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
        
        # If HLS mode is enabled, request H264 codec via transceiver
        if self.use_hls:
            self.log("HLS mode: Adding transceivers for H264 video preference")
            direction = GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY
            
            # Add video transceiver with H264 preference
            h264_caps = Gst.caps_from_string("application/x-rtp,media=video,encoding-name=H264,payload=102,clock-rate=90000,packetization-mode=(string)1")
            video_tcvr = self.webrtc.emit('add-transceiver', direction, h264_caps)
            if video_tcvr:
                # Set codec preferences if GStreamer version supports it
                try:
                    if Gst.version().minor > 18:
                        video_tcvr.set_property("codec-preferences", h264_caps)
                        self.log("   ✅ Set H264 codec preferences on video transceiver")
                except Exception as e:
                    self.log(f"   Could not set codec preferences: {e}")
            else:
                self.log("   Warning: Failed to add H264 transceiver")
                
            # Add audio transceiver as well
            audio_caps = Gst.caps_from_string("application/x-rtp,media=audio,encoding-name=OPUS,payload=111,clock-rate=48000")
            audio_tcvr = self.webrtc.emit('add-transceiver', direction, audio_caps)
            if audio_tcvr:
                self.log("   ✅ Added audio transceiver")
        
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
            
            # If HLS mode is enabled, request H264 codec in the media request
            if self.use_hls:
                # VDO.Ninja codec parameters - both for compatibility
                request["h264"] = True  # Primary H264 flag
                request["codec"] = "h264"  # Alternative codec specification
                self.log("   Requesting H264 codec in media request for HLS")
            
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
    
    def setup_hls_muxer(self):
        """Set up shared mpegtsmux and HLS sink for audio/video"""
        if hasattr(self, 'hls_mux'):
            # Already set up
            return
            
        self.log("Setting up HLS muxer for audio/video")
        
        # Initialize use_hlssink2 based on use_splitmuxsink setting
        self.use_hlssink2 = not self.use_splitmuxsink
        self.log(f"   use_splitmuxsink={self.use_splitmuxsink}, use_hlssink2={self.use_hlssink2}")
            
        # Create HLS sink
        import datetime
        timestamp = int(datetime.datetime.now().timestamp())
        base_filename = f"{self.room}_{self.stream_id}_{timestamp}"
        
        # For HLS, we need different approaches for playlist vs no-playlist mode
        if self.use_splitmuxsink:
            # Simple segmented recording without playlist
            self.hlssink = Gst.ElementFactory.make('splitmuxsink', None)
            if self.hlssink:
                self.hlssink.set_property('location', f"{base_filename}_%05d.ts")
                self.hlssink.set_property('max-size-time', 5 * Gst.SECOND)  # 5 second segments
                self.hlssink.set_property('send-keyframe-requests', True)
                # Tell splitmuxsink to use mpegtsmux internally
                self.hlssink.set_property('muxer', Gst.ElementFactory.make('mpegtsmux', None))
                
                self.log(f"   Output: {base_filename}_*.ts (5 second segments)")
                self.base_filename = base_filename
        else:
            # HLS with m3u8 playlist - use hlssink2 which properly handles segmentation
            self.hlssink = Gst.ElementFactory.make('hlssink2', None)
            if self.hlssink:
                self.hlssink.set_property('location', f"{base_filename}_%05d.ts")
                self.hlssink.set_property('playlist-location', f"{base_filename}.m3u8")
                self.hlssink.set_property('target-duration', 5)  # 5 second segments
                self.hlssink.set_property('max-files', 0)  # Keep all segments
                self.hlssink.set_property('playlist-length', 0)  # Keep all in playlist
                # Enable fragmenting to start writing immediately
                self.hlssink.set_property('send-keyframe-requests', True)
                # Set async handling for dynamic pad connections
                self.hlssink.set_property('async-handling', True)
                
                self.log(f"   Playlist: {base_filename}.m3u8")
                self.log(f"   Segments: {base_filename}_*.ts (5 second chunks)")
                self.base_filename = base_filename
                
        if not self.hlssink:
            self.log("Failed to create HLS sink", "error")
            return
            
        # Add sink to pipeline
        self.pipe.add(self.hlssink)
        
        # Sync state
        self.hlssink.sync_state_with_parent()
        
        self.log("   ✅ HLS muxer ready for audio/video streams")
        
    def setup_ndi_combiner(self):
        """Set up NDI sink combiner for audio/video multiplexing"""
        if hasattr(self, 'ndi_combiner') and self.ndi_combiner:
            # Already set up
            return
            
        self.log("Setting up NDI combiner for audio/video multiplexing")
        
        # Create NDI sink combiner
        self.ndi_combiner = Gst.ElementFactory.make('ndisinkcombiner', None)
        if not self.ndi_combiner:
            self.log("Failed to create ndisinkcombiner - is gst-plugin-ndi installed?", "error")
            return
            
        # Create NDI sink
        self.ndi_sink = Gst.ElementFactory.make('ndisink', None)
        if not self.ndi_sink:
            self.log("Failed to create ndisink", "error")
            return
            
        # Set NDI stream name
        ndi_name = self.ndi_name or f"{self.stream_id}"
        self.ndi_sink.set_property('ndi-name', ndi_name)
        self.log(f"   NDI stream name: {ndi_name}")
        
        # Configure sync settings to reduce audio lag
        self.ndi_sink.set_property('sync', True)
        self.ndi_sink.set_property('max-lateness', 100000000)  # 100ms
        self.ndi_sink.set_property('async', True)
        
        # Add to pipeline
        self.pipe.add(self.ndi_combiner)
        self.pipe.add(self.ndi_sink)
        
        # Link combiner to sink
        if not self.ndi_combiner.link(self.ndi_sink):
            self.log("Failed to link NDI combiner to sink", "error")
            return
            
        # Sync states
        self.ndi_combiner.sync_state_with_parent()
        self.ndi_sink.sync_state_with_parent()
        
        self.log("   ✅ NDI combiner ready for audio/video")
    
    def setup_ndi_audio_pad(self, pad, encoding_name):
        """Set up audio processing for NDI output"""
        # Create queue for buffering
        queue = Gst.ElementFactory.make('queue', None)
        # Set buffer properties for audio - reduce to help sync
        queue.set_property('max-size-time', 1000000000)  # 1 second
        queue.set_property('max-size-buffers', 0)
        queue.set_property('max-size-bytes', 0)
        queue.set_property('leaky', 2)  # Drop old buffers
        
        # Create depayloader and decoder based on codec
        if encoding_name == 'OPUS':
            depay = Gst.ElementFactory.make('rtpopusdepay', None)
            decoder = Gst.ElementFactory.make('opusdec', None)
        else:
            self.log(f"   ⚠️  Unsupported audio codec for NDI: {encoding_name}", "error")
            # Use fakesink as fallback
            fakesink = Gst.ElementFactory.make('fakesink', None)
            self.pipe.add(fakesink)
            fakesink.sync_state_with_parent()
            pad.link(fakesink.get_static_pad('sink'))
            return
            
        # Audio convert and resample for NDI
        audioconvert = Gst.ElementFactory.make('audioconvert', None)
        audioresample = Gst.ElementFactory.make('audioresample', None)
        
        if not all([queue, depay, decoder, audioconvert, audioresample]):
            self.log("Failed to create audio elements for NDI", "error")
            return
            
        # Add elements to pipeline
        elements = [queue, depay, decoder, audioconvert, audioresample]
        for element in elements:
            self.pipe.add(element)
            
        # Link audio processing chain
        if not queue.link(depay):
            self.log("Failed to link audio queue to depay", "error")
            return
        if not depay.link(decoder):
            self.log("Failed to link audio depay to decoder", "error")
            return
        if not decoder.link(audioconvert):
            self.log("Failed to link audio decoder to audioconvert", "error")
            return
        if not audioconvert.link(audioresample):
            self.log("Failed to link audioconvert to audioresample", "error")
            return
            
        # Link to NDI combiner audio pad
        if self.ndi_combiner:
            # Try new API first, fall back to deprecated API
            try:
                audio_pad = self.ndi_combiner.request_pad_simple('audio')
            except AttributeError:
                # Fall back to deprecated method for older GStreamer versions
                audio_pad = self.ndi_combiner.get_request_pad('audio')
            if audio_pad:
                src_pad = audioresample.get_static_pad('src')
                if src_pad.link(audio_pad) == Gst.PadLinkReturn.OK:
                    self.log("   ✅ Connected audio to NDI combiner")
                else:
                    self.log("Failed to link audio to NDI combiner", "error")
                    return
            else:
                self.log("Failed to get audio pad from NDI combiner", "error")
                return
        else:
            self.log("NDI combiner not available for audio", "error")
            return
            
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
            
        # Link incoming pad to queue
        sink_pad = queue.get_static_pad('sink')
        if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link audio pad to queue", "error")
            return
            
        # Add probe to monitor audio flow
        self._audio_ndi_probe_counter = 0
        def audio_probe_cb(pad, info):
            self._audio_ndi_probe_counter += 1
            if self._audio_ndi_probe_counter % 100 == 0:
                self.log(f"   📊 NDI audio flowing: {self._audio_ndi_probe_counter} buffers")
            return Gst.PadProbeReturn.OK
            
        pad.add_probe(Gst.PadProbeType.BUFFER, audio_probe_cb)
        
        self.log("   ✅ NDI audio pipeline connected")
        
        # Schedule periodic NDI status check
        if not hasattr(self, '_ndi_status_timer'):
            def check_ndi_status():
                if hasattr(self, 'ndi_sink') and self.ndi_sink:
                    # Get current state
                    state_ret, state, pending = self.ndi_sink.get_state(0)
                    # Get buffer counts
                    video_count = getattr(self, '_probe_counter', 0)
                    audio_count = getattr(self, '_ndi_audio_probe_counter', 0)
                    self.log(f"   🟢 NDI Status: State={state}, Video buffers={video_count}, Audio buffers={audio_count}")
                return True  # Keep repeating
            
            self._ndi_status_timer = GLib.timeout_add(10000, check_ndi_status)  # Every 10 seconds
        
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
                
                # Add early probe to verify data is coming from WebRTC
                def webrtc_probe_cb(pad, info):
                    if not hasattr(self, f'_webrtc_{media}_probe_logged'):
                        setattr(self, f'_webrtc_{media}_probe_logged', True)
                        self.log(f"   ✅ WebRTC {media} data confirmed at source!")
                    return Gst.PadProbeReturn.OK
                pad.add_probe(Gst.PadProbeType.BUFFER, webrtc_probe_cb)
                
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
            # For NDI, we need to set up the combiner first
            self.setup_ndi_combiner()
        elif self.use_hls:
            self.log(f"📹 HLS RECORDING START: Video stream from {self.stream_id}")
            self.log(f"   Mode: {'splitmuxsink' if self.use_splitmuxsink else 'hlssink'}")
            # For HLS, we'll set up a shared muxer for audio/video
            self.setup_hls_muxer()
        else:
            self.log(f"📹 RECORDING START: Video stream from {self.stream_id}")
        self.log(f"   Codec: {encoding_name}, Resolution: {width}x{height}")
        
        # Create queue for buffering
        queue = Gst.ElementFactory.make('queue', None)
        # Set reasonable limits to prevent queue overflow
        if self.room_ndi:
            # For NDI, use smaller buffer to reduce latency
            queue.set_property('max-size-time', 1000000000)  # 1 second
            queue.set_property('max-size-buffers', 0)
            queue.set_property('max-size-bytes', 0)
            queue.set_property('leaky', 2)  # Drop old buffers if full
        
        # First, we need to depayload the RTP stream
        if encoding_name == 'VP8':
            depay = Gst.ElementFactory.make('rtpvp8depay', None)
            if self.room_ndi:
                # For NDI, we need to decode VP8
                decoder = Gst.ElementFactory.make('vp8dec', None)
            elif self.use_hls:
                # For HLS, decode VP8 and re-encode to H264
                self.log("   ⚠️  VP8 codec requires transcoding to H264 for HLS")
                decoder = Gst.ElementFactory.make('vp8dec', None)
                videoconvert_enc = Gst.ElementFactory.make('videoconvert', None)
                encoder = Gst.ElementFactory.make('x264enc', None)
                if encoder:
                    encoder.set_property('tune', 'zerolatency')
                    encoder.set_property('speed-preset', 'superfast')
                    encoder.set_property('key-int-max', 60)  # Keyframe every 2 seconds at 30fps
                h264parse = Gst.ElementFactory.make('h264parse', None)
                if h264parse:
                    h264parse.set_property('config-interval', -1)  # Send config with every keyframe
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
            if h264parse and self.use_hls:
                h264parse.set_property('config-interval', -1)  # Send config with every keyframe
                # For HLS, we need to ensure we get access units
                h264parse.set_property('update-timecode', False)
            if self.room_ndi:
                # For NDI, we need to decode H264
                decoder = Gst.ElementFactory.make('avdec_h264', None)
            elif not self.use_hls:
                # For H264, we can use MP4
                mux = Gst.ElementFactory.make('mp4mux', None)
                extension = 'mp4'
        elif encoding_name == 'VP9':
            depay = Gst.ElementFactory.make('rtpvp9depay', None)
            if self.room_ndi:
                # For NDI, we need to decode VP9
                decoder = Gst.ElementFactory.make('vp9dec', None)
            elif self.use_hls:
                # For HLS, decode VP9 and re-encode to H264
                self.log("   ⚠️  VP9 codec requires transcoding to H264 for HLS")
                decoder = Gst.ElementFactory.make('vp9dec', None)
                videoconvert_enc = Gst.ElementFactory.make('videoconvert', None)
                encoder = Gst.ElementFactory.make('x264enc', None)
                if encoder:
                    encoder.set_property('tune', 'zerolatency')
                    encoder.set_property('speed-preset', 'superfast')
                    encoder.set_property('key-int-max', 60)  # Keyframe every 2 seconds at 30fps
                h264parse = Gst.ElementFactory.make('h264parse', None)
                if h264parse:
                    h264parse.set_property('config-interval', -1)  # Send config with every keyframe
            else:
                # Use WebM for VP9
                mux = Gst.ElementFactory.make('webmmux', None)
                mux.set_property('streamable', True)
                mux.set_property('min-index-interval', 1000000000)  # 1 second
                extension = 'webm'
        elif encoding_name == 'AV1':
            depay = Gst.ElementFactory.make('rtpav1depay', None)
            if self.room_ndi:
                # For NDI, we need to decode AV1
                decoder = Gst.ElementFactory.make('av1dec', None)
            elif self.use_hls:
                # For HLS, decode AV1 and re-encode to H264
                self.log("   ⚠️  AV1 codec requires transcoding to H264 for HLS")
                decoder = Gst.ElementFactory.make('av1dec', None)
                videoconvert_enc = Gst.ElementFactory.make('videoconvert', None)
                encoder = Gst.ElementFactory.make('x264enc', None)
                if encoder:
                    encoder.set_property('tune', 'zerolatency')
                    encoder.set_property('speed-preset', 'superfast')
                    encoder.set_property('key-int-max', 60)  # Keyframe every 2 seconds at 30fps
                h264parse = Gst.ElementFactory.make('h264parse', None)
                if h264parse:
                    h264parse.set_property('config-interval', -1)  # Send config with every keyframe
            else:
                # Use WebM for AV1
                mux = Gst.ElementFactory.make('webmmux', None)
                mux.set_property('streamable', True)
                mux.set_property('min-index-interval', 1000000000)  # 1 second
                extension = 'webm'
        else:
            self.log(f"Unsupported video codec: {encoding_name}", "error")
            return
        
        if self.room_ndi:
            # Create video processing elements for NDI
            videoconvert = Gst.ElementFactory.make('videoconvert', None)
            videorate = Gst.ElementFactory.make('videorate', None)
            # Add another queue after decoder to prevent blocking
            video_queue2 = Gst.ElementFactory.make('queue', 'ndi_video_queue2')
            if video_queue2:
                video_queue2.set_property('max-size-time', 500000000)  # 0.5 seconds
                video_queue2.set_property('max-size-buffers', 0)
                video_queue2.set_property('max-size-bytes', 0)
                video_queue2.set_property('leaky', 2)  # Drop old buffers
                
            # Configure decoder for low latency
            if decoder:
                # Try to set properties that might exist
                try:
                    decoder.set_property('max-threads', 4)
                except:
                    pass
                try:
                    decoder.set_property('low-latency', True) 
                except:
                    pass
                try:
                    decoder.set_property('output-corrupt', False)
                except:
                    pass
            
            if not all([queue, depay, decoder, videoconvert, videorate]):
                self.log("Failed to create NDI video elements", "error")
                return
                
        elif self.use_hls:
            # HLS recording mode - muxer already set up in setup_hls_muxer()
            
            # Check elements based on codec
            if encoding_name in ['VP8', 'VP9', 'AV1']:
                # VP8/VP9/AV1 need full decode/encode pipeline
                if not all([queue, depay, decoder, videoconvert_enc, encoder, h264parse]):
                    self.log(f"Failed to create HLS elements for {encoding_name}", "error")
                    return
            else:  # H264
                # H264 can go directly to HLS
                if not all([queue, depay, h264parse]):
                    self.log("Failed to create HLS elements for H264", "error")
                    return
        else:
            # Recording mode
            filesink = Gst.ElementFactory.make('filesink', None)
            
            if not all([queue, depay, mux, filesink]):
                self.log("Failed to create recording elements", "error")
                return
        
        if self.room_ndi:
            # Add NDI elements to pipeline
            if encoding_name in ['VP8', 'VP9', 'AV1']:
                elements = [queue, depay, decoder, video_queue2, videoconvert, videorate] if video_queue2 else [queue, depay, decoder, videoconvert, videorate]
            else:  # H264
                elements = [queue, depay, h264parse, decoder, video_queue2, videoconvert, videorate] if video_queue2 else [queue, depay, h264parse, decoder, videoconvert, videorate]
                
            for element in elements:
                self.pipe.add(element)
                
            # Link NDI video pipeline
            if encoding_name in ['VP8', 'VP9', 'AV1']:
                # VP8/VP9/AV1: queue -> depay -> decoder -> video_queue2 -> videoconvert -> videorate -> combiner
                if not queue.link(depay):
                    self.log("Failed to link queue to depay", "error")
                    return
                if not depay.link(decoder):
                    self.log("Failed to link depay to decoder", "error")
                    return
                if video_queue2:
                    if not decoder.link(video_queue2):
                        self.log("Failed to link decoder to video_queue2", "error")
                        return
                    if not video_queue2.link(videoconvert):
                        self.log("Failed to link video_queue2 to videoconvert", "error")
                        return
                else:
                    if not decoder.link(videoconvert):
                        self.log("Failed to link decoder to videoconvert", "error")
                        return
                
                # Link videoconvert to videorate
                if not videoconvert.link(videorate):
                    self.log("Failed to link videoconvert to videorate", "error")
                    return
            else:  # H264
                # H264: queue -> depay -> h264parse -> avdec_h264 -> video_queue2 -> videoconvert -> videorate -> combiner
                if not queue.link(depay):
                    self.log("Failed to link queue to depay", "error")
                    return
                if not depay.link(h264parse):
                    self.log("Failed to link depay to h264parse", "error")
                    return
                if not h264parse.link(decoder):
                    self.log("Failed to link h264parse to decoder", "error")
                    return
                if video_queue2:
                    if not decoder.link(video_queue2):
                        self.log("Failed to link decoder to video_queue2", "error")
                        return
                    if not video_queue2.link(videoconvert):
                        self.log("Failed to link video_queue2 to videoconvert", "error")
                        return
                else:
                    if not decoder.link(videoconvert):
                        self.log("Failed to link decoder to videoconvert", "error")
                        return
                
                # Link videoconvert to videorate
                if not videoconvert.link(videorate):
                    self.log("Failed to link videoconvert to videorate", "error")
                    return
            
            # Link to NDI combiner video pad
            if self.ndi_combiner:
                # Video pad is 'Always' available, not 'On request'
                video_pad = self.ndi_combiner.get_static_pad('video')
                if video_pad:
                    src_pad = videorate.get_static_pad('src')
                    if src_pad.link(video_pad) == Gst.PadLinkReturn.OK:
                        self.log("   ✅ Connected video to NDI combiner")
                        
                        # Add probe to monitor NDI video flow
                        def ndi_video_probe_cb(pad, info):
                            if not hasattr(self, '_ndi_video_probe_count'):
                                self._ndi_video_probe_count = 0
                                self._ndi_video_last_log = 0
                                self.log("   📊 First NDI video buffer!")
                            
                            self._ndi_video_probe_count += 1
                            
                            # Log every 100 buffers
                            if self._ndi_video_probe_count - self._ndi_video_last_log >= 100:
                                self.log(f"   📊 NDI video flowing: {self._ndi_video_probe_count} buffers to combiner")
                                self._ndi_video_last_log = self._ndi_video_probe_count
                                
                            return Gst.PadProbeReturn.OK
                        
                        src_pad.add_probe(Gst.PadProbeType.BUFFER, ndi_video_probe_cb)
                    else:
                        self.log("Failed to link video to NDI combiner", "error")
                        return
                else:
                    self.log("Failed to get video pad from NDI combiner", "error")
                    return
        elif self.use_hls:
            # HLS recording mode
            # Create a queue specifically for video before muxer
            video_queue = Gst.ElementFactory.make('queue', 'video_queue_hls')
            if not video_queue:
                self.log("Failed to create video queue for HLS", "error")
                return
                
            if encoding_name in ['VP8', 'VP9', 'AV1']:
                # VP8/VP9/AV1: queue -> depay -> decoder -> videoconvert -> x264enc -> h264parse -> video_queue -> mux
                elements = [queue, depay, decoder, videoconvert_enc, encoder, h264parse, video_queue]
            else:  # H264
                # H264: queue -> depay -> h264parse -> video_queue -> mux
                self.log("   ✅ H264 codec - no transcoding needed for HLS")
                elements = [queue, depay, h264parse, video_queue]
                
            # Add all elements to pipeline
            for element in elements:
                self.pipe.add(element)
                
            # Link HLS pipeline
            if encoding_name in ['VP8', 'VP9', 'AV1']:
                # Link decode/encode chain for transcoding
                if not queue.link(depay):
                    self.log("Failed to link queue to depay", "error")
                    return
                if not depay.link(decoder):
                    self.log("Failed to link depay to decoder", "error")
                    return
                if not decoder.link(videoconvert_enc):
                    self.log("Failed to link decoder to videoconvert", "error")
                    return
                if not videoconvert_enc.link(encoder):
                    self.log("Failed to link videoconvert to encoder", "error")
                    return
                if not encoder.link(h264parse):
                    self.log("Failed to link encoder to h264parse", "error")
                    return
                if not h264parse.link(video_queue):
                    self.log("Failed to link h264parse to video queue", "error")
                    return
            else:  # H264
                # Link H264 passthrough chain
                if not queue.link(depay):
                    self.log("Failed to link queue to depay", "error")
                    return
                if not depay.link(h264parse):
                    self.log("Failed to link depay to h264parse", "error")
                    return
                    
                # Add probe after depay to monitor incoming video
                depay_pad = depay.get_static_pad('src')
                if depay_pad:
                    def depay_probe_cb(pad, info):
                        if not hasattr(self, '_depay_probe_logged'):
                            self._depay_probe_logged = True
                            self.log("   ✅ Video data confirmed after depay!")
                        return Gst.PadProbeReturn.OK
                    depay_pad.add_probe(Gst.PadProbeType.BUFFER, depay_probe_cb)
                    
                if not h264parse.link(video_queue):
                    self.log("Failed to link h264parse to video queue", "error")
                    return
                    
                # Add probe after h264parse to check flow
                h264_pad = h264parse.get_static_pad('src')
                if h264_pad:
                    def h264_probe_cb(pad, info):
                        if not hasattr(self, '_h264_probe_logged'):
                            self._h264_probe_logged = True
                            self.log("   ✅ Video data confirmed after h264parse!")
                        return Gst.PadProbeReturn.OK
                    h264_pad.add_probe(Gst.PadProbeType.BUFFER, h264_probe_cb)
                    
                # Add probe on video queue output
                queue_src_pad = video_queue.get_static_pad('src')
                if queue_src_pad:
                    def queue_probe_cb(pad, info):
                        if not hasattr(self, '_queue_probe_logged'):
                            self._queue_probe_logged = True
                            self.log("   ✅ Video data confirmed at video_queue output!")
                        return Gst.PadProbeReturn.OK
                    queue_src_pad.add_probe(Gst.PadProbeType.BUFFER, queue_probe_cb)
                    
            # Link video queue to appropriate sink
            if hasattr(self, 'use_hlssink2') and self.use_hlssink2:
                # For hlssink2, request a video pad and connect
                video_pad = self.hlssink.request_pad_simple('video')
                if video_pad:
                    src_pad = video_queue.get_static_pad('src')
                    if src_pad.link(video_pad) == Gst.PadLinkReturn.OK:
                        self.log("   ✅ Video connected to HLS sink")
                        # Check hlssink state
                        state = self.hlssink.get_state(0)
                        self.log(f"   HLS sink state after video connect: {state[1]}")
                    else:
                        self.log("Failed to link video to HLS sink", "error")
                        return
                else:
                    self.log("Failed to get video pad from HLS sink", "error")
                    return
            elif hasattr(self, 'hlssink') and self.hlssink:
                # For splitmuxsink, video is just 'video', not 'video_%u'
                video_pad = self.hlssink.request_pad_simple('video')
                    
                if video_pad:
                    src_pad = video_queue.get_static_pad('src')
                    if src_pad.link(video_pad) == Gst.PadLinkReturn.OK:
                        self.log("   ✅ Video connected to sink")
                    else:
                        self.log("Failed to link video to sink", "error")
                        return
                else:
                    self.log("Failed to get video pad from sink", "error")
                    return
            else:
                self.log("HLS sink not available", "error")
                return
                    
            # Sync states for all elements
            for element in elements:
                element.sync_state_with_parent()
                
            # Also ensure HLS sink is in correct state
            if hasattr(self, 'hlssink') and self.hlssink:
                # First try to sync with parent
                ret = self.hlssink.sync_state_with_parent()
                self.log(f"   HLS sink sync result: {ret}")
                
                # Check the actual state
                state_ret, state, pending = self.hlssink.get_state(0)
                if state != Gst.State.PLAYING:
                    self.log(f"   HLS sink not in PLAYING state ({state}), forcing to PLAYING")
                    ret = self.hlssink.set_state(Gst.State.PLAYING)
                    self.log(f"   HLS sink set_state result: {ret}")
                    # Wait for state change to complete
                    timeout = 5 * Gst.SECOND  # 5 second timeout
                    state_ret, state, pending = self.hlssink.get_state(timeout)
                    self.log(f"   HLS sink final state: {state} (result: {state_ret})")
                
            # Link incoming pad to queue
            sink_pad = queue.get_static_pad('sink')
            if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
                self.log("Failed to link video pad to queue", "error")
                return
                
            # Add probe to monitor data flow
            pad.add_probe(Gst.PadProbeType.BUFFER, self.on_pad_probe, None)
            
            self.log("   ✅ HLS recording pipeline connected and running")
            self.recording_video = True
            # For HLS, we don't have a single filename
            if hasattr(self, 'base_filename'):
                self.video_filename = self.base_filename
                
            # Schedule a check to see if data is flowing after a delay
            def check_hls_status():
                if hasattr(self, 'hlssink') and self.hlssink:
                    state_ret, state, pending = self.hlssink.get_state(0)
                    self.log(f"   HLS sink status check - State: {state}, Video buffers: {getattr(self, '_probe_counter', 0)}")
                    # Check if files are being created
                    import os
                    import glob
                    pattern = f"{self.base_filename}_*.ts" if hasattr(self, 'base_filename') else "*.ts"
                    files = glob.glob(pattern)
                    if files:
                        self.log(f"   ✅ HLS files created: {len(files)} segments")
                        for f in files[:3]:  # Show first 3
                            size = os.path.getsize(f)
                            self.log(f"      {os.path.basename(f)} ({size:,} bytes)")
                    else:
                        self.log("   ⚠️  No HLS files created yet")
                return False  # Don't repeat
            
            GLib.timeout_add(3000, check_hls_status)  # Check after 3 seconds
                
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
        
        if not self.use_hls:  # HLS already handles its own pad linking above
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
            
            # Add monitoring for NDI video flow
            if video_queue2:
                # Monitor queue fullness
                def monitor_ndi_queue():
                    try:
                        if hasattr(self, '_probe_counter'):
                            current_level_time = video_queue2.get_property('current-level-time')
                            current_level_buffers = video_queue2.get_property('current-level-buffers')
                            self.log(f"   📊 NDI Queue Status - Buffers: {self._probe_counter}, Queue level: {current_level_time/1000000:.1f}ms, {current_level_buffers} buffers")
                            
                            # Check if queue is stuck (no new buffers in 5 seconds)
                            if hasattr(self, '_last_ndi_buffer_count'):
                                if self._probe_counter == self._last_ndi_buffer_count:
                                    self.log("   ⚠️  NDI video flow appears stuck - no new buffers in 5 seconds", "warning")
                                    
                                    # Check pipeline state
                                    if self.pipe:
                                        pipe_state = self.pipe.get_state(0)
                                        self.log(f"   Pipeline state: {pipe_state[1]}")
                                    
                                    # Check decoder state if it exists
                                    if decoder:
                                        dec_state = decoder.get_state(0)
                                        self.log(f"   Decoder state: {dec_state[1]}")
                                        
                                    # Try to unblock by sending EOS and flushing
                                    if current_level_buffers == 0 and self._probe_counter > 1000:
                                        self.log("   🔧 Attempting to unblock pipeline with flush")
                                        # Send flush events to try to unblock
                                        if hasattr(self, 'webrtc'):
                                            sink_pads = self.webrtc.iterate_sink_pads()
                                            if sink_pads:
                                                done = False
                                                while not done:
                                                    ret, pad = sink_pads.next()
                                                    if ret == Gst.IteratorResult.OK and pad:
                                                        pad.send_event(Gst.Event.new_flush_start())
                                                        pad.send_event(Gst.Event.new_flush_stop(True))
                                                    else:
                                                        done = True
                            
                            self._last_ndi_buffer_count = self._probe_counter
                    except Exception as e:
                        self.log(f"   Error in NDI monitor: {e}", "warning")
                    return True  # Continue monitoring
                
                # Start monitoring after 5 seconds
                GLib.timeout_add(5000, monitor_ndi_queue)
        elif self.use_hls:
            # Already logged in HLS section above
            pass
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
            self._first_buffer_logged = False
            
        self._probe_counter += 1
        
        # Log first buffer
        if not self._first_buffer_logged:
            self._first_buffer_logged = True
            self.log(f"   📊 First video buffer received!")
            buffer = info.get_buffer()
            if buffer:
                self.log(f"      Buffer size: {buffer.get_size()} bytes")
                self.log(f"      Buffer PTS: {buffer.pts}")
        
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
            self.log(f"   🔊 Setting up NDI audio output")
            # Ensure NDI combiner is set up (in case audio arrives before video)
            self.setup_ndi_combiner()
            # For NDI, we need to decode and send audio to the combiner
            self.setup_ndi_audio_pad(pad, encoding_name)
            return
        
        if not self.record_audio and not self.use_hls:
            self.log(f"   ⏸️  Audio recording disabled (use --audio flag to enable)")
            # Just fakesink audio
            fakesink = Gst.ElementFactory.make('fakesink', None)
            self.pipe.add(fakesink)
            fakesink.sync_state_with_parent()
            pad.link(fakesink.get_static_pad('sink'))
            return
            
            
        # Record audio
        if self.use_hls:
            self.log(f"🔴 HLS AUDIO START: Audio stream from {self.stream_id}")
        else:
            self.log(f"🔴 RECORDING START: Audio stream from {self.stream_id}")
        
        # Create queue for buffering
        queue = Gst.ElementFactory.make('queue', None)
        # Set larger buffer for audio to handle async arrival
        queue.set_property('max-size-time', 10000000000)  # 10 seconds
        queue.set_property('max-size-buffers', 0)
        queue.set_property('max-size-bytes', 0)
        
        if self.use_hls:
            # For HLS, we need to transcode audio to AAC and mux with video
            self.log("   ℹ️  Audio will be muxed with video in HLS stream")
            # Ensure HLS muxer is set up
            self.setup_hls_muxer()
        else:
            # For non-HLS, just record audio alongside video in separate files
            self.log("   ℹ️  Audio recording is currently saved separately from video")
        
        # Check if already recording audio
        if hasattr(self, 'audio_filename') and self.audio_filename and not self.use_hls:
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
            
            if self.use_hls:
                # For HLS, we need to transcode Opus to AAC
                decoder = Gst.ElementFactory.make('opusdec', None)
                audioconvert = Gst.ElementFactory.make('audioconvert', None)
                audioresample = Gst.ElementFactory.make('audioresample', None)
                aacenc = Gst.ElementFactory.make('avenc_aac', None)
                aacparse = Gst.ElementFactory.make('aacparse', None)
                # Create a queue before muxer
                audio_queue = Gst.ElementFactory.make('queue', 'audio_queue_hls')
            else:
                # For non-HLS, decode to raw and save as WAV for maximum compatibility
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
        
        if self.use_hls:
            # HLS mode - check elements
            if not all([queue, depay, decoder, audioconvert, audioresample, aacenc, aacparse, audio_queue]):
                self.log("Failed to create HLS audio elements", "error")
                return
                
            # Add elements to pipeline
            elements = [queue, depay, decoder, audioconvert, audioresample, aacenc, aacparse, audio_queue]
            for element in elements:
                self.pipe.add(element)
                
            # Link audio pipeline for HLS
            if not queue.link(depay):
                self.log("Failed to link queue to depay", "error")
                return
            if not depay.link(decoder):
                self.log("Failed to link depay to decoder", "error")
                return
            if not decoder.link(audioconvert):
                self.log("Failed to link decoder to audioconvert", "error")
                return
            if not audioconvert.link(audioresample):
                self.log("Failed to link audioconvert to audioresample", "error")
                return
            if not audioresample.link(aacenc):
                self.log("Failed to link audioresample to aacenc", "error")
                return
            if not aacenc.link(aacparse):
                self.log("Failed to link aacenc to aacparse", "error")
                return
            if not aacparse.link(audio_queue):
                self.log("Failed to link aacparse to audio queue", "error")
                return
                
            # Link audio queue to appropriate sink
            if hasattr(self, 'use_hlssink2') and self.use_hlssink2:
                # For hlssink2, request an audio pad and connect
                audio_pad = self.hlssink.request_pad_simple('audio')
                if audio_pad:
                    src_pad = audio_queue.get_static_pad('src')
                    if src_pad.link(audio_pad) == Gst.PadLinkReturn.OK:
                        self.log("   ✅ Audio connected to HLS sink")
                    else:
                        self.log("Failed to link audio to HLS sink", "error")
                        return
                else:
                    self.log("Failed to get audio pad from HLS sink", "error")
                    return
            elif hasattr(self, 'hlssink') and self.hlssink:
                # For splitmuxsink, we need to check which sink type we have
                if self.use_splitmuxsink:
                    # splitmuxsink uses template names like audio_%u
                    audio_pad_template = self.hlssink.get_pad_template('audio_%u')
                    if audio_pad_template:
                        audio_pad = self.hlssink.request_pad(audio_pad_template, None, None)
                    else:
                        # Fallback to simple request
                        audio_pad = self.hlssink.request_pad_simple('audio')
                else:
                    audio_pad = self.hlssink.request_pad_simple('audio')
                    
                if audio_pad:
                    src_pad = audio_queue.get_static_pad('src')
                    if src_pad.link(audio_pad) == Gst.PadLinkReturn.OK:
                        self.log("   ✅ Audio connected to sink")
                    else:
                        self.log("Failed to link audio to sink", "error")
                        return
                else:
                    self.log("Failed to get audio pad from sink", "error")
                    return
            else:
                self.log("HLS sink not available for audio", "error")
                return
                
            # Sync states
            for element in elements:
                element.sync_state_with_parent()
                
            # Also ensure HLS sink is in correct state for audio
            if hasattr(self, 'hlssink') and self.hlssink:
                # Don't sync again if already done for video
                pass
                
            # Link incoming pad to queue
            sink_pad = queue.get_static_pad('sink')
            if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
                self.log("Failed to link audio pad to queue", "error")
                return
                
            # Add probe to monitor audio data flow
            self._audio_probe_counter = 0
            def audio_probe_cb(pad, info):
                self._audio_probe_counter += 1
                if self._audio_probe_counter % 100 == 0:
                    self.log(f"   📊 HLS audio flowing: {self._audio_probe_counter} buffers")
                return Gst.PadProbeReturn.OK
                
            pad.add_probe(Gst.PadProbeType.BUFFER, audio_probe_cb)
            
            self.log("   ✅ HLS audio pipeline connected and running")
            self.recording_audio = True
            # For HLS, audio filename is same as video base filename
            if hasattr(self, 'base_filename'):
                self.audio_filename = self.base_filename
            
        else:
            # Non-HLS mode - original recording code
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

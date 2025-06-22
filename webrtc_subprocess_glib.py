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
import os
import hashlib
from typing import Optional, Dict, Any

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp

# Try to import cryptography for decryption support
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


# Initialize GStreamer
Gst.init(None)


# Decryption helper functions (if crypto is available)
if HAS_CRYPTO:
    def to_byte_array(hex_str):
        return bytes.fromhex(hex_str)
    
    def generate_key(phrase):
        return hashlib.sha256(phrase.encode()).digest()
    
    def unpad_message(padded_message):
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        try:
            data = unpadder.update(padded_message) + unpadder.finalize()
            return data
        except ValueError as e:
            print(f"Padding error: {e}")
            return None
    
    def decrypt_message(encrypted_data, iv, phrase):
        key = generate_key(phrase)
        encrypted_data_bytes = to_byte_array(encrypted_data)
        iv_bytes = to_byte_array(iv)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv_bytes), backend=default_backend())
        decryptor = cipher.decryptor()
        try:
            decrypted_padded_message = decryptor.update(encrypted_data_bytes) + decryptor.finalize()
            unpadded_message = unpad_message(decrypted_padded_message)
            if unpadded_message is not None:
                return unpadded_message.decode('utf-8')
            else:
                return None
        except (UnicodeDecodeError, ValueError) as e:
            print(f"Error decoding message: {e}")
            return None


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
        self.ndi_direct = config.get('ndi_direct', False)  # Direct NDI mode flag
        self.use_hls = config.get('use_hls', False)
        self.use_splitmuxsink = config.get('use_splitmuxsink', True)  # Use splitmuxsink for now
        self.password = config.get('password')
        self.salt = config.get('salt', '')
        
        # Debug log the config
        self.log(f"DEBUG: Config received: record_audio={config.get('record_audio', 'NOT SET')}, room_ndi={config.get('room_ndi', False)}, use_hls={config.get('use_hls', False)}")
        self.log(f"DEBUG: Password in config: {'YES' if 'password' in config else 'NO'}, value: {'SET' if config.get('password') else 'NOT SET'}")
        if self.password:
            self.log(f"DEBUG: Password encryption enabled (salt: {len(self.salt)} chars)")
        else:
            self.log(f"DEBUG: No password set for encryption")
        
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
                
                # Check if we need to decrypt
                if isinstance(desc, str) and 'vector' in data:
                    self.log(f"DEBUG: Encrypted SDP detected. Password: {'SET' if self.password else 'NOT SET'}, HAS_CRYPTO: {HAS_CRYPTO}")
                    if self.password and HAS_CRYPTO:
                        # Decrypt the description
                        try:
                            self.log(f"DEBUG: Attempting decryption with password length {len(self.password)} and salt length {len(self.salt)}")
                            decrypted_json = decrypt_message(desc, data['vector'], self.password + self.salt)
                            if decrypted_json:
                                desc = json.loads(decrypted_json)
                                self.log("Successfully decrypted SDP from data channel")
                            else:
                                self.log("Failed to decrypt SDP from data channel - decrypt returned None")
                                return
                        except Exception as e:
                            self.log(f"Error decrypting SDP: {e}")
                            import traceback
                            self.log(f"Traceback: {traceback.format_exc()}")
                            return
                    else:
                        self.log(f"Cannot decrypt: Password={'not set' if not self.password else 'set'}, Crypto={'not available' if not HAS_CRYPTO else 'available'}")
                        return
                
                if isinstance(desc, dict) and desc.get('type') == 'offer':
                    self.log("Received renegotiation offer via data channel")
                    
                    # Store the offer and handle it in the main thread
                    sdp_text = desc['sdp']
                    self.log(f"Scheduling renegotiation handling in main thread ({len(sdp_text)} chars)")
                    
                    # Use GLib.idle_add to handle in main thread context
                    GLib.idle_add(self.handle_renegotiation_offer, sdp_text)
                elif isinstance(desc, str):
                    # This is an encrypted offer but we couldn't decrypt it
                    self.log("WARNING: Received encrypted SDP via data channel - decryption failed or not available")
            elif 'candidates' in data:
                # Handle ICE candidates from data channel
                candidates = data['candidates']
                
                # Check if we need to decrypt
                if isinstance(candidates, str) and 'vector' in data and self.password and HAS_CRYPTO:
                    # Decrypt the candidates
                    try:
                        decrypted_json = decrypt_message(candidates, data['vector'], self.password + self.salt)
                        if decrypted_json:
                            candidates = json.loads(decrypted_json)
                            self.log(f"Successfully decrypted {len(candidates) if isinstance(candidates, list) else 1} ICE candidates from data channel")
                        else:
                            self.log("Failed to decrypt ICE candidates from data channel")
                            return
                    except Exception as e:
                        self.log(f"Error decrypting ICE candidates: {e}")
                        return
                
                if isinstance(candidates, list):
                    self.log(f"Processing {len(candidates)} ICE candidates via data channel")
                    for candidate in candidates:
                        if isinstance(candidate, dict) and 'candidate' in candidate and 'sdpMLineIndex' in candidate:
                            self.webrtc.emit('add-ice-candidate', 
                                           candidate['sdpMLineIndex'], 
                                           candidate['candidate'])
                elif isinstance(candidates, str):
                    # This is still encrypted but we couldn't decrypt it
                    self.log(f"WARNING: Received encrypted ICE candidates - decryption failed or not available")
                        
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
    
    def check_hls_streams_ready(self):
        """Check if both audio and video are connected and start HLS recording"""
        if not self.use_hls:
            return
            
        # Check if both streams are connected
        if hasattr(self, 'hls_audio_connected') and self.hls_audio_connected and \
           hasattr(self, 'hls_video_connected') and self.hls_video_connected:
            
            self.log("   ✅ Both audio and video connected - starting HLS recording")
            
            # Add a small delay for segment events to propagate on slower systems
            def delayed_start():
                self.log("   ⏳ Starting HLS elements...")
                
                # First sync the mux state
                if hasattr(self, 'hls_mux') and self.hls_mux:
                    ret = self.hls_mux.sync_state_with_parent()
                    self.log(f"   Mpegtsmux sync result: {ret}")
                    
                    # Force mux to PLAYING state
                    ret = self.hls_mux.set_state(Gst.State.PLAYING)
                    ret_name = ret.value_name if hasattr(ret, 'value_name') else str(ret)
                    self.log(f"   Mpegtsmux set_state result: {ret_name}")
                
                # Then sync the sink state
                if hasattr(self, 'hlssink') and self.hlssink:
                    ret = self.hlssink.sync_state_with_parent()
                    self.log(f"   HLS sink sync result: {ret}")
                    
                    # Force sink to PLAYING state
                    ret = self.hlssink.set_state(Gst.State.PLAYING)
                    ret_name = ret.value_name if hasattr(ret, 'value_name') else str(ret)
                    self.log(f"   HLS sink set_state result: {ret_name}")
                    
                    # Wait for state changes to complete
                    timeout = 2 * Gst.SECOND
                    
                    # Check mux state
                    if hasattr(self, 'hls_mux') and self.hls_mux:
                        state_ret, state, pending = self.hls_mux.get_state(timeout)
                        state_name = state.value_name if hasattr(state, 'value_name') else str(state)
                        self.log(f"   Mpegtsmux final state: {state_name}")
                    
                    # Check sink state
                    state_ret, state, pending = self.hlssink.get_state(timeout)
                    state_name = state.value_name if hasattr(state, 'value_name') else str(state)
                    ret_name = state_ret.value_name if hasattr(state_ret, 'value_name') else str(state_ret)
                    self.log(f"   HLS sink final state: {state_name} (result: {ret_name})")
                        
                self.log("   🎬 HLS recording started!")
                return False  # Don't repeat
                
            # Schedule the start with a 100ms delay
            GLib.timeout_add(100, delayed_start)
    
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
        
        # For Jetson Nano with GStreamer 1.23.0, we need explicit mpegtsmux control
        # Create our own mpegtsmux to ensure proper segment handling
        self.hls_mux = Gst.ElementFactory.make('mpegtsmux', 'hls_mpegtsmux')
        if not self.hls_mux:
            self.log("Failed to create mpegtsmux", "error")
            return
            
        # Configure mpegtsmux for HLS
        self.hls_mux.set_property('alignment', 7)  # Proper alignment for HLS
        self.pipe.add(self.hls_mux)
        
        # Create filesink or hlssink2 based on mode
        if self.use_splitmuxsink:
            # For splitmuxsink, we need to let it manage the mux internally
            # Remove our explicit mux since splitmuxsink creates its own
            self.pipe.remove(self.hls_mux)
            self.hls_mux = None
            
            # Use splitmuxsink with internal mux
            self.hlssink = Gst.ElementFactory.make('splitmuxsink', None)
            if self.hlssink:
                self.hlssink.set_property('location', f"{base_filename}_%05d.ts")
                self.hlssink.set_property('max-size-time', 5 * Gst.SECOND)
                self.hlssink.set_property('send-keyframe-requests', True)
                self.hlssink.set_property('async-finalize', True)
                
                # Create and configure mpegtsmux for splitmuxsink
                mux = Gst.ElementFactory.make('mpegtsmux', None)
                if mux:
                    mux.set_property('alignment', 7)
                    self.hlssink.set_property('muxer', mux)
                
                self.log(f"   Output: {base_filename}_*.ts (5 second segments)")
                self.base_filename = base_filename
                # Store reference to know we're using internal mux
                self.use_internal_mux = True
        else:
            # For hlssink2, we'll use a different approach
            # Create a regular filesink and handle segmentation manually
            self.use_manual_segmentation = True
            self.segment_counter = 0
            self.current_segment_start = None
            
            # Create initial filesink
            self.hlssink = Gst.ElementFactory.make('filesink', None)
            if self.hlssink:
                segment_filename = f"{base_filename}_{self.segment_counter:05d}.ts"
                self.hlssink.set_property('location', segment_filename)
                self.hlssink.set_property('sync', False)
                self.hlssink.set_property('async', False)
                
                # Create M3U8 playlist
                self.playlist_filename = f"{base_filename}.m3u8"
                self.segment_duration = 5.0
                self.segments = []
                self.write_m3u8_header()
                
                self.log(f"   Playlist: {self.playlist_filename}")
                self.log(f"   First segment: {segment_filename}")
                self.base_filename = base_filename
                
        if not self.hlssink:
            self.log("Failed to create HLS sink", "error")
            return
            
        # Add sink to pipeline
        self.pipe.add(self.hlssink)
        
        # Link mux to sink
        if not self.use_splitmuxsink:
            # For manual segmentation, link mux to filesink
            if not self.hls_mux.link(self.hlssink):
                self.log("Failed to link mux to sink", "error")
                return
        
        # Keep elements in NULL state initially
        self.hls_mux.set_state(Gst.State.NULL)
        self.hlssink.set_state(Gst.State.NULL)
        
        self.log("   ✅ HLS muxer ready for audio/video streams")
        
    def write_m3u8_header(self):
        """Write initial M3U8 playlist header"""
        if hasattr(self, 'playlist_filename'):
            with open(self.playlist_filename, 'w') as f:
                f.write("#EXTM3U\n")
                f.write("#EXT-X-VERSION:3\n")
                f.write(f"#EXT-X-TARGETDURATION:{int(self.segment_duration)}\n")
                f.write("#EXT-X-MEDIA-SEQUENCE:0\n")
                f.write("\n")
        
    def setup_ndi_combiner(self):
        """Set up NDI sink combiner for audio/video multiplexing"""
        if hasattr(self, 'ndi_combiner') and self.ndi_combiner:
            # Already set up
            return
            
        if self.ndi_direct:
            self.log("🔧 Using DIRECT NDI mode (separate audio/video streams, no combiner)")
            self.log("   ℹ️  This is the default mode to avoid freezing issues")
            self.setup_direct_ndi()
            return
            
        self.log("⚠️  Using NDI COMBINER mode for audio/video multiplexing")
        self.log("   ⚠️  WARNING: Known to freeze after ~1500-2000 buffers!")
        self.log("   💡 Use default direct mode instead (remove --ndi-combine flag)")
        
        # Create NDI sink combiner
        self.ndi_combiner = Gst.ElementFactory.make('ndisinkcombiner', None)
        if not self.ndi_combiner:
            self.log("Failed to create ndisinkcombiner - is gst-plugin-ndi installed?", "error")
            return
            
        # Configure NDI combiner - use some latency for transcoding mode
        self.ndi_combiner.set_property("latency", 100000000)  # 100ms latency for sync
        self.ndi_combiner.set_property("min-upstream-latency", 50000000)  # 50ms min latency
        self.ndi_combiner.set_property("start-time-selection", 0)  # 0 = "zero"
            
        # Create NDI sink
        self.ndi_sink = Gst.ElementFactory.make('ndisink', None)
        if not self.ndi_sink:
            self.log("Failed to create ndisink", "error")
            return
            
        # Set NDI stream name
        ndi_name = self.ndi_name or f"{self.stream_id}"
        self.ndi_sink.set_property('ndi-name', ndi_name)
        self.log(f"   NDI stream name: {ndi_name}")
        
        # Configure sync settings - try minimal sync to avoid blocking
        self.ndi_sink.set_property('sync', False)  # Disable sync completely
        self.ndi_sink.set_property('async', False)  # Disable async to avoid blocking
        
        # Create a queue between combiner and sink to prevent blocking
        ndi_queue = Gst.ElementFactory.make('queue', 'ndi_output_queue')
        if ndi_queue:
            # Small queue to prevent accumulation
            ndi_queue.set_property('max-size-time', 100_000_000)  # 100ms
            ndi_queue.set_property('max-size-buffers', 10)
            ndi_queue.set_property('max-size-bytes', 0)
            ndi_queue.set_property('leaky', 2)  # Drop old buffers
        
        # Add to pipeline
        self.pipe.add(self.ndi_combiner)
        self.pipe.add(ndi_queue)
        self.pipe.add(self.ndi_sink)
        
        # Link combiner -> queue -> sink
        if not self.ndi_combiner.link(ndi_queue):
            self.log("Failed to link NDI combiner to queue", "error")
            return
        if not ndi_queue.link(self.ndi_sink):
            self.log("Failed to link queue to NDI sink", "error")
            return
            
        # Add probe to monitor what's coming out of the combiner
        combiner_src_pad = self.ndi_combiner.get_static_pad('src')
        if combiner_src_pad:
            self._combiner_output_count = 0
            def combiner_probe_cb(pad, info):
                self._combiner_output_count += 1
                if self._combiner_output_count % 50 == 0:
                    self.log(f"   📊 NDI combiner output: {self._combiner_output_count} combined buffers")
                return Gst.PadProbeReturn.OK
            combiner_src_pad.add_probe(Gst.PadProbeType.BUFFER, combiner_probe_cb)
            self.log("   ✅ Added probe to monitor NDI combiner output")
            
        # Sync states
        self.ndi_combiner.sync_state_with_parent()
        ndi_queue.sync_state_with_parent()
        self.ndi_sink.sync_state_with_parent()
        
        self.log("   ✅ NDI combiner ready for audio/video")
    
    def setup_direct_ndi(self):
        """Set up direct NDI sink without combiner (video only)"""
        if hasattr(self, 'ndi_sink') and self.ndi_sink:
            return
            
        # Create NDI sink for video
        self.ndi_sink = Gst.ElementFactory.make('ndisink', None)
        if not self.ndi_sink:
            self.log("Failed to create ndisink", "error")
            return
            
        # Set NDI stream name
        ndi_name = self.ndi_name or f"{self.stream_id}"
        self.ndi_sink.set_property('ndi-name', ndi_name + "_video")
        self.log(f"   NDI video stream: {ndi_name}_video")
        
        # Configure sync settings
        self.ndi_sink.set_property('sync', False)
        self.ndi_sink.set_property('async', False)
        
        # Add to pipeline
        self.pipe.add(self.ndi_sink)
        self.ndi_sink.sync_state_with_parent()
        
        # Create NDI sink for audio (separate stream)
        self.ndi_audio_sink = Gst.ElementFactory.make('ndisink', None)
        if self.ndi_audio_sink:
            self.ndi_audio_sink.set_property('ndi-name', ndi_name + "_audio")
            self.ndi_audio_sink.set_property('sync', False)
            self.ndi_audio_sink.set_property('async', False)
            self.pipe.add(self.ndi_audio_sink)
            self.ndi_audio_sink.sync_state_with_parent()
            self.log(f"   NDI audio stream: {ndi_name}_audio")
        
        # Create a fake combiner reference so other code doesn't break
        self.ndi_combiner = True  # Just a placeholder
        
        self.log("   ✅ Direct NDI ready (separate video/audio streams)")
        self.log("   ℹ️  Audio and video sent as separate NDI streams")
    
    def setup_ndi_audio_pad(self, pad, encoding_name):
        """Set up audio processing for NDI output"""
        if self.ndi_direct:
            # In direct mode, send audio to separate NDI stream
            if not hasattr(self, 'ndi_audio_sink') or not self.ndi_audio_sink:
                self.log("   ⚠️  No audio NDI sink available")
                fakesink = Gst.ElementFactory.make('fakesink', None)
                self.pipe.add(fakesink)
                fakesink.sync_state_with_parent()
                pad.link(fakesink.get_static_pad('sink'))
                return
                
            self.log("   🔊 Setting up separate NDI audio stream")
            
            # Create audio processing pipeline
            queue = Gst.ElementFactory.make('queue', None)
            queue.set_property('max-size-time', 1000000000)  # 1 second
            queue.set_property('max-size-buffers', 0)
            queue.set_property('max-size-bytes', 0)
            
            # Create depayloader and decoder based on codec
            if encoding_name == 'OPUS':
                depay = Gst.ElementFactory.make('rtpopusdepay', None)
                decoder = Gst.ElementFactory.make('opusdec', None)
            else:
                self.log(f"   ⚠️  Unsupported audio codec for NDI: {encoding_name}", "error")
                fakesink = Gst.ElementFactory.make('fakesink', None)
                self.pipe.add(fakesink)
                fakesink.sync_state_with_parent()
                pad.link(fakesink.get_static_pad('sink'))
                return
                
            audioconvert = Gst.ElementFactory.make('audioconvert', None)
            audioresample = Gst.ElementFactory.make('audioresample', None)
            
            # Add capsfilter to ensure NDI-compatible format (F32LE)
            audio_capsfilter = Gst.ElementFactory.make('capsfilter', 'audio_ndi_caps')
            if audio_capsfilter:
                audio_caps = Gst.Caps.from_string("audio/x-raw,format=F32LE")
                audio_capsfilter.set_property('caps', audio_caps)
            
            # Add elements
            elements = [queue, depay, decoder, audioconvert, audioresample]
            if audio_capsfilter:
                elements.append(audio_capsfilter)
            
            for element in elements:
                self.pipe.add(element)
                
            # Link chain
            if audio_capsfilter:
                if not (queue.link(depay) and depay.link(decoder) and 
                        decoder.link(audioconvert) and audioconvert.link(audioresample) and
                        audioresample.link(audio_capsfilter) and audio_capsfilter.link(self.ndi_audio_sink)):
                    self.log("Failed to link audio pipeline", "error")
                    return
            else:
                if not (queue.link(depay) and depay.link(decoder) and 
                        decoder.link(audioconvert) and audioconvert.link(audioresample) and
                        audioresample.link(self.ndi_audio_sink)):
                    self.log("Failed to link audio pipeline", "error")
                    return
                
            # Sync states
            for element in elements:
                element.sync_state_with_parent()
                
            # Link pad to queue
            if pad.link(queue.get_static_pad('sink')) != Gst.PadLinkReturn.OK:
                self.log("Failed to link audio pad", "error")
                return
                
            self.log("   ✅ Separate NDI audio stream connected")
            return
            
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
            self._last_ndi_sink_count = 0
            self._ndi_freeze_count = 0
            
            def check_ndi_status():
                if hasattr(self, 'ndi_sink') and self.ndi_sink:
                    # Get current state
                    state_ret, state, pending = self.ndi_sink.get_state(0)
                    # Get buffer counts
                    video_count = getattr(self, '_probe_counter', 0)
                    audio_count = getattr(self, '_ndi_audio_probe_counter', 0)
                    combiner_output = getattr(self, '_combiner_output_count', 0)
                    
                    self.log(f"   🟢 NDI Status: State={state}, Video in={video_count}, Audio in={self._audio_ndi_probe_counter if hasattr(self, '_audio_ndi_probe_counter') else 0}, Combiner out={combiner_output}")
                    
                    # Check if combiner is frozen
                    if combiner_output == self._last_ndi_sink_count and video_count > 100:
                        self._ndi_freeze_count += 1
                        if self._ndi_freeze_count >= 2:
                            self.log("   ⚠️  NDI COMBINER FROZEN - No output for 20+ seconds!", "error")
                            self.log("   ℹ️  Known issue: ndisinkcombiner freezes after ~1500-2000 buffers", "warning")
                            self.log("   💡 Workaround: Restart the process or use --no-audio flag", "info")
                            # Send a message to parent process about the freeze
                            self.send_message({
                                "type": "ndi_frozen",
                                "video_buffers": video_count,
                                "combiner_output": combiner_output
                            })
                    else:
                        if self._ndi_freeze_count > 0:
                            self.log("   ✅ NDI combiner recovered")
                        self._ndi_freeze_count = 0
                        
                    self._last_ndi_sink_count = combiner_output
                    
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
            # For NDI, don't limit the queue - let it buffer as needed
            queue.set_property('max-size-time', 0)  # Unlimited time
            queue.set_property('max-size-buffers', 0)  # Unlimited buffers
            queue.set_property('max-size-bytes', 0)  # Unlimited bytes
        
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
                # Direct VP8 to WebM without transcoding
                self.log("   📦 Direct VP8 → WebM (no transcoding)")
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
                # For NDI, try openh264dec first, fall back to avdec_h264
                decoder = Gst.ElementFactory.make('openh264dec', None)
                if not decoder:
                    self.log("   openh264dec not available, using avdec_h264")
                    decoder = Gst.ElementFactory.make('avdec_h264', None)
            elif not self.use_hls:
                # Direct H264 to MP4 without transcoding
                self.log("   📦 Direct H264 → MP4 (no transcoding)")
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
                # Direct VP9 to WebM without transcoding
                self.log("   📦 Direct VP9 → WebM (no transcoding)")
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
            
            if not self.ndi_direct:
                # Add transcoding elements for standard NDI mode
                self.log("   🔄 Using transcoding mode for better sync")
                videorate = Gst.ElementFactory.make('videorate', None)
                videoscale = Gst.ElementFactory.make('videoscale', None)
                capsfilter = Gst.ElementFactory.make('capsfilter', None)
                
                # Set consistent output format
                caps = Gst.Caps.from_string("video/x-raw,framerate=30/1")
                capsfilter.set_property('caps', caps)
            else:
                # For direct NDI mode, check if we can avoid decoding
                if encoding_name == 'H264':
                    # Check if we have NDI H264 support (requires newer NDI SDK)
                    # For now, we still need to decode H264
                    self.log("   ℹ️  Direct NDI mode - H264 requires decoding to raw format")
                else:
                    self.log("   ℹ️  Direct NDI mode - minimal processing")
                
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
            
            if not all([queue, depay, decoder, videoconvert]):
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
            if self.ndi_direct:
                # Direct mode - minimal processing
                if encoding_name in ['VP8', 'VP9', 'AV1']:
                    elements = [queue, depay, decoder, videoconvert]
                else:  # H264
                    elements = [queue, depay, h264parse, decoder, videoconvert]
            else:
                # Transcoding mode - full processing for better sync
                if encoding_name in ['VP8', 'VP9', 'AV1']:
                    elements = [queue, depay, decoder, videoconvert, videorate, videoscale, capsfilter]
                else:  # H264
                    elements = [queue, depay, h264parse, decoder, videoconvert, videorate, videoscale, capsfilter]
                    
            for element in elements:
                self.pipe.add(element)
                
            # Link NDI video pipeline
            if self.ndi_direct:
                # Direct mode - minimal linking
                if encoding_name in ['VP8', 'VP9', 'AV1']:
                    if not queue.link(depay):
                        self.log("Failed to link queue to depay", "error")
                        return
                    if not depay.link(decoder):
                        self.log("Failed to link depay to decoder", "error")
                        return
                    if not decoder.link(videoconvert):
                        self.log("Failed to link decoder to videoconvert", "error")
                        return
                else:  # H264
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
            else:
                # Transcoding mode - full pipeline
                if encoding_name in ['VP8', 'VP9', 'AV1']:
                    if not (queue.link(depay) and depay.link(decoder) and 
                            decoder.link(videoconvert) and videoconvert.link(videorate) and
                            videorate.link(videoscale) and videoscale.link(capsfilter)):
                        self.log("Failed to link video transcoding pipeline", "error")
                        return
                else:  # H264
                    if not (queue.link(depay) and depay.link(h264parse) and 
                            h264parse.link(decoder) and decoder.link(videoconvert) and
                            videoconvert.link(videorate) and videorate.link(videoscale) and
                            videoscale.link(capsfilter)):
                        self.log("Failed to link H264 transcoding pipeline", "error")
                        return
                
            
            # Link to NDI combiner video pad or directly to sink
            if self.ndi_combiner:
                if self.ndi_direct:
                    # For direct NDI, add capsfilter to specify optimal format
                    ndi_capsfilter = Gst.ElementFactory.make('capsfilter', 'ndi_caps')
                    if ndi_capsfilter:
                        # Use UYVY format for best NDI performance
                        ndi_caps = Gst.Caps.from_string("video/x-raw,format=UYVY")
                        ndi_capsfilter.set_property('caps', ndi_caps)
                        self.pipe.add(ndi_capsfilter)
                        ndi_capsfilter.sync_state_with_parent()
                        
                        # Link: videoconvert -> capsfilter -> ndisink
                        if videoconvert.link(ndi_capsfilter) and ndi_capsfilter.link(self.ndi_sink):
                            self.log("   ✅ Connected video directly to NDI sink (UYVY format)")
                        else:
                            self.log("Failed to link video to NDI sink", "error")
                            return
                    else:
                        # Fallback without capsfilter
                        if videoconvert.link(self.ndi_sink) == Gst.PadLinkReturn.OK:
                            self.log("   ✅ Connected video directly to NDI sink")
                        else:
                            self.log("Failed to link video to NDI sink", "error")
                            return
                else:
                    # Transcoding mode - link capsfilter to combiner
                    video_pad = self.ndi_combiner.get_static_pad('video')
                    if video_pad:
                        src_pad = capsfilter.get_static_pad('src')
                        if src_pad.link(video_pad) == Gst.PadLinkReturn.OK:
                            self.log("   ✅ Connected transcoded video to NDI combiner")
                        
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
            # Store reference for later access
            self.video_queue = video_queue
                
            # Add identity element to help with segment handling
            video_identity = Gst.ElementFactory.make('identity', 'video_identity')
            if video_identity:
                video_identity.set_property('single-segment', True)
                
            if encoding_name in ['VP8', 'VP9', 'AV1']:
                # VP8/VP9/AV1: queue -> depay -> decoder -> videoconvert -> x264enc -> h264parse -> identity -> video_queue -> mux
                if video_identity:
                    elements = [queue, depay, decoder, videoconvert_enc, encoder, h264parse, video_identity, video_queue]
                else:
                    elements = [queue, depay, decoder, videoconvert_enc, encoder, h264parse, video_queue]
            else:  # H264
                # H264: queue -> depay -> h264parse -> identity -> video_queue -> mux
                self.log("   ✅ H264 codec - no transcoding needed for HLS")
                if video_identity:
                    elements = [queue, depay, h264parse, video_identity, video_queue]
                else:
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
                # Link with or without identity  
                if video_identity:
                    if not h264parse.link(video_identity):
                        self.log("Failed to link h264parse to identity", "error")
                        return
                    if not video_identity.link(video_queue):
                        self.log("Failed to link identity to video queue", "error")
                        return
                else:
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
                    
                # Link with or without identity
                if video_identity:
                    if not h264parse.link(video_identity):
                        self.log("Failed to link h264parse to identity", "error")
                        return
                    if not video_identity.link(video_queue):
                        self.log("Failed to link identity to video queue", "error")
                        return
                else:
                    if not h264parse.link(video_queue):
                        self.log("Failed to link h264parse to video queue", "error")
                        return
                    
                # Add probe after h264parse to check flow and inject segment if needed
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
                    
            # Link video queue to mpegtsmux or sink
            if hasattr(self, 'use_internal_mux') and self.use_internal_mux:
                # For splitmuxsink, connect directly to sink
                if hasattr(self, 'hlssink') and self.hlssink:
                    video_pad = self.hlssink.request_pad_simple('video')
                    if video_pad:
                        src_pad = video_queue.get_static_pad('src')
                        if src_pad.link(video_pad) == Gst.PadLinkReturn.OK:
                            self.log("   ✅ Video connected to HLS sink")
                        else:
                            self.log("Failed to link video to HLS sink", "error")
                            return
                    else:
                        self.log("Failed to get video pad from HLS sink", "error")
                        return
            elif hasattr(self, 'hls_mux') and self.hls_mux:
                # Request video pad from mpegtsmux
                video_pad_template = self.hls_mux.get_pad_template('sink_%d')
                if video_pad_template:
                    video_pad = self.hls_mux.request_pad(video_pad_template, None, None)
                else:
                    # Fallback for different mpegtsmux versions
                    video_pad = self.hls_mux.request_pad_simple('sink_%d')
                    
                if video_pad:
                    src_pad = video_queue.get_static_pad('src')
                    
                    # Add probe to inject segment event before first buffer
                    def video_segment_probe(pad, info):
                        if info.type & Gst.PadProbeType.BUFFER:
                            if not hasattr(self, '_video_segment_injected'):
                                self._video_segment_injected = True
                                # Create and send segment event
                                segment = Gst.Segment()
                                segment.init(Gst.Format.TIME)
                                segment.set_running_time(Gst.Format.TIME, 0)
                                event = Gst.Event.new_segment(segment)
                                video_pad.send_event(event)
                                self.log("   ✅ Injected segment event for video mux pad")
                            # Remove probe after first buffer
                            return Gst.PadProbeReturn.REMOVE
                        return Gst.PadProbeReturn.OK
                        
                    src_pad.add_probe(
                        Gst.PadProbeType.BUFFER,
                        video_segment_probe
                    )
                    
                    if src_pad.link(video_pad) == Gst.PadLinkReturn.OK:
                        self.log("   ✅ Video connected to mpegtsmux")
                        # Store pad reference
                        self.video_mux_pad = video_pad
                    else:
                        self.log("Failed to link video to mpegtsmux", "error")
                        return
                else:
                    self.log("Failed to get video pad from mpegtsmux", "error")
                    return
            else:
                self.log("HLS mux not available", "error")
                return
                    
            # Sync states for all elements
            for element in elements:
                element.sync_state_with_parent()
                
            # For HLS, ensure proper synchronization
            if self.use_hls:
                # Explicitly set the pipeline to PLAYING state now that video is connected
                # This helps ensure segment events propagate properly
                if hasattr(self, 'pipe') and self.pipe:
                    current_state = self.pipe.get_state(0)[1]
                    if current_state != Gst.State.PLAYING:
                        self.pipe.set_state(Gst.State.PLAYING)
                        self.log("   ▶️  Set pipeline to PLAYING state after video connection")
                    
            # Track that video is connected
            self.hls_video_connected = True
            
            # Check if both streams are ready to start
            self.check_hls_streams_ready()
                
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
                    state_name = state.value_name if hasattr(state, 'value_name') else str(state)
                    self.log(f"   HLS sink status check - State: {state_name}, Video buffers: {getattr(self, '_probe_counter', 0)}")
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
            
            # Add watchdog for NDI freezing
            def ndi_watchdog():
                if hasattr(self, '_probe_counter') and hasattr(self, '_last_watchdog_count'):
                    if self._probe_counter == self._last_watchdog_count:
                        self.log("   ⚠️  NDI video flow stuck - no new buffers in 10 seconds", "warning")
                        self.log("   ℹ️  This might be the known NDI cool-down issue", "info")
                        self.log("   ℹ️  Try restarting after waiting 1-2 minutes", "info")
                        
                        # Log element states for debugging
                        if decoder:
                            state = decoder.get_state(0)
                            self.log(f"   Decoder state: {state[1]}")
                        if self.ndi_combiner:
                            state = self.ndi_combiner.get_state(0)
                            self.log(f"   NDI combiner state: {state[1]}")
                        if self.ndi_sink:
                            state = self.ndi_sink.get_state(0)
                            self.log(f"   NDI sink state: {state[1]}")
                            
                        return False  # Stop watchdog
                
                self._last_watchdog_count = getattr(self, '_probe_counter', 0)
                return True  # Continue
            
            # Set initial count and start watchdog after 10 seconds
            self._last_watchdog_count = 0
            GLib.timeout_add(10000, ndi_watchdog)
            
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
                # Store reference for later access
                self.audio_queue = audio_queue
                # Add identity element for audio segment handling
                audio_identity = Gst.ElementFactory.make('identity', 'audio_identity')
                if audio_identity:
                    audio_identity.set_property('single-segment', True)
            else:
                # For non-HLS, save OPUS directly in WebM container without transcoding
                opusparse = Gst.ElementFactory.make('opusparse', None)
                webmmux = Gst.ElementFactory.make('webmmux', None)
                extension = 'webm'
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
            if audio_identity:
                elements = [queue, depay, decoder, audioconvert, audioresample, aacenc, aacparse, audio_identity, audio_queue]
            else:
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
            # Link with or without identity
            if audio_identity:
                if not aacparse.link(audio_identity):
                    self.log("Failed to link aacparse to audio identity", "error")
                    return
                if not audio_identity.link(audio_queue):
                    self.log("Failed to link audio identity to audio queue", "error")
                    return
            else:
                if not aacparse.link(audio_queue):
                    self.log("Failed to link aacparse to audio queue", "error")
                    return
                
            # Link audio queue to mpegtsmux or sink
            if hasattr(self, 'use_internal_mux') and self.use_internal_mux:
                # For splitmuxsink, connect directly to sink
                if hasattr(self, 'hlssink') and self.hlssink:
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
            elif hasattr(self, 'hls_mux') and self.hls_mux:
                # Request audio pad from mpegtsmux
                audio_pad_template = self.hls_mux.get_pad_template('sink_%d')
                if audio_pad_template:
                    audio_pad = self.hls_mux.request_pad(audio_pad_template, None, None)
                else:
                    # Fallback for different mpegtsmux versions
                    audio_pad = self.hls_mux.request_pad_simple('sink_%d')
                    
                if audio_pad:
                    src_pad = audio_queue.get_static_pad('src')
                    
                    # Add probe to inject segment event before first buffer
                    def audio_segment_probe(pad, info):
                        if info.type & Gst.PadProbeType.BUFFER:
                            if not hasattr(self, '_audio_segment_injected'):
                                self._audio_segment_injected = True
                                # Create and send segment event
                                segment = Gst.Segment()
                                segment.init(Gst.Format.TIME)
                                segment.set_running_time(Gst.Format.TIME, 0)
                                event = Gst.Event.new_segment(segment)
                                audio_pad.send_event(event)
                                self.log("   ✅ Injected segment event for audio mux pad")
                            # Remove probe after first buffer
                            return Gst.PadProbeReturn.REMOVE
                        return Gst.PadProbeReturn.OK
                        
                    src_pad.add_probe(
                        Gst.PadProbeType.BUFFER,
                        audio_segment_probe
                    )
                    
                    if src_pad.link(audio_pad) == Gst.PadLinkReturn.OK:
                        self.log("   ✅ Audio connected to mpegtsmux")
                        # Store pad reference
                        self.audio_mux_pad = audio_pad
                    else:
                        self.log("Failed to link audio to mpegtsmux", "error")
                        return
                else:
                    self.log("Failed to get audio pad from mpegtsmux", "error")
                    return
            else:
                self.log("HLS mux not available for audio", "error")
                return
                
            # Sync states
            for element in elements:
                element.sync_state_with_parent()
                
                
                    
            # Track that audio is connected
            self.hls_audio_connected = True
            
            # Check if both streams are ready to start
            self.check_hls_streams_ready()
                
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
            # Non-HLS mode - save OPUS directly without transcoding
            filesink = Gst.ElementFactory.make('filesink', None)
            
            if not all([queue, depay, opusparse, webmmux, filesink]):
                self.log("Failed to create audio elements", "error")
                return
                
            import datetime
            timestamp = int(datetime.datetime.now().timestamp())
            filename = f"{self.room}_{self.stream_id}_{timestamp}_audio.{extension}"
            filesink.set_property('location', filename)
            self.audio_filename = filename
            self.log(f"   📦 Direct OPUS → WebM (no transcoding)")
            self.log(f"   Output file: {filename}")
            
            # Add elements to pipeline
            elements = [queue, depay, opusparse, webmmux, filesink]
            for element in elements:
                self.pipe.add(element)
                
            # Link elements
            if not queue.link(depay):
                self.log("Failed to link queue to depay", "error")
                return
            if not depay.link(opusparse):
                self.log("Failed to link depay to opusparse", "error")
                return
            if not opusparse.link(webmmux):
                self.log("Failed to link opusparse to webmmux", "error")
                return
            if not webmmux.link(filesink):
                self.log("Failed to link webmmux to filesink", "error")
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

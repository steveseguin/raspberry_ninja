#!/usr/bin/env python3
"""
WebRTC Subprocess Handler with HLS Recording
This version implements audio/video muxing to HLS format within each subprocess.
Based on recommendations from Gemini Pro 2.5 and OpenAI o3-mini.
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


class HLSWebRTCHandler:
    """Handles WebRTC pipeline with HLS recording in a subprocess"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.stream_id = config.get('stream_id')
        self.mode = config.get('mode', 'view')
        self.room = config.get('room')
        self.record_file = config.get('record_file')
        self.record_audio = config.get('record_audio', False)
        
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
        self.recording_started = False
        self.hls_mux = None
        self.hls_filename = None
        self.audio_pad_connected = False
        self.video_pad_connected = False
        
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
        
        if msg_type == 'start':
            self.start_pipeline()
        elif msg_type == 'offer' or msg_type == 'sdp':
            # Handle both 'offer' and 'sdp' message types
            if msg_type == 'sdp':
                # Format: {type: 'sdp', sdp_type: 'offer', sdp: '...', session_id: '...'}
                offer_data = {
                    'sdp': msg.get('sdp'),
                    'type': msg.get('sdp_type', 'offer')
                }
                self.session_id = msg.get('session_id')
            else:
                offer_data = msg.get('data', msg)
            self.handle_remote_offer(offer_data)
        elif msg_type == 'ice':
            # ICE candidates can be in different formats
            if 'data' in msg:
                self.add_ice_candidate(msg['data'])
            else:
                # Direct format: {type: 'ice', candidate: '...', sdpMLineIndex: 0}
                self.add_ice_candidate(msg)
        elif msg_type == 'stop':
            self.shutdown()
        else:
            self.log(f"Unknown message type: {msg_type}", "warning")
            
    def setup_hls_recording(self):
        """Setup HLS recording pipeline elements"""
        if self.hls_mux:
            self.log("HLS recording already setup")
            return
            
        try:
            # Create HLS recording elements
            if self.config.get('use_splitmuxsink', False):
                # Option 1: Using splitmuxsink (recommended by Gemini)
                self.hls_mux = Gst.ElementFactory.make('splitmuxsink', 'hls_mux')
                self.hls_mux.set_property('muxer', 'mpegtsmux')
                self.hls_mux.set_property('max-size-time', 10 * Gst.SECOND)  # 10 second segments
                
                # Set filenames
                timestamp = int(datetime.datetime.now().timestamp())
                base_name = f"{self.room}_{self.stream_id}_{timestamp}"
                self.hls_mux.set_property('location', f"{base_name}_segment_%05d.ts")
                self.hls_mux.set_property('playlist-location', f"{base_name}.m3u8")
                self.hls_filename = f"{base_name}.m3u8"
            else:
                # Option 2: Using mpegtsmux + hlssink (traditional approach)
                self.hls_mux = Gst.ElementFactory.make('mpegtsmux', 'hls_mux')
                
                # Create HLS sink
                hlssink = Gst.ElementFactory.make('hlssink', 'hlssink')
                hlssink.set_property('max-files', 0)  # Keep all segments
                hlssink.set_property('target-duration', 10)  # 10 second segments
                hlssink.set_property('playlist-length', 0)  # Full playlist
                
                # Set filenames
                timestamp = int(datetime.datetime.now().timestamp())
                base_name = f"{self.room}_{self.stream_id}_{timestamp}"
                hlssink.set_property('location', f"{base_name}_segment_%05d.ts")
                hlssink.set_property('playlist-location', f"{base_name}.m3u8")
                self.hls_filename = f"{base_name}.m3u8"
                
                # Add to pipeline and link
                self.pipe.add(self.hls_mux)
                self.pipe.add(hlssink)
                self.hls_mux.link(hlssink)
                hlssink.sync_state_with_parent()
                
            self.pipe.add(self.hls_mux)
            self.hls_mux.sync_state_with_parent()
            
            self.log(f"🎬 HLS recording setup complete: {self.hls_filename}")
            self.recording_started = True
            
        except Exception as e:
            self.log(f"Failed to setup HLS recording: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            
    def handle_video_pad(self, pad):
        """Handle video pad - connect to HLS muxer"""
        # Get codec info from caps
        caps = pad.get_current_caps()
        structure = caps.get_structure(0)
        encoding_name = structure.get_string('encoding-name')
        width = structure.get_int('width')[1] if structure.has_field('width') else 'unknown'
        height = structure.get_int('height')[1] if structure.has_field('height') else 'unknown'
        
        self.log(f"📹 VIDEO STREAM DETECTED: {self.stream_id}")
        self.log(f"   Codec: {encoding_name}, Resolution: {width}x{height}")
        
        # Setup HLS recording if not already done
        if not self.hls_mux:
            self.setup_hls_recording()
            
        # Create video processing branch
        queue = Gst.ElementFactory.make('queue', 'video-queue')
        
        # Depayload based on codec
        if encoding_name == 'VP8':
            depay = Gst.ElementFactory.make('rtpvp8depay', 'video-depay')
            # For HLS, we need to transcode VP8 to H264
            decoder = Gst.ElementFactory.make('vp8dec', 'video-decoder')
            encoder = Gst.ElementFactory.make('x264enc', 'video-encoder')
            encoder.set_property('tune', 'zerolatency')
            encoder.set_property('bitrate', 2000)  # 2 Mbps
            encoder.set_property('key-int-max', 30)  # Keyframe every 30 frames
            parse = Gst.ElementFactory.make('h264parse', 'video-parse')
            elements = [queue, depay, decoder, encoder, parse]
        elif encoding_name == 'H264':
            depay = Gst.ElementFactory.make('rtph264depay', 'video-depay')
            parse = Gst.ElementFactory.make('h264parse', 'video-parse')
            elements = [queue, depay, parse]
        else:
            self.log(f"Unsupported video codec: {encoding_name}", "error")
            return
            
        # Add elements to pipeline
        for element in elements:
            self.pipe.add(element)
            
        # Link elements
        for i in range(len(elements) - 1):
            if not elements[i].link(elements[i + 1]):
                self.log(f"Failed to link {elements[i].get_name()} to {elements[i + 1].get_name()}", "error")
                return
                
        # Request video pad from muxer and link
        if self.config.get('use_splitmuxsink', False):
            mux_pad = self.hls_mux.request_pad_simple('video_%u')
        else:
            mux_pad = self.hls_mux.request_pad_simple('sink_%d')
            
        last_element = elements[-1]
        src_pad = last_element.get_static_pad('src')
        if src_pad.link(mux_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link video to muxer", "error")
            return
            
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
            
        # Link pad to queue
        sink_pad = queue.get_static_pad('sink')
        if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link video pad to queue", "error")
            return
            
        self.log("   ✅ Video connected to HLS muxer")
        self.video_pad_connected = True
        
    def handle_audio_pad(self, pad):
        """Handle audio pad - connect to HLS muxer"""
        # Get codec info from caps
        caps = pad.get_current_caps()
        structure = caps.get_structure(0)
        encoding_name = structure.get_string('encoding-name')
        clock_rate = structure.get_int('clock-rate')[1] if structure.has_field('clock-rate') else 'unknown'
        
        self.log(f"🎤 AUDIO STREAM DETECTED: {self.stream_id}")
        self.log(f"   Codec: {encoding_name}, Sample rate: {clock_rate} Hz")
        
        if not self.record_audio:
            self.log(f"   ⏸️  Audio recording disabled")
            # Just fakesink audio
            fakesink = Gst.ElementFactory.make('fakesink', None)
            self.pipe.add(fakesink)
            fakesink.sync_state_with_parent()
            pad.link(fakesink.get_static_pad('sink'))
            return
            
        # Setup HLS recording if not already done
        if not self.hls_mux:
            self.setup_hls_recording()
            
        # Create audio processing branch
        queue = Gst.ElementFactory.make('queue', 'audio-queue')
        
        # Process based on codec
        if encoding_name == 'OPUS':
            # For HLS, we need to transcode Opus to AAC
            depay = Gst.ElementFactory.make('rtpopusdepay', 'audio-depay')
            decoder = Gst.ElementFactory.make('opusdec', 'audio-decoder')
            convert = Gst.ElementFactory.make('audioconvert', 'audio-convert')
            resample = Gst.ElementFactory.make('audioresample', 'audio-resample')
            encoder = Gst.ElementFactory.make('avenc_aac', 'audio-encoder')
            encoder.set_property('bitrate', 128000)  # 128 kbps
            parse = Gst.ElementFactory.make('aacparse', 'audio-parse')
            elements = [queue, depay, decoder, convert, resample, encoder, parse]
        elif encoding_name in ['PCMU', 'PCMA']:
            # For G.711, transcode to AAC
            depay_name = f'rtp{encoding_name.lower()}depay'
            depay = Gst.ElementFactory.make(depay_name, 'audio-depay')
            decoder_name = f'{encoding_name.lower()}dec'
            decoder = Gst.ElementFactory.make(decoder_name, 'audio-decoder')
            convert = Gst.ElementFactory.make('audioconvert', 'audio-convert')
            resample = Gst.ElementFactory.make('audioresample', 'audio-resample')
            encoder = Gst.ElementFactory.make('avenc_aac', 'audio-encoder')
            encoder.set_property('bitrate', 128000)
            parse = Gst.ElementFactory.make('aacparse', 'audio-parse')
            elements = [queue, depay, decoder, convert, resample, encoder, parse]
        else:
            self.log(f"Unsupported audio codec: {encoding_name}", "error")
            return
            
        # Add elements to pipeline
        for element in elements:
            self.pipe.add(element)
            
        # Link elements
        for i in range(len(elements) - 1):
            if not elements[i].link(elements[i + 1]):
                self.log(f"Failed to link {elements[i].get_name()} to {elements[i + 1].get_name()}", "error")
                return
                
        # Request audio pad from muxer and link
        if self.config.get('use_splitmuxsink', False):
            mux_pad = self.hls_mux.request_pad_simple('audio_%u')
        else:
            mux_pad = self.hls_mux.request_pad_simple('sink_%d')
            
        last_element = elements[-1]
        src_pad = last_element.get_static_pad('src')
        if src_pad.link(mux_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link audio to muxer", "error")
            return
            
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
            
        # Link pad to queue
        sink_pad = queue.get_static_pad('sink')
        if pad.link(sink_pad) != Gst.PadLinkReturn.OK:
            self.log("Failed to link audio pad to queue", "error")
            return
            
        self.log("   ✅ Audio connected to HLS muxer")
        self.audio_pad_connected = True
        
    def on_pad_added(self, element, pad):
        """Handle new pad added to webrtcbin"""
        pad_name = pad.get_name()
        self.log(f"New pad added: {pad_name}")
        
        # Check if it's an RTP pad
        if not pad_name.startswith('src_'):
            self.log(f"Ignoring non-RTP pad: {pad_name}")
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
            self.handle_video_pad(pad)
        elif media_type == 'audio':
            self.handle_audio_pad(pad)
        else:
            self.log(f"Unknown media type: {media_type}", "warning")
            
    def start_pipeline(self):
        """Start the GStreamer pipeline"""
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
                
            if 'turn_server' in self.config and self.config['turn_server']:
                self.webrtc.set_property('turn-server', self.config['turn_server'])
                self.log(f"TURN server configured")
            elif 'stun_server' not in self.config:
                # Default STUN server if none provided
                self.webrtc.set_property('stun-server', 'stun://stun.cloudflare.com:3478')
                
            # Start pipeline
            self.pipe.set_state(Gst.State.PLAYING)
            self.log("Pipeline set to PLAYING state")
            
            # Send ready signal
            self.send_message({"type": "pipeline_ready"})
            
        except Exception as e:
            self.log(f"Failed to start pipeline: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            
    def on_ice_connection_state_notify(self, element, pspec):
        """Monitor ICE connection state changes"""
        state = element.get_property('ice-connection-state')
        self.log(f"ICE connection state: {state.value_name}")
        
        # Check for pads when connected
        if state == GstWebRTC.WebRTCICEConnectionState.CONNECTED:
            self.log("ICE connected, checking for pads...")
            GLib.timeout_add(1000, self.check_for_pads)
        elif state == GstWebRTC.WebRTCICEConnectionState.COMPLETED:
            self.log("ICE completed, checking for pads...")
            GLib.timeout_add(500, self.check_for_pads)
            
    def check_for_pads(self):
        """Check if pads have been added"""
        try:
            # Check WebRTC state
            ice_state = self.webrtc.get_property('ice-connection-state')
            self.log(f"Current ICE state during pad check: {ice_state.value_name}")
            
            # Iterate through pads
            pad_count = 0
            src_pads = list(self.webrtc.iterate_src_pads())
            self.log(f"Total pads found: {len(src_pads)}")
            
            for pad in src_pads:
                pad_count += 1
                pad_name = pad.get_name()
                self.log(f"Found pad #{pad_count}: {pad_name}")
                
                # Try to get caps
                caps = pad.get_current_caps()
                if caps:
                    self.log(f"  Caps: {caps.to_string()}")
                    # Try to process this pad if it's an RTP pad
                    if pad_name.startswith('src_'):
                        self.log(f"  Processing RTP pad: {pad_name}")
                        self.process_pad_with_caps(pad, caps)
                else:
                    self.log(f"  No caps available yet")
                    
            if pad_count == 0:
                self.log("No source pads found yet")
                # Try again in a bit
                return True  # Continue timeout
                
        except Exception as e:
            self.log(f"ERROR checking pads: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            
        return False  # Stop timeout
            
    def on_ice_gathering_state_notify(self, element, pspec):
        """Monitor ICE gathering state changes"""
        state = element.get_property('ice-gathering-state')
        self.log(f"ICE gathering state: {state.value_name}")
        
    def on_ice_candidate(self, element, mline, candidate):
        """Handle local ICE candidate"""
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
        # Handle different ICE data formats
        if isinstance(ice_data, dict):
            candidate = ice_data.get('candidate')
            sdp_mline_index = ice_data.get('sdpMLineIndex', 0)
        else:
            # If ice_data is not a dict, it might be the candidate string directly
            candidate = ice_data
            sdp_mline_index = 0
        
        if candidate:
            self.webrtc.emit('add-ice-candidate', sdp_mline_index, candidate)
            self.log(f"Added ICE candidate for mline {sdp_mline_index}")
            
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
        
    def on_data_channel(self, element, channel):
        """Handle data channel creation"""
        self.log(f"Data channel created: {channel.get_property('label')}")
        
    def handle_remote_offer(self, offer_data):
        """Handle offer from remote peer"""
        try:
            self.log(f"Processing remote offer")
            
            # Ensure pipeline is playing
            if self.pipe.get_state(0)[1] != Gst.State.PLAYING:
                self.pipe.set_state(Gst.State.PLAYING)
                self.log("Set pipeline to PLAYING for offer handling")
            
            self.pipeline_start_time = time.time()
            
            # Create offer object
            offer_sdp = offer_data['sdp']
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(offer_sdp)
            if res != GstSdp.SDPResult.OK:
                self.log(f"Failed to parse SDP: {res}", "error")
                return
                
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # Create promise for setting remote description
            promise = Gst.Promise.new_with_change_func(
                self.on_remote_description_set,
                None
            )
            
            # Set remote description
            self.webrtc.emit('set-remote-description', offer, promise)
            
        except Exception as e:
            self.log(f"Error handling offer: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            
    def on_remote_description_set(self, promise, user_data):
        """Called when remote description is set"""
        self.log("Remote description callback triggered")
        
        result = promise.wait()
        self.log(f"Remote desc promise result: {result}")
        
        reply = promise.get_reply()
        if result != Gst.PromiseResult.REPLIED:
            self.log(f"Failed to set remote description, result: {result}", "error")
            return
            
        self.log("Remote description set, creating answer")
        
        # Create answer
        promise = Gst.Promise.new_with_change_func(
            self.on_answer_created,
            None
        )
        self.webrtc.emit('create-answer', None, promise)
        
    def on_answer_created(self, promise, user_data):
        """Called when answer is created"""
        self.log("Answer creation callback triggered")
        
        result = promise.wait()
        self.log(f"Promise wait result: {result}")
        
        reply = promise.get_reply()
        if not reply:
            self.log("No reply from promise", "error")
            return
            
        if result != Gst.PromiseResult.REPLIED:
            self.log(f"Failed to create answer, result: {result}", "error")
            return
            
        # Get the answer
        answer = reply.get_value('answer')
        if not answer:
            self.log("No answer in reply", "error")
            return
            
        # Extract SDP
        sdp = answer.sdp.as_text()
        self.log("Answer created successfully")
        
        # Log a snippet of the answer to verify it contains media
        sdp_lines = sdp.split('\n')
        media_lines = [line for line in sdp_lines if line.startswith('m=')]
        self.log(f"Media lines in answer: {media_lines}")
        
        # Set local description
        promise = Gst.Promise.new_with_change_func(
            self.on_local_description_set,
            None
        )
        self.webrtc.emit('set-local-description', answer, promise)
        
        # Send answer to parent
        self.send_message({
            "type": "answer",
            "data": {
                "sdp": sdp,
                "type": "answer"
            }
        })
        
    def on_local_description_set(self, promise, user_data):
        """Called when local description is set"""
        reply = promise.get_reply()
        if promise.wait() != Gst.PromiseResult.REPLIED:
            self.log("Failed to set local description", "error")
            return
            
        self.log("Local description set successfully")
        
        # Schedule a check for pads after negotiation completes
        GLib.timeout_add(2000, self.check_for_pads)
        
    def shutdown(self):
        """Shutdown the handler"""
        self.log("Shutting down...")
        
        # Log recording status
        if self.recording_started and self.hls_filename:
            self.log(f"🛑 HLS RECORDING STOPPED: {self.stream_id}")
            
            # Check if playlist exists
            if os.path.exists(self.hls_filename):
                size = os.path.getsize(self.hls_filename)
                
                # Count segments
                base_dir = os.path.dirname(self.hls_filename) or '.'
                base_name = os.path.basename(self.hls_filename).replace('.m3u8', '')
                segments = [f for f in os.listdir(base_dir) if f.startswith(base_name) and f.endswith('.ts')]
                
                streams = []
                if self.video_pad_connected:
                    streams.append("video")
                if self.audio_pad_connected:
                    streams.append("audio")
                stream_info = "+".join(streams) if streams else "no streams"
                
                self.log(f"   Playlist: {self.hls_filename} ({size} bytes)")
                self.log(f"   Segments: {len(segments)} files")
                self.log(f"   Streams: {stream_info}")
            else:
                self.log(f"   Warning: Playlist file not found")
                
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
        
        # Enable HLS by default
        config['use_splitmuxsink'] = config.get('use_splitmuxsink', True)
        
        # Create handler
        handler = HLSWebRTCHandler(config)
        
        # Send ready signal
        handler.send_message({"type": "ready"})
        
        # Start pipeline immediately - WebRTC connections will come later
        handler.start_pipeline()
        
        # Run main loop
        handler.run()
        
    except Exception as e:
        sys.stderr.write(f"Subprocess error: {e}\n")
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
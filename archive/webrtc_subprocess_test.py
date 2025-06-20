#!/usr/bin/env python3
"""
WebRTC Subprocess Handler - Test different muxing formats
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


class TestWebRTCHandler:
    """Test WebRTC handler with different muxing options"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.stream_id = config.get('stream_id')
        self.mode = config.get('mode', 'view')
        self.room = config.get('room')
        self.record_file = config.get('record_file')
        self.record_audio = config.get('record_audio', False)
        self.mux_format = config.get('mux_format', 'webm')  # webm, mp4, ts, mkv
        
        # Pipeline state
        self.pipe = None
        self.webrtc = None
        self.session_id = None
        self.pipeline_started = False
        
        # Track what's connected
        self.video_connected = False
        self.audio_connected = False
        self.pad_count = 0
        
        # IPC communication
        self.running = True
        
        # ICE candidates queue
        self.ice_candidates = []
        
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
            
            # Start pipeline
            self.pipe.set_state(Gst.State.PLAYING)
            self.pipeline_start_time = time.time()
            self.pipeline_started = True
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
        self.pad_count += 1
        pad_name = pad.get_name()
        self.log(f"🎬 PAD #{self.pad_count} ADDED: {pad_name}")
        
        # Get pad direction
        direction = pad.get_direction()
        self.log(f"   Direction: {direction.value_nick}")
        
        # Check if it's an RTP pad
        if not pad_name.startswith('src_'):
            self.log(f"   Not a src pad, ignoring")
            return
            
        # Get pad caps to determine media type
        caps = pad.get_current_caps()
        if not caps:
            # Sometimes caps aren't immediately available, wait a bit
            self.log(f"   No caps yet, scheduling check")
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
        self.log(f"   Full caps: {caps.to_string()}")
        
        if media_type == 'video':
            self.handle_video_pad(pad, structure)
        elif media_type == 'audio':
            self.handle_audio_pad(pad, structure)
        else:
            self.log(f"Unknown media type: {media_type}", "warning")
            
    def handle_video_pad(self, pad, structure):
        """Handle video pad - connect to recording pipeline"""
        if self.video_connected:
            self.log("Video already connected, ignoring additional video pad")
            return
            
        encoding_name = structure.get_string('encoding-name')
        self.log(f"📹 VIDEO STREAM: {encoding_name}")
        
        # Create recording pipeline based on format
        timestamp = int(datetime.datetime.now().timestamp())
        
        if self.mux_format == 'webm':
            # WebM recording (VP8 only)
            if encoding_name == 'VP8':
                pipeline_str = f"queue ! rtpvp8depay ! webmmux ! filesink location={self.room}_{self.stream_id}_{timestamp}.webm"
            else:
                self.log(f"WebM doesn't support {encoding_name}, using fakesink", "warning")
                pipeline_str = "fakesink"
                
        elif self.mux_format == 'mp4':
            # MP4 recording (H264 only)
            if encoding_name == 'H264':
                pipeline_str = f"queue ! rtph264depay ! h264parse ! mp4mux ! filesink location={self.room}_{self.stream_id}_{timestamp}.mp4"
            else:
                self.log(f"MP4 doesn't support {encoding_name}, using fakesink", "warning")
                pipeline_str = "fakesink"
                
        elif self.mux_format == 'ts':
            # MPEG-TS recording (supports both)
            if encoding_name == 'VP8':
                pipeline_str = f"queue ! rtpvp8depay ! mpegtsmux ! filesink location={self.room}_{self.stream_id}_{timestamp}.ts"
            elif encoding_name == 'H264':
                pipeline_str = f"queue ! rtph264depay ! h264parse ! mpegtsmux ! filesink location={self.room}_{self.stream_id}_{timestamp}.ts"
            else:
                self.log(f"Unknown codec {encoding_name}, using fakesink", "warning")
                pipeline_str = "fakesink"
                
        elif self.mux_format == 'mkv':
            # Matroska recording (supports both)
            if encoding_name == 'VP8':
                pipeline_str = f"queue ! rtpvp8depay ! matroskamux ! filesink location={self.room}_{self.stream_id}_{timestamp}.mkv"
            elif encoding_name == 'H264':
                pipeline_str = f"queue ! rtph264depay ! h264parse ! matroskamux ! filesink location={self.room}_{self.stream_id}_{timestamp}.mkv"
            else:
                self.log(f"Unknown codec {encoding_name}, using fakesink", "warning")
                pipeline_str = "fakesink"
        else:
            self.log(f"Unknown mux format {self.mux_format}, using fakesink", "error")
            pipeline_str = "fakesink"
            
        # Create the recording bin
        self.log(f"Creating recording pipeline: {pipeline_str}")
        recording_bin = Gst.parse_bin_from_description(pipeline_str, True)
        
        if recording_bin:
            self.pipe.add(recording_bin)
            recording_bin.sync_state_with_parent()
            
            # Link pad to recording bin
            sink_pad = recording_bin.get_static_pad('sink')
            if pad.link(sink_pad) == Gst.PadLinkReturn.OK:
                self.video_connected = True
                self.log(f"✅ Video recording started with {self.mux_format} format")
            else:
                self.log("Failed to link video pad", "error")
        else:
            self.log("Failed to create recording bin", "error")
            
    def handle_audio_pad(self, pad, structure):
        """Handle audio pad"""
        if not self.record_audio:
            self.log("Audio recording disabled, using fakesink")
            fakesink = Gst.ElementFactory.make('fakesink', None)
            self.pipe.add(fakesink)
            fakesink.sync_state_with_parent()
            pad.link(fakesink.get_static_pad('sink'))
            return
            
        encoding_name = structure.get_string('encoding-name')
        self.log(f"🎤 AUDIO STREAM: {encoding_name}")
        
        # For now, just use fakesink for audio
        # TODO: Implement audio muxing
        fakesink = Gst.ElementFactory.make('fakesink', None)
        self.pipe.add(fakesink)
        fakesink.sync_state_with_parent()
        pad.link(fakesink.get_static_pad('sink'))
        self.log("Audio using fakesink for now")
        
    def on_ice_connection_state_notify(self, element, pspec):
        """Monitor ICE connection state changes"""
        state = element.get_property('ice-connection-state')
        self.log(f"ICE connection state: {state.value_name}")
        
        if state == GstWebRTC.WebRTCICEConnectionState.CONNECTED:
            self.log("✅ ICE connected successfully!")
            
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
        
    def handle_remote_offer(self, offer_data):
        """Handle offer from remote peer"""
        try:
            self.log(f"Processing remote offer")
            
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
            
            # Set remote description
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', offer, promise)
            
            # Wait for completion
            promise.wait()
            result = promise.get_reply()
            
            self.log("Remote description set, creating answer")
            
            # Create answer
            promise = Gst.Promise.new()
            self.webrtc.emit('create-answer', None, promise)
            
            # Wait for answer
            promise.wait()
            reply = promise.get_reply()
            
            # Get answer from reply
            answer = reply.get_value('answer')
            if not answer:
                self.log("Failed to get answer from reply", "error")
                return
                
            # Set local description
            promise = Gst.Promise.new()
            self.webrtc.emit('set-local-description', answer, promise)
            promise.wait()
            
            self.log("Local description set successfully")
            
            # Send answer back
            answer_sdp = answer.sdp.as_text()
            self.send_message({
                "type": "answer",
                "data": {
                    "sdp": answer_sdp,
                    "type": "answer"
                }
            })
            
            self.log("Answer sent to parent process")
            
        except Exception as e:
            self.log(f"Error handling offer: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            
    def shutdown(self):
        """Shutdown the handler"""
        self.log("Shutting down...")
        
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
        handler = TestWebRTCHandler(config)
        
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
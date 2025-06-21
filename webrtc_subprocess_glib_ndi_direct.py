#!/usr/bin/env python3
"""
Alternative NDI implementation using direct ndisink (no combiner)
This bypasses the freezing issue with ndisinkcombiner
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
    """Handles WebRTC pipeline with direct NDI output (no combiner)"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.stream_id = config.get('stream_id')
        self.mode = config.get('mode', 'view')
        self.room = config.get('room')
        self.room_ndi = config.get('room_ndi', False)
        self.ndi_name = config.get('ndi_name')
        
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
        
        # NDI state
        self.ndi_video_sink = None
        self.ndi_audio_sink = None
        
        # Main loop
        self.main_loop = GLib.MainLoop()
        
        # Setup stdin monitoring
        self.setup_stdin_watch()
        
    def setup_stdin_watch(self):
        """Setup monitoring of stdin for messages"""
        self.stdin_channel = GLib.IOChannel.unix_new(sys.stdin.fileno())
        self.stdin_channel.set_encoding(None)
        self.stdin_channel.set_buffered(False)
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
            
        return True
        
    def log(self, message: str, level: str = "info"):
        """Send log message to parent process"""
        log_msg = {
            "type": "log",
            "level": level,
            "message": f"[{self.stream_id}] {message}"
        }
        self.send_message(log_msg)
        
    def send_message(self, message: dict):
        """Send message to parent process via stdout"""
        try:
            json_str = json.dumps(message)
            sys.stdout.write(json_str + '\n')
            sys.stdout.flush()
        except Exception as e:
            # Can't log error about logging...
            pass
            
    def handle_message(self, msg: dict):
        """Handle message from parent process"""
        msg_type = msg.get('type')
        
        if msg_type == 'sdp':
            GLib.idle_add(self.handle_sdp_message, msg)
        elif msg_type == 'ice':
            GLib.idle_add(self.handle_ice_message, msg)
        elif msg_type == 'start':
            GLib.idle_add(self.start_pipeline)
        elif msg_type == 'stop':
            GLib.idle_add(self.shutdown)
            
    def create_pipeline(self):
        """Create the GStreamer pipeline"""
        self.log("Creating pipeline with DIRECT NDI output...")
        
        # Create pipeline
        self.pipe = Gst.Pipeline.new('webrtc-pipeline')
        
        # Create WebRTC bin
        self.webrtc = Gst.ElementFactory.make('webrtcbin', 'webrtc')
        if not self.webrtc:
            self.log("Failed to create webrtcbin", "error")
            return False
            
        # Configure WebRTC
        self.webrtc.set_property('bundle-policy', GstWebRTC.WebRTCBundlePolicy.MAX_BUNDLE)
        
        # Set up STUN/TURN servers
        stun_server = self.config.get('stun_server', 'stun://stun.cloudflare.com:3478')
        self.webrtc.set_property('stun-server', stun_server)
        self.log(f"STUN server: {stun_server}")
        
        turn_server = self.config.get('turn_server')
        if turn_server:
            self.webrtc.set_property('turn-server', turn_server)
            self.log("TURN server configured")
            
        # Add webrtc to pipeline
        self.pipe.add(self.webrtc)
        
        # Connect signals
        self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
        self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)
        self.webrtc.connect('pad-added', self.on_pad_added)
        self.webrtc.connect('on-ice-connection-state', self.on_ice_connection_state)
        self.webrtc.connect('on-connection-state', self.on_connection_state)
        self.webrtc.connect('on-data-channel', self.on_data_channel)
        
        return True
        
    def on_pad_added(self, element, pad):
        """Handle new pad from webrtcbin"""
        pad_name = pad.get_name()
        self.log(f"New pad added: {pad_name}")
        
        # Get caps to determine media type
        caps = pad.get_current_caps()
        if not caps:
            caps = pad.query_caps()
            
        structure = caps.get_structure(0)
        media_type = structure.get_name()
        
        if media_type.startswith('video/'):
            self.handle_video_pad_direct(pad)
        elif media_type.startswith('audio/'):
            self.handle_audio_pad_direct(pad)
        elif media_type.startswith('application/'):
            self.log(f"Data channel pad: {pad_name}")
        else:
            self.log(f"Unknown pad type: {media_type}")
            
    def handle_video_pad_direct(self, pad):
        """Handle video pad with direct NDI output"""
        caps = pad.get_current_caps()
        structure = caps.get_structure(0)
        encoding_name = structure.get_string('encoding-name')
        
        self.log(f"📹 NDI VIDEO OUTPUT: {encoding_name}")
        
        # Create video processing pipeline
        queue = Gst.ElementFactory.make('queue', None)
        
        # Depayloader based on codec
        if encoding_name == 'VP8':
            depay = Gst.ElementFactory.make('rtpvp8depay', None)
            decoder = Gst.ElementFactory.make('vp8dec', None)
        elif encoding_name == 'H264':
            depay = Gst.ElementFactory.make('rtph264depay', None)
            h264parse = Gst.ElementFactory.make('h264parse', None)
            decoder = Gst.ElementFactory.make('avdec_h264', None)
        else:
            self.log(f"Unsupported codec: {encoding_name}", "error")
            return
            
        videoconvert = Gst.ElementFactory.make('videoconvert', None)
        
        # Create direct NDI video sink
        self.ndi_video_sink = Gst.ElementFactory.make('ndisink', None)
        if not self.ndi_video_sink:
            self.log("Failed to create NDI video sink", "error")
            return
            
        ndi_name = f"{self.ndi_name or self.stream_id}_video"
        self.ndi_video_sink.set_property('ndi-name', ndi_name)
        self.ndi_video_sink.set_property('sync', False)
        self.ndi_video_sink.set_property('async', False)
        
        # Add elements
        if encoding_name == 'H264':
            elements = [queue, depay, h264parse, decoder, videoconvert, self.ndi_video_sink]
        else:
            elements = [queue, depay, decoder, videoconvert, self.ndi_video_sink]
            
        for element in elements:
            self.pipe.add(element)
            
        # Link elements
        if encoding_name == 'H264':
            queue.link(depay)
            depay.link(h264parse)
            h264parse.link(decoder)
            decoder.link(videoconvert)
            videoconvert.link(self.ndi_video_sink)
        else:
            queue.link(depay)
            depay.link(decoder)
            decoder.link(videoconvert)
            videoconvert.link(self.ndi_video_sink)
            
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
            
        # Link pad
        sink_pad = queue.get_static_pad('sink')
        pad.link(sink_pad)
        
        self.log(f"   ✅ NDI video output connected: {ndi_name}")
        
    def handle_audio_pad_direct(self, pad):
        """Handle audio pad with direct NDI output"""
        caps = pad.get_current_caps()
        structure = caps.get_structure(0)
        encoding_name = structure.get_string('encoding-name')
        
        self.log(f"🎤 NDI AUDIO OUTPUT: {encoding_name}")
        
        # For now, just fakesink audio since direct NDI audio is complex
        fakesink = Gst.ElementFactory.make('fakesink', None)
        self.pipe.add(fakesink)
        fakesink.sync_state_with_parent()
        pad.link(fakesink.get_static_pad('sink'))
        
        self.log("   ℹ️  Audio output to fakesink (video-only NDI)")
        
    def handle_sdp_message(self, msg: dict):
        """Handle SDP offer/answer"""
        sdp_type = msg.get('sdp', {}).get('type')
        sdp_str = msg.get('sdp', {}).get('sdp', '')
        session_id = msg.get('session')
        
        self.log(f"Received SDP {sdp_type} (session: {session_id})")
        
        if sdp_type == 'offer':
            self.session_id = session_id
            
            if not self.pipe:
                self.create_pipeline()
                self.start_pipeline()
                
            # Set remote description
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_str)
            if res != GstSdp.SDPResult.OK:
                self.log("Failed to parse SDP", "error")
                return
                
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER, sdp_msg)
            
            promise = Gst.Promise.new_with_change_func(self.on_offer_set, None)
            self.webrtc.emit('set-remote-description', offer, promise)
            
    def on_offer_set(self, promise, _):
        """Called when remote offer is set"""
        promise.wait()
        
        # Create answer
        promise = Gst.Promise.new_with_change_func(self.on_answer_created, None)
        self.webrtc.emit('create-answer', None, promise)
        
    def on_answer_created(self, promise, _):
        """Called when answer is created"""
        promise.wait()
        reply = promise.get_reply()
        answer = reply['answer']
        
        # Set local description
        promise = Gst.Promise.new_with_change_func(self.on_answer_set, None)
        self.webrtc.emit('set-local-description', answer, promise)
        
        # Send answer
        sdp_str = answer.sdp.as_text()
        answer_msg = {
            "type": "sdp",
            "sdp": {
                "type": "answer",
                "sdp": sdp_str
            },
            "session": self.session_id
        }
        self.send_message(answer_msg)
        self.log(f"Sent SDP answer (session: {self.session_id})")
        
    def on_answer_set(self, promise, _):
        """Called when local answer is set"""
        promise.wait()
        self.log("Local description set")
        
    def on_negotiation_needed(self, element):
        """Handle negotiation needed signal"""
        self.log("Negotiation needed")
        
    def on_ice_candidate(self, element, mlineindex, candidate):
        """Handle ICE candidate"""
        self.log(f"Generated ICE candidate for mlineindex {mlineindex}")
        ice_msg = {
            "type": "ice",
            "candidate": {
                "candidate": candidate,
                "sdpMLineIndex": mlineindex
            }
        }
        self.send_message(ice_msg)
        
    def handle_ice_message(self, msg: dict):
        """Handle ICE candidate from remote"""
        candidate = msg.get('candidate', {})
        sdp_mline_index = candidate.get('sdpMLineIndex', 0)
        candidate_str = candidate.get('candidate', '')
        
        if candidate_str:
            self.webrtc.emit('add-ice-candidate', sdp_mline_index, candidate_str)
            self.log("Added ICE candidate")
            
    def on_ice_connection_state(self, element, state):
        """Handle ICE connection state changes"""
        state_name = state.value_name
        self.log(f"ICE connection state: {state_name}")
        
    def on_connection_state(self, element, state):
        """Handle WebRTC connection state changes"""
        state_name = state.value_name
        self.log(f"WebRTC connection state: {state_name}")
        
    def on_data_channel(self, element, channel):
        """Handle data channel"""
        self.log("Data channel created")
        
    def start_pipeline(self):
        """Start the pipeline"""
        if self.pipe:
            self.log("Starting pipeline...")
            self.pipe.set_state(Gst.State.PLAYING)
            self.pipeline_start_time = time.time()
            
    def shutdown(self):
        """Shutdown the pipeline and exit"""
        self.log("Shutting down...")
        
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            
        self.running = False
        self.main_loop.quit()
        
    def run(self):
        """Run the main loop"""
        self.log("Starting GLib main loop...")
        
        # Notify parent we're ready
        self.send_message({"type": "ready"})
        
        try:
            self.main_loop.run()
        except KeyboardInterrupt:
            self.log("Interrupted")
        finally:
            self.shutdown()
            

def main():
    # Read config from stdin
    config_line = sys.stdin.readline()
    try:
        config = json.loads(config_line.strip())
    except json.JSONDecodeError:
        sys.stderr.write("Failed to parse config\n")
        sys.exit(1)
        
    # Create and run handler
    handler = GLibWebRTCHandler(config)
    handler.run()
    

if __name__ == '__main__':
    main()
#!/usr/bin/env python3
"""
Fixed HLS WebRTC Subprocess Handler
Uses synchronous promise handling to avoid callback issues
"""

import sys
import json
import gi
import time
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


class FixedHLSWebRTCHandler:
    """Fixed HLS recording handler with synchronous promise handling"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.stream_id = config.get('stream_id')
        self.room = config.get('room')
        self.record_audio = config.get('record_audio', False)
        
        self.pipe = None
        self.webrtc = None
        self.session_id = None
        self.running = True
        
        # Recording state
        self.muxer = None
        self.hlssink = None
        
        # Base filename
        timestamp = int(datetime.datetime.now().timestamp())
        self.base_name = f"{self.room}_{self.stream_id}_{timestamp}"
        
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
            if 'data' in msg:
                self.add_ice_candidate(msg['data'])
            else:
                self.add_ice_candidate(msg)
        elif msg_type == 'stop':
            self.shutdown()
            
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
            
            # Add to pipeline
            self.pipe.add(self.webrtc)
            
            # Configure STUN/TURN
            if 'stun_server' in self.config:
                self.webrtc.set_property('stun-server', self.config['stun_server'])
                
            if 'turn_server' in self.config and self.config['turn_server']:
                self.webrtc.set_property('turn-server', self.config['turn_server'])
            
            # Start pipeline
            self.pipe.set_state(Gst.State.PLAYING)
            self.log("Pipeline started")
            
            # Send ready signal
            self.send_message({"type": "pipeline_ready"})
            
        except Exception as e:
            self.log(f"Failed to start pipeline: {e}", "error")
            
    def on_pad_added(self, element, pad):
        """Handle new pad added to webrtcbin"""
        pad_name = pad.get_name()
        self.log(f"New pad: {pad_name}")
        
        # Simple passthrough to fakesink for now to test connectivity
        fakesink = Gst.ElementFactory.make('fakesink', f'sink_{pad_name}')
        self.pipe.add(fakesink)
        fakesink.sync_state_with_parent()
        pad.link(fakesink.get_static_pad('sink'))
        
        self.log(f"Pad {pad_name} connected to fakesink")
        
    def on_ice_candidate(self, element, mline, candidate):
        """Handle local ICE candidate"""
        self.send_message({
            "type": "ice_candidate",
            "data": {
                'candidate': candidate,
                'sdpMLineIndex': mline
            }
        })
        
    def add_ice_candidate(self, ice_data):
        """Add remote ICE candidate"""
        if isinstance(ice_data, dict):
            candidate = ice_data.get('candidate')
            sdp_mline_index = ice_data.get('sdpMLineIndex', 0)
        else:
            candidate = ice_data
            sdp_mline_index = 0
        
        if candidate:
            self.webrtc.emit('add-ice-candidate', sdp_mline_index, candidate)
            
    def handle_remote_offer(self, offer_data):
        """Handle offer from remote peer"""
        try:
            self.log("Processing offer")
            
            # Create offer object
            offer_sdp = offer_data['sdp']
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(offer_sdp)
            
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # Set remote description synchronously
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', offer, promise)
            promise.wait()
            
            self.log("Remote description set")
            
            # Create answer synchronously
            promise = Gst.Promise.new()
            self.webrtc.emit('create-answer', None, promise)
            promise.wait()
            
            reply = promise.get_reply()
            answer = reply.get_value('answer')
            
            # Set local description
            promise = Gst.Promise.new()
            self.webrtc.emit('set-local-description', answer, promise)
            promise.wait()
            
            # Send answer
            self.send_message({
                "type": "answer",
                "data": {
                    "sdp": answer.sdp.as_text(),
                    "type": "answer"
                }
            })
            
            self.log("Answer sent")
            
        except Exception as e:
            self.log(f"Error handling offer: {e}", "error")
            
    def shutdown(self):
        """Shutdown the handler"""
        self.log("Shutting down...")
        
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            
        self.main_loop.quit()
        
    def run(self):
        """Run the main loop"""
        self.log("Starting main loop...")
        self.main_loop.run()


def main():
    """Main entry point"""
    try:
        # Read configuration
        config_line = sys.stdin.readline()
        if not config_line:
            sys.stderr.write("No configuration received\n")
            return
            
        config = json.loads(config_line.strip())
        
        # Create handler
        handler = FixedHLSWebRTCHandler(config)
        
        # Send ready signal
        handler.send_message({"type": "ready"})
        
        # Start pipeline
        handler.start_pipeline()
        
        # Run main loop
        handler.run()
        
    except Exception as e:
        sys.stderr.write(f"Subprocess error: {e}\n")
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
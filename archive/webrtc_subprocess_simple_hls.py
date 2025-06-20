#!/usr/bin/env python3
"""
Simplified HLS WebRTC Subprocess Handler
This version uses minimal transcoding to test basic functionality
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


class SimpleHLSWebRTCHandler:
    """Simplified HLS recording handler"""
    
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
        self.recording_started = False
        self.muxer = None
        self.hlssink = None
        self.video_connected = False
        self.audio_connected = False
        
        # Base filename for recordings
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
            self.webrtc.connect('notify::ice-connection-state', self.on_ice_connection_state_notify)
            
            # Add to pipeline
            self.pipe.add(self.webrtc)
            
            # Configure STUN/TURN
            if 'stun_server' in self.config:
                self.webrtc.set_property('stun-server', self.config['stun_server'])
            
            if 'turn_server' in self.config and self.config['turn_server']:
                self.webrtc.set_property('turn-server', self.config['turn_server'])
            
            # Create muxer and sink upfront (simplified approach)
            self.setup_recording_elements()
            
            # Start pipeline
            self.pipe.set_state(Gst.State.PLAYING)
            self.log("Pipeline started in PLAYING state")
            
            # Send ready signal
            self.send_message({"type": "pipeline_ready"})
            
        except Exception as e:
            self.log(f"Failed to start pipeline: {e}", "error")
            import traceback
            self.log(f"Traceback: {traceback.format_exc()}", "error")
            
    def setup_recording_elements(self):
        """Setup recording elements upfront"""
        try:
            # Create muxer
            self.muxer = Gst.ElementFactory.make('mpegtsmux', 'muxer')
            
            # Create HLS sink
            self.hlssink = Gst.ElementFactory.make('hlssink', 'hlssink')
            self.hlssink.set_property('max-files', 0)
            self.hlssink.set_property('target-duration', 10)
            self.hlssink.set_property('playlist-length', 0)
            self.hlssink.set_property('location', f"{self.base_name}_segment_%05d.ts")
            self.hlssink.set_property('playlist-location', f"{self.base_name}.m3u8")
            
            # Add to pipeline
            self.pipe.add(self.muxer)
            self.pipe.add(self.hlssink)
            
            # Link muxer to sink
            self.muxer.link(self.hlssink)
            
            # Set to playing
            self.muxer.sync_state_with_parent()
            self.hlssink.sync_state_with_parent()
            
            self.log(f"Recording elements ready: {self.base_name}.m3u8")
            
        except Exception as e:
            self.log(f"Failed to setup recording: {e}", "error")
            
    def on_pad_added(self, element, pad):
        """Handle new pad added to webrtcbin"""
        pad_name = pad.get_name()
        self.log(f"[Simple] New pad added: {pad_name}")
        
        # Get caps
        caps = pad.get_current_caps()
        if not caps:
            # Wait for caps
            pad.connect('notify::caps', self.on_pad_caps_changed)
            return
            
        self.handle_pad_with_caps(pad, caps)
        
    def on_pad_caps_changed(self, pad, pspec):
        """Handle caps becoming available"""
        caps = pad.get_current_caps()
        if caps:
            self.handle_pad_with_caps(pad, caps)
            
    def handle_pad_with_caps(self, pad, caps):
        """Process pad with known caps"""
        structure = caps.get_structure(0)
        media_type = structure.get_value('media')
        encoding_name = structure.get_string('encoding-name')
        
        self.log(f"[Simple] Processing {media_type} pad with {encoding_name}")
        
        if media_type == 'video':
            self.handle_simple_video_pad(pad, encoding_name)
        elif media_type == 'audio' and self.record_audio:
            self.handle_simple_audio_pad(pad, encoding_name)
            
    def handle_simple_video_pad(self, pad, encoding_name):
        """Handle video pad with minimal processing"""
        self.log(f"[Simple] Connecting video ({encoding_name})")
        
        # Create simple pipeline: depay -> h264parse -> muxer
        queue = Gst.ElementFactory.make('queue', f'vqueue_{pad.get_name()}')
        
        if encoding_name == 'H264':
            depay = Gst.ElementFactory.make('rtph264depay', f'vdepay_{pad.get_name()}')
            parse = Gst.ElementFactory.make('h264parse', f'vparse_{pad.get_name()}')
            elements = [queue, depay, parse]
        elif encoding_name == 'VP8':
            # For VP8, we need to transcode
            depay = Gst.ElementFactory.make('rtpvp8depay', f'vdepay_{pad.get_name()}')
            dec = Gst.ElementFactory.make('vp8dec', f'vdec_{pad.get_name()}')
            enc = Gst.ElementFactory.make('x264enc', f'venc_{pad.get_name()}')
            enc.set_property('tune', 'zerolatency')
            enc.set_property('speed-preset', 'ultrafast')
            parse = Gst.ElementFactory.make('h264parse', f'vparse_{pad.get_name()}')
            elements = [queue, depay, dec, enc, parse]
        else:
            self.log(f"[Simple] Unsupported video codec: {encoding_name}")
            return
            
        # Add elements
        for element in elements:
            self.pipe.add(element)
            
        # Link elements
        for i in range(len(elements) - 1):
            elements[i].link(elements[i + 1])
            
        # Link to muxer
        mux_pad = self.muxer.request_pad_simple('sink_%d')
        elements[-1].get_static_pad('src').link(mux_pad)
        
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
            
        # Link pad to queue
        pad.link(queue.get_static_pad('sink'))
        
        self.video_connected = True
        self.log(f"[Simple] ✅ Video connected to HLS")
        
    def handle_simple_audio_pad(self, pad, encoding_name):
        """Handle audio pad with minimal processing"""
        self.log(f"[Simple] Connecting audio ({encoding_name})")
        
        # Create simple pipeline
        queue = Gst.ElementFactory.make('queue', f'aqueue_{pad.get_name()}')
        
        if encoding_name == 'OPUS':
            # Need to transcode Opus to AAC
            depay = Gst.ElementFactory.make('rtpopusdepay', f'adepay_{pad.get_name()}')
            dec = Gst.ElementFactory.make('opusdec', f'adec_{pad.get_name()}')
            conv = Gst.ElementFactory.make('audioconvert', f'aconv_{pad.get_name()}')
            enc = Gst.ElementFactory.make('avenc_aac', f'aenc_{pad.get_name()}')
            parse = Gst.ElementFactory.make('aacparse', f'aparse_{pad.get_name()}')
            elements = [queue, depay, dec, conv, enc, parse]
        else:
            self.log(f"[Simple] Unsupported audio codec: {encoding_name}")
            return
            
        # Add elements
        for element in elements:
            self.pipe.add(element)
            
        # Link elements
        for i in range(len(elements) - 1):
            elements[i].link(elements[i + 1])
            
        # Link to muxer
        mux_pad = self.muxer.request_pad_simple('sink_%d')
        elements[-1].get_static_pad('src').link(mux_pad)
        
        # Sync states
        for element in elements:
            element.sync_state_with_parent()
            
        # Link pad to queue
        pad.link(queue.get_static_pad('sink'))
        
        self.audio_connected = True
        self.log(f"[Simple] ✅ Audio connected to HLS")
        
    def on_ice_connection_state_notify(self, element, pspec):
        """Monitor ICE connection state changes"""
        state = element.get_property('ice-connection-state')
        self.log(f"[Simple] ICE connection state: {state.value_name}")
        
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
            self.log(f"[Simple] Processing remote offer")
            
            # Create offer object
            offer_sdp = offer_data['sdp']
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(offer_sdp)
            
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # Set remote description
            promise = Gst.Promise.new_with_change_func(
                self.on_remote_description_set,
                None
            )
            self.webrtc.emit('set-remote-description', offer, promise)
            
        except Exception as e:
            self.log(f"[Simple] Error handling offer: {e}", "error")
            
    def on_remote_description_set(self, promise, user_data):
        """Called when remote description is set"""
        self.log("[Simple] Remote description set, creating answer")
        
        # Create answer
        promise = Gst.Promise.new_with_change_func(
            self.on_answer_created,
            None
        )
        self.webrtc.emit('create-answer', None, promise)
        
    def on_answer_created(self, promise, user_data):
        """Called when answer is created"""
        reply = promise.get_reply()
        
        # Get the answer
        answer = reply.get_value('answer')
        
        # Extract SDP
        sdp = answer.sdp.as_text()
        self.log("[Simple] Answer created")
        
        # Set local description
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', answer, promise)
        
        # Send answer to parent
        self.send_message({
            "type": "answer",
            "data": {
                "sdp": sdp,
                "type": "answer"
            }
        })
        
        self.log("[Simple] Answer sent")
        
    def shutdown(self):
        """Shutdown the handler"""
        self.log("[Simple] Shutting down...")
        
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            
        self.main_loop.quit()
        
    def run(self):
        """Run the main loop"""
        self.log("[Simple] Starting main loop...")
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
        handler = SimpleHLSWebRTCHandler(config)
        
        # Send ready signal
        handler.send_message({"type": "ready"})
        
        # Start pipeline immediately
        handler.start_pipeline()
        
        # Run main loop
        handler.run()
        
    except Exception as e:
        sys.stderr.write(f"Subprocess error: {e}\n")
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
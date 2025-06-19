#!/usr/bin/env python3
"""
WebRTC Subprocess Handler
This runs as a subprocess and handles the GStreamer/WebRTC pipeline.
It communicates with the parent process via stdin/stdout using JSON messages.
"""

import sys
import json
import asyncio
import gi
import time
import threading
from typing import Optional, Dict, Any

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp

# Initialize GStreamer
Gst.init(None)


class IPCWebRTCHandler:
    """Handles WebRTC pipeline in a subprocess with IPC communication"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.stream_id = config.get('stream_id')
        self.mode = config.get('mode', 'publish')  # 'publish' or 'view'
        self.room = config.get('room')
        self.record_file = config.get('record_file')
        
        self.pipe = None
        self.webrtc = None
        self.session_id = None
        
        # IPC communication
        self.running = True
        self.loop = None
        
        # ICE candidates queue
        self.ice_candidates = []
        
    def send_message(self, msg: Dict[str, Any]):
        """Send message to parent process via stdout"""
        try:
            sys.stdout.write(json.dumps(msg) + '\n')
            sys.stdout.flush()
        except Exception as e:
            self.log(f"Error sending message: {e}", "error")
    
    def log(self, message: str, level: str = "info"):
        """Send log message to parent"""
        self.send_message({
            "type": "log",
            "level": level,
            "message": f"[{self.stream_id}] {message}"
        })
    
    def create_pipeline(self):
        """Create the GStreamer pipeline based on config"""
        self.log("Creating pipeline...")
        
        if self.mode == 'publish':
            # Publishing pipeline
            pipeline_str = self.config.get('pipeline', '')
            if not pipeline_str:
                self.log("No pipeline configuration provided", "error")
                return False
                
            self.pipe = Gst.parse_launch(pipeline_str)
            
        else:  # view/record mode
            # Simple receiving pipeline
            self.pipe = Gst.Pipeline.new('recorder-pipeline')
            
        # Get or create webrtcbin
        self.webrtc = self.pipe.get_by_name('sendrecv')
        if not self.webrtc:
            self.webrtc = Gst.ElementFactory.make('webrtcbin', 'sendrecv')
            self.pipe.add(self.webrtc)
            
        # Configure STUN/TURN
        if 'stun_server' in self.config:
            self.webrtc.set_property('stun-server', self.config['stun_server'])
        if 'turn_server' in self.config:
            self.webrtc.set_property('turn-server', self.config['turn_server'])
            
        # Connect signals
        self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)
        self.webrtc.connect('pad-added', self.on_pad_added)
        self.webrtc.connect('notify::ice-connection-state', self.on_ice_state_changed)
        self.webrtc.connect('notify::connection-state', self.on_connection_state_changed)
        
        if self.mode == 'publish':
            self.webrtc.connect('on-negotiation-needed', self.on_negotiation_needed)
            
        # Set up bus
        bus = self.pipe.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_bus_message)
        
        # Start pipeline
        ret = self.pipe.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self.log("Failed to start pipeline", "error")
            return False
            
        self.log("Pipeline started successfully")
        return True
        
    def on_negotiation_needed(self, webrtc):
        """Create offer when negotiation is needed"""
        self.log("Negotiation needed")
        promise = Gst.Promise.new_with_change_func(self.on_offer_created, webrtc, None)
        webrtc.emit('create-offer', None, promise)
        
    def on_offer_created(self, promise, webrtc, _):
        """Handle created offer"""
        promise.wait()
        reply = promise.get_reply()
        offer = reply.get_value('offer')
        
        if not offer:
            self.log("Failed to create offer", "error")
            return
            
        # Set local description
        promise = Gst.Promise.new()
        webrtc.emit('set-local-description', offer, promise)
        promise.interrupt()
        
        # Send offer to parent
        text = offer.sdp.as_text()
        self.send_message({
            "type": "sdp",
            "sdp_type": "offer",
            "sdp": text,
            "session_id": self.session_id
        })
        
    def on_ice_candidate(self, webrtc, mlineindex, candidate):
        """Send ICE candidate to parent"""
        self.send_message({
            "type": "ice",
            "candidate": candidate,
            "sdpMLineIndex": mlineindex,
            "session_id": self.session_id
        })
        
    def on_pad_added(self, webrtc, pad):
        """Handle new pad - set up recording if needed"""
        caps = pad.get_current_caps()
        if not caps:
            return
            
        structure = caps.get_structure(0)
        name = structure.get_name()
        
        self.log(f"New pad: {name}")
        
        if self.record_file and name.startswith('application/x-rtp'):
            media = structure.get_string('media')
            if media == 'video':
                self.setup_recording(pad, structure)
                
    def setup_recording(self, pad, structure):
        """Set up recording pipeline"""
        encoding_name = structure.get_string('encoding-name')
        self.log(f"Setting up recording for {encoding_name}")
        
        # Create recording elements based on codec
        if encoding_name == 'H264':
            depay = 'rtph264depay'
            parse = 'h264parse'
            mux = 'mpegtsmux'
        elif encoding_name == 'VP8':
            depay = 'rtpvp8depay'
            # For VP8, decode and re-encode to handle resolution changes
            decode = 'vp8dec'
            scale = 'videoscale'
            encode = 'vp8enc deadline=1 cpu-used=4'
            parse = None
            mux = 'matroskamux streamable=true'
        elif encoding_name == 'VP9':
            depay = 'rtpvp9depay'
            parse = None
            mux = 'matroskamux'
        else:
            self.log(f"Unsupported codec: {encoding_name}", "error")
            return
            
        # Build recording pipeline string
        if encoding_name == 'VP8':
            # Special handling for VP8 with resolution changes
            pipeline_str = (
                f"queue name=rec_queue max-size-buffers=0 max-size-time=0 ! "
                f"{depay} ! {decode} ! {scale} ! video/x-raw,width=1280,height=720 ! "
                f"{encode} ! {mux} ! filesink location={self.record_file}"
            )
        else:
            # Standard recording
            elements = [f"queue name=rec_queue max-size-buffers=0 max-size-time=0", depay]
            if parse:
                elements.append(parse)
            elements.extend([mux, f"filesink location={self.record_file}"])
            pipeline_str = " ! ".join(elements)
            
        # Create bin from description
        try:
            recording_bin = Gst.parse_bin_from_description(pipeline_str, True)
            self.pipe.add(recording_bin)
            recording_bin.sync_state_with_parent()
            
            # Link pad to recording bin
            sink_pad = recording_bin.get_static_pad('sink')
            if pad.link(sink_pad) == Gst.PadLinkReturn.OK:
                self.log(f"Recording started: {self.record_file}")
                self.send_message({
                    "type": "recording_started",
                    "file": self.record_file,
                    "codec": encoding_name
                })
            else:
                self.log("Failed to link recording pipeline", "error")
                
        except Exception as e:
            self.log(f"Error setting up recording: {e}", "error")
            
    def on_ice_state_changed(self, webrtc, pspec):
        """ICE connection state changed"""
        state = webrtc.get_property('ice-connection-state')
        self.log(f"ICE state: {state.value_name}")
        self.send_message({
            "type": "ice_state",
            "state": state.value_name
        })
        
    def on_connection_state_changed(self, webrtc, pspec):
        """WebRTC connection state changed"""
        state = webrtc.get_property('connection-state')
        self.log(f"Connection state: {state.value_name}")
        self.send_message({
            "type": "connection_state",
            "state": state.value_name
        })
        
        # If connected, we should start seeing pads
        if state == GstWebRTC.WebRTCPeerConnectionState.CONNECTED:
            self.log("WebRTC connected successfully!")
            self.send_message({
                "type": "recording_started",
                "file": self.record_file or "pending",
                "codec": "pending"
            })
        
    def on_bus_message(self, bus, message):
        """Handle GStreamer bus messages"""
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            self.log(f"Pipeline error: {err.message}", "error")
            self.send_message({
                "type": "error",
                "error": err.message,
                "debug": debug
            })
        elif t == Gst.MessageType.EOS:
            self.log("End of stream")
            self.send_message({"type": "eos"})
            
    async def handle_message(self, msg: Dict[str, Any]):
        """Handle message from parent process"""
        msg_type = msg.get('type')
        self.log(f"Received message type: {msg_type}", "info")
        
        if msg_type == 'start':
            # Start the pipeline
            self.session_id = msg.get('session_id')
            if self.create_pipeline():
                self.send_message({"type": "started"})
            else:
                self.send_message({"type": "error", "error": "Failed to create pipeline"})
                
        elif msg_type == 'sdp':
            # Handle SDP offer/answer
            sdp_type = msg.get('sdp_type')
            sdp_text = msg.get('sdp')
            
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                self.log("Failed to parse SDP", "error")
                return
                
            if sdp_type == 'offer':
                # Set remote description
                offer = GstWebRTC.WebRTCSessionDescription.new(
                    GstWebRTC.WebRTCSDPType.OFFER,
                    sdp_msg
                )
                promise = Gst.Promise.new()
                self.webrtc.emit('set-remote-description', offer, promise)
                promise.interrupt()
                
                # Create answer
                promise = Gst.Promise.new_with_change_func(self.on_answer_created, self.webrtc, None)
                self.webrtc.emit('create-answer', None, promise)
                
            elif sdp_type == 'answer':
                # Set remote description
                answer = GstWebRTC.WebRTCSessionDescription.new(
                    GstWebRTC.WebRTCSDPType.ANSWER,
                    sdp_msg
                )
                promise = Gst.Promise.new()
                self.webrtc.emit('set-remote-description', answer, promise)
                promise.interrupt()
                
        elif msg_type == 'ice':
            # Add ICE candidate
            candidate = msg.get('candidate')
            sdpMLineIndex = msg.get('sdpMLineIndex', 0)
            
            if self.webrtc:
                self.webrtc.emit('add-ice-candidate', sdpMLineIndex, candidate)
            else:
                # Queue for later
                self.ice_candidates.append((sdpMLineIndex, candidate))
                
        elif msg_type == 'stop':
            # Stop pipeline
            self.running = False
            if self.pipe:
                self.pipe.set_state(Gst.State.NULL)
            self.send_message({"type": "stopped"})
            
    def on_answer_created(self, promise, webrtc, _):
        """Handle created answer"""
        promise.wait()
        reply = promise.get_reply()
        answer = reply.get_value('answer')
        
        if not answer:
            self.log("Failed to create answer", "error")
            return
            
        # Set local description
        promise = Gst.Promise.new()
        webrtc.emit('set-local-description', answer, promise)
        promise.interrupt()
        
        # Send answer to parent
        text = answer.sdp.as_text()
        self.send_message({
            "type": "sdp",
            "sdp_type": "answer",
            "sdp": text,
            "session_id": self.session_id
        })
        
    async def run(self):
        """Main event loop"""
        self.loop = asyncio.get_running_loop()
        
        # Read messages from stdin
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await self.loop.connect_read_pipe(lambda: protocol, sys.stdin)
        
        while self.running:
            try:
                line = await reader.readline()
                if not line:
                    break
                    
                msg = json.loads(line.decode().strip())
                await self.handle_message(msg)
                
            except json.JSONDecodeError as e:
                self.log(f"Invalid JSON: {e}", "error")
            except Exception as e:
                self.log(f"Error handling message: {e}", "error")
                
        self.log("Subprocess exiting")


async def main():
    """Main entry point for subprocess"""
    try:
        # Read configuration from first line
        config_line = sys.stdin.readline()
        if not config_line:
            sys.stderr.write("No configuration received\n")
            return
            
        config = json.loads(config_line.strip())
        
        # Create handler
        handler = IPCWebRTCHandler(config)
        
        # Send ready signal
        handler.send_message({"type": "ready"})
        
        # Run event loop
        await handler.run()
    except Exception as e:
        sys.stderr.write(f"Subprocess error: {e}\n")
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    # Run the subprocess
    asyncio.run(main())
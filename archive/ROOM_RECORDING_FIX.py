#!/usr/bin/env python3
"""
Fixed version of multi_peer_client.py with proper ICE handling
"""

import asyncio
import json
import time
import os
import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp
from typing import Dict, Optional
import queue
import threading

# Initialize GStreamer
Gst.init(None)

def printc(message, color_code=""):
    """Colored print function"""
    if color_code:
        colors = {
            "0F0": "\033[92m",  # Green
            "F00": "\033[91m",  # Red  
            "FF0": "\033[93m",  # Yellow
            "0FF": "\033[96m",  # Cyan
            "F0F": "\033[95m",  # Magenta
            "77F": "\033[94m",  # Blue
            "FFF": "\033[97m",  # White
        }
        color = colors.get(color_code[:3], "")
        print(f"{color}{message}\033[0m")
    else:
        print(message)

class StreamRecorder:
    """Handles recording for a single stream with fixed ICE handling"""
    
    def __init__(self, stream_id: str, room_name: str, record_prefix: str, parent_client):
        self.stream_id = stream_id
        self.room_name = room_name
        self.record_prefix = record_prefix
        self.session_id = None
        self.parent_client = parent_client
        
        # GStreamer elements
        self.pipe = None
        self.webrtc = None
        self.filesink = None
        
        # State
        self.recording = False
        self.recording_file = None
        self.start_time = None
        
        # Thread-safe queue for ICE candidates
        self.ice_queue = queue.Queue()
        
    def create_pipeline(self):
        """Create the WebRTC receiving pipeline"""
        printc(f"[{self.stream_id}] Creating pipeline", "77F")
        
        self.pipe = Gst.Pipeline.new(f'pipe_{self.stream_id}')
        self.webrtc = Gst.ElementFactory.make('webrtcbin', 'webrtc')
        
        if not self.webrtc:
            printc(f"[{self.stream_id}] ERROR: Failed to create webrtcbin", "F00")
            return
            
        # Configure webrtcbin
        self.webrtc.set_property('bundle-policy', GstWebRTC.WebRTCBundlePolicy.MAX_BUNDLE)
        self.webrtc.set_property('latency', 0)
        self.webrtc.set_property('stun-server', 'stun://stun.cloudflare.com:3478')
        
        # Add to pipeline
        self.pipe.add(self.webrtc)
        
        # Add transceiver for receiving video
        direction = GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY
        caps_video = Gst.caps_from_string("application/x-rtp,media=video")
        self.webrtc.emit('add-transceiver', direction, caps_video)
        
        # Add audio transceiver if needed
        if not self.parent_client.ws_client.noaudio:
            caps_audio = Gst.caps_from_string("application/x-rtp,media=audio")
            self.webrtc.emit('add-transceiver', direction, caps_audio)
        
        # Connect signals
        self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)
        self.webrtc.connect('pad-added', self.on_pad_added)
        self.webrtc.connect('notify::ice-connection-state', self.on_ice_state_changed)
        self.webrtc.connect('notify::connection-state', self.on_connection_state_changed)
        
        # Start pipeline
        ret = self.pipe.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            printc(f"[{self.stream_id}] ERROR: Failed to start pipeline", "F00")
        else:
            printc(f"[{self.stream_id}] Pipeline started successfully", "0F0")
        
    def on_ice_candidate(self, webrtc, mlineindex, candidate):
        """Handle local ICE candidate - queue it for sending"""
        # Queue the candidate - this is thread-safe
        self.ice_queue.put((candidate, mlineindex))
        printc(f"[{self.stream_id}] Queued ICE candidate", "77F")
        
    def get_pending_ice_candidates(self):
        """Get all pending ICE candidates (called from main thread)"""
        candidates = []
        while not self.ice_queue.empty():
            try:
                candidates.append(self.ice_queue.get_nowait())
            except queue.Empty:
                break
        return candidates
        
    def on_pad_added(self, webrtc, pad):
        """Handle new pad added - set up recording"""
        caps = pad.get_current_caps()
        if not caps:
            return
            
        structure = caps.get_structure(0)
        name = structure.get_name()
        
        printc(f"[{self.stream_id}] New pad: {name}", "77F")
        
        if name.startswith('application/x-rtp'):
            media = structure.get_string('media')
            if media != 'video':
                return
                
            encoding_name = structure.get_string('encoding-name')
            printc(f"[{self.stream_id}] Video codec: {encoding_name}", "0F0")
            
            self.setup_recording(pad, encoding_name)
            
    def setup_recording(self, pad, encoding_name):
        """Set up recording pipeline for the stream"""
        if self.recording:
            return
            
        # Determine pipeline elements based on codec
        if encoding_name == 'H264':
            depay = 'rtph264depay'
            parse = 'h264parse'
            mux = 'mpegtsmux'
            extension = 'ts'
        elif encoding_name == 'VP8':
            depay = 'rtpvp8depay'
            parse = None
            mux = 'matroskamux'
            extension = 'mkv'
        elif encoding_name == 'VP9':
            depay = 'rtpvp9depay'
            parse = None
            mux = 'matroskamux'  
            extension = 'mkv'
        else:
            printc(f"[{self.stream_id}] Unknown codec: {encoding_name}", "F00")
            return
            
        # Generate filename
        timestamp = int(time.time())
        self.recording_file = f"{self.record_prefix}_{self.stream_id}_{timestamp}.{extension}"
        
        printc(f"[{self.stream_id}] Recording to: {self.recording_file}", "0F0")
        
        # Create elements
        queue = Gst.ElementFactory.make('queue', f'queue_{self.stream_id}')
        depayloader = Gst.ElementFactory.make(depay, f'depay_{self.stream_id}')
        
        if parse:
            parser = Gst.ElementFactory.make(parse, f'parse_{self.stream_id}')
            
        muxer = Gst.ElementFactory.make(mux, f'mux_{self.stream_id}')
        self.filesink = Gst.ElementFactory.make('filesink', f'filesink_{self.stream_id}')
        self.filesink.set_property('location', self.recording_file)
        
        # Add to pipeline
        self.pipe.add(queue)
        self.pipe.add(depayloader)
        if parse:
            self.pipe.add(parser)
        self.pipe.add(muxer)
        self.pipe.add(self.filesink)
        
        # Link elements
        queue.link(depayloader)
        if parse:
            depayloader.link(parser)
            parser.link(muxer)
        else:
            depayloader.link(muxer)
        muxer.link(self.filesink)
        
        # Sync states
        queue.sync_state_with_parent()
        depayloader.sync_state_with_parent()
        if parse:
            parser.sync_state_with_parent()
        muxer.sync_state_with_parent()
        self.filesink.sync_state_with_parent()
        
        # Link pad to queue
        queue_sink = queue.get_static_pad('sink')
        if pad.link(queue_sink) == Gst.PadLinkReturn.OK:
            self.recording = True
            self.start_time = time.time()
            printc(f"[{self.stream_id}] ✅ Recording started", "0F0")
        else:
            printc(f"[{self.stream_id}] ❌ Failed to link recording pipeline", "F00")
            
    def on_ice_state_changed(self, webrtc, pspec):
        """ICE connection state changed"""
        state = webrtc.get_property('ice-connection-state')
        printc(f"[{self.stream_id}] ICE state: {state.value_name}", "77F")
        
    def on_connection_state_changed(self, webrtc, pspec):
        """WebRTC connection state changed"""
        state = webrtc.get_property('connection-state')
        printc(f"[{self.stream_id}] Connection state: {state.value_name}", "77F")
        
        if state == GstWebRTC.WebRTCPeerConnectionState.FAILED:
            ice_state = webrtc.get_property('ice-connection-state')
            printc(f"[{self.stream_id}] ICE state on failure: {ice_state.value_name}", "F00")
        
    async def handle_offer(self, offer_sdp):
        """Handle SDP offer from remote peer"""
        printc(f"[{self.stream_id}] Setting remote description", "77F")
        
        if not self.webrtc:
            printc(f"[{self.stream_id}] ERROR: webrtc is None", "F00")
            return None
            
        # Parse SDP
        res, sdp_msg = GstSdp.SDPMessage.new_from_text(offer_sdp)
        if res != GstSdp.SDPResult.OK:
            printc(f"[{self.stream_id}] ERROR: Failed to parse SDP", "F00")
            return None
            
        offer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.OFFER,
            sdp_msg
        )
        
        # Set remote description
        promise = Gst.Promise.new()
        self.webrtc.emit('set-remote-description', offer, promise)
        promise.wait()
        
        # Check for errors
        reply = promise.get_reply()
        if reply:
            error = reply.get_value('error')
            if error:
                printc(f"[{self.stream_id}] ERROR setting remote description: {error}", "F00")
                return None
        
        # Create answer
        promise = Gst.Promise.new()
        self.webrtc.emit('create-answer', None, promise)
        promise.wait()
        
        reply = promise.get_reply()
        if not reply:
            printc(f"[{self.stream_id}] ERROR: No reply when creating answer", "F00")
            return None
            
        answer = reply.get_value('answer')
        if not answer:
            printc(f"[{self.stream_id}] ERROR: No answer in reply", "F00")
            error = reply.get_value('error')
            if error:
                printc(f"[{self.stream_id}] Error details: {error}", "F00")
            return None
        
        # Set local description
        promise2 = Gst.Promise.new()
        self.webrtc.emit('set-local-description', answer, promise2)
        promise2.wait()
        
        # Get the SDP text
        if answer and hasattr(answer, 'sdp'):
            answer_sdp = answer.sdp.as_text()
            printc(f"[{self.stream_id}] Answer created successfully", "0F0")
            return answer_sdp
        else:
            printc(f"[{self.stream_id}] ERROR: Could not get SDP from answer", "F00")
            return None
        
    def add_ice_candidate(self, candidate, sdpMLineIndex):
        """Add remote ICE candidate"""
        if self.webrtc:
            self.webrtc.emit('add-ice-candidate', sdpMLineIndex, candidate)
            printc(f"[{self.stream_id}] Added remote ICE candidate", "77F")
            
    def get_stats(self):
        """Get recording statistics"""
        stats = {
            'stream_id': self.stream_id,
            'recording': self.recording,
            'file': self.recording_file,
            'bytes': 0,
            'duration': 0
        }
        
        if self.recording and self.filesink:
            try:
                position = self.filesink.query_position(Gst.Format.BYTES)[1]
                stats['bytes'] = position
            except:
                pass
                
        if self.start_time:
            stats['duration'] = time.time() - self.start_time
            
        return stats
        
    def cleanup(self):
        """Clean up the recorder"""
        if self.pipe:
            self.pipe.set_state(Gst.State.NULL)
            self.pipe = None
            
        if self.recording_file and os.path.exists(self.recording_file):
            size = os.path.getsize(self.recording_file)
            printc(f"[{self.stream_id}] Recording saved: {self.recording_file} ({size:,} bytes)", "0F0")


class MultiPeerClient:
    """WebRTC client that handles multiple peer connections on a single WebSocket"""
    
    def __init__(self, websocket_client, room_name: str, record_prefix: str):
        self.ws_client = websocket_client
        self.room_name = room_name
        self.record_prefix = record_prefix
        
        # Stream recorders
        self.recorders: Dict[str, StreamRecorder] = {}
        
        # Message routing
        self.sessions: Dict[str, str] = {}  # session_id -> stream_id mapping
        
        # Start ICE candidate processor
        self._running = True
        self._ice_task = None
        
        printc("\n🎬 Multi-Peer Recording Client initialized", "0FF")
        
    async def start_ice_processor(self):
        """Start the ICE candidate processor task"""
        if not self._ice_task:
            self._ice_task = asyncio.create_task(self._process_ice_candidates())
            
    async def _process_ice_candidates(self):
        """Process ICE candidates from all recorders"""
        while self._running:
            for stream_id, recorder in self.recorders.items():
                if recorder.session_id:
                    # Get pending candidates
                    candidates = recorder.get_pending_ice_candidates()
                    for candidate, mlineindex in candidates:
                        await self.send_ice_candidate(
                            stream_id,
                            recorder.session_id,
                            candidate,
                            mlineindex
                        )
            # Check every 100ms
            await asyncio.sleep(0.1)
            
    async def send_ice_candidate(self, stream_id: str, session_id: str, candidate: str, mlineindex: int):
        """Send ICE candidate via WebSocket"""
        await self.ws_client.sendMessageAsync({
            'candidates': [{
                'candidate': candidate,
                'sdpMLineIndex': mlineindex
            }],
            'session': session_id,
            'type': 'remote',
            'UUID': self.ws_client.puuid
        })
        
    async def add_stream(self, stream_id: str):
        """Add a new stream to record"""
        if stream_id in self.recorders:
            printc(f"Stream {stream_id} already being recorded", "FF0")
            return
            
        printc(f"\n📹 Adding recorder for stream: {stream_id}", "0F0")
        
        # Create recorder
        recorder = StreamRecorder(stream_id, self.room_name, self.record_prefix, self)
        recorder.create_pipeline()
        
        if not recorder.pipe or not recorder.webrtc:
            printc(f"[{stream_id}] ERROR: Failed to create pipeline/webrtc", "F00")
            return
            
        self.recorders[stream_id] = recorder
        
        # Start ICE processor if not running
        await self.start_ice_processor()
        
        # Request to play this stream
        printc(f"[{stream_id}] Requesting stream playback", "77F")
        await self.ws_client.sendMessageAsync({
            "request": "play",
            "streamID": stream_id
        })
        
    async def handle_message(self, msg: dict):
        """Route messages to appropriate recorders"""
        # Determine message type
        msg_type = "unknown"
        if 'description' in msg:
            msg_type = f"description/{msg['description'].get('type', 'unknown')}"
        elif 'candidates' in msg:
            msg_type = "candidates"
        elif 'request' in msg:
            msg_type = f"request/{msg['request']}"
            
        # Find target recorder
        session = msg.get('session')
        from_id = msg.get('from')
        
        printc(f"[MultiPeer] Handling message: {msg_type}, session={session}", "77F")
        
        target_recorder = None
        
        # Match by session
        if session and session in self.sessions:
            stream_id = self.sessions[session]
            target_recorder = self.recorders.get(stream_id)
            
        # Match by from field
        if not target_recorder and from_id:
            for stream_id, recorder in self.recorders.items():
                if stream_id in from_id:
                    target_recorder = recorder
                    if session:
                        self.sessions[session] = stream_id
                        recorder.session_id = session
                    break
                    
        # Match offer to recorder without session
        if not target_recorder and 'description' in msg:
            for stream_id, recorder in self.recorders.items():
                if not recorder.session_id:
                    target_recorder = recorder
                    if session:
                        self.sessions[session] = stream_id
                        recorder.session_id = session
                    break
                    
        if not target_recorder:
            return
            
        # Handle the message
        if 'description' in msg:
            desc = msg['description']
            if isinstance(desc, dict) and desc.get('type') == 'offer':
                # Handle offer
                sdp = desc.get('sdp')
                answer_sdp = await target_recorder.handle_offer(sdp)
                
                if answer_sdp:
                    # Send answer
                    await self.ws_client.sendMessageAsync({
                        'description': {
                            'type': 'answer',
                            'sdp': answer_sdp
                        },
                        'session': target_recorder.session_id,
                        'UUID': self.ws_client.puuid
                    })
                    
        elif 'candidates' in msg:
            # Handle ICE candidates
            for candidate in msg['candidates']:
                if 'candidate' in candidate:
                    target_recorder.add_ice_candidate(
                        candidate['candidate'],
                        candidate.get('sdpMLineIndex', 0)
                    )
                    
    def get_all_stats(self):
        """Get statistics for all recorders"""
        stats = []
        for recorder in self.recorders.values():
            stats.append(recorder.get_stats())
        return stats
        
    def cleanup(self):
        """Clean up all recorders"""
        self._running = False
        
        if self._ice_task:
            self._ice_task.cancel()
            
        printc("\n🛑 Stopping all recorders...", "FF0")
        
        for stream_id, recorder in self.recorders.items():
            recorder.cleanup()
            
        # Summary
        printc("\n" + "="*60, "FFF")
        printc("📹 Recording Summary", "0FF")
        printc("="*60, "FFF")
        
        for stream_id, recorder in self.recorders.items():
            if recorder.recording_file and os.path.exists(recorder.recording_file):
                size = os.path.getsize(recorder.recording_file)
                printc(f"\n{stream_id}:", "0F0")
                printc(f"  ✅ {recorder.recording_file} ({size:,} bytes)", "0F0")
            else:
                printc(f"\n{stream_id}:", "F00")
                printc(f"  ❌ No recording", "F00")
                
        printc("="*60, "FFF")
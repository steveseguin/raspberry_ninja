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
from gi.repository import Gst, GObject, GLib
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
        self.generated_ice_candidates = []  # Track our generated candidates
        self.pipeline_start_time = None
        self.pending_answer = None  # For delayed answer sending
        
        # Start GLib main loop in a separate thread
        self.main_loop = GLib.MainLoop()
        self.main_loop_thread = threading.Thread(target=self._run_main_loop, daemon=True)
        self.main_loop_thread.start()
        
    def _run_main_loop(self):
        """Run GLib main loop in a separate thread"""
        self.main_loop.run()
        
    def _create_and_send_answer_sync(self):
        """Create and send answer synchronously in a thread"""
        try:
            # Check signaling state
            signaling_state = self.webrtc.get_property('signaling-state')
            self.log(f"Signaling state before creating answer: {signaling_state.value_name}")
            
            if signaling_state != GstWebRTC.WebRTCSignalingState.HAVE_REMOTE_OFFER:
                self.log(f"Cannot create answer - wrong signaling state: {signaling_state.value_name}", "error")
                return
            
            # Create answer
            self.log("Creating answer...")
            promise = Gst.Promise.new()
            self.webrtc.emit('create-answer', None, promise)
            
            # Try to get the answer with polling
            start_time = time.time()
            timeout = 5.0
            answer = None
            
            while time.time() - start_time < timeout:
                try:
                    reply = promise.get_reply()
                    if reply:
                        result = promise.get_result()
                        if result == Gst.PromiseResult.REPLIED:
                            answer = reply.get_value('answer')
                            if answer:
                                break
                except:
                    pass
                time.sleep(0.1)
            
            if not answer:
                self.log("Failed to create answer within timeout", "error")
                return
            
            self.log("Answer created successfully")
            
            # Get answer text
            text = answer.sdp.as_text()
            self.log(f"Answer SDP length: {len(text)} chars")
            
            # Set local description
            self.log("Setting local description...")
            local_promise = Gst.Promise.new()
            self.webrtc.emit('set-local-description', answer, local_promise)
            local_promise.interrupt()
            
            # Send answer to parent
            self.log("Sending answer to parent process...")
            self.send_message({
                "type": "sdp",
                "sdp_type": "answer",
                "sdp": text,
                "session_id": self.session_id
            })
            
            # Add any queued ICE candidates
            if self.ice_candidates:
                self.log(f"Processing {len(self.ice_candidates)} queued ICE candidates")
                while self.ice_candidates:
                    sdpMLineIndex, candidate = self.ice_candidates.pop(0)
                    self.webrtc.emit('add-ice-candidate', sdpMLineIndex, candidate)
            
        except Exception as e:
            self.log(f"Error creating answer: {e}", "error")
            import traceback
            self.log(traceback.format_exc(), "error")
    
    def _on_negotiation_needed(self, element):
        """Handle negotiation-needed signal"""
        self.log("Negotiation needed signal received")
        # For viewer mode, we don't initiate offers
        
    def _on_ice_connection_state(self, element, param_spec):
        """Handle ICE connection state changes"""
        state = element.get_property('ice-connection-state')
        self.log(f"ICE connection state: {state.value_name}")
        
        if state == GstWebRTC.WebRTCICEConnectionState.FAILED:
            self.log("ICE connection failed", "error")
        elif state == GstWebRTC.WebRTCICEConnectionState.CONNECTED:
            self.log("ICE connection established")
            
    def _on_ice_gathering_state(self, element, param_spec):
        """Handle ICE gathering state changes"""
        state = element.get_property('ice-gathering-state')
        self.log(f"ICE gathering state: {state.value_name}")
        
        if state == GstWebRTC.WebRTCICEGatheringState.COMPLETE:
            self.log("ICE gathering complete")
            self.log(f"Error checking answer: {e}", "error")
            
        return False  # Don't repeat
    
    def _create_answer_after_remote_desc(self, sdp_msg, num_media):
        """Create answer after remote description is set"""
        try:
            # Check signaling state
            signaling_state = self.webrtc.get_property('signaling-state')
            self.log(f"Signaling state after setting remote offer: {signaling_state.value_name}")
            
            # Check if this is just a data channel offer
            has_video = False
            has_audio = False
            for i in range(num_media):
                media = sdp_msg.get_media(i)
                media_type = media.get_media()
                if media_type == 'video':
                    has_video = True
                elif media_type == 'audio':
                    has_audio = True
            
            if not has_video and not has_audio:
                self.log("Offer contains only data channel, expecting renegotiation for media tracks")
                
            # Process any queued ICE candidates
            if self.ice_candidates:
                self.log(f"Found {len(self.ice_candidates)} queued ICE candidates")
                self._process_queued_ice_candidates()
                
            # Create answer
            self.log("Creating answer...")
            promise = Gst.Promise.new_with_change_func(self.on_answer_created, self.webrtc, None)
            self.webrtc.emit('create-answer', None, promise)
            
        except Exception as e:
            self.log(f"Error creating answer: {e}", "error")
            
        return False  # Don't repeat
        
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
    
    def _process_queued_ice_candidates(self):
        """Process queued ICE candidates - called via GObject.timeout_add"""
        if self.ice_candidates and self.webrtc:
            # Check pipeline state
            state_ret, state, pending = self.pipe.get_state(0)
            if state_ret == Gst.StateChangeReturn.SUCCESS and state == Gst.State.PLAYING:
                self.log(f"Processing {len(self.ice_candidates)} queued ICE candidates (pipeline in {state.value_name} state)")
                for sdpMLineIndex, candidate in self.ice_candidates:
                    self.webrtc.emit('add-ice-candidate', sdpMLineIndex, candidate)
                self.ice_candidates.clear()
            else:
                self.log(f"Pipeline not ready yet (state: {state.value_name}), will retry queued ICE candidates")
                # Retry in a moment
                GObject.timeout_add(100, self._process_queued_ice_candidates)
        return False  # Don't repeat
        
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
            self.log("Created webrtcbin element")
        else:
            self.log("Found existing webrtcbin element in pipeline")
            
        # Configure webrtcbin for better compatibility
        try:
            # Set bundle-policy to max-bundle (often required for WebRTC compatibility)
            self.webrtc.set_property('bundle-policy', GstWebRTC.WebRTCBundlePolicy.MAX_BUNDLE)
            self.log("Set bundle-policy to MAX_BUNDLE")
        except Exception as e:
            self.log(f"Could not set bundle-policy: {e}", "warning")
        
        try:
            # Configure ICE agent for better connectivity
            # Set ICE TCP to false to avoid issues with some networks
            self.webrtc.set_property('ice-tcp', False)
            self.log("Disabled ICE TCP candidates")
        except Exception as e:
            self.log(f"Could not disable ICE TCP: {e}", "warning")
        
        try:
            # Enable async handling of ICE candidates for better performance
            self.webrtc.set_property('async-handling', True)
            self.log("Enabled async handling")
        except Exception as e:
            self.log(f"Could not enable async handling: {e}", "warning")
            
        # Verify webrtcbin has sink pads for publish mode
        if self.mode == 'publish':
            # Check if webrtcbin has any sink pads
            sink_pads = []
            it = self.webrtc.iterate_sink_pads()
            while True:
                result, pad = it.next()
                if result == Gst.IteratorResult.OK:
                    sink_pads.append(pad)
                elif result == Gst.IteratorResult.DONE:
                    break
                else:
                    break
            
            if sink_pads:
                self.log(f"Webrtcbin has {len(sink_pads)} sink pad(s) connected")
            else:
                self.log("WARNING: Webrtcbin has no sink pads - pipeline may not be properly connected!", "warning")
            
        # Configure STUN/TURN
        if 'stun_server' in self.config:
            stun = self.config['stun_server']
            self.webrtc.set_property('stun-server', stun)
            self.log(f"STUN server configured: {stun}")
        if 'turn_server' in self.config and self.config['turn_server']:
            turn = self.config['turn_server']
            # Use add-turn-server signal for better compatibility
            result = self.webrtc.emit('add-turn-server', turn)
            if result:
                self.log(f"TURN server configured: {turn}")
            else:
                # Fallback to property if signal fails
                self.webrtc.set_property('turn-server', turn)
                self.log(f"TURN server configured via property: {turn}")
        
        # Set ICE transport policy if specified
        if 'ice_transport_policy' in self.config:
            policy = self.config['ice_transport_policy']
            if policy == 'relay':
                self.webrtc.set_property('ice-transport-policy', GstWebRTC.WebRTCICETransportPolicy.RELAY)
                self.log("ICE transport policy set to: RELAY only")
            else:
                self.webrtc.set_property('ice-transport-policy', GstWebRTC.WebRTCICETransportPolicy.ALL)
                self.log("ICE transport policy set to: ALL (direct + relay)")
                
        # Set additional ICE properties for better connectivity
        try:
            # Set latency to reduce buffering delays
            self.webrtc.set_property('latency', 100)
            self.log("Set webrtcbin latency to 100ms")
        except Exception as e:
            self.log(f"Could not set latency: {e}", "warning")
        
        # Configure ICE agent properties if accessible
        try:
            ice_agent = self.webrtc.get_property('ice-agent')
            if ice_agent:
                # Set controlling mode for publish, controlled for view
                if self.mode == 'publish':
                    ice_agent.set_property('controlling-mode', True)
                    self.log("Set ICE agent to controlling mode (publisher)")
                else:
                    ice_agent.set_property('controlling-mode', False)
                    self.log("Set ICE agent to controlled mode (viewer)")
                
                # Set network interfaces if needed (commented out as it's usually auto-detected)
                # ice_agent.set_property('network-interfaces', 'eth0,wlan0')
        except Exception as e:
            self.log(f"Could not configure ICE agent: {e}", "warning")
            
        try:
            # Enable NACK for video streams for better error resilience
            self.webrtc.set_property('nack', True)
            self.log("Enabled NACK for error resilience")
        except Exception as e:
            self.log(f"Could not enable NACK: {e}", "warning")
            
        # Connect signals
        self.webrtc.connect('on-ice-candidate', self.on_ice_candidate)
        self.webrtc.connect('pad-added', self.on_pad_added)
        self.webrtc.connect('notify::ice-connection-state', self.on_ice_state_changed)
        self.webrtc.connect('notify::ice-gathering-state', self.on_ice_gathering_state_changed)
        self.webrtc.connect('notify::connection-state', self.on_connection_state_changed)
        
        # Initialize data channel support early (as recommended by o3)
        # This helps with data-channel-only offers
        if self.mode == 'view' or self.record_file:
            channel = self.webrtc.emit('create-data-channel', 'control', None)
            if channel:
                self.log("Initialized data channel support")
            else:
                self.log("Could not initialize data channel", "warning")
        
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
            
        # Wait for state change to complete if it's async
        if ret == Gst.StateChangeReturn.ASYNC:
            self.log("Pipeline state change is async, waiting...")
            state_ret, state, pending = self.pipe.get_state(Gst.CLOCK_TIME_NONE)
            if state_ret == Gst.StateChangeReturn.SUCCESS:
                self.log(f"Pipeline reached {state.value_name} state")
            else:
                self.log(f"Pipeline state change failed: {state_ret}", "error")
                return False
                
        # Track pipeline start time for debugging
        self.pipeline_start_time = time.time()
        self.log("Pipeline started successfully")
        
        # Process any queued ICE candidates now that pipeline is ready
        if self.ice_candidates:
            self.log(f"Processing {len(self.ice_candidates)} queued ICE candidates")
            # Give the pipeline a moment to stabilize
            GObject.timeout_add(100, self._process_queued_ice_candidates)
            
        return True
        
    def on_negotiation_needed(self, webrtc):
        """Create offer when negotiation is needed"""
        self.log("Negotiation needed")
        
        # Check current state
        signaling_state = webrtc.get_property('signaling-state')
        self.log(f"Current signaling state: {signaling_state.value_name}")
        
        # Only create offer if we're in a valid state
        if signaling_state == GstWebRTC.WebRTCSignalingState.STABLE:
            promise = Gst.Promise.new_with_change_func(self.on_offer_created, webrtc, None)
            webrtc.emit('create-offer', None, promise)
        else:
            self.log(f"Skipping offer creation - signaling state is {signaling_state.value_name}, not STABLE", "warning")
        
    def on_offer_created(self, promise, webrtc, _):
        """Handle created offer"""
        promise.wait()
        reply = promise.get_reply()
        
        if not reply:
            self.log("Failed to get promise reply for offer creation", "error")
            return
            
        offer = reply.get_value('offer')
        
        if not offer:
            self.log("Failed to create offer - no offer in promise reply", "error")
            # Log current state for debugging
            signaling_state = webrtc.get_property('signaling-state')
            self.log(f"Current signaling state: {signaling_state.value_name}", "error")
            return
        
        self.log("Offer created successfully")
        
        # Get offer text and log key details
        text = offer.sdp.as_text()
        self.log(f"Offer SDP length: {len(text)} chars")
        
        # Parse offer to log media details
        res, sdp_msg = GstSdp.SDPMessage.new_from_text(text)
        if res == GstSdp.SDPResult.OK:
            num_media = sdp_msg.medias_len()
            self.log(f"Offer contains {num_media} media section(s)")
            
        # Set local description
        self.log("Setting local description (offer)...")
        promise = Gst.Promise.new()
        webrtc.emit('set-local-description', offer, promise)
        promise.interrupt()
        
        # Log signaling state after setting local description
        signaling_state = webrtc.get_property('signaling-state')
        self.log(f"Signaling state after setting local offer: {signaling_state.value_name}")
        
        # Check ICE gathering state
        gathering_state = webrtc.get_property('ice-gathering-state')
        self.log(f"ICE gathering state after setting local offer: {gathering_state.value_name}")
        
        # Force ICE gathering to start if it hasn't
        if gathering_state == GstWebRTC.WebRTCICEGatheringState.NEW:
            self.log("ICE gathering hasn't started, checking pipeline state...")
            state_ret, state, pending = self.pipe.get_state(0)
            self.log(f"Pipeline state: {state.value_name}, pending: {pending.value_name if pending else 'None'}")
            
            # Get ICE agent to check its state
            ice_agent = webrtc.get_property('ice-agent')
            if ice_agent:
                self.log("ICE agent exists, gathering should start soon...")
            else:
                self.log("WARNING: No ICE agent found!", "warning")
        
        # Send offer to parent
        self.log("Sending offer to parent process...")
        self.send_message({
            "type": "sdp",
            "sdp_type": "offer",
            "sdp": text,
            "session_id": self.session_id
        })
        
    def on_ice_candidate(self, webrtc, mlineindex, candidate):
        """Send ICE candidate to parent"""
        # Track generated candidates
        self.generated_ice_candidates.append((mlineindex, candidate))
        
        # Log candidate type
        if 'typ host' in candidate:
            self.log(f"Generated host candidate: {candidate[:60]}...")
        elif 'typ srflx' in candidate:
            self.log(f"Generated server reflexive candidate: {candidate[:60]}...")
        elif 'typ relay' in candidate:
            self.log(f"Generated TURN relay candidate: {candidate[:60]}...")
            
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
            
    def on_ice_gathering_state_changed(self, webrtc, pspec):
        """ICE gathering state changed"""
        state = webrtc.get_property('ice-gathering-state')
        self.log(f"ICE gathering state: {state.value_name}")
        
        # Send gathering state to parent
        self.send_message({
            "type": "ice_gathering_state",
            "state": state.value_name
        })
        
        # Log when gathering starts
        if state == GstWebRTC.WebRTCICEGatheringState.GATHERING:
            self.log("ICE gathering started - collecting local candidates...")
            # Reset generated candidates list when gathering starts
            self.generated_ice_candidates = []
        
        # Log additional info when gathering completes
        if state == GstWebRTC.WebRTCICEGatheringState.COMPLETE:
            num_candidates = len(self.generated_ice_candidates)
            self.log(f"ICE gathering complete - generated {num_candidates} candidates")
            
            # Log candidate types summary
            host_count = sum(1 for _, c in self.generated_ice_candidates if c and 'typ host' in c)
            srflx_count = sum(1 for _, c in self.generated_ice_candidates if c and 'typ srflx' in c)
            relay_count = sum(1 for _, c in self.generated_ice_candidates if c and 'typ relay' in c)
            
            self.log(f"Candidate types: {host_count} host, {srflx_count} server reflexive, {relay_count} relay")
            
            # Check if we're using TURN only and have no relay candidates
            if self.config.get('ice_transport_policy') == 'relay' and relay_count == 0:
                self.log("WARNING: ICE transport policy is 'relay' but no TURN relay candidates were generated!", "warning")
            
            # Send pending answer if we were waiting for ICE gathering
            if hasattr(self, 'pending_answer') and self.pending_answer:
                self.log("ICE gathering complete - now sending delayed answer to parent process...")
                self.send_message({
                    "type": "sdp",
                    "sdp_type": "answer",
                    "sdp": self.pending_answer,
                    "session_id": self.session_id
                })
                self.pending_answer = None
    
    def on_ice_state_changed(self, webrtc, pspec):
        """ICE connection state changed"""
        state = webrtc.get_property('ice-connection-state')
        self.log(f"ICE state: {state.value_name}")
        
        # Log more details if failed
        if state == GstWebRTC.WebRTCICEConnectionState.FAILED:
            gathering_state = webrtc.get_property('ice-gathering-state')
            self.log(f"ICE gathering state: {gathering_state.value_name}", "error")
            
            # Get statistics about ICE candidates
            num_local_candidates = len(self.generated_ice_candidates)
            self.log(f"Number of local candidates generated: {num_local_candidates}", "error")
            
            # Check if we have any relay candidates
            has_relay = any('typ relay' in str(c[1]) for c in self.generated_ice_candidates if len(c) > 1 and c[1])
            if not has_relay and self.config.get('turn_server'):
                self.log("No TURN relay candidates were generated - TURN server may be unreachable", "error")
            
            # Log time since pipeline started
            if hasattr(self, 'pipeline_start_time'):
                elapsed = time.time() - self.pipeline_start_time
                self.log(f"ICE failed after {elapsed:.1f} seconds", "error")
                
            # Log current signaling state
            signaling_state = webrtc.get_property('signaling-state')
            self.log(f"Signaling state at failure: {signaling_state.value_name}", "error")
            
        self.send_message({
            "type": "ice_state",
            "state": state.value_name
        })
        
    def on_connection_state_changed(self, webrtc, pspec):
        """WebRTC connection state changed"""
        state = webrtc.get_property('connection-state')
        
        # Track previous state for better logging
        prev_state = getattr(self, 'last_connection_state', None)
        self.last_connection_state = state
        
        if prev_state:
            self.log(f"Connection state: {prev_state.value_name} -> {state.value_name}")
        else:
            self.log(f"Connection state: {state.value_name}")
            
        self.send_message({
            "type": "connection_state",
            "state": state.value_name
        })
        
        # If connected, we should start seeing pads
        if state == GstWebRTC.WebRTCPeerConnectionState.CONNECTED:
            self.log("WebRTC connected successfully!")
            if hasattr(self, 'pipeline_start_time'):
                elapsed = time.time() - self.pipeline_start_time
                self.log(f"Connection established in {elapsed:.1f} seconds")
            self.send_message({
                "type": "recording_started",
                "file": self.record_file or "pending",
                "codec": "pending"
            })
            
        # Log additional details for failure states
        elif state == GstWebRTC.WebRTCPeerConnectionState.FAILED:
            self.log("WebRTC connection failed!", "error")
            
            # Get ICE connection state
            ice_state = webrtc.get_property('ice-connection-state')
            self.log(f"ICE connection state at failure: {ice_state.value_name}", "error")
            
            # Get signaling state
            signaling_state = webrtc.get_property('signaling-state')
            self.log(f"Signaling state at failure: {signaling_state.value_name}", "error")
            
            # Log timing information
            if hasattr(self, 'pipeline_start_time'):
                elapsed = time.time() - self.pipeline_start_time
                self.log(f"Connection failed after {elapsed:.1f} seconds", "error")
                
        elif state == GstWebRTC.WebRTCPeerConnectionState.DISCONNECTED:
            self.log("WebRTC disconnected - connection lost", "warning")
            
        elif state == GstWebRTC.WebRTCPeerConnectionState.CLOSED:
            self.log("WebRTC connection closed", "warning")
        
    def on_bus_message(self, bus, message):
        """Handle GStreamer bus messages"""
        t = message.type
        if t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            element = message.src.get_name() if message.src else "unknown"
            self.log(f"Pipeline error from {element}: {err.message}", "error")
            if debug:
                self.log(f"Debug info: {debug}", "error")
                
            # Log element state
            if message.src:
                state = message.src.get_state(0)
                if state[0] == Gst.StateChangeReturn.SUCCESS:
                    current_state = state[1].value_name
                    pending_state = state[2].value_name
                    self.log(f"Element {element} state: current={current_state}, pending={pending_state}", "error")
                    
            self.send_message({
                "type": "error",
                "error": err.message,
                "debug": debug,
                "element": element
            })
            
        elif t == Gst.MessageType.WARNING:
            err, debug = message.parse_warning()
            element = message.src.get_name() if message.src else "unknown"
            self.log(f"Pipeline warning from {element}: {err.message}", "warning")
            
        elif t == Gst.MessageType.INFO:
            err, debug = message.parse_info()
            element = message.src.get_name() if message.src else "unknown"
            self.log(f"Pipeline info from {element}: {err.message}")
            
        elif t == Gst.MessageType.STATE_CHANGED:
            # Only log state changes from the pipeline itself
            if message.src == self.pipe:
                old_state, new_state, pending_state = message.parse_state_changed()
                if old_state != new_state:
                    self.log(f"Pipeline state changed: {old_state.value_name} -> {new_state.value_name}")
                    
        elif t == Gst.MessageType.LATENCY:
            self.log("Pipeline latency needs recalculation")
            if self.pipe:
                self.pipe.recalculate_latency()
                
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
            
            self.log(f"Received SDP {sdp_type} (length: {len(sdp_text)} chars)")
            
            # Ensure pipeline is created before handling SDP
            if not self.webrtc:
                self.log("Pipeline not created yet, creating now...")
                if not self.create_pipeline():
                    self.log("Failed to create pipeline for SDP handling", "error")
                    return
            
            # Schedule SDP handling on GLib main thread
            GLib.idle_add(self._handle_sdp_on_main_thread, sdp_type, sdp_text)
            return
            
        elif msg_type == 'ice':
            # Add ICE candidate
            candidate = msg.get('candidate')
            sdpMLineIndex = msg.get('sdpMLineIndex', 0)
            
            # Log remote candidate type
            if candidate:
                if 'typ host' in candidate:
                    self.log(f"Received remote host candidate")
                elif 'typ srflx' in candidate:
                    self.log(f"Received remote server reflexive candidate")
                elif 'typ relay' in candidate:
                    self.log(f"Received remote TURN relay candidate")
            
            if self.webrtc:
                # Check if we have a remote description set
                signaling_state = self.webrtc.get_property('signaling-state')
                if signaling_state in [GstWebRTC.WebRTCSignalingState.HAVE_REMOTE_OFFER, 
                                     GstWebRTC.WebRTCSignalingState.HAVE_LOCAL_PRANSWER,
                                     GstWebRTC.WebRTCSignalingState.HAVE_REMOTE_PRANSWER,
                                     GstWebRTC.WebRTCSignalingState.HAVE_LOCAL_OFFER,
                                     GstWebRTC.WebRTCSignalingState.STABLE]:
                    # Safe to add ICE candidate
                    self.webrtc.emit('add-ice-candidate', sdpMLineIndex, candidate)
                    self.log(f"Added ICE candidate immediately (signaling state: {signaling_state.value_name})")
                else:
                    # Queue for later - remote description not set yet
                    self.ice_candidates.append((sdpMLineIndex, candidate))
                    self.log(f"Queued ICE candidate - signaling state not ready: {signaling_state.value_name}")
            else:
                # Queue for later - webrtc element doesn't exist yet
                self.ice_candidates.append((sdpMLineIndex, candidate))
                self.log("Queued ICE candidate - webrtc element not created yet")
                
        elif msg_type == 'stop':
            # Stop pipeline
            self.running = False
            if self.pipe:
                self.pipe.set_state(Gst.State.NULL)
            self.send_message({"type": "stopped"})
            
    def _handle_sdp_on_main_thread(self, sdp_type, sdp_text):
        """Handle SDP on the GLib main thread"""
        try:
            # Parse SDP and extract key info
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                self.log(f"Failed to parse SDP: result={res}", "error")
                return False
            
            # Log media information
            num_media = sdp_msg.medias_len()
            self.log(f"SDP contains {num_media} media section(s)")
            
            for i in range(num_media):
                media = sdp_msg.get_media(i)
                media_type = media.get_media()
                num_formats = media.formats_len()
                self.log(f"  Media {i}: type={media_type}, formats={num_formats}")
                
                # Log codec information
                for j in range(media.attributes_len()):
                    attr = media.get_attribute(j)
                    if attr.key == 'rtpmap':
                        self.log(f"    Codec: {attr.value}")
                
            if sdp_type == 'offer':
                self.log("Processing SDP offer...")
                
                # Set remote description first
                offer = GstWebRTC.WebRTCSessionDescription.new(
                    GstWebRTC.WebRTCSDPType.OFFER,
                    sdp_msg
                )
                
                # Check current signaling state before setting offer
                signaling_state = self.webrtc.get_property('signaling-state')
                self.log(f"Current signaling state: {signaling_state.value_name}")
                
                self.log("Setting remote description (offer)...")
                # Store state for use in callback
                self._current_sdp_msg = sdp_msg
                self._current_num_media = num_media
                
                # Check if this is just a data channel offer
                has_video = False
                has_audio = False
                for i in range(num_media):
                    media = sdp_msg.get_media(i)
                    media_type = media.get_media()
                    if media_type == 'video':
                        has_video = True
                    elif media_type == 'audio':
                        has_audio = True
                
                if not has_video and not has_audio:
                    self.log("Offer contains only data channel, expecting renegotiation for media tracks")
                    
                # Process any queued ICE candidates immediately
                if self.ice_candidates:
                    self.log(f"Processing {len(self.ice_candidates)} queued ICE candidates")
                    while self.ice_candidates:
                        sdpMLineIndex, candidate = self.ice_candidates.pop(0)
                        self.webrtc.emit('add-ice-candidate', sdpMLineIndex, candidate)
                        
                # Set remote description
                self.log("Setting remote description...")
                set_promise = Gst.Promise.new()
                self.webrtc.emit('set-remote-description', offer, set_promise)
                set_promise.interrupt()
                
                # Give it a moment to process
                time.sleep(0.2)
                
                # Check signaling state
                signaling_state = self.webrtc.get_property('signaling-state')
                self.log(f"Signaling state after set-remote-description: {signaling_state.value_name}")
                
                if signaling_state == GstWebRTC.WebRTCSignalingState.HAVE_REMOTE_OFFER:
                    # Create answer immediately
                    self.log("Creating answer immediately...")
                    answer_promise = Gst.Promise.new()
                    self.webrtc.emit('create-answer', None, answer_promise)
                    answer_promise.interrupt()
                    
                    # Give it a moment
                    time.sleep(0.2)
                    
                    # Try to get the answer
                    try:
                        reply = answer_promise.get_reply()
                        if reply:
                            answer = reply.get_value('answer')
                            if answer:
                                self.log("Answer created successfully")
                                
                                # Get answer text
                                text = answer.sdp.as_text()
                                self.log(f"Answer SDP length: {len(text)} chars")
                                
                                # Set local description
                                self.log("Setting local description...")
                                local_promise = Gst.Promise.new()
                                self.webrtc.emit('set-local-description', answer, local_promise)
                                local_promise.interrupt()
                                
                                # Send answer to parent
                                self.log("Sending answer to parent process...")
                                self.send_message({
                                    "type": "sdp",
                                    "sdp_type": "answer",
                                    "sdp": text,
                                    "session_id": self.session_id
                                })
                                
                                # Add any queued ICE candidates
                                if self.ice_candidates:
                                    self.log(f"Processing {len(self.ice_candidates)} queued ICE candidates")
                                    while self.ice_candidates:
                                        sdpMLineIndex, candidate = self.ice_candidates.pop(0)
                                        self.webrtc.emit('add-ice-candidate', sdpMLineIndex, candidate)
                            else:
                                self.log("No answer in promise reply", "error")
                        else:
                            self.log("No reply from create-answer promise", "error")
                    except Exception as e:
                        self.log(f"Error getting answer: {e}", "error")
                else:
                    self.log(f"Cannot create answer - wrong signaling state: {signaling_state.value_name}", "error")
                
                return False
                
            elif sdp_type == 'answer':
                self.log("Processing SDP answer...")
                
                # Set remote description
                answer = GstWebRTC.WebRTCSessionDescription.new(
                    GstWebRTC.WebRTCSDPType.ANSWER,
                    sdp_msg
                )
                
                self.log("Setting remote description (answer)...")
                promise = Gst.Promise.new()
                self.webrtc.emit('set-remote-description', answer, promise)
                promise.interrupt()
                
                # Log final signaling state
                signaling_state = self.webrtc.get_property('signaling-state')
                self.log(f"Signaling state after setting remote answer: {signaling_state.value_name}")
                
                # Process any queued ICE candidates after setting remote description
                if self.ice_candidates:
                    self.log(f"Found {len(self.ice_candidates)} queued ICE candidates after setting remote description")
                    # Give the webrtc element a moment to process the remote description
                    GObject.timeout_add(50, self._process_queued_ice_candidates)
                    
        except Exception as e:
            self.log(f"Error handling SDP: {e}", "error")
            
        return False  # For GLib.idle_add
            
    def create_and_send_answer(self):
        """Create and send answer synchronously"""
        
        # Create a promise without callback
        promise = Gst.Promise.new()
        
        # Emit create-answer signal
        self.webrtc.emit('create-answer', None, promise)
        
        # Wait for promise with timeout
        promise.wait()
        reply = promise.get_reply()
        
        if not reply:
            self.log("Failed to get promise reply for answer creation", "error")
            return
            
        answer = reply.get_value('answer')
        
        if not answer:
            self.log("Failed to create answer - no answer in promise reply", "error")
            return
            
        self.log("Answer created successfully")
        
        # Get answer text
        text = answer.sdp.as_text()
        self.log(f"Answer SDP length: {len(text)} chars")
        
        # Parse answer to log media details
        res, sdp_msg = GstSdp.SDPMessage.new_from_text(text)
        if res == GstSdp.SDPResult.OK:
            num_media = sdp_msg.medias_len()
            self.log(f"Answer contains {num_media} media section(s)")
            
        # Set local description
        self.log("Setting local description (answer)...")
        promise2 = Gst.Promise.new()
        self.webrtc.emit('set-local-description', answer, promise2)
        promise2.interrupt()
        
        # Send answer to parent
        self.log("Sending answer to parent process...")
        self.send_message({
            "type": "sdp",
            "sdp_type": "answer", 
            "sdp": text,
            "session_id": self.session_id
        })
    
    def on_answer_created(self, promise, webrtc, _):
        """Handle created answer"""
        promise.wait()
        reply = promise.get_reply()
        
        if not reply:
            self.log("Failed to get promise reply for answer creation", "error")
            return
            
        answer = reply.get_value('answer')
        
        if not answer:
            self.log("Failed to create answer - no answer in promise reply", "error")
            return
            
        self.log("Answer created successfully")
        
        # Get answer text and log key details
        text = answer.sdp.as_text()
        self.log(f"Answer SDP length: {len(text)} chars")
        
        # Log first few lines of answer to debug
        lines = text.split('\n')
        for i, line in enumerate(lines[:20]):  # First 20 lines
            if line.strip():
                self.log(f"Answer SDP [{i}]: {line.strip()}")
        
        # Parse answer to log media details
        res, sdp_msg = GstSdp.SDPMessage.new_from_text(text)
        if res == GstSdp.SDPResult.OK:
            num_media = sdp_msg.medias_len()
            self.log(f"Answer contains {num_media} media section(s)")
            
        # Set local description
        self.log("Setting local description (answer)...")
        promise = Gst.Promise.new()
        self.webrtc.emit('set-local-description', answer, promise)
        promise.interrupt()
        
        # Log signaling state after setting local description
        signaling_state = self.webrtc.get_property('signaling-state')
        self.log(f"Signaling state after setting local answer: {signaling_state.value_name}")
        
        # Check ICE gathering state
        gathering_state = self.webrtc.get_property('ice-gathering-state')
        self.log(f"ICE gathering state after setting local answer: {gathering_state.value_name}")
        
        # Send answer to parent immediately
        self.log("Sending answer to parent process...")
        self.send_message({
            "type": "sdp",
            "sdp_type": "answer",
            "sdp": text,
            "session_id": self.session_id
        })
        
        # Log first few lines of answer to debug
        lines = text.split('\n')
        for i, line in enumerate(lines[:20]):  # First 20 lines
            if line.strip():
                self.log(f"Answer SDP [{i}]: {line.strip()}")
        
        # Parse answer to log media details
        res, sdp_msg = GstSdp.SDPMessage.new_from_text(text)
        if res == GstSdp.SDPResult.OK:
            num_media = sdp_msg.medias_len()
            self.log(f"Answer contains {num_media} media section(s)")
            
        # Set local description
        self.log("Setting local description (answer)...")
        promise = Gst.Promise.new()
        webrtc.emit('set-local-description', answer, promise)
        promise.interrupt()
        
        # Log signaling state after setting local description
        signaling_state = webrtc.get_property('signaling-state')
        self.log(f"Signaling state after setting local answer: {signaling_state.value_name}")
        
        # Check ICE gathering state
        gathering_state = webrtc.get_property('ice-gathering-state')
        self.log(f"ICE gathering state after setting local answer: {gathering_state.value_name}")
        
        # Force ICE gathering to start if it hasn't
        if gathering_state == GstWebRTC.WebRTCICEGatheringState.NEW:
            self.log("ICE gathering hasn't started, checking pipeline state...")
            state_ret, state, pending = self.pipe.get_state(0)
            self.log(f"Pipeline state: {state.value_name}, pending: {pending.value_name if pending else 'None'}")
            
            # Get ICE agent to check its state
            ice_agent = webrtc.get_property('ice-agent')
            if ice_agent:
                self.log("ICE agent exists, gathering should start soon...")
            else:
                self.log("WARNING: No ICE agent found!", "warning")
        
        # Check if we should wait for ICE gathering to complete
        wait_for_gathering = self.config.get('wait_for_ice_gathering', False)
        
        if wait_for_gathering and gathering_state != GstWebRTC.WebRTCICEGatheringState.COMPLETE:
            self.log("Waiting for ICE gathering to complete before sending answer...")
            # Store the answer to send later
            self.pending_answer = text
        else:
            # Send answer to parent immediately
            self.log("Sending answer to parent process...")
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
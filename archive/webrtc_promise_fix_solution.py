#!/usr/bin/env python3
"""
WebRTC Promise Callback Fix for AsyncIO + GLib Threading

This module provides solutions for the common issue where WebRTC promise callbacks
don't execute in a mixed asyncio/GLib threading environment.
"""

import asyncio
import gi
import threading
import time
from typing import Optional, Callable, Any, Dict

gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp, GLib, GObject

# Initialize GStreamer
Gst.init(None)


class WebRTCHandler:
    """
    Fixed WebRTC handler that properly manages promises in a threaded environment
    """
    
    def __init__(self):
        self.webrtc = None
        self.pipeline = None
        
        # Threading setup
        self.main_loop = GLib.MainLoop()
        self.main_context = GLib.MainContext.default()
        self.main_loop_thread = threading.Thread(target=self._run_main_loop, daemon=True)
        self.main_loop_thread.start()
        
        # Give the main loop time to start
        time.sleep(0.1)
        
    def _run_main_loop(self):
        """Run GLib main loop in separate thread"""
        # Make this context the default for this thread
        self.main_context.push_thread_default()
        try:
            self.main_loop.run()
        finally:
            self.main_context.pop_thread_default()
            
    def create_pipeline(self, mode='receive'):
        """Create WebRTC pipeline"""
        if mode == 'receive':
            # For receiving, create a simple webrtcbin
            pipeline_str = "webrtcbin name=webrtc bundle-policy=max-bundle"
        else:
            # For sending, you'd add your source elements
            pipeline_str = "webrtcbin name=webrtc bundle-policy=max-bundle"
            
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.webrtc = self.pipeline.get_by_name('webrtc')
        
        # Configure webrtcbin
        self.webrtc.set_property('stun-server', 'stun:stun.l.google.com:19302')
        
        # IMPORTANT: For data channel support, create a data channel early
        # This ensures webrtcbin is ready to handle data channel offers
        self._ensure_data_channel_support()
        
        # Set pipeline to PLAYING
        self.pipeline.set_state(Gst.State.PLAYING)
        
        # Wait for state change
        self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
        
    def _ensure_data_channel_support(self):
        """Ensure webrtcbin can handle data channels"""
        # Creating a data channel early ensures the SCTP transport is initialized
        # This is crucial for handling offers that only contain data channels
        channel = self.webrtc.emit('create-data-channel', 'control', None)
        if channel:
            print("Data channel support initialized")
            
    def handle_remote_offer(self, sdp_text: str, callback: Optional[Callable] = None):
        """
        Handle remote SDP offer - this is the fixed version
        
        Args:
            sdp_text: The SDP offer as a string
            callback: Optional callback to invoke with the answer
        """
        # Schedule the handling on the GLib main thread
        GLib.idle_add(self._handle_offer_on_main_thread, sdp_text, callback)
        
    def _handle_offer_on_main_thread(self, sdp_text: str, callback: Optional[Callable]):
        """Handle offer on the GLib main thread - SOLUTION 1: Synchronous approach"""
        try:
            # Parse SDP
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                print(f"Failed to parse SDP: {res}")
                return False
                
            # Create offer description
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # SOLUTION 1: Use synchronous promise handling
            # This is the most reliable approach for cross-thread scenarios
            print("Setting remote description (synchronous)...")
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', offer, promise)
            
            # Wait for the promise to complete
            promise.wait()
            reply = promise.get_reply()
            
            if not reply:
                print("ERROR: Failed to set remote description - no reply")
                return False
                
            # Check the result
            structure = reply
            if structure.has_field('error'):
                error = structure.get_value('error')
                print(f"ERROR: Failed to set remote description: {error}")
                return False
                
            # Check signaling state
            signaling_state = self.webrtc.get_property('signaling-state')
            print(f"Signaling state after setting offer: {signaling_state.value_name}")
            
            # Create answer
            print("Creating answer...")
            answer_promise = Gst.Promise.new()
            self.webrtc.emit('create-answer', None, answer_promise)
            
            # Wait for answer
            answer_promise.wait()
            answer_reply = answer_promise.get_reply()
            
            if not answer_reply:
                print("ERROR: Failed to create answer - no reply")
                return False
                
            answer = answer_reply.get_value('answer')
            if not answer:
                print("ERROR: No answer in reply")
                return False
                
            # Set local description
            print("Setting local description...")
            local_promise = Gst.Promise.new()
            self.webrtc.emit('set-local-description', answer, local_promise)
            local_promise.wait()
            
            # Get the answer SDP
            answer_sdp = answer.sdp.as_text()
            print(f"Answer created successfully ({len(answer_sdp)} bytes)")
            
            # Invoke callback if provided
            if callback:
                callback(answer_sdp)
                
        except Exception as e:
            print(f"Exception in offer handling: {e}")
            import traceback
            traceback.print_exc()
            
        return False  # For GLib.idle_add
        
    def handle_remote_offer_async(self, sdp_text: str, callback: Optional[Callable] = None):
        """
        Handle remote SDP offer - SOLUTION 2: Async callback approach
        
        This approach uses callbacks but ensures they run on the correct thread
        """
        GLib.idle_add(self._handle_offer_async_on_main_thread, sdp_text, callback)
        
    def _handle_offer_async_on_main_thread(self, sdp_text: str, callback: Optional[Callable]):
        """Handle offer with async callbacks - ensuring proper thread context"""
        try:
            # Parse SDP
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                print(f"Failed to parse SDP: {res}")
                return False
                
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # SOLUTION 2: Use callbacks but ensure they run on main thread
            def on_offer_set(promise, _, __):
                # This callback might be called from a different thread
                # So we schedule the actual work on the main thread
                GLib.idle_add(self._create_answer_after_offer, callback)
                
            print("Setting remote description (async)...")
            promise = Gst.Promise.new_with_change_func(on_offer_set, None, None)
            self.webrtc.emit('set-remote-description', offer, promise)
            
        except Exception as e:
            print(f"Exception in async offer handling: {e}")
            
        return False
        
    def _create_answer_after_offer(self, callback: Optional[Callable]):
        """Create answer after offer is set - runs on main thread"""
        try:
            # Check signaling state
            signaling_state = self.webrtc.get_property('signaling-state')
            print(f"Signaling state: {signaling_state.value_name}")
            
            def on_answer_created(promise, _, __):
                # Again, schedule on main thread
                GLib.idle_add(self._handle_answer_created, promise, callback)
                
            print("Creating answer (async)...")
            promise = Gst.Promise.new_with_change_func(on_answer_created, None, None)
            self.webrtc.emit('create-answer', None, promise)
            
        except Exception as e:
            print(f"Exception creating answer: {e}")
            
        return False
        
    def _handle_answer_created(self, promise, callback: Optional[Callable]):
        """Handle answer creation - runs on main thread"""
        try:
            promise.wait()
            reply = promise.get_reply()
            
            if not reply:
                print("ERROR: No reply from answer creation")
                return False
                
            answer = reply.get_value('answer')
            if not answer:
                print("ERROR: No answer in reply")
                return False
                
            # Set local description
            local_promise = Gst.Promise.new()
            self.webrtc.emit('set-local-description', answer, local_promise)
            local_promise.wait()
            
            # Get answer SDP
            answer_sdp = answer.sdp.as_text()
            print(f"Answer created successfully ({len(answer_sdp)} bytes)")
            
            if callback:
                callback(answer_sdp)
                
        except Exception as e:
            print(f"Exception handling answer: {e}")
            
        return False
        
    def add_ice_candidate(self, candidate: str, sdp_mline_index: int):
        """Add ICE candidate - safe for cross-thread calls"""
        GLib.idle_add(self._add_ice_candidate_on_main_thread, candidate, sdp_mline_index)
        
    def _add_ice_candidate_on_main_thread(self, candidate: str, sdp_mline_index: int):
        """Add ICE candidate on main thread"""
        if self.webrtc:
            self.webrtc.emit('add-ice-candidate', sdp_mline_index, candidate)
        return False


class AsyncWebRTCWrapper:
    """
    Wrapper that provides async/await interface for WebRTC operations
    while properly handling the GLib threading
    """
    
    def __init__(self):
        self.handler = WebRTCHandler()
        self.handler.create_pipeline('receive')
        
    async def handle_offer(self, sdp_text: str) -> str:
        """
        Async method to handle offer and get answer
        
        Returns:
            The answer SDP as a string
        """
        future = asyncio.Future()
        
        def on_answer_ready(answer_sdp):
            # Schedule the future completion on the asyncio loop
            asyncio.get_event_loop().call_soon_threadsafe(
                future.set_result, answer_sdp
            )
            
        # Handle the offer
        self.handler.handle_remote_offer(sdp_text, on_answer_ready)
        
        # Wait for the answer
        return await future
        
    async def add_ice_candidate(self, candidate: str, sdp_mline_index: int):
        """Add ICE candidate"""
        self.handler.add_ice_candidate(candidate, sdp_mline_index)


# Example usage for your subprocess architecture
class SubprocessWebRTCHandler:
    """
    Example of how to integrate the fixes into your subprocess architecture
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.webrtc = None
        self.pipeline = None
        
        # Start GLib main loop
        self.main_loop = GLib.MainLoop()
        self.main_loop_thread = threading.Thread(target=self._run_main_loop, daemon=True)
        self.main_loop_thread.start()
        
    def _run_main_loop(self):
        """Run GLib main loop"""
        self.main_loop.run()
        
    def _handle_sdp_on_main_thread(self, sdp_type: str, sdp_text: str):
        """
        Fixed version of your _handle_sdp_on_main_thread method
        """
        try:
            # Parse SDP
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                self.log(f"Failed to parse SDP: result={res}", "error")
                return False
            
            if sdp_type == 'offer':
                self.log("Processing SDP offer...")
                
                # Create offer description
                offer = GstWebRTC.WebRTCSessionDescription.new(
                    GstWebRTC.WebRTCSDPType.OFFER,
                    sdp_msg
                )
                
                # FIX: Use synchronous promise handling for reliability
                self.log("Setting remote description (offer)...")
                promise = Gst.Promise.new()
                self.webrtc.emit('set-remote-description', offer, promise)
                
                # Wait for completion
                promise.wait()
                reply = promise.get_reply()
                
                if not reply:
                    self.log("Failed to set remote description - promise has no reply", "error")
                    return False
                    
                # Now create answer
                self.log("Creating answer...")
                answer_promise = Gst.Promise.new()
                self.webrtc.emit('create-answer', None, answer_promise)
                
                # Wait for answer
                answer_promise.wait()
                answer_reply = answer_promise.get_reply()
                
                if answer_reply:
                    answer = answer_reply.get_value('answer')
                    if answer:
                        # Set local description
                        local_promise = Gst.Promise.new()
                        self.webrtc.emit('set-local-description', answer, local_promise)
                        local_promise.wait()
                        
                        # Send answer
                        answer_sdp = answer.sdp.as_text()
                        self.send_message({
                            "type": "sdp",
                            "sdp_type": "answer",
                            "sdp": answer_sdp,
                            "session_id": self.session_id
                        })
                    else:
                        self.log("Failed to create answer - no answer in reply", "error")
                else:
                    self.log("Failed to create answer - no reply", "error")
                    
        except Exception as e:
            self.log(f"Error handling SDP: {e}", "error")
            
        return False
        
    def log(self, message: str, level: str = "info"):
        """Log message"""
        print(f"[{level}] {message}")
        
    def send_message(self, msg: Dict[str, Any]):
        """Send message (placeholder)"""
        print(f"Would send: {msg['type']}")


# Test the solutions
async def test_async_wrapper():
    """Test the async wrapper"""
    print("\n=== Testing Async Wrapper ===")
    
    wrapper = AsyncWebRTCWrapper()
    
    # Test SDP offer (data channel only)
    test_offer = """v=0
o=- 0 0 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0
a=extmap-allow-mixed
a=msid-semantic: WMS
m=application 9 UDP/DTLS/SCTP webrtc-datachannel
c=IN IP4 0.0.0.0
a=ice-ufrag:test
a=ice-pwd:testpassword
a=ice-options:trickle
a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00
a=setup:actpass
a=mid:0
a=sctp-port:5000
a=max-message-size:262144
"""
    
    print("Handling offer...")
    answer = await wrapper.handle_offer(test_offer)
    print(f"Got answer: {answer[:200]}...")
    
    # Test ICE candidate
    await wrapper.add_ice_candidate("candidate:1 1 UDP 2122194687 192.168.1.1 54321 typ host", 0)
    print("Added ICE candidate")


if __name__ == "__main__":
    print("WebRTC Promise Fix Solutions")
    print("=" * 50)
    
    # Run async test
    asyncio.run(test_async_wrapper())
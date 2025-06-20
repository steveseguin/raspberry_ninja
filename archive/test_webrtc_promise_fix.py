#!/usr/bin/env python3
"""
Test and demonstrate fixes for WebRTC promise callback issues with asyncio + GLib threading
"""

import asyncio
import gi
import sys
import time
import threading
from typing import Optional

gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp, GLib, GObject

# Initialize GStreamer
Gst.init(None)


class WebRTCPromiseTest:
    """Test different approaches to handling WebRTC promises in threaded environment"""
    
    def __init__(self):
        self.main_loop = GLib.MainLoop()
        self.main_loop_thread = threading.Thread(target=self._run_main_loop, daemon=True)
        self.main_loop_thread.start()
        
        self.webrtc = None
        self.pipeline = None
        
    def _run_main_loop(self):
        """Run GLib main loop in separate thread"""
        print("GLib main loop started in thread:", threading.current_thread().name)
        self.main_loop.run()
        
    def create_pipeline(self):
        """Create a simple WebRTC pipeline"""
        print("\n=== Creating Pipeline ===")
        print("Current thread:", threading.current_thread().name)
        
        # Simple pipeline with webrtcbin
        self.pipeline = Gst.parse_launch("webrtcbin name=webrtc bundle-policy=max-bundle")
        self.webrtc = self.pipeline.get_by_name('webrtc')
        
        # Configure webrtcbin
        self.webrtc.set_property('stun-server', 'stun:stun.l.google.com:19302')
        
        # Start pipeline
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("ERROR: Failed to start pipeline")
            return False
            
        # Wait for pipeline to reach PLAYING state
        ret, state, pending = self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
        print(f"Pipeline state: {state.value_name}")
        
        return True
        
    def test_approach_1_callback_with_glib_idle(self):
        """Approach 1: Use GLib.idle_add to ensure callback runs on main thread"""
        print("\n=== Test Approach 1: Callback with GLib.idle_add ===")
        
        def handle_sdp():
            print("handle_sdp called on thread:", threading.current_thread().name)
            
            # Create a simple offer SDP (data channel only)
            sdp_text = """v=0
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
            
            # Parse SDP
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                print("ERROR: Failed to parse SDP")
                return False
                
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # Method 1: Using promise callback that schedules work on main thread
            def on_offer_set(promise, _, __):
                print("on_offer_set callback called on thread:", threading.current_thread().name)
                
                # Schedule the actual work on GLib main thread
                def do_create_answer():
                    print("Creating answer on thread:", threading.current_thread().name)
                    
                    # Check signaling state
                    state = self.webrtc.get_property('signaling-state')
                    print(f"Signaling state: {state.value_name}")
                    
                    # Create answer
                    answer_promise = Gst.Promise.new_with_change_func(on_answer_created, None, None)
                    self.webrtc.emit('create-answer', None, answer_promise)
                    return False
                    
                GLib.idle_add(do_create_answer)
                
            def on_answer_created(promise, _, __):
                print("on_answer_created callback called on thread:", threading.current_thread().name)
                promise.wait()
                reply = promise.get_reply()
                if reply:
                    print("SUCCESS: Answer created")
                else:
                    print("ERROR: Failed to create answer")
                    
            print("Setting remote description...")
            promise = Gst.Promise.new_with_change_func(on_offer_set, None, None)
            self.webrtc.emit('set-remote-description', offer, promise)
            
            return False  # For GLib.idle_add
            
        # Execute on GLib main thread
        GLib.idle_add(handle_sdp)
        
    def test_approach_2_sync_promise(self):
        """Approach 2: Use synchronous promise handling"""
        print("\n=== Test Approach 2: Synchronous Promise ===")
        
        def handle_sdp():
            print("handle_sdp called on thread:", threading.current_thread().name)
            
            # Create a simple offer SDP
            sdp_text = """v=0
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
            
            # Parse SDP
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                print("ERROR: Failed to parse SDP")
                return False
                
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # Method 2: Synchronous promise handling
            print("Setting remote description (synchronous)...")
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', offer, promise)
            
            # Wait for promise to complete
            promise.wait()
            reply = promise.get_reply()
            
            if reply:
                print("Remote description set successfully")
                
                # Check signaling state
                state = self.webrtc.get_property('signaling-state')
                print(f"Signaling state: {state.value_name}")
                
                # Create answer synchronously
                print("Creating answer (synchronous)...")
                answer_promise = Gst.Promise.new()
                self.webrtc.emit('create-answer', None, answer_promise)
                
                # Wait for answer
                answer_promise.wait()
                answer_reply = answer_promise.get_reply()
                
                if answer_reply:
                    answer = answer_reply.get_value('answer')
                    if answer:
                        print("SUCCESS: Answer created")
                        print(f"Answer SDP length: {len(answer.sdp.as_text())}")
                    else:
                        print("ERROR: No answer in reply")
                else:
                    print("ERROR: Failed to create answer")
            else:
                print("ERROR: Failed to set remote description")
                
            return False  # For GLib.idle_add
            
        # Execute on GLib main thread
        GLib.idle_add(handle_sdp)
        
    def test_approach_3_hybrid(self):
        """Approach 3: Hybrid approach - callbacks that use GLib context"""
        print("\n=== Test Approach 3: Hybrid with Context Push ===")
        
        def handle_sdp():
            print("handle_sdp called on thread:", threading.current_thread().name)
            
            # Create a simple offer SDP
            sdp_text = """v=0
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
            
            # Parse SDP
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                print("ERROR: Failed to parse SDP")
                return False
                
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # Get main context
            main_context = GLib.MainContext.default()
            
            # Method 3: Ensure callbacks run in correct context
            class CallbackData:
                def __init__(self):
                    self.completed = False
                    self.success = False
                    
            callback_data = CallbackData()
            
            def on_offer_set(promise, _, data):
                print("on_offer_set callback called on thread:", threading.current_thread().name)
                
                # Push main context to ensure we're in the right context
                main_context.push_thread_default()
                try:
                    promise.wait()
                    reply = promise.get_reply()
                    
                    if reply:
                        print("Remote description set successfully")
                        
                        # Check signaling state
                        state = self.webrtc.get_property('signaling-state')
                        print(f"Signaling state: {state.value_name}")
                        
                        # Create answer with callback
                        answer_promise = Gst.Promise.new_with_change_func(on_answer_created, None, data)
                        self.webrtc.emit('create-answer', None, answer_promise)
                    else:
                        print("ERROR: Failed to set remote description")
                        data.completed = True
                finally:
                    main_context.pop_thread_default()
                    
            def on_answer_created(promise, _, data):
                print("on_answer_created callback called on thread:", threading.current_thread().name)
                
                main_context.push_thread_default()
                try:
                    promise.wait()
                    reply = promise.get_reply()
                    
                    if reply:
                        answer = reply.get_value('answer')
                        if answer:
                            print("SUCCESS: Answer created")
                            data.success = True
                        else:
                            print("ERROR: No answer in reply")
                    else:
                        print("ERROR: Failed to create answer")
                        
                    data.completed = True
                finally:
                    main_context.pop_thread_default()
                    
            print("Setting remote description...")
            promise = Gst.Promise.new_with_change_func(on_offer_set, None, callback_data)
            self.webrtc.emit('set-remote-description', offer, promise)
            
            # Wait a bit for callbacks to complete
            for i in range(50):  # Wait up to 5 seconds
                if callback_data.completed:
                    break
                time.sleep(0.1)
                
            if callback_data.success:
                print("Test completed successfully")
            else:
                print("Test failed")
                
            return False  # For GLib.idle_add
            
        # Execute on GLib main thread
        GLib.idle_add(handle_sdp)
        
    def test_approach_4_data_channel_transceiver(self):
        """Approach 4: Properly handle data channel transceivers"""
        print("\n=== Test Approach 4: Data Channel Transceiver Handling ===")
        
        def handle_sdp():
            print("handle_sdp called on thread:", threading.current_thread().name)
            
            # First, add a data channel to webrtcbin BEFORE setting remote description
            # This ensures webrtcbin is ready to handle data channel offers
            print("Creating data channel...")
            channel = self.webrtc.emit('create-data-channel', 'test-channel', None)
            if channel:
                print("Data channel created successfully")
            else:
                print("WARNING: Failed to create data channel")
            
            # Create a simple offer SDP with data channel
            sdp_text = """v=0
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
            
            # Parse SDP
            res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
            if res != GstSdp.SDPResult.OK:
                print("ERROR: Failed to parse SDP")
                return False
                
            offer = GstWebRTC.WebRTCSessionDescription.new(
                GstWebRTC.WebRTCSDPType.OFFER,
                sdp_msg
            )
            
            # Check transceivers before setting offer
            print("\nTransceivers before setting offer:")
            for i in range(10):  # Check up to 10 transceivers
                trans = self.webrtc.emit('get-transceiver', i)
                if not trans:
                    break
                print(f"  Transceiver {i}: {trans}")
            
            # Set remote description synchronously
            print("\nSetting remote description...")
            promise = Gst.Promise.new()
            self.webrtc.emit('set-remote-description', offer, promise)
            
            # Wait for completion
            promise.wait()
            reply = promise.get_reply()
            
            if reply:
                print("Remote description set successfully")
                
                # Check signaling state
                state = self.webrtc.get_property('signaling-state')
                print(f"Signaling state: {state.value_name}")
                
                # Check transceivers after setting offer
                print("\nTransceivers after setting offer:")
                for i in range(10):
                    trans = self.webrtc.emit('get-transceiver', i)
                    if not trans:
                        break
                    print(f"  Transceiver {i}: {trans}")
                
                # Create answer
                print("\nCreating answer...")
                answer_promise = Gst.Promise.new()
                self.webrtc.emit('create-answer', None, answer_promise)
                
                answer_promise.wait()
                answer_reply = answer_promise.get_reply()
                
                if answer_reply:
                    answer = answer_reply.get_value('answer')
                    if answer:
                        print("SUCCESS: Answer created")
                        sdp = answer.sdp.as_text()
                        print(f"Answer SDP preview: {sdp[:200]}...")
                        
                        # Set local description
                        local_promise = Gst.Promise.new()
                        self.webrtc.emit('set-local-description', answer, local_promise)
                        local_promise.wait()
                        
                        # Final state check
                        final_state = self.webrtc.get_property('signaling-state')
                        print(f"Final signaling state: {final_state.value_name}")
                    else:
                        print("ERROR: No answer in reply")
                else:
                    print("ERROR: Failed to create answer")
            else:
                print("ERROR: Failed to set remote description")
                
            return False  # For GLib.idle_add
            
        # Execute on GLib main thread
        GLib.idle_add(handle_sdp)
        
    def run_tests(self):
        """Run all test approaches"""
        if not self.create_pipeline():
            print("ERROR: Failed to create pipeline")
            return
            
        # Let user choose which test to run
        print("\nAvailable tests:")
        print("1. Callback with GLib.idle_add")
        print("2. Synchronous promise handling")
        print("3. Hybrid with context push")
        print("4. Data channel transceiver handling")
        print("5. Run all tests")
        
        choice = input("\nSelect test (1-5): ").strip()
        
        if choice == '1':
            self.test_approach_1_callback_with_glib_idle()
            time.sleep(2)
        elif choice == '2':
            self.test_approach_2_sync_promise()
            time.sleep(2)
        elif choice == '3':
            self.test_approach_3_hybrid()
            time.sleep(6)
        elif choice == '4':
            self.test_approach_4_data_channel_transceiver()
            time.sleep(2)
        elif choice == '5':
            self.test_approach_1_callback_with_glib_idle()
            time.sleep(2)
            self.test_approach_2_sync_promise()
            time.sleep(2)
            self.test_approach_3_hybrid()
            time.sleep(6)
            self.test_approach_4_data_channel_transceiver()
            time.sleep(2)
        else:
            print("Invalid choice")
            
        # Clean up
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        self.main_loop.quit()


if __name__ == "__main__":
    print("WebRTC Promise Handling Test")
    print("=" * 50)
    
    test = WebRTCPromiseTest()
    test.run_tests()
    
    print("\nTest completed")
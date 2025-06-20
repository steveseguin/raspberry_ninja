#!/usr/bin/env python3
"""Test GStreamer WebRTC promise handling"""

import gi
import time
import threading
from typing import Optional

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib
gi.require_version('GstWebRTC', '1.0')
from gi.repository import GstWebRTC
gi.require_version('GstSdp', '1.0')
from gi.repository import GstSdp

# Initialize GStreamer
Gst.init(None)

def test_promise_handling():
    """Test different promise handling approaches"""
    
    # Create a simple pipeline with webrtcbin
    pipe = Gst.Pipeline.new("test-pipeline")
    webrtc = Gst.ElementFactory.make("webrtcbin", "test-webrtc")
    webrtc.set_property('bundle-policy', 'max-bundle')
    
    pipe.add(webrtc)
    pipe.set_state(Gst.State.PLAYING)
    
    # Create a simple SDP offer
    sdp_text = """v=0
o=- 0 0 IN IP4 0.0.0.0
s=-
t=0 0
m=application 9 UDP/DTLS/SCTP webrtc-datachannel
c=IN IP4 0.0.0.0
a=ice-ufrag:test
a=ice-pwd=testpassword
a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00
a=setup:actpass
a=sctp-port:5000
"""
    
    # Parse the SDP
    res, sdp_msg = GstSdp.SDPMessage.new_from_text(sdp_text)
    if res != GstSdp.SDPResult.OK:
        print(f"Failed to parse SDP: {res}")
        return
    
    # Create offer
    offer = GstWebRTC.WebRTCSessionDescription.new(
        GstWebRTC.WebRTCSDPType.OFFER,
        sdp_msg
    )
    
    print("Setting remote description...")
    
    # Test 1: Synchronous approach with promise.wait()
    print("\nTest 1: Synchronous with promise.wait()")
    promise1 = Gst.Promise.new()
    webrtc.emit('set-remote-description', offer, promise1)
    
    # Wait for completion
    promise1.wait()
    reply1 = promise1.get_reply()
    print(f"  Reply received: {reply1 is not None}")
    
    # Test 2: Create answer synchronously
    print("\nTest 2: Create answer synchronously")
    promise2 = Gst.Promise.new()
    webrtc.emit('create-answer', None, promise2)
    
    # Poll for answer
    start_time = time.time()
    timeout = 2.0
    answer = None
    
    while time.time() - start_time < timeout:
        reply2 = promise2.get_reply()
        if reply2:
            answer = reply2.get_value('answer')
            if answer:
                print(f"  Answer created: SDP length = {len(answer.sdp.as_text())}")
                break
        time.sleep(0.01)
    
    if not answer:
        print("  Failed to create answer within timeout")
    
    # Cleanup
    pipe.set_state(Gst.State.NULL)
    
    return answer is not None

# Run test with GLib main loop
def run_with_main_loop():
    """Run test within GLib main loop context"""
    main_loop = GLib.MainLoop()
    
    def test_and_quit():
        success = test_promise_handling()
        print(f"\nTest result: {'SUCCESS' if success else 'FAILED'}")
        main_loop.quit()
        return False
    
    # Schedule test
    GLib.timeout_add(100, test_and_quit)
    
    # Run main loop
    print("Starting GLib main loop...")
    main_loop.run()

if __name__ == "__main__":
    # Test 1: Without main loop
    print("=== Test without GLib main loop ===")
    test_promise_handling()
    
    print("\n=== Test with GLib main loop ===")
    run_with_main_loop()
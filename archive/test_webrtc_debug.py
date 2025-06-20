#!/usr/bin/env python3
"""
Debug WebRTC negotiation issues
"""

import asyncio
import json
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
gi.require_version('GstSdp', '1.0')
from gi.repository import Gst, GstWebRTC, GstSdp

Gst.init(None)

async def test_webrtc_answer():
    """Test creating an answer from a simple offer"""
    print("="*60)
    print("WEBRTC ANSWER CREATION TEST")
    print("="*60)
    
    # Create a simple test offer SDP
    offer_sdp = """v=0
o=- 1234567890 2 IN IP4 127.0.0.1
s=-
t=0 0
a=group:BUNDLE 0
a=msid-semantic: WMS
m=video 9 UDP/TLS/RTP/SAVPF 96
c=IN IP4 0.0.0.0
a=rtcp:9 IN IP4 0.0.0.0
a=ice-ufrag:test
a=ice-pwd:testpwd123456789012345678
a=ice-options:trickle
a=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00
a=setup:actpass
a=mid:0
a=sendonly
a=rtcp-mux
a=rtpmap:96 H264/90000
a=fmtp:96 level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f
"""
    
    print("1. Creating pipeline and webrtcbin...")
    
    # Create minimal pipeline
    pipe = Gst.Pipeline.new('test-pipe')
    webrtc = Gst.ElementFactory.make('webrtcbin', 'webrtc')
    
    if not webrtc:
        print("ERROR: Failed to create webrtcbin")
        return
        
    pipe.add(webrtc)
    
    # Add receive-only transceiver before setting remote description
    print("2. Adding receive-only transceiver...")
    caps = Gst.caps_from_string("application/x-rtp,media=video")
    tcvr = webrtc.emit('add-transceiver', GstWebRTC.WebRTCRTPTransceiverDirection.RECVONLY, caps)
    
    # Start pipeline
    pipe.set_state(Gst.State.PLAYING)
    
    print("3. Parsing offer SDP...")
    res, sdp_msg = GstSdp.SDPMessage.new_from_text(offer_sdp)
    if res != GstSdp.SDPResult.OK:
        print("ERROR: Failed to parse SDP")
        return
        
    offer = GstWebRTC.WebRTCSessionDescription.new(
        GstWebRTC.WebRTCSDPType.OFFER,
        sdp_msg
    )
    
    print("4. Setting remote description...")
    promise = Gst.Promise.new()
    webrtc.emit('set-remote-description', offer, promise)
    promise.wait()
    
    reply = promise.get_reply()
    if reply:
        error = reply.get_value('error')
        if error:
            print(f"ERROR setting remote description: {error}")
            return
    
    print("5. Creating answer...")
    promise = Gst.Promise.new()
    webrtc.emit('create-answer', None, promise)
    promise.wait()
    
    reply = promise.get_reply()
    if not reply:
        print("ERROR: No reply from create-answer")
        return
        
    answer = reply.get_value('answer')
    error = reply.get_value('error')
    
    if error:
        print(f"ERROR creating answer: {error}")
        # Try to get more details
        struct = promise.get_reply()
        if struct:
            print(f"Full reply structure: {struct.to_string()}")
        return
        
    if not answer:
        print("ERROR: No answer in reply")
        return
        
    print("6. Setting local description...")
    promise2 = Gst.Promise.new()
    webrtc.emit('set-local-description', answer, promise2)
    promise2.wait()
    
    # Get answer SDP
    if hasattr(answer, 'sdp'):
        answer_sdp = answer.sdp.as_text()
        print("\n✅ SUCCESS! Answer created:")
        print("-" * 60)
        print(answer_sdp[:200] + "...")
        print("-" * 60)
    else:
        print("ERROR: Could not get SDP from answer")
        
    # Cleanup
    pipe.set_state(Gst.State.NULL)
    

def test_gstreamer_basics():
    """Test basic GStreamer functionality"""
    print("\n" + "="*60)
    print("GSTREAMER BASIC TEST")
    print("="*60)
    
    # Test 1: Can we create webrtcbin?
    webrtc = Gst.ElementFactory.make('webrtcbin', 'test')
    if webrtc:
        print("✅ webrtcbin element available")
    else:
        print("❌ webrtcbin element NOT available")
        print("   Run: sudo apt-get install gstreamer1.0-plugins-bad")
        return False
        
    # Test 2: Check installed plugins
    registry = Gst.Registry.get()
    webrtc_plugin = registry.find_plugin('webrtc')
    if webrtc_plugin:
        print(f"✅ WebRTC plugin found: {webrtc_plugin.get_name()}")
    else:
        print("❌ WebRTC plugin not found")
        
    # Test 3: Simple pipeline
    pipeline_str = "videotestsrc ! fakesink"
    pipe = Gst.parse_launch(pipeline_str)
    if pipe:
        print("✅ Basic pipeline creation works")
        pipe.set_state(Gst.State.NULL)
    else:
        print("❌ Basic pipeline creation failed")
        
    return True


if __name__ == "__main__":
    print("Starting WebRTC debug tests...\n")
    
    # First test basics
    if test_gstreamer_basics():
        # Then test WebRTC
        asyncio.run(test_webrtc_answer())
    else:
        print("\nSkipping WebRTC test due to missing components")
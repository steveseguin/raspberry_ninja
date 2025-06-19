#!/usr/bin/env python3
"""Test if TURN server is being used correctly"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC

Gst.init(None)

print("Testing TURN server configuration methods...")
print("=" * 70)

# Create webrtcbin
webrtc = Gst.ElementFactory.make('webrtcbin', 'test')

# Method 1: Using property
print("\n1. Testing turn-server property:")
turn_url = "turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478"
webrtc.set_property('turn-server', turn_url)
print(f"   Set: {turn_url}")
print(f"   Get: {webrtc.get_property('turn-server')}")

# Method 2: Using add-turn-server signal
print("\n2. Testing add-turn-server signal:")
if hasattr(webrtc, 'emit'):
    try:
        # Try emitting the signal
        webrtc.emit('add-turn-server', turn_url)
        print("   ✅ Signal emitted successfully")
    except Exception as e:
        print(f"   ❌ Signal failed: {e}")

# Check if we can see the ICE agent
ice_agent = webrtc.get_property('ice-agent')
if ice_agent:
    print(f"\n3. ICE agent available: {ice_agent}")
    # Try to get TURN servers from agent
    if hasattr(ice_agent, 'get_property'):
        try:
            print("   Checking ICE agent properties...")
        except:
            pass

# Test with a pipeline
print("\n4. Testing in a pipeline:")
pipe = Gst.Pipeline.new('test-pipe')
pipe.add(webrtc)

# Set to PLAYING to initialize
ret = pipe.set_state(Gst.State.PLAYING)
print(f"   Pipeline state: {ret}")

# Clean up
pipe.set_state(Gst.State.NULL)

print("\n" + "=" * 70)
print("Note: GStreamer might need the TURN URL in a specific format")
print("or might need to use add-turn-server signal instead of property")
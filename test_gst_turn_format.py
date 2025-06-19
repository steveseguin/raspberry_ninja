#!/usr/bin/env python3
"""Test different TURN URL formats with GStreamer"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC

Gst.init(None)

print("Testing TURN URL formats with GStreamer...")
print("=" * 70)

# Test different formats
formats = [
    "turn:steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478",
    "turn://steve:setupYourOwnPlease@turn-cae1.vdo.ninja:3478",
    "turn:turn-cae1.vdo.ninja:3478",
    "turn://turn-cae1.vdo.ninja:3478"
]

for fmt in formats:
    print(f"\nTesting format: {fmt}")
    
    try:
        webrtc = Gst.ElementFactory.make('webrtcbin', 'test')
        webrtc.set_property('turn-server', fmt)
        
        # Try to get the property back
        value = webrtc.get_property('turn-server')
        print(f"  Set successfully, value: {value}")
        
        # Create a minimal pipeline to see if it initializes
        pipe = Gst.Pipeline.new('test-pipe')
        pipe.add(webrtc)
        
        # Try to set to PLAYING state
        ret = pipe.set_state(Gst.State.PLAYING)
        print(f"  State change: {ret}")
        
        # Check for errors
        bus = pipe.get_bus()
        msg = bus.timed_pop_filtered(100000000, Gst.MessageType.ERROR | Gst.MessageType.WARNING)
        if msg:
            print(f"  Message: {msg.type} - {msg.parse_error() if msg.type == Gst.MessageType.ERROR else msg.parse_warning()}")
        
        pipe.set_state(Gst.State.NULL)
        
    except Exception as e:
        print(f"  Error: {e}")

print("\nChecking GStreamer documentation format...")
print("The standard format should be: turn://username:password@hostname:port")
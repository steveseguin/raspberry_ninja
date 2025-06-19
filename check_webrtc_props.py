#!/usr/bin/env python3
"""Check webrtcbin properties"""

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstWebRTC', '1.0')
from gi.repository import Gst, GstWebRTC

Gst.init(None)

webrtc = Gst.ElementFactory.make('webrtcbin', 'test')

print("WebRTCBin properties related to TURN/STUN:")
print("=" * 50)

# Get all properties
props = webrtc.list_properties()
for prop in props:
    name = prop.name
    if any(kw in name.lower() for kw in ['turn', 'stun', 'ice', 'server', 'user', 'pass']):
        print(f"  {name}: {prop.blurb}")
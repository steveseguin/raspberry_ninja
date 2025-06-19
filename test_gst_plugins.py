#!/usr/bin/env python3
"""
Check GStreamer plugins
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

# Initialize
Gst.init(None)

# Check for webrtcbin
registry = Gst.Registry.get()
webrtc = registry.find_plugin('webrtc')

if webrtc:
    print(f"✅ webrtc plugin found: {webrtc.get_name()}")
else:
    print("❌ webrtc plugin NOT found")
    
# Try to create webrtcbin
try:
    element = Gst.ElementFactory.make('webrtcbin', 'test')
    if element:
        print("✅ webrtcbin element created successfully")
    else:
        print("❌ webrtcbin element could not be created")
except Exception as e:
    print(f"❌ Error creating webrtcbin: {e}")
    
# List available plugins
print("\nAvailable plugins containing 'rtc':")
for plugin in registry.get_plugin_list():
    name = plugin.get_name()
    if 'rtc' in name or 'webrtc' in name:
        print(f"  - {name}")
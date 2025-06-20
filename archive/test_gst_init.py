#!/usr/bin/env python3
"""Test if GStreamer initializes properly"""

print("Testing GStreamer initialization...")

try:
    import gi
    print("✓ gi imported")
    
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    print("✓ Gst imported")
    
    Gst.init(None)
    print("✓ Gst initialized")
    
    # Test creating a simple pipeline
    pipeline = Gst.parse_launch("fakesrc ! fakesink")
    print("✓ Test pipeline created")
    
    print("\n✅ GStreamer is working properly!")
    
except Exception as e:
    print(f"\n❌ GStreamer error: {e}")
    import traceback
    traceback.print_exc()
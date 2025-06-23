#!/usr/bin/env python3

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject

Gst.init(None)

# Create splitmuxsink element
sink = Gst.ElementFactory.make('splitmuxsink', None)

if sink:
    print("Splitmuxsink signals:")
    print("-" * 40)
    
    # Get all signals for this element
    signal_ids = GObject.signal_list_ids(sink)
    for signal_id in signal_ids:
        signal_info = GObject.signal_query(signal_id)
        print(f"\nSignal: {signal_info.signal_name}")
        
    # Test specific signals we're interested in
    print("\n\nTesting signal connections:")
    print("-" * 40)
    
    def test_format_location(splitmux, fragment_id):
        print(f"format-location called with: splitmux={splitmux}, fragment_id={fragment_id}")
        return f"test_{fragment_id:05d}.ts"
    
    def test_format_location_full_2args(splitmux, filename):
        print(f"format-location-full (2 args) called with: splitmux={splitmux}, filename={filename}")
        
    def test_format_location_full_3args(splitmux, fragment_id, filename):
        print(f"format-location-full (3 args) called with: splitmux={splitmux}, fragment_id={fragment_id}, filename={filename}")
    
    # Try connecting with different signatures
    try:
        sink.connect('format-location', test_format_location)
        print("✓ format-location connected successfully")
    except Exception as e:
        print(f"✗ format-location failed: {e}")
        
    try:
        sink.connect('format-location-full', test_format_location_full_2args)
        print("✓ format-location-full (2 args) connected successfully")
    except Exception as e:
        print(f"✗ format-location-full (2 args) failed: {e}")
        
    try:
        sink.disconnect_by_func(test_format_location_full_2args)
    except:
        pass
        
    try:
        sink.connect('format-location-full', test_format_location_full_3args)
        print("✓ format-location-full (3 args) connected successfully") 
    except Exception as e:
        print(f"✗ format-location-full (3 args) failed: {e}")
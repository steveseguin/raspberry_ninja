#!/usr/bin/env python3
"""
Test NDI flow to understand current implementation
"""

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

# Initialize GStreamer
Gst.init(None)

def test_ndi_elements():
    """Test if NDI elements are available and how they work"""
    print("Testing NDI GStreamer elements...")
    
    # Check if NDI plugin is available
    ndisink = Gst.ElementFactory.make('ndisink', None)
    if not ndisink:
        print("❌ ndisink element not available. Make sure gst-plugin-ndi is installed.")
        return
    
    print("✓ ndisink element is available")
    
    # Check properties
    print("\nNDI Sink Properties:")
    for prop in ndisink.list_properties():
        print(f"  - {prop.name}: {prop.value_type.name} (default: {ndisink.get_property(prop.name)})")
    
    # Check if ndisinkcombiner exists
    ndicombiner = Gst.ElementFactory.make('ndisinkcombiner', None)
    if ndicombiner:
        print("\n✓ ndisinkcombiner element is available")
        print("\nNDI Sink Combiner Properties:")
        for prop in ndicombiner.list_properties():
            print(f"  - {prop.name}: {prop.value_type.name} (default: {ndicombiner.get_property(prop.name)})")
    else:
        print("\n❌ ndisinkcombiner element not available")
    
    # Test pipeline creation
    print("\nTesting NDI pipeline creation...")
    
    # Simple test pipeline
    pipeline_str = "videotestsrc ! video/x-raw,width=640,height=480,framerate=30/1 ! ndisink ndi-name=TestStream"
    try:
        pipeline = Gst.parse_launch(pipeline_str)
        print("✓ Simple video NDI pipeline created successfully")
        pipeline.set_state(Gst.State.NULL)
    except Exception as e:
        print(f"❌ Failed to create NDI pipeline: {e}")
    
    # Test audio+video pipeline
    if ndicombiner:
        pipeline_str = """
            ndisinkcombiner name=mux ! ndisink ndi-name=TestAVStream
            videotestsrc ! video/x-raw,width=640,height=480,framerate=30/1 ! mux.video
            audiotestsrc ! audio/x-raw,rate=48000,channels=2 ! mux.audio
        """
        try:
            pipeline = Gst.parse_launch(pipeline_str)
            print("✓ Audio+Video NDI pipeline created successfully")
            pipeline.set_state(Gst.State.NULL)
        except Exception as e:
            print(f"❌ Failed to create A/V NDI pipeline: {e}")

if __name__ == "__main__":
    test_ndi_elements()